from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING

from arbitrator.application.hedged_execution_service import HedgedExecutionService
from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.screener_auto_trader import ScreenerAutoTrader
from arbitrator.application.screener_stream_worker import ScreenerStreamWorker
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.exchange_gateway import ExchangeGateway
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.symbol_market_info import SymbolMarketInfo
from arbitrator.domain.ticker import Ticker

if TYPE_CHECKING:
    from arbitrator.application.strategy_table_service import StrategyTableService
    from arbitrator.application.token_identity_service import TokenIdentityService


class LiveAutoTrader:
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
        token_identity: "TokenIdentityService | None" = None,
        gateways: Mapping[str, ExchangeGateway] | None = None,
        strategy_table_service: "StrategyTableService | None" = None,
    ) -> None:
        self._settings = settings
        self._screener = screener_worker
        self._exec = execution_service
        self._cache = market_cache
        self._token_identity = token_identity
        self._gateways: Mapping[str, ExchangeGateway] = gateways or {}
        self._strategy_table_service = strategy_table_service
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task[None] | None = None
        # (symbol, short_ex, long_ex) -> open_since_monotonic
        self._open_pairs: dict[tuple[str, str, str], float] = {}
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
            self._settings.screener_auto_trade_max_positions,
            self._settings.screener_auto_trade_open_spread_pct,
            self._settings.screener_auto_trade_close_spread_pct,
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
        interval = self._settings.screener_auto_trade_check_seconds
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
            except (asyncio.TimeoutError, asyncio.CancelledError):
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
        from arbitrator.domain.position_leg import PositionLeg

        positions_by_symbol: dict[str, list[tuple[str, PositionLeg]]] = {}
        for exchange_id, gateway in self._exec._gateways.items():
            try:
                legs = await gateway.fetch_open_positions()
            except Exception:
                logger.exception("live auto trader: failed to fetch positions | ex={}", exchange_id)
                continue
            for leg in legs:
                positions_by_symbol.setdefault(leg.symbol, []).append((exchange_id, leg))

        base_notional = self._settings.screener_auto_trade_notional_usdt

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
                    (short_leg.entry_price - long_leg.entry_price)
                    / long_leg.entry_price * 100.0
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
                symbol, short_ex, long_ex, self._entry_spreads.get(key, 0.0),
                position_usdt, self._dca_layers[key],
            )

        logger.info("live auto trader: restored {} open pairs", len(self._open_pairs))

    # ------------------------------------------------------------------ #
    # Main tick
    # ------------------------------------------------------------------ #

    async def _tick(self) -> None:
        tickers, _symbols, _updates, status, _threshold = self._screener.read_state()
        if status != "Live":
            return

        open_spread_pct = self._settings.screener_auto_trade_open_spread_pct
        close_spread_pct = self._settings.screener_auto_trade_close_spread_pct
        max_pos = self._settings.screener_auto_trade_max_positions

        # --- build ranked candidates ---
        by_symbol: dict[str, dict[str, float]] = {}
        for (exchange_id, symbol), ticker in tickers.items():
            if ticker.last is not None and ticker.last > 0.0:
                by_symbol.setdefault(symbol, {})[exchange_id] = ticker.last

        candidates: list[tuple[float, str, str, str, float, float]] = []
        for symbol, prices in by_symbol.items():
            if len(prices) < 2:
                continue
            short_ex = max(prices, key=lambda ex: prices[ex])
            long_ex = min(prices, key=lambda ex: prices[ex])
            short_ticker = tickers.get((short_ex, symbol))
            long_ticker = tickers.get((long_ex, symbol))
            if not short_ticker or not long_ticker:
                continue
            # Use bid/ask when available, fallback to last for exchanges
            # that don't stream bid/ask (mexc, gate)
            short_bid = short_ticker.bid or short_ticker.last
            long_ask = long_ticker.ask or long_ticker.last
            if not short_bid or not long_ask or long_ask <= 0.0:
                continue
            # Skip illiquid: if either ticker streams bid/ask and it's too wide
            if self._ticker_too_wide(short_ticker) or self._ticker_too_wide(long_ticker):
                continue
            spread = (short_bid - long_ask) / long_ask * 100.0
            candidates.append((spread, symbol, short_ex, long_ex, short_bid, long_ask))

        candidates.sort(key=lambda c: c[0], reverse=True)

        # --- close pass ---
        to_remove: list[tuple[str, str, str]] = []
        for key, _opened_at in list(self._open_pairs.items()):
            sym, s_ex, l_ex = key
            s_ticker = tickers.get((s_ex, sym))
            l_ticker = tickers.get((l_ex, sym))
            short_ask = (
                s_ticker.ask if s_ticker and s_ticker.ask
                else s_ticker.last if s_ticker else None
            )
            long_bid = (
                l_ticker.bid if l_ticker and l_ticker.bid
                else l_ticker.last if l_ticker else None
            )
            if short_ask is None or long_bid is None or long_bid <= 0.0:
                # Ticker absent from screener universe — fallback to order book REST
                logger.debug(
                    "live close: no ticker, fetching book | sym={} short={} long={}",
                    sym, s_ex, l_ex,
                )
                fresh = await self._fetch_book_spread(sym, s_ex, l_ex)
                if fresh is None:
                    logger.warning(
                        "live close skipped: book fetch also failed | sym={} short={} long={}",
                        sym, s_ex, l_ex,
                    )
                    continue
                short_ask, long_bid, _ = fresh
            exit_spread = (short_ask - long_bid) / long_bid * 100.0
            logger.debug(
                "live close check | sym={} short={} long={} exit_spread={:.4f}% threshold={}%",
                sym, s_ex, l_ex, exit_spread, close_spread_pct,
            )
            if exit_spread > close_spread_pct:
                continue
            logger.info(
                "live auto close | sym={} short={} long={} exit_spread={:.4f}% threshold={}%"
                " short_ask={} long_bid={}",
                sym, s_ex, l_ex, exit_spread, close_spread_pct, short_ask, long_bid,
            )
            logger["trades/live_trades.log"].info(
                "CLOSE | trigger=spread sym={} short={} long={}"
                " exit_spread={:.4f}% threshold={}% short_ask={} long_bid={}",
                sym, s_ex, l_ex, exit_spread, close_spread_pct, short_ask, long_bid,
            )
            outcome = await self._exec.close_all(
                symbol=sym,
                short_exchange_id=s_ex,
                long_exchange_id=l_ex,
            )
            logger.info(
                "live auto close result | sym={} status={} imbalance={}",
                sym, outcome.status.value, outcome.imbalance_pct,
            )
            logger["trades/live_trades.log"].info(
                "CLOSE_RESULT | sym={} status={} short_ex={} long_ex={}"
                " short_filled={} short_order={} long_filled={} long_order={} imbalance={}",
                sym, outcome.status.value, s_ex, l_ex,
                outcome.short_leg.filled_amount if outcome.short_leg else "n/a",
                outcome.short_leg.order_id if outcome.short_leg else "n/a",
                outcome.long_leg.filled_amount if outcome.long_leg else "n/a",
                outcome.long_leg.order_id if outcome.long_leg else "n/a",
                outcome.imbalance_pct,
            )
            to_remove.append(key)

        for key in to_remove:
            self._open_pairs.pop(key, None)
            self._entry_spreads.pop(key, None)
            self._dca_layers.pop(key, None)

        # --- DCA pass: accumulate into existing positions if spread widened ---
        await self._dca_pass(tickers)

        # --- open pass ---
        open_count = len(self._open_pairs)
        already_open_symbols = {sym for (sym, _s, _l) in self._open_pairs}

        for _net, symbol, short_ex, long_ex, short_bid, long_ask in candidates:
            if open_count >= max_pos:
                break
            if symbol in already_open_symbols:
                continue
            # Skip pairs in rollback/fail cooldown
            _ck = (symbol, short_ex, long_ex)
            if self._open_cooldown.get(_ck, 0.0) > time.monotonic():
                continue
            # Skip if no gateway for either exchange
            if short_ex not in self._exec._gateways or long_ex not in self._exec._gateways:
                continue
            entry_spread = (short_bid - long_ask) / long_ask * 100.0
            if entry_spread < open_spread_pct:
                continue
            # Fetch fresh order books (REST) — gates all subsequent checks
            fresh = await self._fetch_book_spread(symbol, short_ex, long_ex)
            if fresh is None:
                logger.debug(
                    "live open skipped: order book fetch failed | sym={} short={} long={}",
                    symbol, short_ex, long_ex,
                )
                continue
            fresh_bid, fresh_ask, fresh_spread = fresh
            if fresh_spread < open_spread_pct:
                # Book disagrees with ticker direction — try reversed legs from cache
                rev = self._reversed_book_spread(symbol, short_ex, long_ex)
                if rev is None or rev[2] < open_spread_pct:
                    logger.debug(
                        "live open skipped: book spread below threshold | sym={} short={} long={} was={:.3f}% now={:.3f}%",
                        symbol, short_ex, long_ex, entry_spread, fresh_spread,
                    )
                    continue
                short_ex, long_ex = long_ex, short_ex
                fresh_bid, fresh_ask, fresh_spread = rev
                # ponytail: check cooldown for reversed direction too
                _ck_rev = (symbol, short_ex, long_ex)
                if self._open_cooldown.get(_ck_rev, 0.0) > time.monotonic():
                    continue
                logger.debug(
                    "live open: reversed legs from book | sym={} short={} long={} spread={:.3f}%",
                    symbol, short_ex, long_ex, fresh_spread,
                )
            if fresh_spread > self._settings.anomaly_max_spread_pct:
                logger.warning(
                    "live open blocked: anomaly spread — likely different tokens | "
                    "sym={} short={} long={} spread={:.1f}% max={}%",
                    symbol, short_ex, long_ex, fresh_spread,
                    self._settings.anomaly_max_spread_pct,
                )
                continue
            notional_float = self._resolve_min_notional(symbol, short_ex, long_ex, fresh_bid, fresh_ask)
            if notional_float is None:
                logger.debug(
                    "live open skipped: market info not yet cached | sym={} short={} long={}",
                    symbol, short_ex, long_ex,
                )
                continue
            rejection = self._validate_cross_pair(symbol, short_ex, long_ex, notional_float)
            if rejection is not None:
                logger.warning(
                    "live open skipped: {} | sym={} short={} long={}",
                    rejection, symbol, short_ex, long_ex,
                )
                continue
            # Pre-trade slippage estimation: predict actual fill spread from book depth
            estimated_spread = self._estimate_spread_after_fill(
                symbol, short_ex, long_ex, notional_float
            )
            if estimated_spread is not None and estimated_spread < open_spread_pct:
                logger.warning(
                    "live open blocked: estimated fill spread below threshold | "
                    "sym={} short={} long={} book_spread={:.3f}% estimated_fill={:.3f}% threshold={}%",
                    symbol, short_ex, long_ex, fresh_spread, estimated_spread, open_spread_pct,
                )
                continue
            # Set cross-margin mode on both exchanges before opening
            await self._set_cross_margin(symbol, short_ex)
            await self._set_cross_margin(symbol, long_ex)
            # Determine best strategy from StrategyTable (defaults to futures_futures)
            strategy_kind = "futures_futures"
            if self._strategy_table_service is not None:
                tables = self._strategy_table_service.read_tables()
                table = tables.get(symbol)
                if table is not None and table.best_strategy_id is not None:
                    strategy_kind = table.best_strategy_id.value

            notional = Decimal(str(notional_float))
            price = Decimal(str(fresh_bid))
            logger.info(
                "live auto open | sym={} short={} long={} spread={:.4f}% notional={}"
                " short_bid={} long_ask={} entry_spread={:.4f}% threshold={}%"
                " estimated_fill_spread={} anomaly_max={}% slippage_max={}% strategy={}",
                symbol, short_ex, long_ex, fresh_spread, notional,
                fresh_bid, fresh_ask, entry_spread, open_spread_pct,
                f"{estimated_spread:.3f}%" if estimated_spread else "n/a",
                self._settings.anomaly_max_spread_pct, self._settings.slippage_max_pct,
                strategy_kind,
            )
            logger["trades/live_trades.log"].info(
                "OPEN | trigger=spread sym={} short={} long={}"
                " spread={:.4f}% entry_spread={:.4f}% threshold={}%"
                " short_bid={} long_ask={} notional={} max_positions={} open_count={}"
                " estimated_fill_spread={} strategy={}",
                symbol, short_ex, long_ex,
                fresh_spread, entry_spread, open_spread_pct,
                fresh_bid, fresh_ask, notional, max_pos, open_count,
                f"{estimated_spread:.3f}%" if estimated_spread else "n/a",
                strategy_kind,
            )
            outcome = await self._exec.open(
                symbol=symbol,
                short_exchange_id=short_ex,
                long_exchange_id=long_ex,
                notional_usdt=notional,
                price=price,
            )
            logger.info(
                "live auto open result | sym={} status={} imbalance={}",
                symbol, outcome.status.value, outcome.imbalance_pct,
            )
            logger["trades/live_trades.log"].info(
                "OPEN_RESULT | sym={} status={} short_ex={} long_ex={}"
                " short_requested={} short_filled={} short_order={}"
                " long_requested={} long_filled={} long_order={}"
                " imbalance={} message={}",
                symbol, outcome.status.value, short_ex, long_ex,
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
                self._entry_spreads[key] = fresh_spread
                self._dca_layers[key] = 0
                self._pair_strategy[key] = strategy_kind
                already_open_symbols.add(symbol)
                open_count += 1
                # Post-fill spread guard: verify actual spread from positions
                await self._post_fill_guard(key)
            else:
                # Prevent immediate re-entry after rollback/fail on same pair
                self._open_cooldown[key] = time.monotonic() + self._settings.open_fail_cooldown_sec

    # ------------------------------------------------------------------ #
    # Post-fill guard: close if real spread < threshold
    # ------------------------------------------------------------------ #

    async def _post_fill_guard(self, key: tuple[str, str, str]) -> None:
        """Check actual entry spread from position entry prices right after fill.

        If real spread < live_auto_trade_post_fill_min_spread_pct → close immediately.
        """
        symbol, short_ex, long_ex = key
        min_spread = self._settings.live_auto_trade_post_fill_min_spread_pct
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
            (short_leg.entry_price - long_leg.entry_price)
            / long_leg.entry_price * 100.0
        )
        # Update stored entry spread with the real value
        self._entry_spreads[key] = actual_spread
        if actual_spread < min_spread:
            logger.warning(
                "post_fill_guard: actual spread {:.3f}% < {:.1f}% — closing immediately | "
                "sym={} short={} long={} short_entry={} long_entry={}",
                actual_spread, min_spread,
                symbol, short_ex, long_ex,
                short_leg.entry_price, long_leg.entry_price,
            )
            logger["trades/live_trades.log"].warning(
                "POST_FILL_CLOSE | sym={} actual_spread={:.3f}% min={:.1f}%"
                " short_entry={} long_entry={}",
                symbol, actual_spread, min_spread,
                short_leg.entry_price, long_leg.entry_price,
            )
            await self._exec.close_all(
                symbol=symbol,
                short_exchange_id=short_ex,
                long_exchange_id=long_ex,
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
        dca_step = self._settings.live_auto_trade_dca_spread_step_pct
        max_layers = self._settings.live_auto_trade_dca_max_layers
        min_liq_dist = self._settings.live_auto_trade_dca_min_liq_distance_pct
        funding_skip_sec = self._settings.live_auto_trade_dca_funding_skip_seconds

        for key in list(self._open_pairs.keys()):
            symbol, short_ex, long_ex = key
            layers = self._dca_layers.get(key, 0)
            if layers >= max_layers:
                continue
            entry_spread = self._entry_spreads.get(key)
            if entry_spread is None:
                continue
            # Check current spread
            fresh = await self._fetch_book_spread(symbol, short_ex, long_ex)
            if fresh is None:
                continue
            _bid, _ask, current_spread = fresh
            required_spread = entry_spread + dca_step
            if current_spread < required_spread:
                continue
            # Notional for DCA = 2x base notional
            notional_float = self._resolve_min_notional(symbol, short_ex, long_ex, _bid, _ask)
            if notional_float is None:
                continue
            dca_notional = notional_float * 2.0
            # Pre-trade slippage estimation for DCA volume
            estimated = self._estimate_spread_after_fill(symbol, short_ex, long_ex, dca_notional)
            if estimated is not None and estimated < self._settings.screener_auto_trade_open_spread_pct:
                logger.debug(
                    "DCA skipped: estimated fill spread too low | sym={} est={:.3f}%",
                    symbol, estimated,
                )
                continue
            # Depth check for DCA volume
            depth_rejection = self._check_order_book_depth(symbol, short_ex, long_ex, dca_notional)
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
                symbol, short_ex, long_ex, current_spread,
                entry_spread, dca_notional, layers + 1,
            )
            logger["trades/live_trades.log"].info(
                "DCA | sym={} short={} long={} current_spread={:.3f}%"
                " entry_spread={:.3f}% required={:.3f}% notional={} layer={}",
                symbol, short_ex, long_ex, current_spread,
                entry_spread, required_spread, dca_notional, layers + 1,
            )
            outcome = await self._exec.accumulate(
                symbol=symbol,
                short_exchange_id=short_ex,
                long_exchange_id=long_ex,
                notional_usdt=notional,
                price=price,
            )
            if outcome.status.value in ("success", "partial"):
                self._dca_layers[key] = layers + 1
                # Update entry spread to average (weighted by layers)
                total_layers = layers + 2  # original + all DCA layers
                self._entry_spreads[key] = (
                    (entry_spread * (total_layers - 1) + current_spread) / total_layers
                )
                logger.info(
                    "DCA result | sym={} status={} new_avg_spread={:.3f}%",
                    symbol, outcome.status.value, self._entry_spreads[key],
                )
            else:
                logger.warning(
                    "DCA failed | sym={} status={} message={}",
                    symbol, outcome.status.value, outcome.message,
                )

    async def _liq_distance_ok(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        min_pct: float,
    ) -> bool:
        """Return True if both legs are > min_pct away from estimated liquidation."""
        leverage = float(self._settings.opp_default_leverage)
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
            if leg.side == "short":
                liq = entry * (1.0 + buffer)
            else:
                liq = entry * (1.0 - buffer)
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
            funding = self._cache.get_funding(exchange_id, symbol)
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
    # Helpers — identical logic to ScreenerAutoTrader
    # ------------------------------------------------------------------ #

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

    def _min_notional_for_exchange(
        self,
        symbol: str,
        exchange_id: str,
        live_price: float | None,
    ) -> float | None:
        info = self._cache.get_market_info(exchange_id, symbol)
        if info is None:
            return None
        from_contracts: float | None = None
        if (
            info.min_amount_contracts is not None
            and info.contract_size > 0.0
            and live_price is not None
            and live_price > 0.0
        ):
            from_contracts = info.min_amount_contracts * info.contract_size * live_price
        if info.min_order_volume_usdt is not None and from_contracts is not None:
            return max(info.min_order_volume_usdt, from_contracts)
        if info.min_order_volume_usdt is not None:
            return info.min_order_volume_usdt
        return from_contracts

    def _resolve_min_notional(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        short_price: float | None = None,
        long_price: float | None = None,
    ) -> float | None:
        min_a = self._min_notional_for_exchange(symbol, short_ex, short_price)
        min_b = self._min_notional_for_exchange(symbol, long_ex, long_price)
        if min_a is None or min_b is None:
            return None
        floor = self._settings.screener_auto_trade_notional_usdt
        return max(min_a, min_b, floor)

    def _ticker_too_wide(self, ticker: Ticker) -> bool:
        """Reject tickers where the exchange's own bid-ask spread indicates illiquidity.

        Returns False (pass) when bid/ask absent — those exchanges (mexc, gate)
        don't stream bid/ask; the book fetch later is the real gate.
        """
        if ticker.bid and ticker.ask and ticker.ask > 0.0:
            inner_spread = (ticker.ask - ticker.bid) / ticker.ask * 100.0
            return inner_spread > self._settings.ticker_max_inner_spread_pct
        return False

    async def _fetch_book_spread(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
    ) -> tuple[float, float, float] | None:
        """Fetch order books via REST for both legs, cache them, return (bid, ask, spread%).

        Returns None if either fetch fails or book is empty — blocks the trade.
        """
        depth = self._settings.opportunity_order_book_depth
        for exchange_id in (short_ex, long_ex):
            gw = self._gateways.get(exchange_id)
            if gw is None:
                return None
            try:
                book = await gw.fetch_order_book_once(symbol, depth)
            except Exception:
                logger.exception(
                    "fetch_order_book_once failed | ex={} sym={}", exchange_id, symbol
                )
                return None
            if not book.bids or not book.asks:
                return None
            self._cache.put_order_book(book)
        short_book = self._cache.get_order_book(short_ex, symbol)
        long_book = self._cache.get_order_book(long_ex, symbol)
        if short_book is None or long_book is None:
            return None
        if not short_book.bids or not long_book.asks:
            return None
        bid = short_book.bids[0].price
        ask = long_book.asks[0].price
        if ask <= 0.0:
            return None
        spread = (bid - ask) / ask * 100.0
        return bid, ask, spread

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
        book = self._cache.get_order_book(exchange_id, symbol)
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
        return (short_fill - long_fill) / long_fill * 100.0

    def _reversed_book_spread(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
    ) -> tuple[float, float, float] | None:
        """Return (bid, ask, spread%) for the reversed direction using cached books."""
        long_book = self._cache.get_order_book(short_ex, symbol)   # was short → now long
        short_book = self._cache.get_order_book(long_ex, symbol)   # was long → now short
        if long_book is None or short_book is None:
            return None
        if not short_book.bids or not long_book.asks:
            return None
        bid = short_book.bids[0].price
        ask = long_book.asks[0].price
        if ask <= 0.0:
            return None
        return bid, ask, (bid - ask) / ask * 100.0

    def _fresh_spread(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
    ) -> tuple[float, float, float] | None:
        q_short = self._cache.get_quote(short_ex, symbol, "futures")
        q_long = self._cache.get_quote(long_ex, symbol, "futures")
        if q_short is None or q_long is None:
            return None
        max_age_ms = int(self._settings.quote_max_age_seconds * 1000)
        now_ms = int(time.time() * 1000)
        if now_ms - q_short.recv_time_ms > max_age_ms:
            logger.debug(
                "_fresh_spread: quote stale | ex={} sym={} age_ms={}",
                short_ex, symbol, now_ms - q_short.recv_time_ms,
            )
            return None
        if now_ms - q_long.recv_time_ms > max_age_ms:
            logger.debug(
                "_fresh_spread: quote stale | ex={} sym={} age_ms={}",
                long_ex, symbol, now_ms - q_long.recv_time_ms,
            )
            return None
        bid = float(q_short.bid) if q_short.bid is not None else (
            float(q_short.last) if q_short.last is not None else None
        )
        ask = float(q_long.ask) if q_long.ask is not None else (
            float(q_long.last) if q_long.last is not None else None
        )
        if bid is None or ask is None or ask <= 0.0:
            return None
        spread = (bid - ask) / ask * 100.0
        return bid, ask, spread

    def _validate_cross_pair(
        self,
        symbol: str,
        exchange_a: str,
        exchange_b: str,
        notional_usdt: float,
    ) -> str | None:
        from arbitrator.domain.symbol_normalizer import SymbolNormalizer

        expected_base = SymbolNormalizer.base_asset(symbol)
        tickers_snapshot = self._screener.read_state()[0]
        ticker_a = tickers_snapshot.get((exchange_a, symbol))
        ticker_b = tickers_snapshot.get((exchange_b, symbol))

        for ticker, ex in ((ticker_a, exchange_a), (ticker_b, exchange_b)):
            if ticker is not None:
                ticker_base = ticker.base_asset.upper()
                if ticker_base and ticker_base != expected_base.upper():
                    return f"ticker_base_mismatch:{ex}:{ticker_base}!={expected_base}"

        for ticker, ex in ((ticker_a, exchange_a), (ticker_b, exchange_b)):
            if ticker is not None:
                q = ticker.quote_asset.upper()
                if q and q != "USDT":
                    return f"quote_asset_not_usdt:{ex}:{q}"

        info_a = self._cache.get_market_info(exchange_a, symbol)
        info_b = self._cache.get_market_info(exchange_b, symbol)
        if info_a is None:
            return f"market_info_missing:{exchange_a}"
        if info_b is None:
            return f"market_info_missing:{exchange_b}"

        if info_a.base_asset.upper() != info_b.base_asset.upper():
            return (
                f"market_base_mismatch:"
                f"{exchange_a}:{info_a.base_asset}"
                f"!={exchange_b}:{info_b.base_asset}"
            )

        for info, ex in ((info_a, exchange_a), (info_b, exchange_b)):
            if info.min_order_volume_usdt is not None and notional_usdt < info.min_order_volume_usdt:
                return (
                    f"below_min_notional:{ex}:"
                    f"{notional_usdt:.2f}<{info.min_order_volume_usdt:.2f}"
                )

        if self._token_identity is not None:
            result = self._token_identity.compare(expected_base, exchange_a, exchange_b)
            if result.should_block:
                return (
                    f"token_identity_conflict:{expected_base}:"
                    f"{exchange_a}/{exchange_b}:{result.notes}"
                )
            if result.match_type == "symbol_only_ccxt_dedup":
                logger.debug(
                    "token_identity unverified, proceeding | base={} {}/{} notes={}",
                    expected_base, exchange_a, exchange_b, result.notes,
                )

        depth_rejection = self._check_order_book_depth(symbol, exchange_a, exchange_b, notional_usdt)
        if depth_rejection is not None:
            return depth_rejection

        return None

    def _check_order_book_depth(
        self,
        symbol: str,
        exchange_a: str,
        exchange_b: str,
        notional_usdt: float,
    ) -> str | None:
        """Return rejection reason if either exchange lacks sufficient order book depth.

        Required depth = notional_usdt * 2 within 0.4% of best bid/ask price.
        Uses cached OrderBookSnapshot (populated by _fetch_book_spread before this runs).
        """
        required = notional_usdt * 2.0
        for exchange_id in (exchange_a, exchange_b):
            book = self._cache.get_order_book(exchange_id, symbol)
            if book is None:
                return f"no_order_book:{exchange_id}"
            ask_depth = ScreenerAutoTrader._side_depth_usdt(book.asks, price_limit_pct=0.004)
            bid_depth = ScreenerAutoTrader._side_depth_usdt(book.bids, price_limit_pct=0.004)
            logger.debug(
                "order book depth | sym={} ex={} bid_depth={:.0f} ask_depth={:.0f} required={:.0f}",
                symbol, exchange_id, bid_depth, ask_depth, required,
            )
            if ask_depth < required:
                logger.warning(
                    "live open blocked: insufficient ask depth | sym={} ex={} "
                    "ask_depth={:.0f} required={:.0f}",
                    symbol, exchange_id, ask_depth, required,
                )
                return f"insufficient_ask_depth:{exchange_id}:{ask_depth:.0f}<{required:.0f}"
            if bid_depth < required:
                logger.warning(
                    "live open blocked: insufficient bid depth | sym={} ex={} "
                    "bid_depth={:.0f} required={:.0f}",
                    symbol, exchange_id, bid_depth, required,
                )
                return f"insufficient_bid_depth:{exchange_id}:{bid_depth:.0f}<{required:.0f}"
        return None
