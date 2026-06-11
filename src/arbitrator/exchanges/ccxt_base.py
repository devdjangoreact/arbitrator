from __future__ import annotations

import asyncio
import ssl
from abc import abstractmethod
from collections.abc import AsyncIterator, Sequence
from typing import ClassVar

import aiohttp
import ccxt.pro as ccxtpro
import certifi

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.exchange_gateway import ExchangeGateway
from arbitrator.domain.ticker import Ticker


class CcxtBase(ExchangeGateway):
    """Template base class for every ccxt.pro-backed exchange adapter.

    Handles SSL, custom DNS resolver, lazy session creation and the standard
    ``watch_tickers`` -> ``dict[symbol, Ticker]`` streaming.

    When the underlying ccxt.pro exchange supports a multi-ticker WebSocket
    channel, all symbols are delivered through a single bulk subscription.
    Otherwise the base transparently falls back to per-symbol ``watch_ticker``
    coroutines that still share a single WS connection via ccxt.pro's
    internal multiplexing.

    Concrete subclasses only declare which ccxt.pro exchange class to
    instantiate and the exchange-specific options.
    """

    exchange_id: ClassVar[str]
    display_name: ClassVar[str]

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: ccxtpro.Exchange | None = None
        self._session: aiohttp.ClientSession | None = None

    @abstractmethod
    def _create_client(self, session: aiohttp.ClientSession) -> ccxtpro.Exchange:
        """Return a configured ccxt.pro exchange bound to the given aiohttp session."""

    async def watch_tickers(self, symbols: Sequence[str]) -> AsyncIterator[dict[str, Ticker]]:
        symbol_list = list(symbols)
        if not symbol_list:
            return
        client = await self._ensure_open()
        supports_bulk = bool(client.has.get("watchTickers"))
        logger.info(
            "Streaming tickers | exchange={} symbols={} mode={}",
            self.exchange_id,
            len(symbol_list),
            "bulk" if supports_bulk else "fanout",
        )
        if supports_bulk:
            async for update in self._stream_bulk(client, symbol_list):
                yield update
        else:
            async for update in self._stream_fanout(client, symbol_list):
                yield update

    async def list_symbols(self) -> list[str]:
        client = await self._ensure_open()
        try:
            markets = await client.load_markets()
        except Exception:
            logger.exception("load_markets failed | exchange={}", self.exchange_id)
            raise

        symbols: list[str] = []
        for symbol, market in markets.items():
            if not isinstance(symbol, str) or not isinstance(market, dict):
                continue
            if not market.get("swap"):
                continue
            if market.get("quote") != "USDT" or market.get("settle") != "USDT":
                continue
            if market.get("active") is False:
                continue
            symbols.append(symbol)
        symbols.sort()
        logger.info(
            "list_symbols | exchange={} count={}",
            self.exchange_id,
            len(symbols),
        )
        return symbols

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                logger.exception("ccxt close failed | exchange={}", self.exchange_id)
            self._client = None
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:
                logger.exception("aiohttp session close failed | exchange={}", self.exchange_id)
            self._session = None
        logger.debug("Exchange closed | exchange={}", self.exchange_id)

    async def _stream_bulk(
        self,
        client: ccxtpro.Exchange,
        symbols: Sequence[str],
    ) -> AsyncIterator[dict[str, Ticker]]:
        symbol_list = list(symbols)
        while True:
            try:
                payload = await client.watch_tickers(symbol_list)
            except Exception:
                logger.exception(
                    "watch_tickers error | exchange={} symbols={}",
                    self.exchange_id,
                    len(symbol_list),
                )
                raise
            yield self._to_tickers(payload)

    async def _stream_fanout(
        self,
        client: ccxtpro.Exchange,
        symbols: Sequence[str],
    ) -> AsyncIterator[dict[str, Ticker]]:
        queue: asyncio.Queue[tuple[str, Ticker]] = asyncio.Queue()
        tasks: list[asyncio.Task[None]] = []

        async def _watch_one(symbol: str) -> None:
            while True:
                try:
                    payload = await client.watch_ticker(symbol)
                except Exception:
                    logger.exception(
                        "watch_ticker error | exchange={} symbol={}",
                        self.exchange_id,
                        symbol,
                    )
                    raise
                queue.put_nowait((symbol, self._to_ticker(symbol, payload)))

        for symbol in symbols:
            tasks.append(
                asyncio.create_task(
                    _watch_one(symbol),
                    name=f"watch_ticker:{self.exchange_id}:{symbol}",
                )
            )
        try:
            while True:
                symbol, ticker = await queue.get()
                update: dict[str, Ticker] = {symbol: ticker}
                while not queue.empty():
                    extra_symbol, extra_ticker = queue.get_nowait()
                    update[extra_symbol] = extra_ticker
                yield update
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    async def _ensure_open(self) -> ccxtpro.Exchange:
        if self._client is not None:
            return self._client
        self._session = self._build_session()
        self._client = self._create_client(self._session)
        logger.info("Exchange client opened | exchange={}", self.exchange_id)
        return self._client

    def _build_session(self) -> aiohttp.ClientSession:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        resolver = self._build_resolver()
        connector = aiohttp.TCPConnector(
            ssl=ssl_context,
            resolver=resolver,
            enable_cleanup_closed=True,
        )
        return aiohttp.ClientSession(
            connector=connector,
            trust_env=self._settings.aiohttp_trust_env,
        )

    def _build_resolver(self) -> aiohttp.abc.AbstractResolver:
        if self._settings.use_threaded_dns_resolver:
            return aiohttp.ThreadedResolver()
        return aiohttp.AsyncResolver()

    @staticmethod
    def _to_tickers(payload: object) -> dict[str, Ticker]:
        if not isinstance(payload, dict):
            return {}
        result: dict[str, Ticker] = {}
        for symbol, data in payload.items():
            if not isinstance(symbol, str) or not isinstance(data, dict):
                continue
            result[symbol] = CcxtBase._to_ticker(symbol, data)
        return result

    @staticmethod
    def _to_ticker(symbol: str, payload: dict[str, object]) -> Ticker:
        return Ticker(
            symbol=symbol,
            last=CcxtBase._as_float(payload.get("last")),
            high_24h=CcxtBase._as_float(payload.get("high")),
            low_24h=CcxtBase._as_float(payload.get("low")),
            base_volume_24h=CcxtBase._as_float(payload.get("baseVolume")),
            quote_volume_24h=CcxtBase._as_float(payload.get("quoteVolume")),
            timestamp_ms=CcxtBase._as_int(payload.get("timestamp")),
        )

    @staticmethod
    def _as_float(value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    @staticmethod
    def _as_int(value: object) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return None
