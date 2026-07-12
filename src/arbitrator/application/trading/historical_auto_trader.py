from __future__ import annotations
from arbitrator.config.ui_config_manager import UIConfigManager

import asyncio
import threading
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING

from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.trading.executable_spread_resolver import ExecutableSpreadResolver
from arbitrator.application.trading.paper_execution_gateway import PaperExecutionGateway
from arbitrator.config.logger import logger
from arbitrator.config.monitor_config_store import MonitorConfigStore
from arbitrator.config.settings import Settings

if TYPE_CHECKING:
    from arbitrator.domain.exchange.exchange_gateway import ExchangeGateway

class HistoricalAutoTrader:
    """Monitors the active opportunities using MonitorConfigStore and opens/closes them automatically."""

    def __init__(
        self,
        settings: Settings,
        store: MonitorConfigStore,
        paper_gateway: PaperExecutionGateway,
        market_cache: MarketDataCacheMemory,
        gateways: Mapping[str, ExchangeGateway] | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._paper = paper_gateway
        self._spread_resolver = ExecutableSpreadResolver(settings, market_cache, gateways)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._open_pairs: dict[str, tuple[str, str, str]] = {}
        # Tracks how many consecutive ticks a spread condition has been met
        self._open_tick_counters: dict[str, int] = {}
        self._close_tick_counters: dict[str, int] = {}
        self._live_state: dict[str, dict] = {}

    def start(self) -> None:
        if not UIConfigManager.get_config().historical_screener_enabled:
            return
        self._restore_open_pairs()
        self._thread = threading.Thread(
            target=self._run,
            name="historical-auto-trader",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    
    def get_live_state(self) -> dict:
        return self._live_state

    def _restore_open_pairs(self) -> None:
        records = self._paper._store.load_all()
        open_ids = {r.pair_id for r in records if r.action == "open" and r.status == "filled"}
        closed_ids = {r.pair_id for r in records if r.action == "open" and r.status == "closed"}
        active_pair_ids = open_ids - closed_ids
        for r in records:
            if r.pair_id not in active_pair_ids:
                continue
            if r.action != "open" or r.status != "filled":
                continue
            if not str(r.pair_id).startswith("hist_"):
                continue
            if r.side == "sell":
                buy_leg = next((x for x in records if x.pair_id == r.pair_id and x.side == "buy"), None)
                if buy_leg is not None:
                    self._open_pairs[r.pair_id] = (r.symbol, r.exchange_id, buy_leg.exchange_id)

    def _run(self) -> None:
        try:
            asyncio.run(self._async_run())
        except Exception:
            logger.exception("Historical auto trader run failed")

    async def _async_run(self) -> None:
        check_interval = self._settings.historical_trader_tick_seconds
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("Historical auto trader tick failed")

            sleep_time = check_interval
            while sleep_time > 0 and not self._stop.is_set():
                await asyncio.sleep(min(sleep_time, 0.5))
                sleep_time -= 0.5

    async def _tick(self) -> None:
        configs = self._store.get_all()

        # 1. Update live state for ALL configs (even stopped) for UI charts
        new_state = {}
        for config in configs:
            try:
                # Figure out active sides
                if config.side == "auto":
                    # For UI display when auto, just pick short=short_ex to show *some* spread, or resolve best
                    active_short = config.short_ex
                    active_long = config.long_ex
                elif config.side == "short":
                    active_short = config.short_ex
                    active_long = config.long_ex
                else:
                    active_short = config.long_ex
                    active_long = config.short_ex

                # Fetch fresh spread once per config for UI
                entry_res = await self._spread_resolver.entry_spread(config.symbol, active_short, active_long, fetch_fresh=True)
                exit_res = await self._spread_resolver.exit_spread(config.symbol, active_short, active_long, fetch_fresh=True)

                entry_pct = entry_res[2] if entry_res else 0.0
                exit_pct = exit_res[2] if exit_res else 0.0

                # Check how many pairs are open
                open_pairs = [(pid, sym, s, l) for pid, (sym, s, l) in self._open_pairs.items() if sym == config.symbol]

                new_state[config.symbol] = {
                    "open_spread": entry_pct,
                    "close_spread": exit_pct,
                    "open_ticks": self._open_tick_counters.get(config.symbol, 0),
                    "close_ticks": max([self._close_tick_counters.get(pid, 0) for pid, _, _, _ in open_pairs]) if open_pairs else 0,
                    "open_orders": len(open_pairs)
                }
            except Exception:
                logger.exception(f"Error resolving state for {config.symbol}")

        self._live_state = new_state


        closed_this_tick = []
        for pair_id, (symbol, short_ex, long_ex) in list(self._open_pairs.items()):
            config = self._store.get(symbol)
            if not config or not config.is_active or config.total_stop:
                self._close_tick_counters[pair_id] = 0
                continue

            try:
                spread_res = await self._spread_resolver.exit_spread(symbol, short_ex, long_ex, fetch_fresh=True)
                if spread_res is not None:
                    _, _, exit_spread_pct = spread_res
                    if exit_spread_pct <= config.close_spread_pct:
                        self._close_tick_counters[pair_id] = self._close_tick_counters.get(pair_id, 0) + 1
                        if self._close_tick_counters[pair_id] >= config.close_ticks:
                            logger.info("Historical close | pair={} spread={:.3f}% <= {}", pair_id, exit_spread_pct, config.close_spread_pct)
                            self._paper.close_pair(pair_id)
                            closed_this_tick.append(pair_id)
                            self._close_tick_counters[pair_id] = 0
                    else:
                        self._close_tick_counters[pair_id] = 0
            except Exception:
                logger.exception("Error checking close condition | pair={}", pair_id)

        for pair_id in closed_this_tick:
            del self._open_pairs[pair_id]

        for config in configs:
            if not config.is_active or config.total_stop or config.force_stop:
                self._open_tick_counters[config.symbol] = 0
                continue

            already_open_count = sum(1 for sym, _, _ in self._open_pairs.values() if sym == config.symbol)
            if already_open_count >= config.max_orders:
                self._open_tick_counters[config.symbol] = 0
                continue

            try:
                # Resolve direction based on side
                if config.side == "auto":
                    # Pick highest entry spread
                    res_ab = self._spread_resolver.entry_spread_pct(config.symbol, config.short_ex, config.long_ex)
                    res_ba = self._spread_resolver.entry_spread_pct(config.symbol, config.long_ex, config.short_ex)
                    val_ab = res_ab if res_ab is not None else -999
                    val_ba = res_ba if res_ba is not None else -999
                    if val_ab < config.open_spread_pct * 0.8 and val_ba < config.open_spread_pct * 0.8:
                        self._open_tick_counters[config.symbol] = 0
                        continue
                    if val_ab >= val_ba:
                        active_short = config.short_ex
                        active_long = config.long_ex
                    else:
                        active_short = config.long_ex
                        active_long = config.short_ex
                elif config.side == "short":
                    active_short = config.short_ex
                    active_long = config.long_ex
                else: # long means swap
                    active_short = config.long_ex
                    active_long = config.short_ex

                cached_entry = self._spread_resolver.entry_spread_pct(config.symbol, active_short, active_long)
                if cached_entry is None or cached_entry >= config.open_spread_pct * 0.8:
                    spread_res = await self._spread_resolver.entry_spread(config.symbol, active_short, active_long, fetch_fresh=True)
                    if spread_res is not None:
                        _, _, entry_spread_pct = spread_res
                        if entry_spread_pct >= config.open_spread_pct:
                            self._open_tick_counters[config.symbol] = self._open_tick_counters.get(config.symbol, 0) + 1
                            if self._open_tick_counters[config.symbol] >= config.open_ticks:
                                logger.info("Historical open | sym={} spread={:.3f}% >= {}", config.symbol, entry_spread_pct, config.open_spread_pct)
                                pair_id = f"hist_{int(time.time()*1000)}"
                                self._paper.open_pair(
                                    pair_id=pair_id,
                                    symbol=config.symbol,
                                    short_exchange_id=active_short,
                                    long_exchange_id=active_long,
                                    notional_usdt=config.order_size_usdt,
                                    strategy="futures_futures"
                                )
                                self._open_pairs[pair_id] = (config.symbol, active_short, active_long)
                                self._open_tick_counters[config.symbol] = 0
                        else:
                            self._open_tick_counters[config.symbol] = 0
            except Exception:
                logger.exception("Error checking open condition | sym={}", config.symbol)
