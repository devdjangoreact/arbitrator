from __future__ import annotations

import asyncio
import time

from arbitrator_2.connector.bbo import Bbo
from arbitrator_2.connector.book_store import BookStore
from arbitrator_2.connector.latency_metrics import LatencyMetrics
from arbitrator_2.connector.market_id import MarketId
from arbitrator_2.connector.market_kind import MarketKind
from arbitrator_2.connector.normalize_queue import NormalizeQueue
from arbitrator_2.connector.unified_tick import UnifiedTick
from arbitrator_2.connector.venue_adapter import VenueAdapter


class ConnectorRuntime:
    def __init__(
        self,
        adapters: list[VenueAdapter],
        *,
        enable_trades: bool = False,
        book_depth: int = 1,
    ) -> None:
        self._adapters = {a.venue_id: a for a in adapters}
        self._enable_trades = enable_trades
        self._store = BookStore(depth=book_depth)
        self._metrics = LatencyMetrics()
        self._norm = NormalizeQueue()
        self._unified: asyncio.Queue[UnifiedTick] = asyncio.Queue()
        self._stop = asyncio.Event()
        self._armed: set[MarketId] = set()
        self._tasks: list[asyncio.Task[None]] = []
        self._load_tasks: dict[tuple[str, MarketKind], asyncio.Task[None]] = {}
        self._norm_started = False

    def get_bbo(self, market: MarketId) -> Bbo | None:
        return self._store.get_bbo(market)

    def metrics_snapshot(self) -> dict[str, float]:
        return self._metrics.snapshot()

    async def next_unified(self) -> UnifiedTick:
        return await self._unified.get()

    async def subscribe(
        self, markets: list[MarketId], *, timeout: float = 20.0
    ) -> list[tuple[MarketId, BaseException | None]]:
        _ = timeout
        out: list[tuple[MarketId, BaseException | None]] = []
        for market in markets:
            self._kick_load(market)
            self._arm(market)
            out.append((market, None))
        return out

    def _kick_load(self, market: MarketId) -> None:
        key = (market.venue, market.kind)
        if key in self._load_tasks:
            return
        self._load_tasks[key] = asyncio.create_task(self._load_in_background(key))

    async def _load_in_background(self, key: tuple[str, MarketKind]) -> None:
        venue, kind = key
        try:
            await self._adapters[venue].load_markets(kind)
        except Exception:
            return

    def _arm(self, market: MarketId) -> None:
        if market in self._armed:
            return
        self._armed.add(market)
        self._metrics.mark_subscribe(
            f"{market.venue}:{market.kind}:{market.symbol}", time.monotonic_ns()
        )
        self._ensure_normalize()
        self._tasks.append(asyncio.create_task(self._book_loop(market)))
        if self._enable_trades:
            self._tasks.append(asyncio.create_task(self._trade_loop(market)))

    def _ensure_normalize(self) -> None:
        if self._norm_started:
            return
        self._norm_started = True
        self._tasks.append(asyncio.create_task(self._normalize_loop()))

    async def close(self) -> None:
        self._stop.set()
        for task in self._load_tasks.values():
            task.cancel()
        for adapter in self._adapters.values():
            try:
                await asyncio.wait_for(adapter.close(), timeout=3.0)
            except TimeoutError:
                pass
        for task in self._tasks:
            task.cancel()
        pending = [
            *self._tasks,
            *self._load_tasks.values(),
        ]
        if pending:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True), timeout=3.0
                )
            except TimeoutError:
                pass
        self._tasks.clear()
        self._load_tasks.clear()

    async def _book_loop(self, market: MarketId) -> None:
        adapter = self._adapters[market.venue]
        key = f"{market.venue}:{market.kind}:{market.symbol}"
        while not self._stop.is_set():
            try:
                book = await adapter.watch_book(market)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(0)
                continue
            recv = time.monotonic_ns()
            ts_raw = book.get("timestamp")
            exchange_ts = int(ts_raw) if isinstance(ts_raw, (int, float)) else None
            snap = self._store.apply(market, book.get("bids"), book.get("asks"), exchange_ts, recv)
            if snap is None:
                continue
            self._metrics.record_apply(key, snap.recv_ts_ns, snap.apply_ts_ns)
            self._norm.try_put(market, snap)

    async def _trade_loop(self, market: MarketId) -> None:
        adapter = self._adapters[market.venue]
        while not self._stop.is_set():
            await adapter.watch_trades(market)

    async def _normalize_loop(self) -> None:
        while not self._stop.is_set():
            market, snap = await self._norm.get()
            tick = UnifiedTick(
                market=market,
                bids=snap.bids,
                asks=snap.asks,
                exchange_ts_ms=snap.exchange_ts_ms,
                recv_ts_ns=snap.recv_ts_ns,
                apply_ts_ns=snap.apply_ts_ns,
                norm_ts_ns=time.monotonic_ns(),
            )
            await self._unified.put(tick)
