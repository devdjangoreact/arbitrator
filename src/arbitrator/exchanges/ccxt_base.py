from __future__ import annotations

import asyncio
import ssl
import time
from abc import abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar, Literal

import aiohttp
import ccxt.pro as ccxtpro
import certifi
from ccxt.base.errors import BadSymbol, NetworkError, UnsubscribeError

from arbitrator.config.ccxt_position_mapper import CcxtPositionMapper
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.closed_position_leg import ClosedPositionLeg
from arbitrator.domain.exchange_connection_status import ExchangeConnectionStatus
from arbitrator.domain.exchange_gateway import ExchangeGateway
from arbitrator.domain.open_order_leg import OpenOrderLeg
from arbitrator.domain.order_book_level import OrderBookLevel
from arbitrator.domain.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.funding_info import FundingInfo
from arbitrator.domain.symbol_market_info import SymbolMarketInfo, SymbolMarketInfoParser
from arbitrator.domain.symbol_normalizer import SymbolNormalizer
from arbitrator.domain.ticker import Ticker
from arbitrator.domain.token_identity import CurrencyNetworkInfo
from arbitrator.domain.trade_tick import TradeTick


@dataclass
class _ClosedTradeAccumulator:
    realized_pnl: float = 0.0
    commission: float = 0.0
    min_timestamp_ms: int | None = None
    max_timestamp_ms: int | None = None
    arb_marker_id: str | None = None
    position_id: str | None = None

    def track_timestamp(self, timestamp_ms: int) -> None:
        if self.min_timestamp_ms is None or timestamp_ms < self.min_timestamp_ms:
            self.min_timestamp_ms = timestamp_ms
        if self.max_timestamp_ms is None or timestamp_ms > self.max_timestamp_ms:
            self.max_timestamp_ms = timestamp_ms

    def closed_at(self) -> datetime:
        if self.max_timestamp_ms is not None:
            return datetime.fromtimestamp(self.max_timestamp_ms / 1000.0, tz=UTC)
        return datetime.now(UTC)

    def opened_at(self) -> datetime | None:
        if self.min_timestamp_ms is None:
            return None
        return datetime.fromtimestamp(self.min_timestamp_ms / 1000.0, tz=UTC)


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
    _COMPOSITE_INDEX_BASES: ClassVar[frozenset[str]] = frozenset({"ALL", "DEFI", "BTCDOM"})

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: ccxtpro.Exchange | None = None
        self._session: aiohttp.ClientSession | None = None
        self._markets_lock = asyncio.Lock()
        self._open_lock = asyncio.Lock()

    @abstractmethod
    def _create_client(self, session: aiohttp.ClientSession) -> ccxtpro.Exchange:
        """Return a configured ccxt.pro exchange bound to the given aiohttp session."""

    def _base_client_config(self, session: aiohttp.ClientSession) -> dict[str, object]:
        config: dict[str, object] = {
            "session": session,
            "enableRateLimit": self._settings.enable_rate_limit,
            "options": {"defaultType": self._settings.default_type},
        }
        creds = self._settings.credentials_for(self.exchange_id)
        if creds is not None:
            config["apiKey"] = creds.api_key
            config["secret"] = creds.api_secret
            if creds.password:
                config["password"] = creds.password
        return config

    def _missing_credentials_message(self) -> str:
        if self.exchange_id == "bitget":
            return "API key, secret, and passphrase required in .env"
        return "API key and secret required in .env"

    def _failed_status(self, message: str) -> ExchangeConnectionStatus:
        return ExchangeConnectionStatus(
            exchange_id=self.exchange_id,
            display_name=self.display_name,
            credentials_configured=True,
            authenticated=False,
            trading_enabled=False,
            usdt_balance=None,
            message=message,
        )

    async def _probe_trading_access(self, client: ccxtpro.Exchange) -> bool:
        if not client.has.get("fetchPositions"):
            return bool(client.has.get("createOrder"))
        try:
            await client.fetch_positions()
            return True
        except ccxtpro.PermissionDenied:
            return False
        except Exception:
            logger.exception("Trading access probe failed | exchange={}", self.exchange_id)
            return False

    async def _first_usdt_balance(self, client: ccxtpro.Exchange) -> float | None:
        balance = await client.fetch_balance()
        return self._extract_usdt_balance(balance)

    @staticmethod
    def _extract_usdt_balance(balance: object) -> float | None:
        if not isinstance(balance, dict):
            return None
        usdt_entry = balance.get("USDT")
        if isinstance(usdt_entry, dict):
            total = usdt_entry.get("total")
            if isinstance(total, (int, float)):
                return float(total)
        total_map = balance.get("total")
        if isinstance(total_map, dict):
            usdt_total = total_map.get("USDT")
            if isinstance(usdt_total, (int, float)):
                return float(usdt_total)
        return None

    async def watch_tickers(self, symbols: Sequence[str]) -> AsyncIterator[dict[str, Ticker]]:
        symbol_list = list(symbols)
        if not symbol_list:
            return
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        symbol_list = [
            symbol
            for symbol in symbol_list
            if CcxtBase._is_arbitrage_symbol(client.markets.get(symbol))
        ]
        if not symbol_list:
            return
        supports_bulk = bool(client.has.get("watchTickers"))
        chunk_size = self._settings.watch_tickers_chunk_size
        chunk_count = (
            (len(symbol_list) + chunk_size - 1) // chunk_size if supports_bulk else 0
        )
        logger.info(
            "Streaming tickers | exchange={} symbols={} mode={} chunks={}",
            self.exchange_id,
            len(symbol_list),
            "bulk" if supports_bulk else "fanout",
            chunk_count if supports_bulk else "-",
        )
        if supports_bulk:
            async for update in self._stream_bulk(client, symbol_list):
                yield update
        else:
            async for update in self._stream_fanout(client, symbol_list):
                yield update

    async def watch_order_book(
        self,
        symbol: str,
        limit: int,
    ) -> AsyncIterator[OrderBookSnapshot]:
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        if not client.has.get("watchOrderBook"):
            logger.info("watchOrderBook unsupported | exchange={}", self.exchange_id)
            return
        logger.info(
            "Streaming order book | exchange={} symbol={} limit={}",
            self.exchange_id,
            symbol,
            limit,
        )
        while True:
            try:
                payload = await client.watch_order_book(symbol, limit)
            except asyncio.CancelledError:
                raise
            except BadSymbol:
                logger.warning(
                    "watch_order_book symbol unknown, skipping | exchange={} symbol={}",
                    self.exchange_id,
                    symbol,
                )
                return
            except UnsubscribeError:
                logger.debug(
                    "watch_order_book unsubscribed, resubscribing | exchange={} symbol={}",
                    self.exchange_id,
                    symbol,
                )
                continue
            except NetworkError as error:
                logger.debug(
                    "watch_order_book transient, retrying | exchange={} symbol={} err={}",
                    self.exchange_id,
                    symbol,
                    type(error).__name__,
                )
                continue
            except Exception:
                logger.exception(
                    "watch_order_book error | exchange={} symbol={}",
                    self.exchange_id,
                    symbol,
                )
                continue
            yield self._to_order_book_snapshot(symbol, payload)

    async def watch_trades(self, symbol: str) -> AsyncIterator[TradeTick]:
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        if not client.has.get("watchTrades"):
            logger.info("watchTrades unsupported | exchange={}", self.exchange_id)
            return
        logger.info("Streaming trades | exchange={} symbol={}", self.exchange_id, symbol)
        while True:
            try:
                payload = await client.watch_trades(symbol)
            except asyncio.CancelledError:
                raise
            except UnsubscribeError:
                logger.debug(
                    "watch_trades unsubscribed, resubscribing | exchange={} symbol={}",
                    self.exchange_id,
                    symbol,
                )
                continue
            except NetworkError as error:
                logger.debug(
                    "watch_trades transient, retrying | exchange={} symbol={} err={}",
                    self.exchange_id,
                    symbol,
                    type(error).__name__,
                )
                continue
            except Exception:
                logger.exception(
                    "watch_trades error | exchange={} symbol={}",
                    self.exchange_id,
                    symbol,
                )
                continue
            for tick in self._to_trade_ticks(symbol, payload):
                yield tick

    def _to_order_book_snapshot(self, symbol: str, payload: object) -> OrderBookSnapshot:
        if not isinstance(payload, dict):
            return OrderBookSnapshot(
                exchange_id=self.exchange_id,
                symbol=symbol,
                timestamp_ms=None,
                bids=(),
                asks=(),
            )
        ts = CcxtBase._as_int(payload.get("timestamp"))
        return OrderBookSnapshot(
            exchange_id=self.exchange_id,
            symbol=symbol,
            timestamp_ms=ts,
            bids=CcxtBase._parse_book_levels(payload.get("bids")),
            asks=CcxtBase._parse_book_levels(payload.get("asks")),
        )

    def _to_trade_ticks(self, symbol: str, payload: object) -> list[TradeTick]:
        items: list[object]
        if isinstance(payload, list):
            items = list(payload)
        elif isinstance(payload, dict):
            items = [payload]
        else:
            return []
        ticks: list[TradeTick] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            price = CcxtBase._as_float(item.get("price"))
            amount = CcxtBase._as_float(item.get("amount"))
            ts = CcxtBase._as_int(item.get("timestamp"))
            side_raw = item.get("side")
            if price is None or amount is None or ts is None:
                continue
            if side_raw == "buy":
                side: Literal["buy", "sell"] = "buy"
            elif side_raw == "sell":
                side = "sell"
            else:
                continue
            ticks.append(
                TradeTick(
                    exchange_id=self.exchange_id,
                    symbol=symbol,
                    timestamp_ms=ts,
                    price=price,
                    amount=amount,
                    side=side,
                )
            )
        return ticks

    @staticmethod
    def _parse_book_levels(raw: object) -> tuple[OrderBookLevel, ...]:
        if not isinstance(raw, list):
            return ()
        levels: list[OrderBookLevel] = []
        for entry in raw:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                price = CcxtBase._as_float(entry[0])
                size = CcxtBase._as_float(entry[1])
            elif isinstance(entry, dict):
                price = CcxtBase._as_float(entry.get("price"))
                size = CcxtBase._as_float(entry.get("amount"))
            else:
                continue
            if price is None or size is None:
                continue
            levels.append(OrderBookLevel(price=price, size=size))
        return tuple(levels)

    async def list_symbols(self) -> list[str]:
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        markets = client.markets
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
            if not CcxtBase._is_arbitrage_symbol(market):
                continue
            symbols.append(symbol)
        symbols.sort()
        logger.info(
            "list_symbols | exchange={} count={}",
            self.exchange_id,
            len(symbols),
        )
        return symbols

    async def fetch_symbol_market_info(self, symbol: str) -> SymbolMarketInfo | None:
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        resolved = CcxtBase._resolve_market_symbol(client, symbol)
        if resolved is None:
            logger.debug(
                "market symbol not found | exchange={} symbol={}",
                self.exchange_id,
                symbol,
            )
            return None
        market = client.markets.get(resolved)
        if not isinstance(market, dict):
            return None
        ticker_data = client.tickers.get(resolved) if isinstance(client.tickers, dict) else None
        mark_price: float | None = None
        if isinstance(ticker_data, dict):
            mark_price = CcxtBase._as_float(ticker_data.get("last"))
        return SymbolMarketInfoParser.from_ccxt_market(market, mark_price=mark_price)

    async def verify_connection(self) -> ExchangeConnectionStatus:
        try:
            return await self.probe_connection()
        finally:
            await self.close()

    async def probe_connection(self) -> ExchangeConnectionStatus:
        """Validate credentials without closing the gateway session."""
        creds = self._settings.credentials_for(self.exchange_id)
        if creds is None:
            message = self._missing_credentials_message()
            return ExchangeConnectionStatus(
                exchange_id=self.exchange_id,
                display_name=self.display_name,
                credentials_configured=False,
                authenticated=False,
                trading_enabled=False,
                usdt_balance=None,
                message=message,
            )
        try:
            client = await self._ensure_open()
            client.check_required_credentials()
            await self._ensure_markets_loaded(client)
            usdt_balance = await self._first_usdt_balance(client)
            trading_enabled = await self._probe_trading_access(client)
            message = "Connected"
            if not trading_enabled:
                message = "Connected (trading access disabled)"
            logger.info(
                "Connection verified | exchange={} trading={} usdt={}",
                self.exchange_id,
                trading_enabled,
                usdt_balance,
            )
            return ExchangeConnectionStatus(
                exchange_id=self.exchange_id,
                display_name=self.display_name,
                credentials_configured=True,
                authenticated=True,
                trading_enabled=trading_enabled,
                usdt_balance=usdt_balance,
                message=message,
            )
        except ccxtpro.AccountNotEnabled:
            logger.warning(
                "Futures account not enabled | exchange={}",
                self.exchange_id,
            )
            return ExchangeConnectionStatus(
                exchange_id=self.exchange_id,
                display_name=self.display_name,
                credentials_configured=True,
                authenticated=True,
                trading_enabled=False,
                usdt_balance=None,
                message=(
                    "API keys valid; activate USDT futures account "
                    "(transfer funds to futures wallet on exchange)"
                ),
            )
        except ccxtpro.PermissionDenied:
            logger.exception("Permission denied | exchange={}", self.exchange_id)
            return self._failed_status("API key lacks required permissions")
        except ccxtpro.AuthenticationError:
            logger.exception("Authentication failed | exchange={}", self.exchange_id)
            return self._failed_status("Invalid API key or secret")
        except Exception:
            logger.exception("Connection check failed | exchange={}", self.exchange_id)
            return self._failed_status("Connection check failed")

    async def fetch_ticker_once(self, symbol: str) -> Ticker | None:
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        if not client.has.get("fetchTicker"):
            logger.info("fetchTicker unsupported | exchange={}", self.exchange_id)
            return None
        try:
            payload = await client.fetch_ticker(symbol)
        except Exception:
            logger.exception(
                "fetch_ticker_once failed | exchange={} symbol={}",
                self.exchange_id,
                symbol,
            )
            return None
        if not isinstance(payload, dict):
            return None
        return CcxtBase._to_ticker(symbol, payload)

    async def fetch_order_book_once(self, symbol: str, limit: int) -> OrderBookSnapshot:
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        if not client.has.get("fetchOrderBook"):
            logger.info("fetchOrderBook unsupported | exchange={}", self.exchange_id)
            return OrderBookSnapshot(
                exchange_id=self.exchange_id,
                symbol=symbol,
                timestamp_ms=None,
                bids=(),
                asks=(),
            )
        try:
            payload = await client.fetch_order_book(symbol, limit)
        except Exception:
            logger.exception(
                "fetch_order_book_once failed | exchange={} symbol={}",
                self.exchange_id,
                symbol,
            )
            return OrderBookSnapshot(
                exchange_id=self.exchange_id,
                symbol=symbol,
                timestamp_ms=None,
                bids=(),
                asks=(),
            )
        return self._to_order_book_snapshot(symbol, payload)

    async def fetch_open_orders(self, symbol: str | None = None) -> list[OpenOrderLeg]:
        creds = self._settings.credentials_for(self.exchange_id)
        if creds is None:
            return []
        client = await self._ensure_open()
        if not client.has.get("fetchOpenOrders"):
            logger.info("fetchOpenOrders unsupported | exchange={}", self.exchange_id)
            return []
        await self._ensure_markets_loaded(client)
        try:
            if symbol is None:
                raw_orders = await client.fetch_open_orders()
            else:
                raw_orders = await client.fetch_open_orders(symbol)
        except Exception:
            logger.exception("fetch_open_orders failed | exchange={}", self.exchange_id)
            return []
        legs = self._map_raw_orders(raw_orders)
        logger.info(
            "Open orders fetched | exchange={} count={}",
            self.exchange_id,
            len(legs),
        )
        return legs

    async def fetch_open_positions(self) -> list[PositionLeg]:
        creds = self._settings.credentials_for(self.exchange_id)
        if creds is None:
            return []
        client = await self._ensure_open()
        if not client.has.get("fetchPositions"):
            logger.info("fetchPositions unsupported | exchange={}", self.exchange_id)
            return []
        await self._ensure_markets_loaded(client)
        try:
            raw_positions = await client.fetch_positions()
        except Exception:
            logger.exception("fetch_open_positions failed | exchange={}", self.exchange_id)
            return []
        legs = await self._map_raw_positions(client, raw_positions)
        logger.info(
            "Open positions fetched | exchange={} count={}",
            self.exchange_id,
            len(legs),
        )
        return legs

    async def watch_open_positions(self) -> AsyncIterator[list[PositionLeg]]:
        creds = self._settings.credentials_for(self.exchange_id)
        if creds is None:
            return
        client = await self._ensure_open()
        if not client.has.get("fetchPositions"):
            logger.info("fetchPositions unsupported | exchange={}", self.exchange_id)
            return
        await self._ensure_markets_loaded(client)
        use_ws = bool(client.has.get("watchPositions"))
        logger.info(
            "Position stream started | exchange={} mode={}",
            self.exchange_id,
            "ws" if use_ws else "rest_once",
        )
        if not use_ws:
            try:
                raw_positions = await client.fetch_positions()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("position stream error | exchange={}", self.exchange_id)
                return
            yield await self._map_raw_positions(client, raw_positions)
            return
        while True:
            try:
                raw_positions = await client.watch_positions()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "position stream error | exchange={}",
                    self.exchange_id,
                )
                continue
            yield await self._map_raw_positions(client, raw_positions)

    async def watch_usdt_balance(self) -> AsyncIterator[float | None]:
        creds = self._settings.credentials_for(self.exchange_id)
        if creds is None:
            return
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        use_ws = bool(client.has.get("watchBalance"))
        logger.info(
            "Balance stream started | exchange={} mode={}",
            self.exchange_id,
            "ws" if use_ws else "rest_once",
        )
        if not use_ws:
            try:
                payload = await client.fetch_balance()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("balance stream error | exchange={}", self.exchange_id)
                return
            yield self._extract_usdt_balance(payload)
            return
        while True:
            try:
                payload = await client.watch_balance()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "balance stream error | exchange={}",
                    self.exchange_id,
                )
                continue
            yield self._extract_usdt_balance(payload)

    async def _map_raw_positions(
        self,
        client: ccxtpro.Exchange,
        raw_positions: object,
    ) -> list[PositionLeg]:
        legs: list[PositionLeg] = []
        if not isinstance(raw_positions, list):
            return legs
        for item in raw_positions:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol")
            if not isinstance(symbol, str):
                continue
            since_ms = self._position_since_ms(item)
            funding = await self.fetch_funding_since(symbol, since_ms)
            close_fee = self._estimate_close_fee(client, symbol, item)
            mapped = CcxtPositionMapper.map_open_position(
                item,
                exchange_id=self.exchange_id,
                display_name=self.display_name,
                accrued_funding=funding,
                estimated_close_fee=close_fee,
            )
            if mapped is not None:
                legs.append(mapped)
        return legs

    def _map_raw_orders(self, raw_orders: object) -> list[OpenOrderLeg]:
        legs: list[OpenOrderLeg] = []
        if not isinstance(raw_orders, list):
            return legs
        for item in raw_orders:
            if not isinstance(item, dict):
                continue
            order_id = item.get("id")
            symbol = item.get("symbol")
            side_raw = item.get("side")
            if not isinstance(order_id, str) or not isinstance(symbol, str):
                continue
            if side_raw == "buy":
                side: Literal["buy", "sell"] = "buy"
            elif side_raw == "sell":
                side = "sell"
            else:
                continue
            order_type = item.get("type")
            legs.append(
                OpenOrderLeg(
                    exchange_id=self.exchange_id,
                    order_id=order_id,
                    symbol=symbol,
                    side=side,
                    order_type=str(order_type) if order_type is not None else "unknown",
                    price=CcxtBase._as_float(item.get("price")),
                    amount=CcxtBase._as_float(item.get("amount")),
                    filled=CcxtBase._as_float(item.get("filled")),
                    remaining=CcxtBase._as_float(item.get("remaining")),
                    status=str(item.get("status")) if item.get("status") is not None else None,
                    timestamp_ms=CcxtBase._as_int(item.get("timestamp")),
                )
            )
        return legs

    async def fetch_closed_positions(
        self,
        since_ms: int,
        symbols: Sequence[str],
    ) -> list[ClosedPositionLeg]:
        creds = self._settings.credentials_for(self.exchange_id)
        if creds is None:
            return []
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        if not client.has.get("fetchPositionHistory"):
            if client.has.get("fetchMyTrades"):
                if not symbols:
                    logger.info(
                        "fetchMyTrades requires symbols | exchange={}",
                        self.exchange_id,
                    )
                    return []
                return await self._fetch_closed_positions_from_trades(
                    client,
                    since_ms,
                    symbols,
                )
            logger.info(
                "fetchPositionHistory unsupported | exchange={}",
                self.exchange_id,
            )
            return []
        legs: list[ClosedPositionLeg] = []
        try:
            if symbols:
                for symbol in symbols:
                    try:
                        history = await client.fetch_position_history(symbol, since=since_ms)
                    except Exception:
                        logger.exception(
                            "fetch_position_history failed | exchange={} symbol={}",
                            self.exchange_id,
                            symbol,
                        )
                        continue
                    legs.extend(
                        await self._map_closed_history_batch(client, history)
                    )
            else:
                history = await client.fetch_positions_history(None, since=since_ms)
                legs.extend(await self._map_closed_history_batch(client, history))
        except Exception:
            logger.exception(
                "fetch_closed_positions failed | exchange={}",
                self.exchange_id,
            )
            return []
        logger.info(
            "Closed positions fetched | exchange={} count={}",
            self.exchange_id,
            len(legs),
        )
        return legs

    async def _map_closed_history_batch(
        self,
        client: ccxtpro.Exchange,
        history: object,
    ) -> list[ClosedPositionLeg]:
        if not isinstance(history, list):
            return []
        legs: list[ClosedPositionLeg] = []
        for item in history:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol")
            if not isinstance(symbol, str):
                continue
            market = client.markets.get(symbol) if isinstance(client.markets, dict) else None
            if not CcxtBase._is_arbitrage_symbol(market):
                continue
            mapped = CcxtPositionMapper.map_closed_position(
                item,
                exchange_id=self.exchange_id,
                display_name=self.display_name,
            )
            if mapped is not None:
                legs.append(mapped)
        return legs

    async def _fetch_closed_positions_from_trades(
        self,
        client: ccxtpro.Exchange,
        since_ms: int,
        symbols: Sequence[str],
    ) -> list[ClosedPositionLeg]:
        """Fallback when ``fetchPositionHistory`` is unavailable (e.g. Binance)."""
        legs: list[ClosedPositionLeg] = []
        for symbol in symbols:
            try:
                trades = await client.fetch_my_trades(symbol, since=since_ms)
            except Exception:
                logger.exception(
                    "fetch_my_trades failed | exchange={} symbol={}",
                    self.exchange_id,
                    symbol,
                )
                continue
            if not isinstance(trades, list):
                continue
            funding_total = await self.fetch_funding_since(symbol, since_ms)
            accumulators: dict[str, _ClosedTradeAccumulator] = {}
            for trade in trades:
                if not isinstance(trade, dict):
                    continue
                position_side = CcxtBase._position_side_from_trade(trade)
                if position_side is None:
                    continue
                realized = CcxtBase._trade_realized_pnl(trade)
                if realized is None or realized == 0.0:
                    continue
                commission = CcxtBase._extract_trade_commission(trade)
                timestamp_ms = CcxtBase._as_int(trade.get("timestamp"))
                marker = CcxtPositionMapper._extract_marker(trade)
                trade_id = CcxtPositionMapper._as_str(trade.get("id"))
                acc = accumulators.setdefault(position_side, _ClosedTradeAccumulator())
                acc.realized_pnl += realized
                if commission is not None:
                    acc.commission += commission
                if timestamp_ms is not None:
                    acc.track_timestamp(timestamp_ms)
                if marker is not None:
                    acc.arb_marker_id = marker
                if trade_id is not None:
                    acc.position_id = trade_id
            for side, acc in accumulators.items():
                if acc.realized_pnl == 0.0:
                    continue
                if side == "long":
                    leg_side: Literal["long", "short"] = "long"
                elif side == "short":
                    leg_side = "short"
                else:
                    continue
                closed_at = acc.closed_at()
                opened_at = acc.opened_at()
                legs.append(
                    ClosedPositionLeg(
                        exchange_id=self.exchange_id,
                        display_name=self.display_name,
                        symbol=symbol,
                        side=leg_side,
                        realized_pnl=acc.realized_pnl,
                        commission=acc.commission if acc.commission else None,
                        funding=funding_total,
                        opened_at=opened_at,
                        closed_at=closed_at,
                        arb_marker_id=acc.arb_marker_id,
                        position_id=acc.position_id,
                    )
                )
        logger.info(
            "Closed positions from trades | exchange={} count={}",
            self.exchange_id,
            len(legs),
        )
        return legs

    @staticmethod
    def _position_side_from_trade(trade: dict[str, object]) -> str | None:
        info = trade.get("info")
        if isinstance(info, dict):
            raw_side = info.get("positionSide")
            if isinstance(raw_side, str):
                lowered = raw_side.lower()
                if lowered in ("long", "short"):
                    return lowered
        side = trade.get("side")
        if side == "buy":
            return "long"
        if side == "sell":
            return "short"
        return None

    @staticmethod
    def _trade_realized_pnl(trade: dict[str, object]) -> float | None:
        info = trade.get("info")
        if isinstance(info, dict):
            for key in ("realizedPnl", "realizedProfit"):
                value = CcxtBase._as_float(info.get(key))
                if value is not None:
                    return value
        return CcxtBase._as_float(trade.get("realizedPnl"))

    @staticmethod
    def _extract_trade_commission(trade: dict[str, object]) -> float | None:
        fee = trade.get("fee")
        if isinstance(fee, dict):
            cost = fee.get("cost")
            if isinstance(cost, (int, float)):
                return abs(float(cost))
        fees = trade.get("fees")
        if isinstance(fees, list):
            total = 0.0
            found = False
            for entry in fees:
                if not isinstance(entry, dict):
                    continue
                cost = entry.get("cost")
                if isinstance(cost, (int, float)):
                    total += abs(float(cost))
                    found = True
            if found:
                return total
        return None

    async def fetch_funding_since(self, symbol: str, since_ms: int) -> float | None:
        creds = self._settings.credentials_for(self.exchange_id)
        if creds is None:
            return None
        client = await self._ensure_open()
        if not client.has.get("fetchFundingHistory"):
            return None
        try:
            history = await client.fetch_funding_history(symbol, since=since_ms)
        except Exception:
            logger.exception(
                "fetch_funding_history failed | exchange={} symbol={}",
                self.exchange_id,
                symbol,
            )
            return None
        if not isinstance(history, list):
            return None
        total = 0.0
        found = False
        for entry in history:
            if not isinstance(entry, dict):
                continue
            amount = self._as_float(entry.get("amount"))
            if amount is not None:
                total += amount
                found = True
        return total if found else None

    async def fetch_funding_infos(self, symbols: Sequence[str]) -> list[FundingInfo]:
        if not symbols:
            return []
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        if not client.has.get("fetchFundingRates"):
            logger.info("fetchFundingRates unsupported | exchange={}", self.exchange_id)
            return []
        known = {s for s in symbols if s in client.markets}
        if not known:
            return []
        try:
            payload = await client.fetch_funding_rates(list(known))
        except Exception:
            logger.exception(
                "fetch_funding_rates failed | exchange={} symbols={}",
                self.exchange_id,
                len(symbols),
            )
            return []
        if not isinstance(payload, dict):
            return []
        recv_time_ms = int(time.time() * 1000)
        infos: list[FundingInfo] = []
        for symbol, structure in payload.items():
            if not isinstance(symbol, str) or not isinstance(structure, dict):
                continue
            infos.append(
                FundingInfo(
                    exchange_id=self.exchange_id,
                    symbol=symbol,
                    rate=CcxtBase._as_decimal(structure.get("fundingRate")),
                    next_rate=CcxtBase._as_decimal(structure.get("nextFundingRate")),
                    next_settlement_ms=CcxtBase._as_int(structure.get("fundingTimestamp")),
                    recv_time_ms=recv_time_ms,
                )
            )
        return infos

    async def fetch_fee_schedule(self, symbol: str) -> FeeSchedule | None:
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        resolved = CcxtBase._resolve_market_symbol(client, symbol)
        if resolved is None:
            logger.debug(
                "market symbol not found for fees | exchange={} symbol={}",
                self.exchange_id,
                symbol,
            )
            return None
        market = client.markets.get(resolved)
        if not isinstance(market, dict):
            return None
        spot_symbol = SymbolNormalizer.to_display_symbol(resolved)
        spot_resolved = CcxtBase._resolve_market_symbol(client, spot_symbol)
        spot_maker: Decimal | None = None
        spot_taker: Decimal | None = None
        if spot_resolved is not None:
            spot_market = client.markets.get(spot_resolved)
            if isinstance(spot_market, dict):
                spot_maker = CcxtBase._as_decimal(spot_market.get("maker"))
                spot_taker = CcxtBase._as_decimal(spot_market.get("taker"))
        return FeeSchedule(
            exchange_id=self.exchange_id,
            symbol=symbol,
            futures_maker=CcxtBase._as_decimal(market.get("maker")),
            futures_taker=CcxtBase._as_decimal(market.get("taker")),
            spot_maker=spot_maker,
            spot_taker=spot_taker,
        )

    @staticmethod
    def _as_decimal(value: object) -> Decimal | None:
        number = CcxtBase._as_float(value)
        if number is None:
            return None
        return Decimal(str(number))

    async def open_market_position(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        amount: float,
        client_order_id: str,
    ) -> str:
        creds = self._settings.credentials_for(self.exchange_id)
        if creds is None:
            raise RuntimeError("credentials not configured")
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        precise = float(client.amount_to_precision(symbol, amount))
        params: dict[str, object] = {"clientOrderId": client_order_id}
        try:
            order = await client.create_order(symbol, "market", side, precise, None, params)
        except Exception:
            logger.exception(
                "open_market_position failed | exchange={} symbol={} side={}",
                self.exchange_id,
                symbol,
                side,
            )
            raise
        order_id = order.get("id") if isinstance(order, dict) else None
        logger.info(
            "Position opened | exchange={} symbol={} side={} order_id={}",
            self.exchange_id,
            symbol,
            side,
            order_id,
        )
        return str(order_id) if order_id is not None else ""

    async def close_market_position(self, leg: PositionLeg) -> str:
        creds = self._settings.credentials_for(self.exchange_id)
        if creds is None:
            raise RuntimeError("credentials not configured")
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        close_side = "buy" if leg.side == "short" else "sell"
        precise = float(client.amount_to_precision(leg.symbol, leg.contracts))
        params: dict[str, object] = {"reduceOnly": True}
        try:
            order = await client.create_order(
                leg.symbol,
                "market",
                close_side,
                precise,
                None,
                params,
            )
        except Exception:
            logger.exception(
                "close_market_position failed | exchange={} symbol={} side={}",
                self.exchange_id,
                leg.symbol,
                leg.side,
            )
            raise
        order_id = order.get("id") if isinstance(order, dict) else None
        logger.info(
            "Position close submitted | exchange={} symbol={} side={} order_id={}",
            self.exchange_id,
            leg.symbol,
            leg.side,
            order_id,
        )
        return str(order_id) if order_id is not None else ""

    async def set_margin_mode(self, symbol: str, mode: str) -> None:
        """Set margin mode for a swap symbol (best-effort; tolerates 'already set' errors)."""
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        if not client.has.get("setMarginMode"):
            logger.debug(
                "set_margin_mode not supported | exchange={} symbol={} mode={}",
                self.exchange_id, symbol, mode,
            )
            return
        try:
            await client.set_margin_mode(mode, symbol)
            logger.info(
                "set_margin_mode ok | exchange={} symbol={} mode={}",
                self.exchange_id, symbol, mode,
            )
        except Exception as exc:
            msg = str(exc).lower()
            # Tolerate "already set" or "not supported for this market" responses
            if any(k in msg for k in ("already", "not support", "invalid", "no need")):
                logger.debug(
                    "set_margin_mode ignored (already set or unsupported) | "
                    "exchange={} symbol={} mode={} msg={}",
                    self.exchange_id, symbol, mode, str(exc),
                )
            else:
                logger.exception(
                    "set_margin_mode failed | exchange={} symbol={} mode={}",
                    self.exchange_id, symbol, mode,
                )

    def _position_since_ms(self, payload: dict[str, object]) -> int:
        ts = payload.get("timestamp")
        if isinstance(ts, (int, float)) and ts > 0:
            return int(ts)
        return 0

    def _estimate_close_fee(
        self,
        client: ccxtpro.Exchange,
        symbol: str,
        payload: dict[str, object],
    ) -> float | None:
        mark = self._as_float(payload.get("markPrice"))
        contracts = self._as_float(payload.get("contracts"))
        contract_size = self._as_float(payload.get("contractSize")) or 1.0
        if mark is None or contracts is None:
            return None
        notional = abs(contracts) * contract_size * mark
        market = client.markets.get(symbol) if isinstance(client.markets, dict) else None
        taker = 0.0005
        if isinstance(market, dict):
            taker_raw = market.get("taker")
            if isinstance(taker_raw, (int, float)):
                taker = float(taker_raw)
        return notional * taker

    @staticmethod
    def _extract_commission(payload: object) -> float | None:
        if not isinstance(payload, dict):
            return None
        for key in ("fee", "commission"):
            cost = payload.get(key)
            if isinstance(cost, dict):
                amount = cost.get("cost")
                if isinstance(amount, (int, float)):
                    return float(amount)
            if isinstance(cost, (int, float)):
                return abs(float(cost))
        info = payload.get("info")
        if isinstance(info, dict):
            for key in ("fee", "commission"):
                amount = CcxtBase._as_float(info.get(key))
                if amount is not None:
                    return abs(amount)
        return None

    async def fetch_currency_networks(
        self,
        base_codes: Sequence[str],
    ) -> dict[str, CurrencyNetworkInfo]:
        """Fetch per-network contract ids for the requested base codes.

        The 'id' field of each network entry is exchange-specific:
          - Some exchanges return a blockchain contract address ('0xabc…').
          - Others return only a chain identifier ('ERC20', 'BEP20').
          - Some return None — preserved explicitly so callers know the field
            existed but was empty, rather than assuming the network is absent.

        Returns an empty dict when fetchCurrencies is unsupported or fails.
        """
        client = await self._ensure_open()
        if not client.has.get("fetchCurrencies"):
            logger.info("fetchCurrencies unsupported | exchange={}", self.exchange_id)
            return {}
        try:
            raw: object = await client.fetch_currencies()
        except Exception:
            logger.warning("fetchCurrencies failed | exchange={}", self.exchange_id)
            return {}
        if not isinstance(raw, dict):
            return {}

        wanted = set(base_codes)
        result: dict[str, CurrencyNetworkInfo] = {}

        for code, currency in raw.items():
            if not isinstance(code, str) or code not in wanted:
                continue
            if not isinstance(currency, dict):
                continue

            networks_raw = currency.get("networks")
            network_ids: dict[str, str | None] = {}

            if isinstance(networks_raw, dict):
                for net_key, net_data in networks_raw.items():
                    if not isinstance(net_key, str):
                        continue
                    if not isinstance(net_data, dict):
                        network_ids[net_key] = None
                        continue
                    raw_id = net_data.get("id")
                    # Preserve None explicitly — callers need to distinguish
                    # "field missing/null" from "network not listed".
                    network_ids[net_key] = str(raw_id) if raw_id is not None else None

            result[code] = CurrencyNetworkInfo(
                exchange_id=self.exchange_id,
                base_code=code,
                network_ids=network_ids,
            )

        logger.debug(
            "fetch_currency_networks | exchange={} requested={} found={}",
            self.exchange_id,
            len(wanted),
            len(result),
        )
        return result

    async def common_currencies(self) -> dict[str, str]:
        """Return ccxt commonCurrencies remapping for this exchange.

        Populated after load_markets().  Returns empty dict when unavailable.
        """
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        raw = getattr(client, "commonCurrencies", None)
        if not isinstance(raw, dict):
            return {}
        return {str(k): str(v) for k, v in raw.items() if isinstance(k, str)}

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
        chunk_size = self._settings.watch_tickers_chunk_size
        chunks = [
            symbol_list[index : index + chunk_size]
            for index in range(0, len(symbol_list), chunk_size)
        ]
        logger.debug(
            "Bulk stream chunks | exchange={} chunks={} chunk_size={}",
            self.exchange_id,
            len(chunks),
            chunk_size,
        )
        queue: asyncio.Queue[dict[str, Ticker]] = asyncio.Queue()
        tasks: list[asyncio.Task[None]] = []
        sem = asyncio.Semaphore(self._settings.watch_tickers_max_concurrent_chunks)

        async def _watch_chunk(chunk: list[str], chunk_index: int) -> None:
            while True:
                try:
                    async with sem:
                        payload = await client.watch_tickers(chunk)
                except asyncio.CancelledError:
                    raise
                except UnsubscribeError:
                    logger.debug(
                        "watch_tickers unsubscribed, resubscribing | exchange={} chunk={}",
                        self.exchange_id,
                        chunk_index,
                    )
                    continue
                except NetworkError as error:
                    logger.debug(
                        "watch_tickers transient, retrying | exchange={} chunk={} err={}",
                        self.exchange_id,
                        chunk_index,
                        type(error).__name__,
                    )
                    continue
                except Exception:
                    logger.exception(
                        "watch_tickers error | exchange={} chunk={} symbols={}",
                        self.exchange_id,
                        chunk_index,
                        len(chunk),
                    )
                    self._reset_markets_state(client)
                    continue
                queue.put_nowait(self._to_tickers(payload))

        for chunk_index, chunk in enumerate(chunks):
            tasks.append(
                asyncio.create_task(
                    _watch_chunk(chunk, chunk_index),
                    name=f"watch_tickers:{self.exchange_id}:chunk:{chunk_index}",
                )
            )
        try:
            while True:
                try:
                    update = await queue.get()
                except asyncio.CancelledError:
                    break
                while not queue.empty():
                    extra = queue.get_nowait()
                    update.update(extra)
                yield update
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

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
                except asyncio.CancelledError:
                    raise
                except UnsubscribeError:
                    logger.debug(
                        "watch_ticker unsubscribed, resubscribing | exchange={} symbol={}",
                        self.exchange_id,
                        symbol,
                    )
                    continue
                except NetworkError as error:
                    logger.debug(
                        "watch_ticker transient, retrying | exchange={} symbol={} err={}",
                        self.exchange_id,
                        symbol,
                        type(error).__name__,
                    )
                    continue
                except Exception:
                    logger.exception(
                        "watch_ticker error | exchange={} symbol={}",
                        self.exchange_id,
                        symbol,
                    )
                    continue
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
                try:
                    symbol, ticker = await queue.get()
                except asyncio.CancelledError:
                    break
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
        async with self._open_lock:
            if self._client is not None:
                return self._client
            self._session = self._build_session()
            self._client = self._create_client(self._session)
            self._client.timeout = self._settings.ccxt_request_timeout_ms
            logger.info("Exchange client opened | exchange={}", self.exchange_id)
            return self._client

    async def _ensure_markets_loaded(self, client: ccxtpro.Exchange) -> None:
        markets = client.markets
        if isinstance(markets, dict) and markets:
            return
        async with self._markets_lock:
            markets = client.markets
            if isinstance(markets, dict) and markets:
                return
            try:
                await client.load_markets()
            except Exception:
                self._reset_markets_state(client)
                logger.exception("load_markets failed | exchange={}", self.exchange_id)
                raise
            logger.debug(
                "Markets loaded | exchange={} count={}",
                self.exchange_id,
                len(client.markets),
            )

    @staticmethod
    def _reset_markets_state(client: ccxtpro.Exchange) -> None:
        client.markets_loading = None
        client.reloading_markets = False

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
            bid=CcxtBase._as_float(payload.get("bid")),
            ask=CcxtBase._as_float(payload.get("ask")),
            high_24h=CcxtBase._as_float(payload.get("high")),
            low_24h=CcxtBase._as_float(payload.get("low")),
            base_volume_24h=CcxtBase._as_float(payload.get("baseVolume")),
            quote_volume_24h=CcxtBase._as_float(payload.get("quoteVolume")),
            timestamp_ms=CcxtBase._as_int(payload.get("timestamp")),
            funding_rate=CcxtBase._as_float(payload.get("fundingRate")),
        )

    @staticmethod
    def _resolve_market_symbol(client: ccxtpro.Exchange, symbol: str) -> str | None:
        markets = client.markets
        if not isinstance(markets, dict):
            return None
        if symbol in markets:
            return symbol
        swap_symbol = SymbolNormalizer.to_swap_symbol(symbol)
        if swap_symbol in markets:
            return swap_symbol
        try:
            market = client.market(symbol)
        except Exception:
            try:
                market = client.market(swap_symbol)
            except Exception:
                return None
        if not isinstance(market, dict):
            return None
        resolved = market.get("symbol")
        return resolved if isinstance(resolved, str) else None

    @staticmethod
    def _is_arbitrage_symbol(market: object) -> bool:
        """Keep only single-asset contracts suitable for cross-exchange arbitrage."""
        if not isinstance(market, dict):
            return False
        base = market.get("base")
        if isinstance(base, str) and base in CcxtBase._COMPOSITE_INDEX_BASES:
            return False
        info = market.get("info")
        return not (isinstance(info, dict) and info.get("underlyingType") == "INDEX")

    @staticmethod
    def _as_float(value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return float(stripped)
            except ValueError:
                return None
        return None

    @staticmethod
    def _as_int(value: object) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        return None
