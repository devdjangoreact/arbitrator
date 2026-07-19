from __future__ import annotations

import asyncio
import datetime
import threading
import time
import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.trading.executable_spread_resolver import ExecutableSpreadResolver
from arbitrator.application.trading.paper_execution_gateway import PaperExecutionGateway
from arbitrator.config.logger import logger
from arbitrator.config.monitor_config_store import MonitorConfig, MonitorConfigStore
from arbitrator.config.settings import Settings
from arbitrator.config.ui_config_manager import UIConfigManager

if TYPE_CHECKING:
    from arbitrator.application.account.account_stream_worker import AccountStreamWorker
    from arbitrator.application.trading.hedged_execution_service import HedgedExecutionService
    from arbitrator.domain.exchange.exchange_gateway import ExchangeGateway


def _vwap_fill(levels: "list[Any] | tuple[Any, ...]", usdt_size: float, side: str) -> float | None:
    """Walk order-book levels and return VWAP fill price for usdt_size notional."""
    remaining = usdt_size
    total_cost = 0.0
    total_qty = 0.0
    for level in levels:
        price = float(getattr(level, "price", 0) or 0)
        qty = float(getattr(level, "size", 0) or 0)
        if price <= 0 or qty <= 0:
            continue
        level_notional = price * qty
        take = min(remaining, level_notional)
        take_qty = take / price
        total_cost += take_qty * price
        total_qty += take_qty
        remaining -= take
        if remaining <= 0:
            break
    if total_qty <= 0:
        return None
    return total_cost / total_qty


class HistoricalAutoTrader:
    """Monitors active opportunities and opens/closes hedged pairs.

    live mode (live_execution is not None):
        All orders go to real exchanges via HedgedExecutionService.
        open_pairs are tracked in-memory only (no paper store).

    paper mode (paper_gateway is not None, live_execution is None):
        All orders are simulated via PaperExecutionGateway.
        open_pairs are persisted in paper_orders.json.
    """

    def __init__(
        self,
        settings: Settings,
        store: MonitorConfigStore,
        market_cache: MarketDataCacheMemory,
        gateways: Mapping[str, ExchangeGateway] | None = None,
        paper_gateway: PaperExecutionGateway | None = None,
        live_execution: HedgedExecutionService | None = None,
        account_worker: AccountStreamWorker | None = None,
    ) -> None:
        if paper_gateway is None and live_execution is None:
            raise ValueError("HistoricalAutoTrader requires either paper_gateway or live_execution")
        self._settings = settings
        self._store = store
        self._paper = paper_gateway
        self._live = live_execution
        self._market_cache = market_cache
        self._gateways: Mapping[str, ExchangeGateway] = gateways or {}
        self._account_worker = account_worker
        self._spread_resolver = ExecutableSpreadResolver(settings, market_cache, gateways)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._open_pairs: dict[str, tuple[str, str, str]] = {}
        self._open_tick_counters: dict[str, int] = {}
        self._close_tick_counters: dict[str, int] = {}
        self._live_state: dict[str, dict[str, Any]] = {}
        self._open_spread_min: dict[str, float] = {}
        self._open_spread_max: dict[str, float] = {}
        self._close_spread_min: dict[str, float] = {}
        self._close_spread_max: dict[str, float] = {}

    def start(self) -> None:
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

    def get_live_state(self) -> dict[str, dict[str, Any]]:
        return self._live_state

    def restart(self, monitor_id: str) -> None:
        """Reconnect monitor: re-sync open pairs and reset rolling spread stats."""
        config = self._store.get(monitor_id)
        if config is None:
            logger.warning("restart: monitor_id={} not found", monitor_id)
            return
        logger.info("restart monitor_id={}", monitor_id)
        self._restore_open_pairs()
        for key in (self._open_spread_min, self._open_spread_max,
                    self._close_spread_min, self._close_spread_max):
            key.pop(monitor_id, None)

    def close_all_positions(self, monitor_id: str) -> None:
        """Close all open positions for the given monitor."""
        cfg = self._store.get(monitor_id)
        cfg_sym = cfg.symbol if cfg else monitor_id.split(":")[0]
        cfg_exs_raw = monitor_id.split(":")
        cfg_exs = {cfg_exs_raw[-2], cfg_exs_raw[-1]} if cfg else set()
        pairs_for_monitor = {
            pid: info
            for pid, info in list(self._open_pairs.items())
            if info[0] == cfg_sym and {info[1], info[2]} == cfg_exs
        }
        for pair_id, (sym, short_ex, long_ex) in pairs_for_monitor.items():
            try:
                if self._live is not None and self._loop is not None:
                    asyncio.run_coroutine_threadsafe(
                        self._live.close_all(
                            symbol=sym,
                            short_exchange_id=short_ex,
                            long_exchange_id=long_ex,
                        ),
                        self._loop,
                    )
                    logger.info("close_all_positions (live): pair_id={} monitor_id={}", pair_id, monitor_id)
                elif self._paper is not None:
                    short_book = self._spread_resolver.top_of_book_sync(short_ex, sym)
                    long_book = self._spread_resolver.top_of_book_sync(long_ex, sym)
                    short_price = float(short_book.ask) if short_book and short_book.ask else 0.0
                    long_price = float(long_book.bid) if long_book and long_book.bid else 0.0
                    records = self._paper._store.load_all()
                    sell_rec = next((r for r in records if r.pair_id == pair_id and r.side == "sell"), None)
                    amount = float(sell_rec.amount) if sell_rec else 0.0
                    if amount > 0:
                        self._paper.close_pair(
                            pair_id=pair_id,
                            symbol=sym,
                            short_exchange_id=short_ex,
                            long_exchange_id=long_ex,
                            short_price=short_price,
                            long_price=long_price,
                            amount=amount,
                        )
                    logger.info("close_all_positions (paper): pair_id={} monitor_id={}", pair_id, monitor_id)
            except Exception:
                logger.exception("close_all_positions: error closing pair_id={}", pair_id)
            self._open_pairs.pop(pair_id, None)
            self._close_tick_counters.pop(pair_id, None)
        self._live_state.pop(monitor_id, None)
        for key in (self._open_spread_min, self._open_spread_max,
                    self._close_spread_min, self._close_spread_max):
            key.pop(monitor_id, None)

    def _restore_open_pairs(self) -> None:
        if self._paper is not None:
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
            return
        # live mode: seed _open_pairs from account_worker positions + store configs
        if self._account_worker is None:
            return
        self._auto_create_monitors_from_positions()
        configs = self._store.get_all()
        for config in configs:
            monitor_id = config.id or f"{config.symbol}:{config.short_exchange}:{config.long_exchange}"
            sym_norm = config.symbol.split(":")[0]
            try:
                all_legs = self._account_worker.read_positions([config.short_exchange, config.long_exchange])
            except Exception:
                continue
            s_legs = [p for p in all_legs if p.exchange_id == config.short_exchange and p.symbol.split(":")[0] == sym_norm and p.side == "short"]
            l_legs = [p for p in all_legs if p.exchange_id == config.long_exchange and p.symbol.split(":")[0] == sym_norm and p.side == "long"]
            _exs = {config.short_exchange, config.long_exchange}
            existing = sum(1 for v in self._open_pairs.values() if v[0] == config.symbol and {v[1], v[2]} == _exs)
            if existing > 0:
                continue
            if not s_legs and not l_legs:
                continue
            # Exchange merges all contracts into one position object.
            # Estimate pair count from notional / order_size to survive restarts correctly.
            per_order = config.order_size_usdt or 10.0
            def _notional(legs: list[Any]) -> float:
                return float(sum(abs(p.contracts) * p.contract_size * p.entry_price for p in legs))
            s_notional = _notional(s_legs)
            l_notional = _notional(l_legs)
            best_notional = max(s_notional, l_notional)
            n_pairs = max(1, round(best_notional / per_order)) if best_notional > 0 else max(len(s_legs), len(l_legs))
            for i in range(n_pairs):
                synthetic_id = f"live_restore_{monitor_id}_{i}"
                if synthetic_id not in self._open_pairs:
                    self._open_pairs[synthetic_id] = (config.symbol, config.short_exchange, config.long_exchange)

    def _auto_create_monitors_from_positions(self) -> None:
        """Create monitor configs for hedged positions not yet tracked (restart recovery)."""
        if self._account_worker is None:
            return
        all_legs = self._account_worker.read_positions()
        # Group by symbol+exchange → find short+long pairs across different exchanges
        shorts: dict[str, list[Any]] = {}  # sym_norm → [leg, ...]
        longs: dict[str, list[Any]] = {}
        for leg in all_legs:
            sym_norm = leg.symbol.split(":")[0]
            # Reconstruct full futures symbol
            sym = leg.symbol if ":" in leg.symbol else f"{sym_norm}:USDT"
            if leg.side == "short":
                shorts.setdefault(sym_norm, []).append((sym, leg.exchange_id))
            elif leg.side == "long":
                longs.setdefault(sym_norm, []).append((sym, leg.exchange_id))
        for sym_norm, s_list in shorts.items():
            if sym_norm not in longs:
                continue
            for (sym_s, short_ex) in s_list:
                for (sym_l, long_ex) in longs[sym_norm]:
                    if short_ex == long_ex:
                        continue
                    symbol = sym_s
                    monitor_id = f"{symbol}:{short_ex}:{long_ex}"
                    if self._store.get(monitor_id) is not None:
                        continue
                    # Auto-create a stopped monitor so the card appears in UI
                    new_cfg = MonitorConfig(
                        symbol=symbol,
                        short_exchange=short_ex,
                        long_exchange=long_ex,
                        side="auto",
                        open_spread_pct=0.5,
                        close_spread_pct=0.1,
                        order_size_usdt=10.0,
                        max_orders=1,
                        open_ticks=1,
                        close_ticks=1,
                        allowed_size_usdt=0.0,
                        allowed_size_current_usdt=0.0,
                        force_stop=False,
                        total_stop=False,
                        is_active=False,
                        adjustment_mode="notify_only",
                        short_leverage=1,
                        long_leverage=1,
                        max_historical_spread_pct=0.0,
                        id=monitor_id,
                    )
                    self._store.put(new_cfg)
                    logger.info("auto-created monitor from live positions | monitor_id={}", monitor_id)

    def _run(self) -> None:
        try:
            asyncio.run(self._async_run())
        except Exception:
            logger.exception("Historical auto trader run failed")

    async def _async_run(self) -> None:
        self._loop = asyncio.get_running_loop()
        check_interval = max(0.5, self._settings.historical_trader_tick_seconds)
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("Historical auto trader tick failed")

            await asyncio.sleep(check_interval)

    @staticmethod
    def _fmt_next_funding(fi: Any) -> str | None:
        ms = getattr(fi, "next_settlement_ms", None)
        if ms is None:
            return None
        secs = max(0, int(ms / 1000 - time.time()))
        h, rem = divmod(secs, 3600)
        m, s_rem = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s_rem:02d}"

    async def _tick(self) -> None:
        configs = self._store.get_all()

        def _flt(val: Any) -> float | None:
            return float(val) if val is not None else None

        def _rate(fi: Any) -> float | None:
            r = getattr(fi, "rate", None)
            return float(r * 100) if r is not None else None

        new_state: dict[str, dict[str, Any]] = {}
        for config in configs:
            monitor_id = config.id or f"{config.symbol}:{config.short_exchange}:{config.long_exchange}"
            try:
                active_short, active_long = self._resolve_sides(config)

                # Pre-fetch funding (doesn't need resolver)
                short_funding = self._market_cache.get_funding(active_short, config.symbol)
                long_funding = self._market_cache.get_funding(active_long, config.symbol)

                open_spread = 0.0
                close_spread = 0.0
                try:
                    # Use cached order book for display — no REST per tick.
                    entry_res = self._spread_resolver.entry_spread_sync(
                        config.symbol, active_short, active_long
                    )
                    exit_res = self._spread_resolver.exit_spread_sync(
                        config.symbol, active_short, active_long
                    )
                    open_spread = entry_res[2] if entry_res else 0.0
                    close_spread = exit_res[2] if exit_res else 0.0
                except Exception:
                    logger.debug("spread resolver unavailable for {} — using 0.0", monitor_id)

                # Fetch quotes AFTER resolver (it puts to order_book cache via fetch_fresh=True)
                # Try order_book first (resolver writes here), fallback to quote cache
                def _book_top(ex: str) -> tuple[float | None, float | None]:
                    ob = self._market_cache.get_order_book(ex, config.symbol)
                    if ob and ob.bids and ob.asks:
                        return _flt(ob.bids[0].price), _flt(ob.asks[0].price)
                    q = self._market_cache.get_quote(ex, config.symbol, "futures")
                    if q:
                        return _flt(getattr(q, "bid", None)), _flt(getattr(q, "ask", None))
                    return None, None

                short_bid, short_ask = _book_top(active_short)
                long_bid, long_ask = _book_top(active_long)
                short_size_val = _flt(getattr(self._market_cache.get_quote(active_short, config.symbol, "futures"), "ask_size", None))
                long_size_val = _flt(getattr(self._market_cache.get_quote(active_long, config.symbol, "futures"), "bid_size", None))
                short_info = self._market_cache.get_market_info(active_short, config.symbol)
                long_info = self._market_cache.get_market_info(active_long, config.symbol)
                max_size_short = _flt(getattr(short_info, "max_order_volume_usdt", None)) if short_info else None
                max_size_long = _flt(getattr(long_info, "max_order_volume_usdt", None)) if long_info else None
                min_size_short = _flt(getattr(short_info, "min_order_volume_usdt", None)) if short_info else None
                min_size_long = _flt(getattr(long_info, "min_order_volume_usdt", None)) if long_info else None

                if monitor_id not in self._open_spread_min:
                    self._open_spread_min[monitor_id] = open_spread
                    self._open_spread_max[monitor_id] = open_spread
                    self._close_spread_min[monitor_id] = close_spread
                    self._close_spread_max[monitor_id] = close_spread
                else:
                    self._open_spread_min[monitor_id] = min(self._open_spread_min[monitor_id], open_spread)
                    self._open_spread_max[monitor_id] = max(self._open_spread_max[monitor_id], open_spread)
                    self._close_spread_min[monitor_id] = min(self._close_spread_min[monitor_id], close_spread)
                    self._close_spread_max[monitor_id] = max(self._close_spread_max[monitor_id], close_spread)

                # Real open positions — source of truth for orders/P/L/fees/funding.
                # account_worker has a live WS cache (1 channel per exchange, shared across
                # all monitors). Fallback to _open_pairs count when worker is absent (paper).
                short_pnl: float | None = None
                long_pnl: float | None = None
                enter_spread: float | None = None
                short_pos_size: float | None = None
                long_pos_size: float | None = None
                short_accrued_funding: float | None = None
                long_accrued_funding: float | None = None
                short_open_fee: float | None = None
                long_open_fee: float | None = None
                short_close_fee_est: float | None = None
                long_close_fee_est: float | None = None
                short_liq_price: float | None = None
                long_liq_price: float | None = None
                short_entry_price: float | None = None
                long_entry_price: float | None = None
                short_orders_count = 0
                long_orders_count = 0
                if self._account_worker is not None:
                    try:
                        sym_norm = config.symbol.split(":")[0]
                        all_legs = self._account_worker.read_positions([active_short, active_long])
                        s_legs = [p for p in all_legs if p.exchange_id == active_short and p.symbol.split(":")[0] == sym_norm and p.side == "short"]
                        l_legs = [p for p in all_legs if p.exchange_id == active_long and p.symbol.split(":")[0] == sym_norm and p.side == "long"]
                        open_count = sum(
                            1 for sym, s, l in self._open_pairs.values()
                            if sym == config.symbol and {s, l} == {active_short, active_long}
                        )
                        short_orders_count = open_count
                        long_orders_count = open_count
                        mm_rate = 0.005
                        if s_legs:
                            short_pnl = sum(p.unrealized_pnl or 0.0 for p in s_legs)
                            short_accrued_funding = sum(p.accrued_funding or 0.0 for p in s_legs)
                            short_open_fee = sum(p.opening_fee or 0.0 for p in s_legs)
                            short_close_fee_est = sum(p.estimated_close_fee or 0.0 for p in s_legs)
                            total_s_qty = sum(abs(p.contracts) * p.contract_size for p in s_legs)
                            total_s_notional = sum(abs(p.contracts) * p.contract_size * p.entry_price for p in s_legs)
                            short_pos_size = total_s_notional
                            avg_s_entry = total_s_notional / total_s_qty if total_s_qty else 0.0
                            short_entry_price = avg_s_entry if avg_s_entry > 0 else None
                            slev = float(config.short_leverage or 1)
                            buf = 1.0 / slev - mm_rate
                            short_liq_price = round(avg_s_entry * (1.0 + buf), 8) if avg_s_entry > 0 and buf > 0 else None
                        if l_legs:
                            long_pnl = sum(p.unrealized_pnl or 0.0 for p in l_legs)
                            long_accrued_funding = sum(p.accrued_funding or 0.0 for p in l_legs)
                            long_open_fee = sum(p.opening_fee or 0.0 for p in l_legs)
                            long_close_fee_est = sum(p.estimated_close_fee or 0.0 for p in l_legs)
                            total_l_qty = sum(abs(p.contracts) * p.contract_size for p in l_legs)
                            total_l_notional = sum(abs(p.contracts) * p.contract_size * p.entry_price for p in l_legs)
                            long_pos_size = total_l_notional
                            avg_l_entry = total_l_notional / total_l_qty if total_l_qty else 0.0
                            long_entry_price = avg_l_entry if avg_l_entry > 0 else None
                            llev = float(config.long_leverage or 1)
                            buf = 1.0 / llev - mm_rate
                            long_liq_price = round(avg_l_entry * (1.0 - buf), 8) if avg_l_entry > 0 and buf > 0 else None
                        if s_legs and l_legs and avg_l_entry > 0:
                            enter_spread = (avg_s_entry - avg_l_entry) / avg_l_entry * 100.0
                    except Exception:
                        logger.debug("read_positions failed for {} / {}", active_short, active_long)
                else:
                    open_count = sum(
                        1 for sym, s, l in self._open_pairs.values()
                        if sym == config.symbol and {s, l} == {active_short, active_long}
                    )
                    short_orders_count = open_count
                    long_orders_count = open_count

                # Allowed size per exchange = balance × leverage
                short_balance = self._market_cache.get_usdt_balance(active_short) or 0.0
                long_balance = self._market_cache.get_usdt_balance(active_long) or 0.0
                short_lev = config.short_leverage or 1
                long_lev = config.long_leverage or 1
                allowed_short = (short_balance * short_lev) if short_balance > 0 else None
                allowed_long = (long_balance * long_lev) if long_balance > 0 else None

                # VWAP-adjusted spread: walk the order book for order_size_usdt
                order_usdt = config.order_size_usdt or 100.0
                vwap_open_spread = open_spread
                vwap_close_spread = close_spread
                ob_short = self._market_cache.get_order_book(active_short, config.symbol)
                ob_long = self._market_cache.get_order_book(active_long, config.symbol)
                vwap_short_bid: float | None = None
                vwap_long_ask: float | None = None
                vwap_short_ask: float | None = None
                vwap_long_bid: float | None = None
                if ob_short and ob_long:
                    # entry: sell short bids, buy long asks
                    vwap_short_bid = _vwap_fill(ob_short.bids, order_usdt, side="bid")
                    vwap_long_ask = _vwap_fill(ob_long.asks, order_usdt, side="ask")
                    if vwap_short_bid and vwap_long_ask and vwap_long_ask > 0:
                        vwap_open_spread = (vwap_short_bid - vwap_long_ask) / vwap_long_ask * 100.0
                    # exit: buy back short asks, sell long bids
                    vwap_short_ask = _vwap_fill(ob_short.asks, order_usdt, side="ask")
                    vwap_long_bid = _vwap_fill(ob_long.bids, order_usdt, side="bid")
                    if vwap_short_ask and vwap_long_bid and vwap_long_bid > 0:
                        vwap_close_spread = (vwap_short_ask - vwap_long_bid) / vwap_long_bid * 100.0

                # ── Card diagnostics log (logs/cards/) ──────────────────────
                self._log_card_tick(
                    monitor_id=monitor_id,
                    config=config,
                    active_short=active_short,
                    active_long=active_long,
                    ob_short=ob_short,
                    ob_long=ob_long,
                    vwap_short_bid=vwap_short_bid,
                    vwap_long_ask=vwap_long_ask,
                    vwap_short_ask=vwap_short_ask,
                    vwap_long_bid=vwap_long_bid,
                    open_spread=open_spread,
                    close_spread=close_spread,
                    vwap_open_spread=vwap_open_spread,
                    vwap_close_spread=vwap_close_spread,
                    short_balance=short_balance,
                    long_balance=long_balance,
                    allowed_short=allowed_short,
                    allowed_long=allowed_long,
                    open_orders=short_orders_count,
                )

                new_state[monitor_id] = {
                    "active_short": active_short,
                    "active_long": active_long,
                    "short_funding_rate": _rate(short_funding),
                    "long_funding_rate": _rate(long_funding),
                    "short_next_funding": self._fmt_next_funding(short_funding),
                    "long_next_funding": self._fmt_next_funding(long_funding),
                    "short_ask": short_ask,
                    "long_ask": long_ask,
                    "short_bid": short_bid,
                    "long_bid": long_bid,
                    "short_size": short_pos_size if short_pos_size is not None else short_size_val,
                    "long_size": long_pos_size if long_pos_size is not None else long_size_val,
                    "short_leverage": short_lev,
                    "long_leverage": long_lev,
                    "max_size_short": max_size_short,
                    "max_size_long": max_size_long,
                    "min_size_short": min_size_short,
                    "min_size_long": min_size_long,
                    "short_price": short_ask or short_bid,
                    "long_price": long_bid or long_ask,
                    "short_entry_price": short_entry_price,
                    "long_entry_price": long_entry_price,
                    "short_liq_price": short_liq_price,
                    "long_liq_price": long_liq_price,
                    "short_pnl": short_pnl,
                    "long_pnl": long_pnl,
                    "short_realized_pnl": 0.0,
                    "long_realized_pnl": 0.0,
                    "enter_spread": enter_spread,
                    "short_accrued_funding": short_accrued_funding,
                    "long_accrued_funding": long_accrued_funding,
                    "short_open_fee": short_open_fee,
                    "long_open_fee": long_open_fee,
                    "short_close_fee_est": short_close_fee_est,
                    "long_close_fee_est": long_close_fee_est,
                    "allowed_short": allowed_short,
                    "allowed_long": allowed_long,
                    "short_orders": short_orders_count,
                    "long_orders": long_orders_count,
                    "open_spread_current": vwap_open_spread,
                    "open_spread_min": self._open_spread_min[monitor_id],
                    "open_spread_max": self._open_spread_max[monitor_id],
                    "close_spread_current": vwap_close_spread,
                    "close_spread_min": self._close_spread_min[monitor_id],
                    "close_spread_max": self._close_spread_max[monitor_id],
                    "vwap_short_bid": vwap_short_bid,
                    "vwap_long_ask": vwap_long_ask,
                    "vwap_short_ask": vwap_short_ask,
                    "vwap_long_bid": vwap_long_bid,
                }
            except Exception:
                logger.exception("Error resolving state for {}", monitor_id)

        self._live_state = new_state

        closed_this_tick: list[str] = []
        for pair_id, (symbol, short_ex, long_ex) in list(self._open_pairs.items()):
            monitor_id = f"{symbol}:{short_ex}:{long_ex}"
            close_config = self._store.get(monitor_id)
            if close_config is None or not close_config.is_active or close_config.total_stop:
                self._close_tick_counters[pair_id] = 0
                continue

            try:
                spread_res = await self._spread_resolver.exit_spread(symbol, short_ex, long_ex, fetch_fresh=True)
                if spread_res is not None:
                    _, _, exit_spread_pct = spread_res
                    if exit_spread_pct <= close_config.close_spread_pct:
                        self._close_tick_counters[pair_id] = self._close_tick_counters.get(pair_id, 0) + 1
                        if self._close_tick_counters[pair_id] >= close_config.close_ticks:
                            logger.info("Close trigger | pair={} spread={:.3f}% <= {}", pair_id, exit_spread_pct, close_config.close_spread_pct)
                            if self._live is not None:
                                await self._live.close_all(
                                    symbol=symbol,
                                    short_exchange_id=short_ex,
                                    long_exchange_id=long_ex,
                                )
                            elif self._paper is not None:
                                short_book = self._spread_resolver.top_of_book_sync(short_ex, symbol)
                                long_book = self._spread_resolver.top_of_book_sync(long_ex, symbol)
                                sprice = float(short_book.ask) if short_book and short_book.ask else 0.0
                                lprice = float(long_book.bid) if long_book and long_book.bid else 0.0
                                records = self._paper._store.load_all()
                                sell_rec = next((r for r in records if r.pair_id == pair_id and r.side == "sell"), None)
                                amount = float(sell_rec.amount) if sell_rec else close_config.order_size_usdt
                                self._paper.close_pair(
                                    pair_id=pair_id,
                                    symbol=symbol,
                                    short_exchange_id=short_ex,
                                    long_exchange_id=long_ex,
                                    short_price=sprice,
                                    long_price=lprice,
                                    amount=amount,
                                )
                            closed_this_tick.append(pair_id)
                            self._close_tick_counters[pair_id] = 0
                    else:
                        self._close_tick_counters[pair_id] = 0
            except Exception:
                logger.exception("Error checking close condition | pair={}", pair_id)

        for pair_id in closed_this_tick:
            del self._open_pairs[pair_id]

        for config in configs:
            monitor_id = config.id or f"{config.symbol}:{config.short_exchange}:{config.long_exchange}"
            if not config.is_active or config.total_stop or config.force_stop:
                self._open_tick_counters[monitor_id] = 0
                continue

            try:
                if config.side == "auto":
                    res_ab = self._spread_resolver.entry_spread_sync(
                        config.symbol, config.short_exchange, config.long_exchange
                    )
                    res_ba = self._spread_resolver.entry_spread_sync(
                        config.symbol, config.long_exchange, config.short_exchange
                    )
                    val_ab = res_ab[2] if res_ab is not None else -999.0
                    val_ba = res_ba[2] if res_ba is not None else -999.0
                    if val_ab < config.open_spread_pct * 0.8 and val_ba < config.open_spread_pct * 0.8:
                        self._open_tick_counters[monitor_id] = 0
                        continue
                    if val_ab >= val_ba:
                        active_short = config.short_exchange
                        active_long = config.long_exchange
                    else:
                        active_short = config.long_exchange
                        active_long = config.short_exchange
                elif config.side == "short":
                    active_short = config.short_exchange
                    active_long = config.long_exchange
                else:
                    active_short = config.long_exchange
                    active_long = config.short_exchange

                # ── Guard: anti-spam open count ───────────────────────────
                open_count = sum(
                    1 for sym, s, l in self._open_pairs.values()
                    if sym == config.symbol and {s, l} == {active_short, active_long}
                )
                if open_count >= config.max_orders:
                    self._open_tick_counters[monitor_id] = 0
                    continue

                # ── Guard: actual notional from exchange positions ─────────
                order_size_usdt = config.order_size_usdt
                actual_notional = 0.0
                if self._account_worker is not None:
                    try:
                        sym_norm = config.symbol.split(":")[0]
                        all_legs = self._account_worker.read_positions([active_short, active_long])
                        s_legs = [
                            p for p in all_legs
                            if p.exchange_id == active_short
                            and p.symbol.split(":")[0] == sym_norm
                            and p.side == "short"
                        ]
                        actual_notional = float(
                            sum(abs(p.contracts) * p.contract_size * p.entry_price for p in s_legs)
                        )
                    except Exception:
                        logger.debug("read_positions failed during open guard | monitor={}", monitor_id)

                # ── Overflow: actual > target * 1.2 → close excess ────────
                if actual_notional > order_size_usdt * 1.2:
                    excess = actual_notional - order_size_usdt
                    logger.warning(
                        "position overflow | monitor={} actual={:.2f} target={:.2f}",
                        monitor_id, actual_notional, order_size_usdt,
                    )
                    if self._live is not None:
                        try:
                            close_pct = Decimal(str(excess / actual_notional * 100))
                            partial_outcome = await self._live.close_partial(
                                symbol=config.symbol,
                                short_exchange_id=active_short,
                                long_exchange_id=active_long,
                                close_percent=close_pct,
                            )
                            if partial_outcome.status.value not in ("success", "simulated"):
                                logger.warning(
                                    "overflow close_partial status={} → falling back to close_all | monitor={}",
                                    partial_outcome.status.value, monitor_id,
                                )
                                await self._live.close_all(
                                    symbol=config.symbol,
                                    short_exchange_id=active_short,
                                    long_exchange_id=active_long,
                                )
                        except Exception:
                            logger.exception("overflow close failed | monitor={}", monitor_id)
                    self._open_tick_counters[monitor_id] = 0
                    continue

                # ── Guard: position already at / above 95 % of target ─────
                if actual_notional >= order_size_usdt * 0.95:
                    self._open_tick_counters[monitor_id] = 0
                    continue

                # ── Guard: order size below exchange minimum ───────────────
                short_info = self._market_cache.get_market_info(active_short, config.symbol)
                long_info = self._market_cache.get_market_info(active_long, config.symbol)
                min_short = float(getattr(short_info, "min_order_volume_usdt", None) or 0.0)
                min_long = float(getattr(long_info, "min_order_volume_usdt", None) or 0.0)
                if (min_short > 0 and order_size_usdt < min_short) or (min_long > 0 and order_size_usdt < min_long):
                    logger.warning(
                        "order_size_usdt={:.2f} below exchange min (short={:.2f} long={:.2f}) | monitor={}",
                        order_size_usdt, min_short, min_long, monitor_id,
                    )
                    self._open_tick_counters[monitor_id] = 0
                    continue

                cached = self._spread_resolver.entry_spread_sync(config.symbol, active_short, active_long)
                if cached is None or cached[2] >= config.open_spread_pct * 0.8:
                    spread_res = await self._spread_resolver.entry_spread(
                        config.symbol, active_short, active_long, fetch_fresh=True
                    )
                    if spread_res is not None:
                        _, _, entry_spread_pct = spread_res
                        if entry_spread_pct >= config.open_spread_pct:
                            self._open_tick_counters[monitor_id] = self._open_tick_counters.get(monitor_id, 0) + 1
                            if self._open_tick_counters[monitor_id] >= config.open_ticks:
                                logger.info(
                                    "Open trigger | monitor={} sym={} spread={:.3f}% >= {} open_count={}/{}",
                                    monitor_id, config.symbol, entry_spread_pct,
                                    config.open_spread_pct, open_count, config.max_orders,
                                )
                                short_book = self._spread_resolver.top_of_book_sync(active_short, config.symbol)
                                long_book = self._spread_resolver.top_of_book_sync(active_long, config.symbol)
                                sprice = float(short_book.bid) if short_book and short_book.bid else 0.0
                                lprice = float(long_book.ask) if long_book and long_book.ask else 0.0
                                if self._live is not None:
                                    mid_price = (sprice + lprice) / 2 if sprice and lprice else max(sprice, lprice)
                                    outcome = await self._live.open_parallel(
                                        symbol=config.symbol,
                                        short_exchange_id=active_short,
                                        long_exchange_id=active_long,
                                        notional_usdt=Decimal(str(order_size_usdt)),
                                        price=Decimal(str(mid_price)) if mid_price else Decimal("1"),
                                    )
                                    if outcome.status.value not in ("failed", "rolled_back"):
                                        pair_id = outcome.pair_id or uuid.uuid4().hex[:12]
                                        self._open_pairs[pair_id] = (config.symbol, active_short, active_long)
                                elif self._paper is not None:
                                    self._paper.open_pair(
                                        symbol=config.symbol,
                                        short_exchange_id=active_short,
                                        long_exchange_id=active_long,
                                        short_price=sprice,
                                        long_price=lprice,
                                        amount=order_size_usdt,
                                        spread_pct=entry_spread_pct,
                                        strategy_kind="futures_futures",
                                    )
                                    records = self._paper._store.load_all()
                                    last_sell = next(
                                        (r for r in reversed(records)
                                         if r.symbol == config.symbol and r.side == "sell" and r.action == "open"),
                                        None,
                                    )
                                    if last_sell:
                                        self._open_pairs[last_sell.pair_id] = (config.symbol, active_short, active_long)
                                self._open_tick_counters[monitor_id] = 0
                        else:
                            self._open_tick_counters[monitor_id] = 0
            except Exception:
                logger.exception("Error checking open condition | sym={}", config.symbol)

    def _resolve_sides(self, config: MonitorConfig) -> tuple[str, str]:
        if config.side == "long":
            return config.long_exchange, config.short_exchange
        return config.short_exchange, config.long_exchange

    def _log_card_tick(  # noqa: PLR0913
        self,
        *,
        monitor_id: str,
        config: MonitorConfig,
        active_short: str,
        active_long: str,
        ob_short: Any,
        ob_long: Any,
        vwap_short_bid: float | None,
        vwap_long_ask: float | None,
        vwap_short_ask: float | None,
        vwap_long_bid: float | None,
        open_spread: float,
        close_spread: float,
        vwap_open_spread: float,
        vwap_close_spread: float,
        short_balance: float,
        long_balance: float,
        allowed_short: float | None,
        allowed_long: float | None,
        open_orders: int,
    ) -> None:
        """Write per-second card diagnostics to logs/cards/<monitor_id_safe>.log."""
        # Derive a safe filename from monitor_id (replace : and / with _)
        safe_name = monitor_id.replace(":", "_").replace("/", "_")
        card_logger = logger[f"cards/{safe_name}.log"]

        def _levels(levels: Any, n: int = 5) -> str:
            if not levels:
                return "[]"
            parts = [f"{lvl.price:.8g}×{lvl.size:.4g}" for lvl in levels[:n]]
            return "[" + ", ".join(parts) + "]"

        side_mode = config.side
        is_active = config.is_active
        open_thr = config.open_spread_pct
        close_thr = config.close_spread_pct
        order_usdt = config.order_size_usdt
        open_tick_cnt = self._open_tick_counters.get(monitor_id, 0)
        open_needed = config.open_ticks
        close_tick_cnt = max(
            (self._close_tick_counters.get(pid, 0)
             for pid, (sym, s, l) in self._open_pairs.items()
             if f"{sym}:{s}:{l}" == monitor_id),
            default=0,
        )

        card_logger.info(
            "TICK | id={} active={} side={} orders={} | "
            "SHORT({}) bid5={} ask5={} | "
            "LONG({}) bid5={} ask5={} | "
            "balance S={:.2f} L={:.2f} allowed_S={} allowed_L={} | "
            "vwap_entry short_bid={} long_ask={} | "
            "vwap_exit  short_ask={} long_bid={} | "
            "open_spread raw={:.4f}% vwap={:.4f}% thr={:.4f}% tick={}/{} | "
            "close_spread raw={:.4f}% vwap={:.4f}% thr={:.4f}% tick={} | "
            "decision={}",
            monitor_id,
            is_active,
            side_mode,
            open_orders,
            active_short,
            _levels(ob_short.bids if ob_short else None),
            _levels(ob_short.asks if ob_short else None),
            active_long,
            _levels(ob_long.bids if ob_long else None),
            _levels(ob_long.asks if ob_long else None),
            short_balance,
            long_balance,
            f"{allowed_short:.2f}" if allowed_short is not None else "n/a",
            f"{allowed_long:.2f}" if allowed_long is not None else "n/a",
            f"{vwap_short_bid:.8g}" if vwap_short_bid is not None else "n/a",
            f"{vwap_long_ask:.8g}" if vwap_long_ask is not None else "n/a",
            f"{vwap_short_ask:.8g}" if vwap_short_ask is not None else "n/a",
            f"{vwap_long_bid:.8g}" if vwap_long_bid is not None else "n/a",
            open_spread,
            vwap_open_spread,
            open_thr,
            open_tick_cnt,
            open_needed,
            close_spread,
            vwap_close_spread,
            close_thr,
            close_tick_cnt,
            "OPEN_WATCH" if (is_active and vwap_open_spread >= open_thr * 0.8 and open_orders == 0)
            else "CLOSE_WATCH" if (is_active and open_orders > 0 and vwap_close_spread <= close_thr)
            else "IDLE",
        )
