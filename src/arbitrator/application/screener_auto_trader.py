from __future__ import annotations

import threading
import time

from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.paper_execution_gateway import PaperExecutionGateway
from arbitrator.application.screener_stream_worker import ScreenerStreamWorker
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings


class ScreenerAutoTrader:
    """Background thread: scans screener every N seconds, auto-trades via paper gateway.

    Logic per tick:
    1. Group screener tickers by symbol, pick best short/long exchange by last price.
    2. Sort by raw spread descending.
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
    ) -> None:
        self._settings = settings
        self._screener = screener_worker
        self._paper = paper_gateway
        self._market_cache = market_cache
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # pair_id -> (symbol, short_ex, long_ex)
        self._open_pairs: dict[str, tuple[str, str, str]] = {}
        # pair_id -> open_time for unhedged detection
        self._pair_open_time: dict[str, float] = {}

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

    def _tick(self) -> None:
        tickers, _symbols, _updates, status, _threshold = self._screener.read_state()
        if status != "Live":
            return

        open_spread = self._settings.screener_auto_trade_open_spread_pct
        close_spread = self._settings.screener_auto_trade_close_spread_pct
        max_pos = self._settings.screener_auto_trade_max_positions
        notional = self._settings.screener_auto_trade_notional_usdt

        # --- build ranked candidates for open ---
        # Group tickers by symbol, pick best short/long pair by last price.
        # Use ticker.last (bid/ask rarely present in bulk watch_tickers).
        # Sort by raw spread descending so the best opportunity opens first.
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
            # prefer bid/ask; fall back to last
            short_bid = (
                short_ticker.bid if short_ticker and short_ticker.bid
                else short_ticker.last if short_ticker else None
            )
            long_ask = (
                long_ticker.ask if long_ticker and long_ticker.ask
                else long_ticker.last if long_ticker else None
            )
            if short_bid is None or long_ask is None or long_ask <= 0.0:
                continue

            spread = (short_bid - long_ask) / long_ask * 100.0
            candidates.append((spread, symbol, short_ex, long_ex, short_bid, long_ask))

        candidates.sort(key=lambda c: c[0], reverse=True)

        # --- close pass: only tracked open pairs ---
        closed_pair_ids: list[str] = []
        for pair_id, (sym, s_ex, l_ex) in list(self._open_pairs.items()):
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
                continue
            exit_spread = (short_ask - long_bid) / long_bid * 100.0
            if exit_spread > close_spread:
                continue
            amount = notional / long_bid if long_bid > 0 else 0.0
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
            if unhedged_ticker is not None:
                if unhedged_leg.side == "sell":
                    close_price = unhedged_ticker.bid or unhedged_ticker.last
                else:
                    close_price = unhedged_ticker.ask or unhedged_ticker.last
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
            # Verify same underlying coin + compatible markets on both exchanges
            rejection = self._validate_cross_pair(symbol, short_ex, long_ex, notional)
            if rejection is not None:
                logger.warning(
                    "auto open skipped: {} | sym={} short={} long={}",
                    rejection, symbol, short_ex, long_ex,
                )
                continue
            amount = notional / long_ask if long_ask > 0 else 0.0
            outcome = self._paper.open_pair(
                symbol=symbol,
                short_exchange_id=short_ex,
                long_exchange_id=long_ex,
                short_price=short_bid,
                long_price=long_ask,
                amount=amount,
                spread_pct=round(entry_spread, 4),
            )
            if outcome.pair_id is None:
                continue
            self._open_pairs[outcome.pair_id] = (symbol, short_ex, long_ex)
            self._pair_open_time[outcome.pair_id] = time.monotonic()
            already_open_symbols.add(symbol)
            open_count += 1
            logger.info(
                "auto open | pair_id={} sym={} short={} long={} spread={:.3f}%",
                outcome.pair_id, symbol, short_ex, long_ex, entry_spread,
            )

    def _validate_cross_pair(
        self,
        symbol: str,
        exchange_a: str,
        exchange_b: str,
        notional_usdt: float,
    ) -> str | None:
        """Return a rejection reason string, or None when the pair is tradeable.

        Checks (in order):
        1. Base asset via Ticker — fast, no cache required.
        2. Quote asset must be USDT on both sides.
        3. Base asset consistency via SymbolMarketInfo — authoritative when available.
        4. Notional must meet min_order_volume_usdt on both exchanges.

        Fails closed: if market info is absent for either exchange the notional
        check is skipped but the symbol-level checks still run.
        """
        from arbitrator.domain.symbol_normalizer import SymbolNormalizer

        expected_base = SymbolNormalizer.base_asset(symbol)

        tickers_snapshot = self._screener.read_state()[0]
        ticker_a = tickers_snapshot.get((exchange_a, symbol))
        ticker_b = tickers_snapshot.get((exchange_b, symbol))

        # 1 — quick base-asset check from live ticker symbol field
        for ticker, ex in ((ticker_a, exchange_a), (ticker_b, exchange_b)):
            if ticker is not None:
                ticker_base = ticker.base_asset.upper()
                if ticker_base and ticker_base != expected_base.upper():
                    return f"ticker_base_mismatch:{ex}:{ticker_base}!={expected_base}"

        # 2 — quote asset must be USDT (guard against non-USDT pairs sneaking in)
        for ticker, ex in ((ticker_a, exchange_a), (ticker_b, exchange_b)):
            if ticker is not None:
                q = ticker.quote_asset.upper()
                if q and q != "USDT":
                    return f"quote_asset_not_usdt:{ex}:{q}"

        if self._market_cache is None:
            return None

        info_a = self._market_cache.get_market_info(exchange_a, symbol)
        info_b = self._market_cache.get_market_info(exchange_b, symbol)

        # 3 — authoritative base-asset check from market info (fail-closed)
        if (
            info_a is not None
            and info_b is not None
            and info_a.base_asset.upper() != info_b.base_asset.upper()
        ):
            return (
                f"market_base_mismatch:"
                f"{exchange_a}:{info_a.base_asset}"
                f"!={exchange_b}:{info_b.base_asset}"
            )

        # 4 — notional >= min_order_volume_usdt (skip when info absent)
        for info, ex in ((info_a, exchange_a), (info_b, exchange_b)):
            if info is None or info.min_order_volume_usdt is None:
                continue
            if notional_usdt < info.min_order_volume_usdt:
                return (
                    f"below_min_notional:{ex}:"
                    f"{notional_usdt:.2f}<{info.min_order_volume_usdt:.2f}"
                )

        return None
