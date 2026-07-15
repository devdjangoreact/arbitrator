from __future__ import annotations
from arbitrator.config.ui_config_manager import UIConfigManager

import collections
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.market_data.screener_stream_worker import ScreenerStreamWorker
from arbitrator.config.logger import logger
from arbitrator.config.monitor_config_store import MonitorConfigStore
from arbitrator.config.settings import Settings
from arbitrator.domain.market.ticker import Ticker
from arbitrator.domain.strategy.funding_info import FundingInfo
from arbitrator.domain.strategy.quote import Quote


@dataclass
class HistoricalOpportunity:
    symbol: str
    short_ex: str
    long_ex: str
    current_spread_pct: float
    max_historical_spread_pct: float
    short_funding_rate: float
    long_funding_rate: float
    short_next_funding: float
    long_next_funding: float
    short_price: float
    long_price: float
    short_volume_24h: float
    long_volume_24h: float
    detected_at: float
    lookback_seconds: int


class HistoricalScreenerWorker:
    """Runs a periodic scan of market_data_cache_memory to find symbols that
    have a large spread between exchanges, maintaining a short history of spreads.
    """

    def __init__(
        self,
        settings: Settings,
        cache: MarketDataCacheMemory,
        screener_worker: ScreenerStreamWorker | None,
        store: MonitorConfigStore,
        screener_provider: Callable[[], ScreenerStreamWorker | None] | None = None,
    ) -> None:
        self._settings = settings
        self._cache = cache
        self._screener_worker = screener_worker
        self._screener_provider = screener_provider
        self._store = store
        self._stop = threading.Event()
        self._lock = threading.Lock()

        self._lookback_seconds = int(UIConfigManager.get_config().historical_screener_lookback_minutes * 60)
        self._spread_threshold_pct = UIConfigManager.get_config().historical_screener_spread_threshold_pct
        self._min_volume_usdt = getattr(self._settings, "historical_screener_min_volume_usdt", 0.0)

        self._opportunities: dict[str, HistoricalOpportunity] = {}
        self._status: str = "Idle"
        self._thread: threading.Thread | None = None
        self._enabled = bool(UIConfigManager.get_config().historical_screener_enabled)

        # History: symbol -> pair(short_ex, long_ex) -> deque of (timestamp, spread)
        self._history: dict[str, dict[tuple[str, str], collections.deque[tuple[float, float]]]] = (
            collections.defaultdict(lambda: collections.defaultdict(lambda: collections.deque()))
        )

    def _current_screener(self) -> ScreenerStreamWorker | None:
        if self._screener_provider is not None:
            return self._screener_provider()
        return self._screener_worker

    def start(self) -> None:
        self._enabled = True
        if self.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="historical-screener",
            daemon=True,
        )
        self._thread.start()
        with self._lock:
            self._status = "Running"

    def stop(self) -> None:
        self._enabled = False
        self._stop.set()
        with self._lock:
            self._status = "Idle"

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def is_enabled(self) -> bool:
        return self._enabled

    def set_screener_worker(self, screener_worker: ScreenerStreamWorker | None) -> None:
        self._screener_worker = screener_worker

    def read_opportunities(self) -> tuple[str, list[HistoricalOpportunity]]:
        with self._lock:
            return self._status, list(self._opportunities.values())

    def update_filters(
        self,
        lookback_seconds: int | None,
        spread_threshold_pct: float | None,
        min_volume_usdt: float | None,
    ) -> None:
        with self._lock:
            if lookback_seconds is not None:
                self._lookback_seconds = lookback_seconds
            if spread_threshold_pct is not None:
                self._spread_threshold_pct = spread_threshold_pct
            if min_volume_usdt is not None:
                self._min_volume_usdt = min_volume_usdt

    def _run(self) -> None:
        interval = UIConfigManager.get_config().historical_screener_scan_interval_seconds
        while not self._stop.is_set():
            try:
                self._scan()
            except Exception:
                logger.exception("Historical screener scan failed")

            # Sleep in chunks to respond to stop quickly
            sleep_time = interval
            while sleep_time > 0 and not self._stop.is_set():
                time.sleep(min(sleep_time, 1.0))
                sleep_time -= 1.0

    def _scan(self) -> None:
        with self._lock:
            lookback_seconds = self._lookback_seconds
            threshold_pct = self._spread_threshold_pct
            min_volume = self._min_volume_usdt
            self._status = "Scanning"

        now = time.time()
        cutoff_time = now - lookback_seconds

        if not self._current_screener():
            with self._lock:
                self._opportunities = {}
                self._status = "Running" if self._enabled else "Idle"
            return

        screener = self._current_screener()
        assert screener is not None
        snapshot, *_ = screener.read_state()
        funding_list = self._cache.get_all_funding()
        funding_by_symbol: dict[str, dict[str, FundingInfo]] = collections.defaultdict(dict)
        for f in funding_list:
            funding_by_symbol[f.symbol][f.exchange_id] = f

        # Prefer order-book quotes from cache when present (executable bid/ask)
        quotes = {
            (q.exchange_id, q.symbol): q
            for q in self._cache.get_all_quotes()
            if q.market_type == "futures"
        }

        by_symbol: dict[str, dict[str, Ticker]] = collections.defaultdict(dict)
        for (ex_id, symbol), ticker in snapshot.items():
            by_symbol[symbol][ex_id] = ticker

        new_opportunities: dict[str, HistoricalOpportunity] = {}

        for symbol, ex_tickers in by_symbol.items():
            if len(ex_tickers) < 2:
                continue

            if min_volume > 0:
                if any((t.quote_volume_24h or 0) < min_volume for t in ex_tickers.values()):
                    continue

            ex_keys = list(ex_tickers.keys())
            for i in range(len(ex_keys)):
                for j in range(i + 1, len(ex_keys)):
                    ex_a = ex_keys[i]
                    ex_b = ex_keys[j]
                    ta = ex_tickers[ex_a]
                    tb = ex_tickers[ex_b]
                    qa = quotes.get((ex_a, symbol))
                    qb = quotes.get((ex_b, symbol))

                    bid_a, ask_a = self._executable_prices(ta, qa)
                    bid_b, ask_b = self._executable_prices(tb, qb)

                    spreads: list[tuple[str, str, float, float, float]] = []
                    # Prefer executable when both legs have full bid/ask; else last (screener display)
                    if (
                        bid_a is not None
                        and ask_a is not None
                        and bid_b is not None
                        and ask_b is not None
                        and ask_a > 0
                        and ask_b > 0
                    ):
                        spreads.append(
                            (ex_a, ex_b, (bid_a - ask_b) / ask_b * 100.0, bid_a, ask_b)
                        )
                        spreads.append(
                            (ex_b, ex_a, (bid_b - ask_a) / ask_a * 100.0, bid_b, ask_a)
                        )
                    last_a = ta.last
                    last_b = tb.last
                    if last_a and last_b and last_a > 0 and last_b > 0:
                        # Always track last-based too so table matches screener rows
                        spreads.append(
                            (ex_a, ex_b, (last_a - last_b) / last_b * 100.0, last_a, last_b)
                        )
                        spreads.append(
                            (ex_b, ex_a, (last_b - last_a) / last_a * 100.0, last_b, last_a)
                        )

                    for short_ex, long_ex, spread, short_px, long_px in spreads:
                        self._update_history(symbol, short_ex, long_ex, spread, now, cutoff_time)
                        max_spread = max(
                            (s for _, s in self._history[symbol][(short_ex, long_ex)]),
                            default=spread,
                        )
                        if max_spread < threshold_pct:
                            continue
                        if (
                            symbol in new_opportunities
                            and max_spread <= new_opportunities[symbol].max_historical_spread_pct
                        ):
                            continue
                        t_short = ex_tickers[short_ex]
                        t_long = ex_tickers[long_ex]
                        new_opportunities[symbol] = self._build_opportunity(
                            symbol,
                            short_ex,
                            long_ex,
                            spread,
                            max_spread,
                            short_px,
                            long_px,
                            funding_by_symbol,
                            t_short,
                            t_long,
                            now,
                            lookback_seconds,
                        )

        with self._lock:
            self._opportunities = new_opportunities
            self._status = "Running" if self._enabled else "Idle"
        logger.debug(
            "historical screener scan done | opps={} symbols_seen={} threshold={}",
            len(new_opportunities),
            len(by_symbol),
            threshold_pct,
        )

    @staticmethod
    def _executable_prices(
        ticker: Ticker, quote: Quote | None
    ) -> tuple[float | None, float | None]:
        if quote is not None and quote.bid is not None and quote.ask is not None:
            return float(quote.bid), float(quote.ask)
        if ticker.bid is not None and ticker.ask is not None:
            return float(ticker.bid), float(ticker.ask)
        return None, None

    def _update_history(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        spread: float,
        now: float,
        cutoff_time: float,
    ) -> None:
        history = self._history[symbol][(short_ex, long_ex)]
        history.append((now, spread))
        while history and history[0][0] < cutoff_time:
            history.popleft()

    def _build_opportunity(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        current_spread_pct: float,
        max_spread_pct: float,
        short_price: float,
        long_price: float,
        funding_dict: dict[str, dict[str, FundingInfo]],
        t_short: Ticker,
        t_long: Ticker,
        now: float,
        lookback_seconds: int,
    ) -> HistoricalOpportunity:
        f_short = funding_dict.get(symbol, {}).get(short_ex)
        f_long = funding_dict.get(symbol, {}).get(long_ex)

        short_rate = 0.0
        if f_short and f_short.rate is not None:
            short_rate = float(f_short.rate * 100)
        elif t_short.funding_rate is not None:
            short_rate = float(t_short.funding_rate * 100)

        long_rate = 0.0
        if f_long and f_long.rate is not None:
            long_rate = float(f_long.rate * 100)
        elif t_long.funding_rate is not None:
            long_rate = float(t_long.funding_rate * 100)

        return HistoricalOpportunity(
            symbol=symbol,
            short_ex=short_ex,
            long_ex=long_ex,
            current_spread_pct=current_spread_pct,
            max_historical_spread_pct=max_spread_pct,
            short_funding_rate=short_rate,
            long_funding_rate=long_rate,
            short_next_funding=(
                float(f_short.next_settlement_ms / 1000)
                if f_short and f_short.next_settlement_ms is not None
                else 0.0
            ),
            long_next_funding=(
                float(f_long.next_settlement_ms / 1000)
                if f_long and f_long.next_settlement_ms is not None
                else 0.0
            ),
            short_price=short_price,
            long_price=long_price,
            short_volume_24h=float(t_short.quote_volume_24h or 0.0),
            long_volume_24h=float(t_long.quote_volume_24h or 0.0),
            detected_at=now,
            lookback_seconds=lookback_seconds,
        )
