from __future__ import annotations
from arbitrator.config.ui_config_manager import UIConfigManager

import asyncio
import threading
import time
from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING

from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.market_data.screener_stream_worker import ScreenerStreamWorker
from arbitrator.application.trading.auto_trader_base import AutoTraderBase
from arbitrator.application.trading.executable_spread_resolver import ExecutableSpreadResolver
from arbitrator.application.trading.hedged_execution_service import HedgedExecutionService
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.exchange.exchange_gateway import ExchangeGateway
from arbitrator.domain.market.spread_calculator import SpreadCalculator
from arbitrator.domain.market.ticker import Ticker

from .excel_logger import ExcelTradesLogger

if TYPE_CHECKING:
    from arbitrator.application.account.token_identity_service import TokenIdentityService
    from arbitrator.application.strategies.strategy_table_service import StrategyTableService

from .live_trader_logger import (
    _CACHE_MAX_DESYNC_MS,
    LiveTraderLogger,
    _OpenCandidateTrace,
    _OpenCheckResult,
    _OpenCheckStageTrace,
)


class LiveAutoTrader(AutoTraderBase):
    """Auto-trader for live mode: places real orders via HedgedExecutionService.

    Mirrors ScreenerAutoTrader logic (same open/close/validation pass) but:
    - Calls HedgedExecutionService.open / close_all instead of PaperExecutionGateway
    - Recovers open pairs from exchange positions on startup (no local store)
    - Runs on its own asyncio event loop (own thread, like FundingRateWorker)

    Open pair state is keyed by (symbol, short_exchange_id, long_exchange_id).
    On restart the pair set is rebuilt from fetch_open_positions across all
    enabled exchanges — we know short/long exchange by position side:
    short position on exchange A + long position on exchange B = one pair.
    """

    def __init__(
        self,
        settings: Settings,
        screener_worker: ScreenerStreamWorker,
        execution_service: HedgedExecutionService,
        market_cache: MarketDataCacheMemory,
        token_identity: TokenIdentityService | None = None,
        gateways: Mapping[str, ExchangeGateway] | None = None,
        strategy_table_service: StrategyTableService | None = None,
    ) -> None:
        super().__init__(
            settings=settings,
            market_cache=market_cache,
            token_identity=token_identity,
        )
        self._screener = screener_worker
        self._exec = execution_service
        self._gateways: Mapping[str, ExchangeGateway] = gateways or {}
        self._spread_resolver = ExecutableSpreadResolver(settings, market_cache, self._gateways)
        self._strategy_table_service = strategy_table_service
        self._excel_logger = ExcelTradesLogger()
        self._live_logger = LiveTraderLogger(market_cache, self._excel_logger)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task[None] | None = None
        # (symbol, short_ex, long_ex) -> open_since_monotonic
        self._open_pairs: dict[tuple[str, str, str], float] = {}
        # (symbol, short_ex, long_ex) -> consecutive close ticks count
        self._close_confirm: dict[tuple[str, str, str], int] = {}
        # (symbol, short_ex, long_ex) -> entry_spread_pct (for DCA)
        self._entry_spreads: dict[tuple[str, str, str], float] = {}
        # (symbol, short_ex, long_ex) -> DCA layers already added
        self._dca_layers: dict[tuple[str, str, str], int] = {}
        # (symbol, short_ex, long_ex) -> cooldown_until_monotonic (after rollback/fail)
        self._open_cooldown: dict[tuple[str, str, str], float] = {}
        # (symbol, short_ex, long_ex) -> strategy used
        self._pair_strategy: dict[tuple[str, str, str], str] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._thread_main,
            name="live-auto-trader",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "live auto trader started | max_pos={} open_spread={}% close_spread={}%",
            UIConfigManager.get_config().screener_auto_trade_max_positions,
            UIConfigManager.get_config().screener_auto_trade_open_spread_pct,
            UIConfigManager.get_config().screener_auto_trade_close_spread_pct,
        )

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        task = self._main_task
        if loop is not None and task is not None and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ #
    # Thread + async entry
    # ------------------------------------------------------------------ #

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_main())
        except asyncio.CancelledError:
            logger.info("live auto trader stopped")
        except Exception:
            logger.exception("live auto trader crashed")

    async def _async_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._main_task = asyncio.current_task()
        await self._restore_open_pairs()
        interval = UIConfigManager.get_config().screener_auto_trade_check_seconds
        while not self._stop.is_set():
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("live auto trader tick failed")
            try:
                await asyncio.wait_for(
                    asyncio.shield(asyncio.get_event_loop().create_future()),
                    timeout=interval,
                )
            except (TimeoutError, asyncio.CancelledError):
                if self._stop.is_set():
                    raise asyncio.CancelledError
                pass

    # ------------------------------------------------------------------ #
    # Restore open pairs from exchange positions on startup
    # ------------------------------------------------------------------ #

    async def _restore_open_pairs(self) -> None:
        """Rebuild in-memory pair set from live exchange positions.

        Pairs are matched by symbol: a short position on one exchange and a
        long position on another exchange for the same symbol = one open pair.
        Only considers exchanges that HedgedExecutionService has gateways for.
        """
        from arbitrator.domain.account.position_leg import PositionLeg

        positions_by_symbol: dict[str, list[tuple[str, PositionLeg]]] = {}
        for exchange_id, gateway in self._exec._gateways.items():
            try:
                legs = await gateway.fetch_open_positions()
            except Exception:
                logger.exception("live auto trader: failed to fetch positions | ex={}", exchange_id)
                continue
            for leg in legs:
                positions_by_symbol.setdefault(leg.symbol, []).append((exchange_id, leg))

        base_notional = UIConfigManager.get_config().screener_auto_trade_notional_usdt

        for symbol, entries in positions_by_symbol.items():
            short_exs = [(ex, leg) for ex, leg in entries if leg.side == "short"]
            long_exs = [(ex, leg) for ex, leg in entries if leg.side == "long"]
            if not short_exs or not long_exs:
                continue
            short_ex, short_leg = short_exs[0]
            long_ex, long_leg = long_exs[0]
            key = (symbol, short_ex, long_ex)
            self._open_pairs[key] = time.monotonic()
            # Reconstruct entry spread from position entry prices
            if short_leg.entry_price > 0 and long_leg.entry_price > 0:
                entry_spread = (
                    (short_leg.entry_price - long_leg.entry_price) / long_leg.entry_price * 100.0
                )
                self._entry_spreads[key] = entry_spread
            # Determine DCA layers already done by comparing position size to base notional
            position_usdt = (
                abs(short_leg.contracts) * short_leg.contract_size * short_leg.entry_price
            )
            if base_notional > 0 and position_usdt > base_notional * 1.5:
                # Position is bigger than base → at least 1 DCA layer done
                self._dca_layers[key] = max(1, int(position_usdt / base_notional) - 1)
            else:
                self._dca_layers[key] = 0
            logger.info(
                "live auto trader: restored open pair | sym={} short={} long={}"
                " entry_spread={:.3f}% position_usdt={:.1f} dca_layers={}",
                symbol,
                short_ex,
                long_ex,
                self._entry_spreads.get(key, 0.0),
                position_usdt,
                self._dca_layers[key],
            )

        logger.info("live auto trader: restored {} open pairs", len(self._open_pairs))

    # ------------------------------------------------------------------ #
    # Main tick
    # ------------------------------------------------------------------ #

    async def _tick(self) -> None:
        tickers, _symbols, _updates, status, _threshold = self._screener.read_state()
        if status != "Live":
            return

        open_spread_pct = UIConfigManager.get_config().screener_auto_trade_open_spread_pct
        close_spread_pct = UIConfigManager.get_config().screener_auto_trade_close_spread_pct
        max_pos = UIConfigManager.get_config().screener_auto_trade_max_positions

        # --- build ranked candidates: screener spread >= open threshold only ---
        by_symbol: dict[str, dict[str, Ticker]] = {}
        for (exchange_id, symbol), ticker in tickers.items():
            by_symbol.setdefault(symbol, {})[exchange_id] = ticker

        candidates: list[tuple[float, str, str, str, float, float]] = []
        for symbol, per_exchange in by_symbol.items():
            if len(per_exchange) < 2:
                continue
            best = self._spread_resolver.best_entry_pair_sync(symbol, per_exchange)
            if best is None:
                continue
            short_ex, long_ex, short_bid, long_ask, spread = best
            short_ticker = per_exchange.get(short_ex)
            long_ticker = per_exchange.get(long_ex)
            if self._ticker_too_wide(short_ticker) or self._ticker_too_wide(long_ticker):
                continue
            if spread < open_spread_pct:
                continue

            candidates.append((spread, symbol, short_ex, long_ex, short_bid, long_ask))

        candidates.sort(key=lambda c: c[0], reverse=True)

        # --- close pass ---
        to_remove: list[tuple[str, str, str]] = []
        for key, _opened_at in list(self._open_pairs.items()):
            sym, s_ex, l_ex = key

            self._market_cache.clear_executable(s_ex, sym)
            self._market_cache.clear_executable(l_ex, sym)

            s_ticker = tickers.get((s_ex, sym))
            l_ticker = tickers.get((l_ex, sym))
            exit_quotes = await self._spread_resolver.exit_spread(
                sym,
                s_ex,
                l_ex,
                short_ticker=s_ticker,
                long_ticker=l_ticker,
                fetch_fresh=True,
            )
            if exit_quotes is None:
                logger.debug(
                    "live close skipped: no executable bid/ask | sym={} short={} long={}",
                    sym, s_ex, l_ex,
                )
                continue
            short_ask, long_bid, exit_spread = exit_quotes

            desync_ms = self._cache_desync_ms(s_ex, l_ex, sym)
            if desync_ms is None:
                logger.debug(
                    "live close skipped: cache timestamp missing | sym={} short={} long={}",
                    sym, s_ex, l_ex,
                )
                continue
            if desync_ms > _CACHE_MAX_DESYNC_MS:
                logger.debug(
                    "live close skipped: cache desync | sym={} short={} long={} delta_ms={}",
                    sym, s_ex, l_ex, desync_ms,
                )
                continue

            s_recv = self._leg_recv_time_ms(s_ex, sym)
            l_recv = self._leg_recv_time_ms(l_ex, sym)
            pair_strategy = self._pair_strategy.get(key, "futures_futures")
            pair_close_threshold = UIConfigManager.get_config().strategy_close_spread_pct(pair_strategy)
            logger.debug(
                "live close check | sym={} short={} long={} exit_spread={:.4f}% threshold={}%"
                " short_recv_ms={} long_recv_ms={} desync_ms={}",
                sym, s_ex, l_ex, exit_spread, pair_close_threshold,
                s_recv, l_recv, desync_ms,
            )
            if exit_spread > pair_close_threshold:
                self._close_confirm.pop(key, None)
                continue

            # Need 2 consecutive ticks confirming close threshold
            count = self._close_confirm.get(key, 0) + 1
            self._close_confirm[key] = count
            if count < 2:
                logger.debug(
                    "live close check confirm {}/2 | sym={} short={} long={} exit_spread={:.4f}%",
                    count, sym, s_ex, l_ex, exit_spread,
                )
                continue

            self._live_logger.log_close_decision(
                sym, s_ex, l_ex, exit_spread, pair_close_threshold,
                short_ask, long_bid, s_recv, l_recv, desync_ms, confirm_count=count,
            )
            logger.info(
                "live auto close | sym={} short={} long={} exit_spread={:.4f}% threshold={}%"
                " short_ask={} long_bid={}",
                sym,
                s_ex,
                l_ex,
                exit_spread,
                close_spread_pct,
                short_ask,
                long_bid,
            )
            logger["trades/live_trades.log"].info(
                "CLOSE | trigger=spread sym={} short={} long={}"
                " exit_spread={:.4f}% threshold={}% short_ask={} long_bid={}",
                sym,
                s_ex,
                l_ex,
                exit_spread,
                close_spread_pct,
                short_ask,
                long_bid,
            )
            strategy_for_close = self._pair_strategy.get(key, "futures_futures")
            outcome = await self._exec.close_all(
                symbol=sym,
                short_exchange_id=s_ex,
                long_exchange_id=l_ex,
                strategy_kind=strategy_for_close,
            )
            logger.info(
                "live auto close result | sym={} status={} imbalance={}",
                sym,
                outcome.status.value,
                outcome.imbalance_pct,
            )
            logger["trades/live_trades.log"].info(
                "CLOSE_RESULT | sym={} status={} short_ex={} long_ex={}"
                " short_filled={} short_order={} long_filled={} long_order={} imbalance={}",
                sym,
                outcome.status.value,
                s_ex,
                l_ex,
                outcome.short_leg.filled_amount if outcome.short_leg else "n/a",
                outcome.short_leg.order_id if outcome.short_leg else "n/a",
                outcome.long_leg.filled_amount if outcome.long_leg else "n/a",
                outcome.long_leg.order_id if outcome.long_leg else "n/a",
                outcome.imbalance_pct,
            )
            to_remove.append(key)

        for key in to_remove:
            self._open_pairs.pop(key, None)
            self._close_confirm.pop(key, None)
            self._entry_spreads.pop(key, None)
            self._dca_layers.pop(key, None)

        # --- DCA pass: accumulate into existing positions if spread widened ---
        await self._dca_pass(tickers)

        # --- open pass ---
        open_count = len(self._open_pairs)
        already_open_symbols = {sym for (sym, _s, _l) in self._open_pairs}
        tick_ms = int(time.time() * 1000)
        notional_floor = UIConfigManager.get_config().screener_auto_trade_notional_usdt

        if candidates:
            self._live_logger.log_open_candidates_header(
                tick_ms,
                threshold_pct=open_spread_pct,
                notional_floor=notional_floor,
                open_count=open_count,
                max_pos=max_pos,
                candidate_count=len(candidates),
            )

        for rank, (_net, symbol, short_ex, long_ex, short_bid, long_ask) in enumerate(
            candidates, start=1,
        ):
            entry_spread = SpreadCalculator.entry_spread_pct(short_bid, long_ask)
            if entry_spread is None:
                continue
            cache_spread = entry_spread if entry_spread is not None else 0.0
            trace = _OpenCandidateTrace(
                tick_ms=tick_ms,
                rank=rank,
                symbol=symbol,
                short_ex=short_ex,
                long_ex=long_ex,
                threshold_pct=open_spread_pct,
                notional_floor=notional_floor,
                cache_short_bid=short_bid,
                cache_long_ask=long_ask,
                cache_spread_pct=cache_spread,
            )
            trace.mark_ok("pool")

            if open_count >= max_pos:
                trace.reject("max_pos", f"відкрито {open_count}/{max_pos}")
                self._live_logger.log_open_candidate(trace)
                continue
            trace.mark_ok("max_pos")

            if symbol in already_open_symbols:
                trace.reject("dup_sym", f"символ {symbol} вже в портфелі")
                self._live_logger.log_open_candidate(trace)
                continue
            trace.mark_ok("dup_sym")

            _ck = (symbol, short_ex, long_ex)
            cooldown_left = self._open_cooldown.get(_ck, 0.0) - time.monotonic()
            if cooldown_left > 0:
                trace.reject("cooldown", f"cooldown {cooldown_left:.0f}s після фейлу")
                self._live_logger.log_open_candidate(trace)
                continue
            trace.mark_ok("cooldown")

            if short_ex not in self._exec._gateways or long_ex not in self._exec._gateways:
                trace.reject("gateway", "немає gateway/credentials для біржі")
                self._live_logger.log_open_candidate(trace)
                continue
            trace.mark_ok("gateway")
            trace.mark_ok("cache_thr")

            check1_trace = _OpenCheckStageTrace()
            check1, reason1 = await self._run_open_check(
                1, symbol, short_ex, long_ex,
                open_spread_pct=open_spread_pct,
                candidate_spread=entry_spread,
                tickers=tickers,
                stage_trace=check1_trace,
            )
            trace.check1 = check1_trace
            if check1 is None:
                trace.reject("check1", reason1 or "unknown")
                self._live_logger.log_open_candidate(trace)
                logger.debug(
                    "live open skipped check1 | sym={} short={} long={} reason={}",
                    symbol, short_ex, long_ex, reason1,
                )
                continue
            trace.mark_ok("check1")

            check2_trace = _OpenCheckStageTrace()
            check2, reason2 = await self._run_open_check(
                2, symbol, short_ex, long_ex,
                open_spread_pct=open_spread_pct,
                candidate_spread=entry_spread,
                tickers=tickers,
                stage_trace=check2_trace,
            )
            trace.check2 = check2_trace
            if check2 is None:
                trace.reject("check2", reason2 or "unknown")
                self._live_logger.log_open_candidate(trace)
                logger.warning(
                    "live open skipped check2 | sym={} short={} long={} reason={}"
                    " check1_spread={:.4f}%",
                    symbol, short_ex, long_ex, reason2, check1.fresh_spread,
                )
                continue
            trace.mark_ok("check2")

            await self._set_cross_margin(symbol, short_ex)
            await self._set_cross_margin(symbol, long_ex)

            notional = Decimal(str(check2.notional_float))
            price = Decimal(str(check2.fresh_bid))
            trace.mark_ok("execute")
            trace.final_outcome = "OPEN"
            self._live_logger.log_open_candidate(trace)
            logger.info(
                "live auto open | sym={} short={} long={} spread={:.4f}% notional={}"
                " short_bid={} long_ask={} candidate_spread={:.4f}% threshold={}%"
                " estimated_fill_spread={:.4f}% strategy={}"
                " check1_spread={:.4f}% check2_spread={:.4f}% desync_ms={}",
                symbol,
                short_ex,
                long_ex,
                check2.fresh_spread,
                notional,
                check2.fresh_bid,
                check2.fresh_ask,
                entry_spread,
                open_spread_pct,
                check2.estimated_spread,
                check2.strategy_kind,
                check1.fresh_spread,
                check2.fresh_spread,
                abs(check2.short_recv_ms - check2.long_recv_ms),
            )
            logger["trades/live_trades.log"].info(
                "OPEN | trigger=spread sym={} short={} long={}"
                " check1_spread={:.4f}% check2_spread={:.4f}% candidate_spread={:.4f}%"
                " threshold={}% strategy_threshold={}% short_bid={} long_ask={}"
                " estimated_fill_spread={:.4f}% notional={} strategy={}"
                " short_recv_ms={} long_recv_ms={} desync_ms={} max_desync_ms={}",
                symbol,
                short_ex,
                long_ex,
                check1.fresh_spread,
                check2.fresh_spread,
                entry_spread,
                open_spread_pct,
                check2.strategy_open_threshold,
                check2.fresh_bid,
                check2.fresh_ask,
                check2.estimated_spread,
                notional,
                check2.strategy_kind,
                check2.short_recv_ms,
                check2.long_recv_ms,
                abs(check2.short_recv_ms - check2.long_recv_ms),
                _CACHE_MAX_DESYNC_MS,
            )

            outcome = await self._exec.open(
                symbol=symbol,
                short_exchange_id=short_ex,
                long_exchange_id=long_ex,
                notional_usdt=notional,
                price=price,
                strategy_kind=check2.strategy_kind,
            )
            # Clear cache after open so next close pass uses only fresh data
            self._market_cache.clear_symbol(short_ex, symbol)
            self._market_cache.clear_symbol(long_ex, symbol)
            logger.info(
                "live auto open result | sym={} status={} imbalance={}",
                symbol,
                outcome.status.value,
                outcome.imbalance_pct,
            )
            logger["trades/live_trades.log"].info(
                "OPEN_RESULT | sym={} status={} short_ex={} long_ex={}"
                " short_requested={} short_filled={} short_order={}"
                " long_requested={} long_filled={} long_order={}"
                " imbalance={} message={}",
                symbol,
                outcome.status.value,
                short_ex,
                long_ex,
                outcome.short_leg.requested_amount if outcome.short_leg else "n/a",
                outcome.short_leg.filled_amount if outcome.short_leg else "n/a",
                outcome.short_leg.order_id if outcome.short_leg else "n/a",
                outcome.long_leg.requested_amount if outcome.long_leg else "n/a",
                outcome.long_leg.filled_amount if outcome.long_leg else "n/a",
                outcome.long_leg.order_id if outcome.long_leg else "n/a",
                outcome.imbalance_pct,
                outcome.message,
            )
            key = (symbol, short_ex, long_ex)
            if outcome.status.value in ("success", "partial"):
                self._open_pairs[key] = time.monotonic()
                self._entry_spreads[key] = check2.fresh_spread
                self._dca_layers[key] = 0
                self._pair_strategy[key] = check2.strategy_kind
                already_open_symbols.add(symbol)
                open_count += 1
                self._live_logger.log_open_candidate_result(trace, outcome.status.value, outcome.message)
                # Post-fill spread guard: verify actual spread from positions
                await self._post_fill_guard(key)
            else:
                self._live_logger.log_open_candidate_result(trace, outcome.status.value, outcome.message)
                # Prevent immediate re-entry after rollback/fail on same pair
                self._open_cooldown[key] = time.monotonic() + UIConfigManager.get_config().open_fail_cooldown_sec

    # ------------------------------------------------------------------ #
    # Post-fill guard: close if real spread < threshold
    # ------------------------------------------------------------------ #

    async def _post_fill_guard(self, key: tuple[str, str, str]) -> None:
        """Check actual entry spread from position entry prices right after fill.

        If real spread < live_auto_trade_post_fill_min_spread_pct → close immediately.
        """
        symbol, short_ex, long_ex = key
        min_spread = UIConfigManager.get_config().live_auto_trade_post_fill_min_spread_pct
        short_gw = self._exec._gateways.get(short_ex)
        long_gw = self._exec._gateways.get(long_ex)
        if short_gw is None or long_gw is None:
            return
        try:
            short_legs = await short_gw.fetch_open_positions()
            long_legs = await long_gw.fetch_open_positions()
        except Exception:
            logger.exception("post_fill_guard: fetch_positions failed | sym={}", symbol)
            return
        short_leg = next((l for l in short_legs if l.symbol == symbol), None)
        long_leg = next((l for l in long_legs if l.symbol == symbol), None)
        if short_leg is None or long_leg is None:
            return
        if long_leg.entry_price <= 0:
            return
        actual_spread = (
            (short_leg.entry_price - long_leg.entry_price) / long_leg.entry_price * 100.0
        )
        # Update stored entry spread with the real value
        self._entry_spreads[key] = actual_spread
        if actual_spread < min_spread:
            logger.warning(
                "post_fill_guard: actual spread {:.3f}% < {:.1f}% — closing immediately | "
                "sym={} short={} long={} short_entry={} long_entry={}",
                actual_spread,
                min_spread,
                symbol,
                short_ex,
                long_ex,
                short_leg.entry_price,
                long_leg.entry_price,
            )
            logger["trades/live_trades.log"].warning(
                "POST_FILL_CLOSE | sym={} actual_spread={:.3f}% min={:.1f}%"
                " short_entry={} long_entry={}",
                symbol,
                actual_spread,
                min_spread,
                short_leg.entry_price,
                long_leg.entry_price,
            )
            await self._exec.close_all(
                symbol=symbol,
                short_exchange_id=short_ex,
                long_exchange_id=long_ex,
                strategy_kind=self._pair_strategy.get(key, "futures_futures"),
            )
            self._open_pairs.pop(key, None)
            self._entry_spreads.pop(key, None)
            self._dca_layers.pop(key, None)

    # ------------------------------------------------------------------ #
    # DCA pass: accumulate when spread widens
    # ------------------------------------------------------------------ #

    async def _dca_pass(
        self,
        tickers: dict[tuple[str, str], Ticker],
    ) -> None:
        """For each open pair, check if spread widened enough to DCA (add 2x volume)."""
        dca_step = UIConfigManager.get_config().live_auto_trade_dca_spread_step_pct
        max_layers = UIConfigManager.get_config().live_auto_trade_dca_max_layers
        min_liq_dist = UIConfigManager.get_config().live_auto_trade_dca_min_liq_distance_pct
        funding_skip_sec = UIConfigManager.get_config().live_auto_trade_dca_funding_skip_seconds

        for key in list(self._open_pairs.keys()):
            symbol, short_ex, long_ex = key
            layers = self._dca_layers.get(key, 0)
            if layers >= max_layers:
                continue
            entry_spread = self._entry_spreads.get(key)
            if entry_spread is None:
                continue
            cached = self._spread_resolver.entry_spread_sync(
                symbol,
                short_ex,
                long_ex,
                short_ticker=tickers.get((short_ex, symbol)),
                long_ticker=tickers.get((long_ex, symbol)),
            )
            if cached is None:
                continue
            _bid, _ask, current_spread = cached
            required_spread = entry_spread + dca_step
            if current_spread < required_spread:
                continue
            fresh = await self._spread_resolver.entry_spread_for_open(
                symbol,
                short_ex,
                long_ex,
                short_ticker=tickers.get((short_ex, symbol)),
                long_ticker=tickers.get((long_ex, symbol)),
            )
            if fresh is None:
                continue
            _bid, _ask, current_spread = fresh
            if current_spread < required_spread:
                continue
            # Notional for DCA = 2x base notional
            notional_float = self._resolve_min_notional(symbol, short_ex, long_ex, _bid, _ask)
            if notional_float is None:
                continue
            dca_notional = notional_float * 2.0
            # Pre-trade slippage estimation for DCA volume
            estimated = self._estimate_spread_after_fill(symbol, short_ex, long_ex, dca_notional)
            if (
                estimated is not None
                and estimated < UIConfigManager.get_config().screener_auto_trade_open_spread_pct
            ):
                logger.debug(
                    "DCA skipped: estimated fill spread too low | sym={} est={:.3f}%",
                    symbol,
                    estimated,
                )
                continue
            await self._ensure_order_books_cached(
                symbol, short_ex, long_ex, tickers=tickers,
            )
            depth_rejection = self._check_order_book_depth(symbol, short_ex, long_ex, dca_notional, fail_on_missing_book=True)
            if depth_rejection is not None:
                logger.debug("DCA skipped: {} | sym={}", depth_rejection, symbol)
                continue
            # Liquidation distance check
            if not await self._liq_distance_ok(symbol, short_ex, long_ex, min_liq_dist):
                logger.debug("DCA skipped: too close to liquidation | sym={}", symbol)
                continue
            # Funding check: skip if next funding within threshold
            if self._funding_too_close(symbol, short_ex, long_ex, funding_skip_sec):
                logger.debug("DCA skipped: funding too close | sym={}", symbol)
                continue
            # Execute DCA
            price = Decimal(str(_bid))
            notional = Decimal(str(dca_notional))
            logger.info(
                "DCA accumulate | sym={} short={} long={} current_spread={:.3f}%"
                " entry_spread={:.3f}% dca_notional={} layer={}",
                symbol,
                short_ex,
                long_ex,
                current_spread,
                entry_spread,
                dca_notional,
                layers + 1,
            )
            logger["trades/open_candidates.log"].info(
                "DCA | sym={} short={} long={} current_spread={:.3f}%"
                " entry_spread={:.3f}% required={:.3f}% notional={} layer={}",
                symbol,
                short_ex,
                long_ex,
                current_spread,
                entry_spread,
                required_spread,
                dca_notional,
                layers + 1,
            )
            dca_strategy = self._pair_strategy.get(key, "futures_futures")
            outcome = await self._exec.accumulate(
                symbol=symbol,
                short_exchange_id=short_ex,
                long_exchange_id=long_ex,
                notional_usdt=notional,
                price=price,
                strategy_kind=dca_strategy,
            )
            if outcome.status.value in ("success", "partial"):
                self._dca_layers[key] = layers + 1
                # Update entry spread to average (weighted by layers)
                total_layers = layers + 2  # original + all DCA layers
                self._entry_spreads[key] = (
                    entry_spread * (total_layers - 1) + current_spread
                ) / total_layers
                logger.info(
                    "DCA result | sym={} status={} new_avg_spread={:.3f}%",
                    symbol,
                    outcome.status.value,
                    self._entry_spreads[key],
                )
            else:
                logger.warning(
                    "DCA failed | sym={} status={} message={}",
                    symbol,
                    outcome.status.value,
                    outcome.message,
                )

    async def _liq_distance_ok(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        min_pct: float,
    ) -> bool:
        """Return True if both legs are > min_pct away from estimated liquidation."""
        leverage = float(UIConfigManager.get_config().opp_default_leverage)
        for exchange_id in (short_ex, long_ex):
            gw = self._exec._gateways.get(exchange_id)
            if gw is None:
                return False
            try:
                legs = await gw.fetch_open_positions()
            except Exception:
                return False
            leg = next((l for l in legs if l.symbol == symbol), None)
            if leg is None:
                continue
            entry = float(leg.entry_price)
            mark = float(leg.mark_price or 0.0)
            if entry <= 0 or mark <= 0:
                continue
            # Approximate liquidation distance
            buffer = 1.0 / leverage
            liq = entry * (1.0 + buffer) if leg.side == "short" else entry * (1.0 - buffer)
            distance = abs(liq - mark) / mark * 100.0
            if distance < min_pct:
                return False
        return True

    def _funding_too_close(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        threshold_seconds: float,
    ) -> bool:
        """Return True if next funding on either leg is within threshold_seconds."""
        now_ms = int(time.time() * 1000)
        threshold_ms = int(threshold_seconds * 1000)
        for exchange_id in (short_ex, long_ex):
            funding = self._market_cache.get_funding(exchange_id, symbol)
            if funding is None:
                continue
            if funding.next_settlement_ms is not None:
                time_to_funding = funding.next_settlement_ms - now_ms
                if 0 < time_to_funding < threshold_ms:
                    return True
            # Also check if funding rate is critically adverse
            if funding.rate is not None and abs(float(funding.rate)) > 0.01:
                return True
        return False

    # ------------------------------------------------------------------ #
    # Open check: clear cache, fresh books, dual verification
    # ------------------------------------------------------------------ #

    async def _run_open_check(
        self,
        check_no: int,
        symbol: str,
        short_ex: str,
        long_ex: str,
        *,
        open_spread_pct: float,
        candidate_spread: float,
        tickers: Mapping[tuple[str, str], Ticker],
        stage_trace: _OpenCheckStageTrace | None = None,
    ) -> tuple[_OpenCheckResult | None, str | None]:
        self._market_cache.clear_executable(short_ex, symbol)
        self._market_cache.clear_executable(long_ex, symbol)

        short_ticker = tickers.get((short_ex, symbol))
        long_ticker = tickers.get((long_ex, symbol))
        fresh = await self._spread_resolver.entry_spread(
            symbol,
            short_ex,
            long_ex,
            short_ticker=short_ticker,
            long_ticker=long_ticker,
            fetch_fresh=True,
        )
        if fresh is None:
            reason = "no_executable_bid_ask"
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=reason,
                candidate_spread=candidate_spread, open_spread_pct=open_spread_pct,
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=reason,
            )
            return None, reason

        fresh_bid, fresh_ask, fresh_spread = fresh
        desync_ms = self._cache_desync_ms(short_ex, long_ex, symbol)
        if desync_ms is None:
            reason = "cache_timestamp_missing"
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=reason,
                candidate_spread=candidate_spread, open_spread_pct=open_spread_pct,
                fresh_spread=fresh_spread, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=reason, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                fresh_spread=fresh_spread,
            )
            return None, reason
        if desync_ms > _CACHE_MAX_DESYNC_MS:
            reason = f"cache_desync:{desync_ms}"
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=reason,
                candidate_spread=candidate_spread, open_spread_pct=open_spread_pct,
                fresh_spread=fresh_spread, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                short_recv_ms=self._leg_recv_time_ms(short_ex, symbol),
                long_recv_ms=self._leg_recv_time_ms(long_ex, symbol),
                desync_ms=desync_ms,
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=reason, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                fresh_spread=fresh_spread, desync_ms=desync_ms,
            )
            return None, reason

        short_recv = self._leg_recv_time_ms(short_ex, symbol)
        long_recv = self._leg_recv_time_ms(long_ex, symbol)
        if short_recv is None or long_recv is None:
            reason = "cache_timestamp_missing"
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=reason,
                candidate_spread=candidate_spread, open_spread_pct=open_spread_pct,
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=reason, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                fresh_spread=fresh_spread,
            )
            return None, reason

        if fresh_spread < open_spread_pct:
            reason = f"spread_below_threshold:{fresh_spread:.4f}<{open_spread_pct}"
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=reason,
                candidate_spread=candidate_spread, open_spread_pct=open_spread_pct,
                fresh_spread=fresh_spread, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                short_recv_ms=short_recv, long_recv_ms=long_recv, desync_ms=desync_ms,
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=reason, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                fresh_spread=fresh_spread, desync_ms=desync_ms,
            )
            return None, reason
        if fresh_spread > UIConfigManager.get_config().anomaly_max_spread_pct:
            reason = f"anomaly_spread:{fresh_spread:.1f}"
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=reason,
                candidate_spread=candidate_spread, open_spread_pct=open_spread_pct,
                fresh_spread=fresh_spread, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                short_recv_ms=short_recv, long_recv_ms=long_recv, desync_ms=desync_ms,
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=reason, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                fresh_spread=fresh_spread, desync_ms=desync_ms,
            )
            return None, reason

        notional_float = self._resolve_min_notional(
            symbol, short_ex, long_ex, fresh_bid, fresh_ask,
        )
        if notional_float is None:
            reason = "market_info_missing"
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=reason,
                candidate_spread=candidate_spread, open_spread_pct=open_spread_pct,
                fresh_spread=fresh_spread,
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=reason, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                fresh_spread=fresh_spread,
            )
            return None, reason

        # Check funding risk: avoid opening if funding is imminent and potentially adverse
        funding_skip_sec = UIConfigManager.get_config().live_auto_trade_dca_funding_skip_seconds
        if self._funding_too_close(symbol, short_ex, long_ex, funding_skip_sec):
            reason = "funding_too_close"
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=reason,
                candidate_spread=candidate_spread, open_spread_pct=open_spread_pct,
                fresh_spread=fresh_spread, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                notional=notional_float, short_recv_ms=short_recv, long_recv_ms=long_recv,
                desync_ms=desync_ms,
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=reason, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                fresh_spread=fresh_spread, notional=notional_float, desync_ms=desync_ms,
            )
            return None, reason

        rejection = self._validate_cross_pair(
            symbol, short_ex, long_ex, notional_float, tickers_snapshot=tickers, fail_on_missing_book=True
        )
        if rejection is not None:
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=rejection,
                candidate_spread=candidate_spread, open_spread_pct=open_spread_pct,
                fresh_spread=fresh_spread, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                notional=notional_float, short_recv_ms=short_recv, long_recv_ms=long_recv,
                desync_ms=desync_ms,
                detail=self._open_skip_detail(
                    rejection, symbol, short_ex, long_ex, notional_float, tickers,
                ),
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=rejection, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                fresh_spread=fresh_spread, notional=notional_float, desync_ms=desync_ms,
            )
            return None, rejection

        estimated_spread = self._estimate_spread_after_fill(
            symbol, short_ex, long_ex, notional_float,
        )
        if estimated_spread is None:
            reason = "estimated_fill_unavailable"
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=reason,
                candidate_spread=candidate_spread, open_spread_pct=open_spread_pct,
                fresh_spread=fresh_spread, notional=notional_float,
                short_recv_ms=short_recv, long_recv_ms=long_recv, desync_ms=desync_ms,
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=reason, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                fresh_spread=fresh_spread, notional=notional_float, desync_ms=desync_ms,
            )
            return None, reason
        if estimated_spread < open_spread_pct:
            reason = f"estimated_fill_below_threshold:{estimated_spread:.4f}"
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=reason,
                candidate_spread=candidate_spread, open_spread_pct=open_spread_pct,
                fresh_spread=fresh_spread, estimated_spread=estimated_spread,
                notional=notional_float, short_recv_ms=short_recv, long_recv_ms=long_recv,
                desync_ms=desync_ms,
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=reason, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                fresh_spread=fresh_spread, estimated_spread=estimated_spread,
                notional=notional_float, desync_ms=desync_ms,
            )
            return None, reason

        strategy_kind = self._resolve_strategy_kind(symbol)
        if not UIConfigManager.get_config().is_strategy_allowed(strategy_kind):
            reason = f"strategy_not_allowed:{strategy_kind}"
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=reason,
                candidate_spread=candidate_spread, strategy=strategy_kind,
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=reason, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                fresh_spread=fresh_spread, estimated_spread=estimated_spread,
                notional=notional_float, desync_ms=desync_ms, strategy=strategy_kind,
            )
            return None, reason

        strategy_open_threshold = UIConfigManager.get_config().strategy_open_spread_pct(strategy_kind)
        if fresh_spread < strategy_open_threshold:
            reason = f"below_strategy_threshold:{fresh_spread:.4f}<{strategy_open_threshold}"
            self._live_logger.log_open_check(
                check_no, symbol, short_ex, long_ex, reason=reason,
                candidate_spread=candidate_spread, fresh_spread=fresh_spread,
                strategy=strategy_kind, strategy_threshold=strategy_open_threshold,
                short_recv_ms=short_recv, long_recv_ms=long_recv, desync_ms=desync_ms,
            )
            self._live_logger.stamp_check_trace(
                stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
                fail_reason=reason, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
                fresh_spread=fresh_spread, estimated_spread=estimated_spread,
                notional=notional_float, desync_ms=desync_ms, strategy=strategy_kind,
                strategy_threshold=strategy_open_threshold,
            )
            return None, reason

        result = _OpenCheckResult(
            fresh_bid=fresh_bid,
            fresh_ask=fresh_ask,
            fresh_spread=fresh_spread,
            estimated_spread=estimated_spread,
            notional_float=notional_float,
            strategy_kind=strategy_kind,
            strategy_open_threshold=strategy_open_threshold,
            short_recv_ms=short_recv,
            long_recv_ms=long_recv,
        )
        self._live_logger.log_open_check(
            check_no, symbol, short_ex, long_ex, reason="pass",
            candidate_spread=candidate_spread, open_spread_pct=open_spread_pct,
            fresh_spread=fresh_spread, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
            estimated_spread=estimated_spread, notional=notional_float,
            strategy=strategy_kind, strategy_threshold=strategy_open_threshold,
            short_recv_ms=short_recv, long_recv_ms=long_recv, desync_ms=desync_ms,
        )
        self._live_logger.stamp_check_trace(
            stage_trace, symbol=symbol, short_ex=short_ex, long_ex=long_ex,
            passed=True, fresh_bid=fresh_bid, fresh_ask=fresh_ask,
            fresh_spread=fresh_spread, estimated_spread=estimated_spread,
            notional=notional_float, desync_ms=desync_ms, strategy=strategy_kind,
            strategy_threshold=strategy_open_threshold,
        )
        return result, None

    def _resolve_strategy_kind(self, symbol: str) -> str:
        if self._strategy_table_service is None:
            return "futures_futures"
        tables = self._strategy_table_service.read_tables()
        table = tables.get(symbol)
        if table is not None and table.best_strategy_id is not None:
            return table.best_strategy_id.value
        return "futures_futures"

    def _leg_recv_time_ms(self, exchange_id: str, symbol: str) -> int | None:
        book = self._market_cache.get_order_book(exchange_id, symbol)
        if book is not None and book.timestamp_ms is not None:
            return book.timestamp_ms
        quote = self._market_cache.get_quote(exchange_id, symbol, "futures")
        if quote is not None:
            return quote.recv_time_ms
        return None

    def _cache_desync_ms(self, short_ex: str, long_ex: str, symbol: str) -> int | None:
        s_ms = self._leg_recv_time_ms(short_ex, symbol)
        l_ms = self._leg_recv_time_ms(long_ex, symbol)
        if s_ms is None or l_ms is None:
            return None
        return abs(s_ms - l_ms)

    async def _set_cross_margin(self, symbol: str, exchange_id: str) -> None:
        gateway = self._exec._gateways.get(exchange_id)
        if gateway is None:
            return
        try:
            await gateway.set_margin_mode(symbol, "cross")
        except Exception:
            logger.exception(
                "set_margin_mode failed (non-fatal) | ex={} sym={}", exchange_id, symbol
            )

    def _ticker_too_wide(self, ticker: Ticker | None) -> bool:
        """Reject tickers where the exchange's own bid-ask spread indicates illiquidity.

        Returns False when ticker is None or bid/ask absent — resolver fetches books.
        """
        if ticker is None:
            return False
        if ticker.bid and ticker.ask and ticker.ask > 0.0:
            inner_spread = (ticker.ask - ticker.bid) / ticker.ask * 100.0
            return inner_spread > UIConfigManager.get_config().ticker_max_inner_spread_pct
        return False

    def _estimate_fill_price(
        self,
        exchange_id: str,
        symbol: str,
        side: str,
        notional_usdt: float,
    ) -> float | None:
        """Estimate the volume-weighted average fill price from cached order book.

        side='buy' walks asks, side='sell' walks bids.
        Returns None if book is absent or insufficient depth.
        """
        book = self._market_cache.get_order_book(exchange_id, symbol)
        if book is None:
            return None
        levels = book.asks if side == "buy" else book.bids
        if not levels:
            return None
        remaining = notional_usdt
        filled_value = 0.0
        filled_qty = 0.0
        for level in levels:
            level_usdt = level.price * level.size
            take = min(remaining, level_usdt)
            qty = take / level.price
            filled_value += take
            filled_qty += qty
            remaining -= take
            if remaining <= 0:
                break
        if filled_qty <= 0 or remaining > 0:
            return None
        return filled_value / filled_qty

    def _estimate_spread_after_fill(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        notional_usdt: float,
    ) -> float | None:
        """Estimate the actual spread after market orders fill on both sides.

        Short leg sells on short_ex (fills into bids), long leg buys on long_ex (fills into asks).
        """
        short_fill = self._estimate_fill_price(short_ex, symbol, "sell", notional_usdt)
        long_fill = self._estimate_fill_price(long_ex, symbol, "buy", notional_usdt)
        if short_fill is None or long_fill is None or long_fill <= 0:
            return None
        return SpreadCalculator.entry_spread_pct(short_fill, long_fill)

    def _alternate_entry_pairs(
        self,
        symbol: str,
        *,
        per_exchange: Mapping[str, Ticker],
    ) -> str:
        """Ranked alternative short/long pairs for logging (best pair already failed)."""
        if len(per_exchange) < 2 or self._spread_resolver is None:
            return ""
        bid_by: dict[str, float] = {}
        ask_by: dict[str, float] = {}
        for exchange_id, ticker in per_exchange.items():
            top = self._spread_resolver.top_of_book_sync(exchange_id, symbol, ticker)
            if top is None:
                continue
            bid_by[exchange_id] = top.bid
            ask_by[exchange_id] = top.ask
        pairs: list[tuple[float, str, str]] = []
        for short_ex, short_bid in bid_by.items():
            for long_ex, long_ask in ask_by.items():
                if short_ex == long_ex:
                    continue
                spread = SpreadCalculator.entry_spread_pct(short_bid, long_ask)
                if spread is None:
                    continue
                pairs.append((spread, short_ex, long_ex))
        pairs.sort(key=lambda item: item[0], reverse=True)
        return ";".join(f"{s:.2f}%:{sh}/{lo}" for s, sh, lo in pairs[1:4])

    def _open_skip_detail(
        self,
        rejection: str,
        symbol: str,
        short_ex: str,
        long_ex: str,
        notional_usdt: float,
        tickers: Mapping[tuple[str, str], Ticker],
    ) -> str:
        if rejection.startswith("no_order_book:"):
            exchange_id = rejection.split(":", 1)[1]
            ticker = tickers.get((exchange_id, symbol))
            has_top = self._spread_resolver.top_of_book_sync(exchange_id, symbol, ticker) is not None
            book_stream = exchange_id in self._settings.screener_book_stream_exchanges
            return (
                f"depth check needs cached order book on {exchange_id}; "
                f"top_of_book={'yes' if has_top else 'no'} "
                f"book_ws_stream={'yes' if book_stream else 'no'} "
                f"required_depth={notional_usdt * 2.0:.0f}USDT "
                f"(ticker bid/ask alone is not enough for depth validation)"
            )
        if rejection.startswith("insufficient_ask_depth:") or rejection.startswith(
            "insufficient_bid_depth:"
        ):
            return f"order book too thin for notional={notional_usdt:.0f}USDT (need 2x within 0.4%)"
        if rejection.startswith("market_info_missing:"):
            return "exchange market limits not loaded yet; will retry next tick"
        if rejection.startswith("below_min_notional:"):
            return f"resolved notional {notional_usdt:.2f} USDT below exchange minimum"
        return "only best spread pair per symbol is attempted each tick; see alt_pairs for others"


    def _validate_cross_pair(
        self,
        symbol: str,
        exchange_a: str,
        exchange_b: str,
        notional_usdt: float,
        *,
        tickers_snapshot: Mapping[tuple[str, str], Ticker] | None = None,
        **kwargs,
    ) -> str | None:
        if "tickers" in kwargs and tickers_snapshot is None:
            tickers_snapshot = kwargs.pop("tickers")
        kwargs.pop("fail_on_missing_book", None)
        return super()._validate_cross_pair(
            symbol,
            exchange_a,
            exchange_b,
            notional_usdt,
            tickers_snapshot=tickers_snapshot,
            fail_on_missing_book=True,
            **kwargs,
        )

    def _check_order_book_depth(
        self,
        symbol: str,
        exchange_a: str,
        exchange_b: str,
        notional_usdt: float,
        *,
        tickers: Mapping[tuple[str, str], Ticker] | None = None,
        **kwargs,
    ) -> str | None:
        kwargs.pop("fail_on_missing_book", None)
        return super()._check_order_book_depth(
            symbol,
            exchange_a,
            exchange_b,
            notional_usdt,
            fail_on_missing_book=True,
            **kwargs,
        )

    async def _ensure_order_books_cached(
        self,
        symbol: str,
        exchange_a: str,
        exchange_b: str,
        *,
        tickers: Mapping[tuple[str, str], Ticker] | None = None,
    ) -> None:
        for exchange_id in (exchange_a, exchange_b):
            if self._market_cache.get_order_book(exchange_id, symbol) is not None:
                continue
            await self._spread_resolver.top_of_book(
                exchange_id,
                symbol,
                tickers.get((exchange_id, symbol)) if tickers else None,
                fetch_fresh=True,
            )

