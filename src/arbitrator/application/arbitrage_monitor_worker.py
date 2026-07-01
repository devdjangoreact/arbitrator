from __future__ import annotations

import asyncio
import threading
from collections.abc import Sequence

from arbitrator.application.arb_monitor_lifecycle import ArbMonitorLifecycle
from arbitrator.application.arbitrage_close_service import ArbitrageCloseService
from arbitrator.application.multi_exchange_watcher import MultiExchangeWatcher
from arbitrator.application.spread_evaluator import SpreadEvaluator
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.arbitrage_pair import ArbitragePair
from arbitrator.domain.spread_calculator import SpreadCalculator
from arbitrator.domain.spread_snapshot import SpreadSnapshot
from arbitrator.domain.ticker import Ticker
from arbitrator.exchanges.factory import Factory


class ArbitrageMonitorWorker:
    """Watches live spreads for open arbitrage pairs and triggers auto-close."""

    def __init__(
        self,
        settings: Settings,
        factory: Factory,
        close_service: ArbitrageCloseService,
        pairs: Sequence[ArbitragePair],
    ) -> None:
        self._settings = settings
        self._factory = factory
        self._close_service = close_service
        self._pairs = list(pairs)
        self._evaluator = SpreadEvaluator(settings)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._snapshots: dict[str, SpreadSnapshot] = {}
        self._closed_pairs: set[str] = set()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self._settings.arb_auto_close_enabled:
            return
        if not self._pairs:
            return
        self._thread = threading.Thread(
            target=self._thread_main,
            name="arb-monitor",
            daemon=True,
        )
        self._thread.start()
        logger.info("Arbitrage monitor started | pairs={}", len(self._pairs))

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=60.0)
            self._thread = None
        logger.info("Arbitrage monitor stopped")

    def read_snapshots(self) -> dict[str, SpreadSnapshot]:
        with self._lock:
            return dict(self._snapshots)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def monitored_signature(self) -> tuple[tuple[str, str, str, str], ...]:
        return ArbMonitorLifecycle.pair_signature(self._pairs)

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_main())
        except Exception:
            logger.exception("Arbitrage monitor thread failed")

    async def _async_main(self) -> None:
        symbols = sorted({pair.symbol for pair in self._pairs})
        exchange_ids = sorted(
            {pair.short_leg.exchange_id for pair in self._pairs}
            | {pair.long_leg.exchange_id for pair in self._pairs}
        )
        named = self._factory.create_many(exchange_ids)
        symbols_by_exchange = dict.fromkeys(exchange_ids, symbols)
        watcher = MultiExchangeWatcher(self._settings, named)
        try:
            async for snapshot in watcher.updates(symbols_by_exchange):
                if self._stop.is_set():
                    break
                await self._handle_snapshot(snapshot)
        finally:
            await watcher.close()

    async def _handle_snapshot(self, tickers: dict[tuple[str, str], Ticker]) -> None:
        by_symbol: dict[str, dict[str, float]] = {
            pair.symbol: {} for pair in self._pairs
        }
        for (exchange_id, symbol), ticker in tickers.items():
            if ticker.last is None:
                continue
            if symbol not in by_symbol:
                continue
            by_symbol[symbol][exchange_id] = ticker.last
        for symbol, prices in by_symbol.items():
            if len(prices) < 2:
                continue
            spread = SpreadCalculator.compute(symbol, prices)
            with self._lock:
                self._snapshots[symbol] = spread
            if not self._evaluator.should_close(spread):
                continue
            for pair in self._pairs:
                if pair.symbol != symbol or pair.pair_id in self._closed_pairs:
                    continue
                self._closed_pairs.add(pair.pair_id)
                logger.info(
                    "Auto-close triggered | pair_id={} symbol={} spread={}",
                    pair.pair_id,
                    symbol,
                    spread.spread_pct,
                )
                result = await self._close_service.close_pair(pair)
                if not result.all_success:
                    self._closed_pairs.discard(pair.pair_id)
                    logger.error(
                        "Auto-close partial failure | pair_id={} short_ok={} long_ok={}",
                        pair.pair_id,
                        result.short.success,
                        result.long.success,
                    )
