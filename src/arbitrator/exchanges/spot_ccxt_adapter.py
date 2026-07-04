from __future__ import annotations

import asyncio
import ssl
import time
from collections.abc import AsyncIterator, Sequence
from decimal import Decimal

import aiohttp
import ccxt.pro as ccxtpro
import certifi

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.spot_gateway import SpotGateway
from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.quote import Quote


class SpotCcxtAdapter(SpotGateway):
    """Generic ccxt.pro adapter for spot market data (defaultType=spot)."""

    def __init__(self, exchange_id: str, settings: Settings) -> None:
        self._exchange_id = exchange_id
        self._settings = settings
        self._client: ccxtpro.Exchange | None = None
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_client(self) -> ccxtpro.Exchange:
        if self._client is not None:
            return self._client
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        self._session = aiohttp.ClientSession(connector=connector)
        config: dict[str, object] = {
            "session": self._session,
            "enableRateLimit": self._settings.enable_rate_limit,
            "options": {"defaultType": "spot"},
        }
        creds = self._settings.credentials_for(self._exchange_id)
        if creds is not None:
            config["apiKey"] = creds.api_key
            config["secret"] = creds.api_secret
            if creds.password:
                config["password"] = creds.password
        exchange_class = getattr(ccxtpro, self._exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"ccxt.pro has no exchange: {self._exchange_id}")
        self._client = exchange_class(config)
        await self._client.load_markets()
        return self._client

    async def list_spot_symbols(self) -> list[str]:
        client = await self._ensure_client()
        return [
            symbol
            for symbol, market in client.markets.items()
            if market.get("type") == "spot"
            and market.get("quote") == "USDT"
            and market.get("active", True)
        ]

    async def watch_spot_tickers(
        self, symbols: Sequence[str]
    ) -> AsyncIterator[dict[str, Quote]]:
        client = await self._ensure_client()
        symbol_list = list(symbols)
        if not symbol_list:
            return
        while True:
            try:
                raw = await client.watch_tickers(symbol_list)
            except Exception:
                logger.exception(
                    "spot watch_tickers error | exchange={}", self._exchange_id
                )
                await asyncio.sleep(5.0)
                continue
            now_ms = int(time.time() * 1000)
            result: dict[str, Quote] = {}
            for symbol, data in raw.items():
                if symbol not in symbol_list:
                    continue
                bid = data.get("bid")
                ask = data.get("ask")
                last = data.get("last")
                if last is None and bid is None:
                    continue
                result[symbol] = Quote(
                    exchange_id=self._exchange_id,
                    symbol=symbol,
                    market_type="spot",
                    bid=Decimal(str(bid)) if bid else None,
                    ask=Decimal(str(ask)) if ask else None,
                    last=Decimal(str(last)) if last else None,
                    recv_time_ms=now_ms,
                )
            if result:
                yield result

    async def fetch_spot_fee(self, symbol: str) -> FeeSchedule | None:
        client = await self._ensure_client()
        market = client.markets.get(symbol)
        if market is None:
            return None
        maker = market.get("maker")
        taker = market.get("taker")
        return FeeSchedule(
            exchange_id=self._exchange_id,
            symbol=symbol,
            futures_maker=None,
            futures_taker=None,
            spot_maker=Decimal(str(maker)) if maker is not None else None,
            spot_taker=Decimal(str(taker)) if taker is not None else None,
        )

    async def buy_spot_market(
        self, symbol: str, amount: float, client_order_id: str
    ) -> str:
        client = await self._ensure_client()
        params: dict[str, object] = {"clientOrderId": client_order_id}
        order = await client.create_order(symbol, "market", "buy", amount, params=params)
        order_id: str = order.get("id", client_order_id)
        logger.info(
            "spot buy executed | exchange={} symbol={} amount={} order_id={}",
            self._exchange_id, symbol, amount, order_id,
        )
        return order_id

    async def sell_spot_market(
        self, symbol: str, amount: float, client_order_id: str
    ) -> str:
        client = await self._ensure_client()
        params: dict[str, object] = {"clientOrderId": client_order_id}
        order = await client.create_order(symbol, "market", "sell", amount, params=params)
        order_id: str = order.get("id", client_order_id)
        logger.info(
            "spot sell executed | exchange={} symbol={} amount={} order_id={}",
            self._exchange_id, symbol, amount, order_id,
        )
        return order_id

    async def fetch_balance(self, asset: str) -> Decimal:
        client = await self._ensure_client()
        balance = await client.fetch_balance()
        free = balance.get(asset, {}).get("free", 0)
        return Decimal(str(free))

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
        if self._session is not None:
            await self._session.close()
            self._session = None
