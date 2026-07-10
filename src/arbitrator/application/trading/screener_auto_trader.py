from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING

from arbitrator.application.account.token_identity_service import TokenIdentityService
from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.market_data.screener_stream_worker import ScreenerStreamWorker
from arbitrator.application.trading.auto_trader_base import AutoTraderBase
from arbitrator.application.trading.executable_spread_resolver import ExecutableSpreadResolver
from arbitrator.application.trading.paper_execution_gateway import PaperExecutionGateway
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.market.ticker import Ticker

if TYPE_CHECKING:
    from arbitrator.application.strategies.strategy_table_service import StrategyTableService
    from arbitrator.domain.exchange.exchange_gateway import ExchangeGateway


class ScreenerAutoTrader(AutoTraderBase):
    """Background thread: scans screener every N seconds, auto-trades via paper gateway.

    Logic per tick:
    1. Group screener tickers by symbol; pick best short/long by bid/ask (never last).
    2. Sort by executable entry spread descending.
    3. For each symbol where spread >= open_spread and open pairs < max_positions: open a paper pair.
    4. For each tracked open pair where exit_spread <= close_spread: close it.

    Tracked pairs survive process restarts — on start the worker reloads
    all open pair_ids from PaperOrderStore so it can close them later.
    """

    def __init__(
        self,
        settings: Settings,
        screener_worker: ScreenerStreamWorker,
        paper_gateway: PaperExecutionGateway,
        market_cache: MarketDataCacheMemory | None = None,
        token_identity: TokenIdentityService | None = None,
        strategy_table_service: StrategyTableService | None = None,
        gateways: Mapping[str, ExchangeGateway] | None = None,
    ) -> None:
        super().__init__(
            settings=settings,
            market_cache=market_cache,
            token_identity=token_identity,
        )
        self._screener = screener_worker
        self._paper = paper_gateway
        self._spread_resolver = (
            ExecutableSpreadResolver(settings, market_cache, gateways)
            if market_cache is not None
            else None
        )
        self._strategy_table_service = strategy_table_service
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # pair_id -> (symbol, short_ex, long_ex)
        self._open_pairs: dict[str, tuple[str, str, str]] = {}
        # pair_id -> open_time for unhedged detection
        self._pair_open_time: dict[str, float] = {}
        # pair_id -> strategy_kind used for the trade
        self._pair_strategy: dict[str, str] = {}

    def start(self) -> None:
        self._restore_open_pairs()
        self._thread = threading.Thread(
            target=self._run,
            name="screener-auto-trader",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "screener auto trader started | max_pos={} open_spread={}% close_spread={}% restored={}",
            self._settings.screener_auto_trade_max_positions,
            self._settings.screener_auto_trade_open_spread_pct,
            self._settings.screener_auto_trade_close_spread_pct,
            len(self._open_pairs),
        )

    def stop(self) -> None:
        self._stop.set()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ #

    def _restore_open_pairs(self) -> None:
        """Reload open pair_ids from PaperOrderStore so we can close them after restart."""
        records = self._paper._store.load_all()
        open_ids = {r.pair_id for r in records if r.action == "open" and r.status == "filled"}
        closed_ids = {r.pair_id for r in records if r.action == "open" and r.status == "closed"}
        active_pair_ids = open_ids - closed_ids
        for r in records:
            if r.pair_id not in active_pair_ids:
                continue
            if r.action != "open" or r.status != "filled":
                continue
            # reconstruct from the sell (short) leg
            if r.side == "sell":
                # find matching buy leg for same pair_id
                buy_leg = next(
                    (x for x in records if x.pair_id == r.pair_id and x.side == "buy"),
                    None,
                )
                if buy_leg is not None:
                    self._open_pairs[r.pair_id] = (r.symbol, r.exchange_id, buy_leg.exchange_id)
                    self._pair_open_time[r.pair_id] = time.monotonic()

    def _run(self) -> None:
        check_interval = self._settings.screener_auto_trade_check_seconds
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:
                logger.exception("screener auto trader tick failed")
            self._stop.wait(timeout=check_interval)

    def _fresh_spread(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        *,
        short_ticker: Ticker | None = None,
        long_ticker: Ticker | None = None,
    ) -> tuple[float, float, float] | None:
        """Return (short_bid, long_ask, spread_pct); REST only when leg needs book."""

        if self._spread_resolver is None:
            return None
        return asyncio.run(
            self._spread_resolver.entry_spread_for_open(
                symbol,
                short_ex,
                long_ex,
                short_ticker=short_ticker,
                long_ticker=long_ticker,
            )
        )

    def _tick(self) -> None:
        tickers, _symbols, _updates, status, _threshold = self._screener.read_state()
        if status != "Live":
            return

        open_spread = self._settings.screener_auto_trade_open_spread_pct
        max_pos = self._settings.screener_auto_trade_max_positions

        # --- build ranked candidates for open (bid/ask or book top — never last) ---
        by_symbol: dict[str, dict[str, Ticker]] = {}
        for (exchange_id, symbol), ticker in tickers.items():
            by_symbol.setdefault(symbol, {})[exchange_id] = ticker

        candidates: list[tuple[float, str, str, str, float, float]] = []
        for symbol, per_exchange in by_symbol.items():
            if len(per_exchange) < 2 or self._spread_resolver is None:
                continue
            best = self._spread_resolver.best_entry_pair_sync(symbol, per_exchange)
            if best is None:
                continue
            short_ex, long_ex, short_bid, long_ask, spread = best
            candidates.append((spread, symbol, short_ex, long_ex, short_bid, long_ask))

        candidates.sort(key=lambda c: c[0], reverse=True)

        # --- close pass: only tracked open pairs ---
        # Load records once outside the loop to look up filled amounts.
        all_open_records = self._paper._store.load_all()

        closed_pair_ids: list[str] = []
        for pair_id, (sym, s_ex, l_ex) in list(self._open_pairs.items()):
            s_ticker = tickers.get((s_ex, sym))
            l_ticker = tickers.get((l_ex, sym))
            exit_quotes = (
                self._spread_resolver.exit_spread_sync(
                    sym, s_ex, l_ex, short_ticker=s_ticker, long_ticker=l_ticker,
                )
                if self._spread_resolver is not None
                else None
            )
            if exit_quotes is None:
                continue
            short_ask, long_bid, exit_spread = exit_quotes
            pair_strategy = self._pair_strategy.get(pair_id, "futures_futures")
            pair_close_threshold = self._settings.strategy_close_spread_pct(pair_strategy)
            if exit_spread > pair_close_threshold:
                continue
            # Use the filled amount from the open record (long/buy leg).
            long_record = next(
                (r for r in all_open_records
                 if r.pair_id == pair_id and r.side == "buy" and r.action == "open"),
                None,
            )
            amount = long_record.amount if long_record is not None else 0.0
            if amount <= 0.0:
                continue
            self._paper.close_pair(
                pair_id=pair_id,
                symbol=sym,
                short_exchange_id=s_ex,
                long_exchange_id=l_ex,
                short_price=short_ask,
                long_price=long_bid,
                amount=amount,
                spread_pct=round(exit_spread, 4),
            )
            logger.info(
                "auto close | pair_id={} sym={} short={} long={} exit_spread={:.3f}%",
                pair_id, sym, s_ex, l_ex, exit_spread,
            )
            closed_pair_ids.append(pair_id)

        for pair_id in closed_pair_ids:
            self._open_pairs.pop(pair_id, None)
            self._pair_open_time.pop(pair_id, None)

        # --- unhedged close pass: close single-leg pairs after timeout ---
        unhedged_timeout = self._settings.screener_auto_trade_unhedged_timeout_seconds
        unhedged_to_close: list[str] = []
        all_records = self._paper._store.load_all()
        pair_leg_count: dict[str, int] = {}
        for r in all_records:
            if r.status == "filled":
                pair_leg_count[r.pair_id] = pair_leg_count.get(r.pair_id, 0) + 1

        now_ts = time.monotonic()
        for pair_id, (sym, _s_ex, _l_ex) in list(self._open_pairs.items()):
            leg_count = pair_leg_count.get(pair_id, 0)
            if leg_count >= 2:
                continue
            open_ts = self._pair_open_time.get(pair_id)
            if open_ts is None:
                self._pair_open_time[pair_id] = now_ts
                continue
            if now_ts - open_ts < unhedged_timeout:
                continue
            # Find the single open leg and close it at market
            unhedged_leg = next(
                (r for r in all_records if r.pair_id == pair_id and r.status == "filled"),
                None,
            )
            if unhedged_leg is None:
                unhedged_to_close.append(pair_id)
                continue
            ex_id = unhedged_leg.exchange_id
            unhedged_ticker = tickers.get((ex_id, sym))
            close_price: float | None = None
            if unhedged_ticker is not None and self._spread_resolver is not None:
                top = self._spread_resolver.top_of_book_sync(
                    ex_id, sym, unhedged_ticker,
                )
                if top is not None:
                    close_price = top.bid if unhedged_leg.side == "sell" else top.ask
            if close_price is None or close_price <= 0:
                continue
            amount_to_close = unhedged_leg.amount
            if unhedged_leg.side == "sell":
                self._paper._store.record_close(
                    pair_id=pair_id,
                    exchange_id=ex_id,
                    side="sell",
                    amount=amount_to_close,
                    price=close_price,
                    taker_fee_rate=self._paper._taker_fee_rate(ex_id, sym),
                )
            else:
                self._paper._store.record_close(
                    pair_id=pair_id,
                    exchange_id=ex_id,
                    side="buy",
                    amount=amount_to_close,
                    price=close_price,
                    taker_fee_rate=self._paper._taker_fee_rate(ex_id, sym),
                )
            logger.warning(
                "auto close unhedged leg | pair_id={} sym={} ex={} side={} price={}",
                pair_id, sym, ex_id, unhedged_leg.side, close_price,
            )
            unhedged_to_close.append(pair_id)

        for pair_id in unhedged_to_close:
            self._open_pairs.pop(pair_id, None)
            self._pair_open_time.pop(pair_id, None)

        # --- open pass ---
        open_count = len(self._open_pairs)
        already_open_symbols = {sym for _pid, (sym, _s, _l) in self._open_pairs.items()}

        for _net, symbol, short_ex, long_ex, short_bid, long_ask in candidates:
            if open_count >= max_pos:
                break
            if symbol in already_open_symbols:
                continue
            entry_spread = (short_bid - long_ask) / long_ask * 100.0
            if entry_spread < open_spread:
                continue
            # Resolve the minimum notional from exchange market info.
            # Returns None when market info is not yet cached — skip until data arrives.
            notional = self._resolve_min_notional(
                symbol, short_ex, long_ex, short_bid, long_ask
            )
            if notional is None:
                logger.debug(
                    "auto open skipped: market info not yet cached | sym={} short={} long={}",
                    symbol, short_ex, long_ex,
                )
                continue
            # Verify same underlying coin + compatible markets on both exchanges
            rejection = self._validate_cross_pair(symbol, short_ex, long_ex, notional)
            if rejection is not None:
                logger.warning(
                    "auto open skipped: {} | sym={} short={} long={}",
                    rejection, symbol, short_ex, long_ex,
                )
                continue
            # Re-confirm spread; REST only when a leg lacks WS bid/ask.
            fresh = self._fresh_spread(
                symbol,
                short_ex,
                long_ex,
                short_ticker=tickers.get((short_ex, symbol)),
                long_ticker=tickers.get((long_ex, symbol)),
            )
            if fresh is None:
                logger.debug(
                    "auto open skipped: no fresh quote for recheck | sym={} short={} long={}",
                    symbol, short_ex, long_ex,
                )
                continue
            fresh_bid, fresh_ask, fresh_spread = fresh
            if fresh_spread < open_spread:
                logger.debug(
                    "auto open skipped: spread dropped | sym={} was={:.3f}% now={:.3f}% threshold={}%",
                    symbol, entry_spread, fresh_spread, open_spread,
                )
                continue
            # Anomaly guard: spread > anomaly_max_spread_pct almost certainly means
            # two different tokens sharing the same symbol on different exchanges.
            # (e.g. EDGE on mexc vs EDGE on gate — unrelated projects)
            if fresh_spread > self._settings.anomaly_max_spread_pct:
                logger.warning(
                    "auto open blocked: anomaly spread — likely different tokens | "
                    "sym={} short={} long={} spread={:.1f}% max={}%",
                    symbol, short_ex, long_ex, fresh_spread,
                    self._settings.anomaly_max_spread_pct,
                )
                continue
            # Use fresh prices for sizing — more accurate than the ticker snapshot.
            short_bid = fresh_bid
            long_ask = fresh_ask
            entry_spread = fresh_spread
            # Open short first at USDT notional; derive token amount from short price.
            # Open long for exactly that token amount (mirrors real hedged execution).
            if short_bid <= 0.0:
                continue
            amount = notional / short_bid
            # Determine best strategy from StrategyTable (defaults to futures_futures)
            strategy_kind = "futures_futures"
            if self._strategy_table_service is not None:
                tables = self._strategy_table_service.read_tables()
                table = tables.get(symbol)
                if table is not None and table.best_strategy_id is not None:
                    strategy_kind = table.best_strategy_id.value
            # Strategy whitelist filter
            if not self._settings.is_strategy_allowed(strategy_kind):
                continue
            # Per-strategy spread threshold
            strategy_open_threshold = self._settings.strategy_open_spread_pct(strategy_kind)
            if fresh_spread < strategy_open_threshold:
                continue

            outcome = self._paper.open_pair(
                symbol=symbol,
                short_exchange_id=short_ex,
                long_exchange_id=long_ex,
                short_price=short_bid,
                long_price=long_ask,
                amount=amount,
                spread_pct=round(entry_spread, 4),
                strategy_kind=strategy_kind,
            )
            if outcome.pair_id is None:
                continue
            self._open_pairs[outcome.pair_id] = (symbol, short_ex, long_ex)
            self._pair_open_time[outcome.pair_id] = time.monotonic()
            self._pair_strategy[outcome.pair_id] = strategy_kind
            already_open_symbols.add(symbol)
            open_count += 1
            logger.info(
                "auto open | pair_id={} sym={} short={} long={} spread={:.3f}% strategy={}",
                outcome.pair_id, symbol, short_ex, long_ex, entry_spread, strategy_kind,
            )

