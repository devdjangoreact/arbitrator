from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import cast

from arbitrator_2.connector.ccxt_session_factory import CcxtSessionFactory
from arbitrator_2.connector.client_role import ClientRole
from arbitrator_2.connector.market_id import MarketId
from arbitrator_2.connector.market_kind import MarketKind
from arbitrator_2.connector.venue_capabilities import VenueCapabilities


class CcxtProVenue:
    def __init__(
        self,
        venue_id: str,
        caps: VenueCapabilities,
        factory: CcxtSessionFactory | None = None,
        book_depth: int = 1,
    ) -> None:
        self.venue_id = venue_id
        self._caps = caps
        self._factory = factory or CcxtSessionFactory()
        self._book_depth = max(1, book_depth)
        self._clients: dict[tuple[ClientRole, MarketKind], object] = {}
        self._loaded_kinds: set[MarketKind] = set()
        self._load_locks: dict[MarketKind, asyncio.Lock] = {}

    def _client(self, role: ClientRole, kind: MarketKind) -> object:
        key = (role, kind)
        if key not in self._clients:
            self._clients[key] = self._factory.create(self.venue_id, kind)
        return self._clients[key]

    async def load_markets(self, kind: MarketKind) -> None:
        lock = self._load_locks.setdefault(kind, asyncio.Lock())
        async with lock:
            if kind in self._loaded_kinds:
                return
            meta = self._client(ClientRole.META, kind)
            load = getattr(meta, "load_markets")
            await cast(Callable[[], Awaitable[object]], load)()
            markets = getattr(meta, "markets")
            book = self._client(ClientRole.BOOK, kind)
            getattr(book, "set_markets")(markets)
            self._loaded_kinds.add(kind)

    def _ensure_markets(self, client: object, market: MarketId) -> None:
        existing = getattr(client, "markets", None)
        if existing:
            return
        getattr(client, "set_markets")(self._btc_markets(market))

    def _native_id(self, market: MarketId) -> str:
        base, rest = market.symbol.split("/", 1)
        quote = rest.split(":", 1)[0]
        if self.venue_id == "gate":
            return f"{base}_{quote}"
        if self.venue_id == "bingx":
            return f"{base}-{quote}"
        if self.venue_id == "mexc" and market.kind is MarketKind.PERP:
            return f"{base}_{quote}"
        return f"{base}{quote}"

    def _btc_markets(self, market: MarketId) -> dict[str, dict[str, object]]:
        spot = market.kind is MarketKind.SPOT
        base, rest = market.symbol.split("/", 1)
        quote = rest.split(":", 1)[0]
        row: dict[str, object] = {
            "id": self._native_id(market),
            "symbol": market.symbol,
            "base": base,
            "quote": quote,
            "baseId": base,
            "quoteId": quote,
            "spot": spot,
            "swap": not spot,
            "future": False,
            "option": False,
            "type": "spot" if spot else "swap",
            "linear": not spot,
            "inverse": False,
            "contract": not spot,
        }
        if not spot:
            row["settle"] = "USDT"
            row["settleId"] = "usdt" if self.venue_id == "gate" else "USDT"
        return {market.symbol: row}

    async def watch_book(self, market: MarketId) -> dict[str, object]:
        client = self._client(ClientRole.BOOK, market.kind)
        self._ensure_markets(client, market)
        watch = getattr(client, "watch_order_book")
        raw = await cast(Callable[..., Awaitable[object]], watch)(
            market.symbol, max(self._caps.min_depth, self._book_depth)
        )
        if not isinstance(raw, dict):
            return {}
        return cast(dict[str, object], raw)

    async def watch_trades(self, market: MarketId) -> list[object]:
        if not self._caps.trades:
            raise NotImplementedError("trades disabled")
        client = self._client(ClientRole.TRADES, market.kind)
        self._ensure_markets(client, market)
        meta = self._clients.get((ClientRole.META, market.kind))
        if meta is not None:
            loaded = getattr(meta, "markets", None)
            if loaded:
                getattr(client, "set_markets")(loaded)
        watch = getattr(client, "watch_trades")
        raw = await cast(Callable[..., Awaitable[object]], watch)(market.symbol)
        if not isinstance(raw, list):
            return []
        return cast(list[object], raw)

    async def close(self) -> None:
        for client in self._clients.values():
            await self._factory.close_client(client)
        self._clients.clear()
