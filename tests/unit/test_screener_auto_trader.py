"""Tests for ScreenerAutoTrader._tick open/close/fresh-spread logic.

We drive the worker through _tick() directly — no background thread.
All collaborators are minimal fakes: no IO, no file system, no ccxt.
"""
from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest

from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.screener_auto_trader import ScreenerAutoTrader
from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.execution_outcome import ExecutionOutcome, ExecutionStatus
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.symbol_market_info import SymbolMarketInfo
from arbitrator.domain.ticker import Ticker

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

SYM = "BTC/USDT:USDT"
SHORT_EX = "bitget"
LONG_EX = "gate"

# prices: short higher → positive spread
SHORT_PRICE = 105.0
LONG_PRICE = 100.0
SPREAD_PCT = (SHORT_PRICE - LONG_PRICE) / LONG_PRICE * 100.0  # 5.0 %


def _settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = dict(
        screener_auto_trade_enabled=True,
        screener_auto_trade_max_positions=5,
        screener_auto_trade_open_spread_pct=3.0,
        screener_auto_trade_close_spread_pct=0.05,
        screener_auto_trade_notional_usdt=10.0,
        screener_auto_trade_check_seconds=2.0,
        screener_auto_trade_unhedged_timeout_seconds=10.0,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _ticker(symbol: str, last: float, bid: float | None = None, ask: float | None = None) -> Ticker:
    return Ticker(
        symbol=symbol,
        last=last,
        bid=bid,
        ask=ask,
        high_24h=last,
        low_24h=last,
        base_volume_24h=1.0,
        quote_volume_24h=1_000_000.0,
        timestamp_ms=1_000,
    )


def _market_info(
    min_order_volume_usdt: float | None = 5.0,
    min_amount_contracts: float | None = None,
    contract_size: float = 1.0,
) -> SymbolMarketInfo:
    return SymbolMarketInfo(
        unified_symbol=SYM,
        base_asset="BTC",
        native_market_id=None,
        min_order_volume_usdt=min_order_volume_usdt,
        max_order_volume_usdt=None,
        min_amount_contracts=min_amount_contracts,
        contract_size=contract_size,
    )


def _quote(exchange_id: str, bid: float, ask: float, ts_ms: int = 1_000) -> Quote:
    return Quote(
        exchange_id=exchange_id,
        symbol=SYM,
        market_type="futures",
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        last=Decimal(str((bid + ask) / 2)),
        recv_time_ms=ts_ms,
    )


# ---------------------------------------------------------------------------
# Fake screener worker
# ---------------------------------------------------------------------------

class _FakeScreener:
    """Minimal stand-in for ScreenerStreamWorker.read_state()."""

    def __init__(
        self,
        tickers: dict[tuple[str, str], Ticker],
        status: str = "Live",
    ) -> None:
        self._tickers = tickers
        self._status = status

    def read_state(self) -> Any:
        return self._tickers, [], 0, self._status, 0.0


# ---------------------------------------------------------------------------
# Fake paper execution gateway
# ---------------------------------------------------------------------------

class _FakePaper:
    """Records open_pair / close_pair calls; no PaperOrderStore needed."""

    def __init__(self) -> None:
        self.open_calls: list[dict[str, Any]] = []
        self.close_calls: list[dict[str, Any]] = []
        # Fake store that returns an empty list for load_all()
        self._store = MagicMock()
        self._store.load_all.return_value = []

    def open_pair(self, **kwargs: Any) -> ExecutionOutcome:
        self.open_calls.append(kwargs)
        pair_id = f"pair-{len(self.open_calls)}"
        return ExecutionOutcome(
            action="open",
            status=ExecutionStatus.success,
            symbol=kwargs["symbol"],
            pair_id=pair_id,
        )

    def close_pair(self, **kwargs: Any) -> ExecutionOutcome:
        self.close_calls.append(kwargs)
        return ExecutionOutcome(
            action="close",
            status=ExecutionStatus.success,
            symbol=kwargs["symbol"],
        )


# ---------------------------------------------------------------------------
# Builder for ScreenerAutoTrader
# ---------------------------------------------------------------------------

def _make_trader(
    settings: Settings,
    screener: _FakeScreener,
    paper: _FakePaper,
    cache: MarketDataCacheMemory | None = None,
) -> ScreenerAutoTrader:
    trader = ScreenerAutoTrader(
        settings=settings,
        screener_worker=screener,  # type: ignore[arg-type]
        paper_gateway=paper,  # type: ignore[arg-type]
        market_cache=cache,
        token_identity=None,
    )
    return trader


# ===========================================================================
# Tests: _fresh_spread helper
# ===========================================================================

class TestFreshSpread:
    def test_returns_none_when_no_cache(self) -> None:
        trader = _make_trader(_settings(), _FakeScreener({}), _FakePaper(), cache=None)
        assert trader._fresh_spread(SYM, SHORT_EX, LONG_EX) is None

    def test_returns_none_when_short_quote_missing(self) -> None:
        cache = MarketDataCacheMemory()
        cache.put_quote(_quote(LONG_EX, bid=100.0, ask=100.1))
        trader = _make_trader(_settings(), _FakeScreener({}), _FakePaper(), cache=cache)
        assert trader._fresh_spread(SYM, SHORT_EX, LONG_EX) is None

    def test_returns_none_when_long_quote_missing(self) -> None:
        cache = MarketDataCacheMemory()
        cache.put_quote(_quote(SHORT_EX, bid=105.0, ask=105.2))
        trader = _make_trader(_settings(), _FakeScreener({}), _FakePaper(), cache=cache)
        assert trader._fresh_spread(SYM, SHORT_EX, LONG_EX) is None

    def test_returns_spread_from_bid_ask(self) -> None:
        cache = MarketDataCacheMemory()
        cache.put_quote(_quote(SHORT_EX, bid=105.0, ask=105.5))
        cache.put_quote(_quote(LONG_EX, bid=99.5, ask=100.0))
        trader = _make_trader(_settings(), _FakeScreener({}), _FakePaper(), cache=cache)
        result = trader._fresh_spread(SYM, SHORT_EX, LONG_EX)
        assert result is not None
        fresh_bid, fresh_ask, spread = result
        assert fresh_bid == 105.0
        assert fresh_ask == 100.0
        assert abs(spread - 5.0) < 0.01

    def test_falls_back_to_last_when_bid_ask_absent(self) -> None:
        # Quote with bid=None/ask=None — falls back to last
        cache = MarketDataCacheMemory()
        cache.put_quote(Quote(
            exchange_id=SHORT_EX, symbol=SYM, market_type="futures",
            bid=None, ask=None, last=Decimal("105"), recv_time_ms=1,
        ))
        cache.put_quote(Quote(
            exchange_id=LONG_EX, symbol=SYM, market_type="futures",
            bid=None, ask=None, last=Decimal("100"), recv_time_ms=1,
        ))
        trader = _make_trader(_settings(), _FakeScreener({}), _FakePaper(), cache=cache)
        result = trader._fresh_spread(SYM, SHORT_EX, LONG_EX)
        assert result is not None
        _, _, spread = result
        assert abs(spread - 5.0) < 0.01

    def test_negative_spread_returned_as_is(self) -> None:
        # Inverted market — short cheaper than long
        cache = MarketDataCacheMemory()
        cache.put_quote(_quote(SHORT_EX, bid=98.0, ask=98.5))
        cache.put_quote(_quote(LONG_EX, bid=101.0, ask=101.5))
        trader = _make_trader(_settings(), _FakeScreener({}), _FakePaper(), cache=cache)
        result = trader._fresh_spread(SYM, SHORT_EX, LONG_EX)
        assert result is not None
        _, _, spread = result
        assert spread < 0.0


# ===========================================================================
# Tests: open pass — pre-open spread recheck
# ===========================================================================

def _tickers_with_spread(short_price: float, long_price: float) -> dict[tuple[str, str], Ticker]:
    return {
        (SHORT_EX, SYM): _ticker(SYM, short_price, bid=short_price, ask=short_price + 0.1),
        (LONG_EX, SYM): _ticker(SYM, long_price, bid=long_price - 0.1, ask=long_price),
    }


def _cache_with_quotes_and_info(
    short_bid: float,
    long_ask: float,
    min_usdt: float = 5.0,
) -> MarketDataCacheMemory:
    cache = MarketDataCacheMemory()
    cache.put_quote(_quote(SHORT_EX, bid=short_bid, ask=short_bid + 0.1))
    cache.put_quote(_quote(LONG_EX, bid=long_ask - 0.1, ask=long_ask))
    cache.put_market_info(_market_info(min_order_volume_usdt=min_usdt), SHORT_EX)
    cache.put_market_info(_market_info(min_order_volume_usdt=min_usdt), LONG_EX)
    return cache


class TestOpenPassFreshRecheck:
    def test_opens_when_fresh_spread_still_above_threshold(self) -> None:
        """Ticker snapshot: 5% spread. Fresh cache quotes: still 5% → open."""
        settings = _settings(screener_auto_trade_open_spread_pct=3.0)
        paper = _FakePaper()
        tickers = _tickers_with_spread(SHORT_PRICE, LONG_PRICE)
        cache = _cache_with_quotes_and_info(SHORT_PRICE, LONG_PRICE)

        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._tick()

        assert len(paper.open_calls) == 1
        call = paper.open_calls[0]
        assert call["symbol"] == SYM
        assert call["short_exchange_id"] == SHORT_EX
        assert call["long_exchange_id"] == LONG_EX
        # Prices come from fresh cache, not ticker snapshot
        assert call["short_price"] == SHORT_PRICE
        assert call["long_price"] == LONG_PRICE

    def test_skips_when_fresh_spread_dropped_below_threshold(self) -> None:
        """Ticker snapshot shows 5% spread. By the time all checks pass,
        fresh cache quotes show only 1% → must NOT open."""
        settings = _settings(screener_auto_trade_open_spread_pct=3.0)
        paper = _FakePaper()
        # Ticker snapshot: short=105, long=100 → 5% spread (passes first filter)
        tickers = _tickers_with_spread(SHORT_PRICE, LONG_PRICE)
        # Fresh cache: spread collapsed to 1%
        stale_short_bid = 101.0
        stale_long_ask = 100.0
        cache = _cache_with_quotes_and_info(stale_short_bid, stale_long_ask)

        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._tick()

        assert len(paper.open_calls) == 0

    def test_uses_fresh_prices_for_open_pair(self) -> None:
        """The actual open_pair call must use fresh bid/ask, not ticker snapshot prices."""
        settings = _settings(screener_auto_trade_open_spread_pct=3.0)
        paper = _FakePaper()
        # Ticker: short=105, long=100
        tickers = _tickers_with_spread(SHORT_PRICE, LONG_PRICE)
        # Fresh quotes: slightly different (still above threshold)
        fresh_short_bid = 106.0
        fresh_long_ask = 100.5
        cache = _cache_with_quotes_and_info(fresh_short_bid, fresh_long_ask)

        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._tick()

        assert len(paper.open_calls) == 1
        call = paper.open_calls[0]
        assert call["short_price"] == fresh_short_bid
        assert call["long_price"] == fresh_long_ask

    def test_skips_when_no_cache_available(self) -> None:
        """No market_cache injected → _fresh_spread returns None → no open."""
        settings = _settings(screener_auto_trade_open_spread_pct=3.0)
        paper = _FakePaper()
        tickers = _tickers_with_spread(SHORT_PRICE, LONG_PRICE)

        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache=None)
        trader._tick()

        assert len(paper.open_calls) == 0

    def test_skips_when_screener_not_live(self) -> None:
        """Status != 'Live' → entire tick is a no-op."""
        paper = _FakePaper()
        tickers = _tickers_with_spread(SHORT_PRICE, LONG_PRICE)
        screener = _FakeScreener(tickers, status="Loading")
        cache = _cache_with_quotes_and_info(SHORT_PRICE, LONG_PRICE)
        trader = _make_trader(_settings(), screener, paper, cache)
        trader._tick()
        assert len(paper.open_calls) == 0

    def test_anomaly_guard_blocks_excessive_spread(self) -> None:
        """Fresh spread > anomaly_max_spread_pct → blocked as likely different tokens.

        This catches the EDGE/USDT case: mexc EDGE ~$0.27 vs gate EDGE ~$0.07
        — same ticker symbol, different projects, 277% 'spread'.
        """
        # anomaly_max_spread_pct default is 20.0 in settings
        settings = _settings(screener_auto_trade_open_spread_pct=3.0)

        # Prices that simulate two different tokens: ~277% spread
        anomalous_short = 0.2663
        anomalous_long = 0.0706
        sym = "EDGE/USDT:USDT"

        tickers: dict[tuple[str, str], Ticker] = {
            (SHORT_EX, sym): _ticker(sym, anomalous_short, bid=anomalous_short),
            (LONG_EX, sym): _ticker(sym, anomalous_long, ask=anomalous_long),
        }
        cache = MarketDataCacheMemory()
        cache.put_quote(Quote(
            exchange_id=SHORT_EX, symbol=sym, market_type="futures",
            bid=Decimal(str(anomalous_short)), ask=Decimal(str(anomalous_short + 0.001)),
            last=Decimal(str(anomalous_short)), recv_time_ms=1,
        ))
        cache.put_quote(Quote(
            exchange_id=LONG_EX, symbol=sym, market_type="futures",
            bid=Decimal(str(anomalous_long - 0.001)), ask=Decimal(str(anomalous_long)),
            last=Decimal(str(anomalous_long)), recv_time_ms=1,
        ))
        edge_info = SymbolMarketInfo(
            unified_symbol=sym, base_asset="EDGE", native_market_id=None,
            min_order_volume_usdt=5.0, max_order_volume_usdt=None,
            min_amount_contracts=None, contract_size=1.0,
        )
        cache.put_market_info(edge_info, SHORT_EX)
        cache.put_market_info(edge_info, LONG_EX)

        paper = _FakePaper()
        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._tick()

        assert len(paper.open_calls) == 0, "anomaly spread must block the order"


# ===========================================================================
# Tests: notional = max(exchange_min, settings_notional)
# ===========================================================================

class TestNotionalFloor:
    def test_settings_notional_wins_when_larger_than_exchange_min(self) -> None:
        """Settings notional 100 USDT > exchange min 5 USDT → amount = 100 / short_price."""
        settings = _settings(screener_auto_trade_notional_usdt=100.0)
        paper = _FakePaper()
        tickers = _tickers_with_spread(SHORT_PRICE, LONG_PRICE)
        cache = _cache_with_quotes_and_info(SHORT_PRICE, LONG_PRICE, min_usdt=5.0)

        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._tick()

        assert len(paper.open_calls) == 1
        expected_amount = 100.0 / SHORT_PRICE
        assert abs(paper.open_calls[0]["amount"] - expected_amount) < 1e-8

    def test_exchange_min_wins_when_larger_than_settings_notional(self) -> None:
        """Exchange min 50 USDT > settings notional 10 USDT → amount = 50 / short_price."""
        settings = _settings(screener_auto_trade_notional_usdt=10.0)
        paper = _FakePaper()
        tickers = _tickers_with_spread(SHORT_PRICE, LONG_PRICE)
        cache = _cache_with_quotes_and_info(SHORT_PRICE, LONG_PRICE, min_usdt=50.0)

        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._tick()

        assert len(paper.open_calls) == 1
        expected_amount = 50.0 / SHORT_PRICE
        assert abs(paper.open_calls[0]["amount"] - expected_amount) < 1e-8

    def test_zero_settings_notional_uses_exchange_min(self) -> None:
        """Settings notional 0 → always uses exchange minimum."""
        settings = _settings(screener_auto_trade_notional_usdt=0.0)
        paper = _FakePaper()
        tickers = _tickers_with_spread(SHORT_PRICE, LONG_PRICE)
        cache = _cache_with_quotes_and_info(SHORT_PRICE, LONG_PRICE, min_usdt=5.0)

        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._tick()

        assert len(paper.open_calls) == 1
        expected_amount = 5.0 / SHORT_PRICE
        assert abs(paper.open_calls[0]["amount"] - expected_amount) < 1e-8


# ===========================================================================
# Tests: market info absent → fail-closed
# ===========================================================================

class TestMarketInfoFailClosed:
    def test_no_open_when_short_exchange_market_info_missing(self) -> None:
        settings = _settings()
        paper = _FakePaper()
        tickers = _tickers_with_spread(SHORT_PRICE, LONG_PRICE)
        cache = MarketDataCacheMemory()
        # Only long exchange has market info
        cache.put_quote(_quote(SHORT_EX, bid=SHORT_PRICE, ask=SHORT_PRICE + 0.1))
        cache.put_quote(_quote(LONG_EX, bid=LONG_PRICE - 0.1, ask=LONG_PRICE))
        cache.put_market_info(_market_info(), LONG_EX)

        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._tick()
        assert len(paper.open_calls) == 0

    def test_no_open_when_long_exchange_market_info_missing(self) -> None:
        settings = _settings()
        paper = _FakePaper()
        tickers = _tickers_with_spread(SHORT_PRICE, LONG_PRICE)
        cache = MarketDataCacheMemory()
        cache.put_quote(_quote(SHORT_EX, bid=SHORT_PRICE, ask=SHORT_PRICE + 0.1))
        cache.put_quote(_quote(LONG_EX, bid=LONG_PRICE - 0.1, ask=LONG_PRICE))
        cache.put_market_info(_market_info(), SHORT_EX)
        # long exchange market info absent

        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._tick()
        assert len(paper.open_calls) == 0

    def test_opens_once_both_market_infos_present(self) -> None:
        settings = _settings()
        paper = _FakePaper()
        tickers = _tickers_with_spread(SHORT_PRICE, LONG_PRICE)
        cache = _cache_with_quotes_and_info(SHORT_PRICE, LONG_PRICE)

        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._tick()
        assert len(paper.open_calls) == 1


# ===========================================================================
# Tests: max_positions cap
# ===========================================================================

class TestMaxPositions:
    def _two_symbol_tickers(self) -> dict[tuple[str, str], Ticker]:
        sym2 = "ETH/USDT:USDT"
        return {
            (SHORT_EX, SYM): _ticker(SYM, 105.0, bid=105.0),
            (LONG_EX, SYM): _ticker(SYM, 100.0, ask=100.0),
            (SHORT_EX, sym2): _ticker(sym2, 210.0, bid=210.0),
            (LONG_EX, sym2): _ticker(sym2, 200.0, ask=200.0),
        }

    def _cache_for_two(self) -> MarketDataCacheMemory:
        sym2 = "ETH/USDT:USDT"
        cache = MarketDataCacheMemory()
        for ex, sym, bid, ask in [
            (SHORT_EX, SYM, 105.0, 105.1),
            (LONG_EX, SYM, 99.9, 100.0),
            (SHORT_EX, sym2, 210.0, 210.2),
            (LONG_EX, sym2, 199.8, 200.0),
        ]:
            q = Quote(
                exchange_id=ex,
                symbol=sym,
                market_type="futures",
                bid=Decimal(str(bid)),
                ask=Decimal(str(ask)),
                last=Decimal(str((bid + ask) / 2)),
                recv_time_ms=1_000,
            )
            cache.put_quote(q)
        for sym in (SYM, sym2):
            info = SymbolMarketInfo(
                unified_symbol=sym,
                base_asset=sym.split("/")[0],
                native_market_id=None,
                min_order_volume_usdt=5.0,
                max_order_volume_usdt=None,
                min_amount_contracts=None,
                contract_size=1.0,
            )
            cache.put_market_info(info, SHORT_EX)
            cache.put_market_info(info, LONG_EX)
        return cache

    def test_respects_max_positions_limit(self) -> None:
        settings = _settings(screener_auto_trade_max_positions=1)
        paper = _FakePaper()
        tickers = self._two_symbol_tickers()
        cache = self._cache_for_two()

        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._tick()

        assert len(paper.open_calls) == 1

    def test_opens_up_to_max_positions(self) -> None:
        settings = _settings(screener_auto_trade_max_positions=2)
        paper = _FakePaper()
        tickers = self._two_symbol_tickers()
        cache = self._cache_for_two()

        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._tick()

        assert len(paper.open_calls) == 2


# ===========================================================================
# Tests: close pass — uses stored amount, not live price
# ===========================================================================

class TestClosePass:
    def test_closes_tracked_pair_when_spread_collapses(self) -> None:
        """A tracked pair with exit_spread <= close_spread must be closed."""
        settings = _settings(screener_auto_trade_close_spread_pct=0.5)
        paper = _FakePaper()

        # Ticker: exit spread = 0.1% (short ask ≈ long bid)
        short_ask = 100.1
        long_bid = 100.0
        tickers: dict[tuple[str, str], Ticker] = {
            (SHORT_EX, SYM): _ticker(SYM, short_ask, bid=short_ask - 0.1, ask=short_ask),
            (LONG_EX, SYM): _ticker(SYM, long_bid, bid=long_bid, ask=long_bid + 0.1),
        }

        # Pre-populate open pair
        pair_id = "abc123"
        from arbitrator.domain.paper_order import PaperOrder
        stored_amount = 0.5
        open_record = MagicMock(spec=PaperOrder)
        open_record.pair_id = pair_id
        open_record.side = "buy"
        open_record.action = "open"
        open_record.status = "filled"
        open_record.amount = stored_amount

        paper._store.load_all.return_value = [open_record]

        cache = MarketDataCacheMemory()
        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        # Inject the open pair directly
        trader._open_pairs[pair_id] = (SYM, SHORT_EX, LONG_EX)

        trader._tick()

        assert len(paper.close_calls) == 1
        call = paper.close_calls[0]
        assert call["pair_id"] == pair_id
        assert call["amount"] == stored_amount

    def test_does_not_close_when_spread_still_above_close_threshold(self) -> None:
        settings = _settings(screener_auto_trade_close_spread_pct=0.5)
        paper = _FakePaper()

        # Exit spread = 3% — still well above close threshold
        tickers = _tickers_with_spread(SHORT_PRICE, LONG_PRICE)
        pair_id = "xyz987"

        from arbitrator.domain.paper_order import PaperOrder
        open_record = MagicMock(spec=PaperOrder)
        open_record.pair_id = pair_id
        open_record.side = "buy"
        open_record.action = "open"
        open_record.status = "filled"
        open_record.amount = 0.5
        paper._store.load_all.return_value = [open_record]

        cache = _cache_with_quotes_and_info(SHORT_PRICE, LONG_PRICE)
        trader = _make_trader(settings, _FakeScreener(tickers), paper, cache)
        trader._open_pairs[pair_id] = (SYM, SHORT_EX, LONG_EX)

        trader._tick()
        assert len(paper.close_calls) == 0


# ===========================================================================
# Tests: _resolve_min_notional
# ===========================================================================

class TestResolveMinNotional:
    def test_returns_none_when_market_cache_absent(self) -> None:
        trader = _make_trader(_settings(), _FakeScreener({}), _FakePaper(), cache=None)
        result = trader._resolve_min_notional(SYM, SHORT_EX, LONG_EX, SHORT_PRICE, LONG_PRICE)
        assert result is None

    def test_returns_none_when_either_info_missing(self) -> None:
        cache = MarketDataCacheMemory()
        cache.put_market_info(_market_info(min_order_volume_usdt=5.0), SHORT_EX)
        # LONG_EX market info intentionally absent
        trader = _make_trader(_settings(), _FakeScreener({}), _FakePaper(), cache=cache)
        result = trader._resolve_min_notional(SYM, SHORT_EX, LONG_EX, SHORT_PRICE, LONG_PRICE)
        assert result is None

    def test_returns_max_of_both_exchange_mins_and_settings_floor(self) -> None:
        """max(10, 15, settings=20) → 20."""
        settings = _settings(screener_auto_trade_notional_usdt=20.0)
        cache = MarketDataCacheMemory()
        cache.put_market_info(_market_info(min_order_volume_usdt=10.0), SHORT_EX)
        cache.put_market_info(_market_info(min_order_volume_usdt=15.0), LONG_EX)
        trader = _make_trader(settings, _FakeScreener({}), _FakePaper(), cache=cache)
        result = trader._resolve_min_notional(SYM, SHORT_EX, LONG_EX, SHORT_PRICE, LONG_PRICE)
        assert result == pytest.approx(20.0)

    def test_exchange_min_wins_over_settings_floor(self) -> None:
        """max(50, 5, settings=10) → 50."""
        settings = _settings(screener_auto_trade_notional_usdt=10.0)
        cache = MarketDataCacheMemory()
        cache.put_market_info(_market_info(min_order_volume_usdt=50.0), SHORT_EX)
        cache.put_market_info(_market_info(min_order_volume_usdt=5.0), LONG_EX)
        trader = _make_trader(settings, _FakeScreener({}), _FakePaper(), cache=cache)
        result = trader._resolve_min_notional(SYM, SHORT_EX, LONG_EX, SHORT_PRICE, LONG_PRICE)
        assert result == pytest.approx(50.0)

    def test_contract_unit_limit_computed_from_price(self) -> None:
        """mexc-style: min_amount=1 contract, contract_size=0.001 BTC, price=100 → 0.1 USDT min.
        Settings floor 10 wins."""
        settings = _settings(screener_auto_trade_notional_usdt=10.0)
        cache = MarketDataCacheMemory()
        info = _market_info(min_order_volume_usdt=None, min_amount_contracts=1.0, contract_size=0.001)
        cache.put_market_info(info, SHORT_EX)
        cache.put_market_info(_market_info(min_order_volume_usdt=5.0), LONG_EX)
        trader = _make_trader(settings, _FakeScreener({}), _FakePaper(), cache=cache)
        # short min = 1 * 0.001 * 100 = 0.1, long min = 5, settings = 10 → 10
        result = trader._resolve_min_notional(SYM, SHORT_EX, LONG_EX, 100.0, 100.0)
        assert result == pytest.approx(10.0)
