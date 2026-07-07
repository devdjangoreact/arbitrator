"""Tests for LiveAutoTrader._tick open/close/restore logic.

All tests call _tick() directly via asyncio.run — no background thread started.
Collaborators are minimal async fakes.
"""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal
from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock

import pytest

from arbitrator.application.live_auto_trader import LiveAutoTrader
from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.settings import Settings
from arbitrator.domain.order_book_level import OrderBookLevel
from arbitrator.domain.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.domain.strategy.execution_outcome import ExecutionOutcome, ExecutionStatus
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.symbol_market_info import SymbolMarketInfo
from arbitrator.domain.ticker import Ticker

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYM = "BTC/USDT:USDT"
SHORT_EX = "bitget"
LONG_EX = "gate"
SHORT_PRICE = 105.0
LONG_PRICE = 100.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = dict(
        screener_auto_trade_max_positions=5,
        screener_auto_trade_open_spread_pct=3.0,
        screener_auto_trade_close_spread_pct=0.5,
        screener_auto_trade_notional_usdt=10.0,
        screener_auto_trade_check_seconds=2.0,
        screener_auto_trade_unhedged_timeout_seconds=10.0,
        anomaly_max_spread_pct=20.0,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _ticker(symbol: str, last: float, bid: float | None = None, ask: float | None = None) -> Ticker:
    return Ticker(
        symbol=symbol, last=last, bid=bid, ask=ask,
        high_24h=last, low_24h=last,
        base_volume_24h=1.0, quote_volume_24h=1_000_000.0, timestamp_ms=1_000,
    )


def _quote(exchange_id: str, symbol: str, bid: float, ask: float) -> Quote:
    import time as _time
    return Quote(
        exchange_id=exchange_id, symbol=symbol, market_type="futures",
        bid=Decimal(str(bid)), ask=Decimal(str(ask)),
        last=Decimal(str((bid + ask) / 2)), recv_time_ms=int(_time.time() * 1000),
    )


def _market_info(symbol: str = SYM, base: str = "BTC", min_usdt: float = 5.0) -> SymbolMarketInfo:
    return SymbolMarketInfo(
        unified_symbol=symbol, base_asset=base, native_market_id=None,
        min_order_volume_usdt=min_usdt, max_order_volume_usdt=None,
        min_amount_contracts=None, contract_size=1.0,
    )


def _make_position_leg(
    exchange_id: str,
    symbol: str,
    side: Literal["long", "short"],
    contracts: float = 0.1,
) -> PositionLeg:
    from datetime import UTC, datetime
    return PositionLeg(
        exchange_id=exchange_id, display_name=exchange_id, symbol=symbol,
        side=side, contracts=contracts, contract_size=1.0,
        entry_price=100.0, mark_price=100.0,
        opened_at=datetime.now(UTC),
        unrealized_pnl=0.0, accrued_funding=0.0,
        opening_fee=0.01, estimated_close_fee=0.01,
        next_funding_at=None, arb_marker_id=None, position_id="pos-1",
    )


# ---------------------------------------------------------------------------
# Fake screener
# ---------------------------------------------------------------------------

class _FakeScreener:
    def __init__(self, tickers: dict[tuple[str, str], Ticker], status: str = "Live") -> None:
        self._tickers = tickers
        self._status = status

    def read_state(self) -> Any:
        return self._tickers, [], 0, self._status, 0.0


# ---------------------------------------------------------------------------
# Fake gateway
# ---------------------------------------------------------------------------

def _order_book(exchange_id: str, symbol: str, bid: float, ask: float) -> OrderBookSnapshot:
    return OrderBookSnapshot(
        exchange_id=exchange_id,
        symbol=symbol,
        timestamp_ms=int(time.time() * 1000),
        bids=(OrderBookLevel(price=bid, size=10000.0),),
        asks=(OrderBookLevel(price=ask, size=10000.0),),
    )


class _FakeGateway:
    def __init__(
        self,
        positions: list[PositionLeg] | None = None,
        exchange_id: str = "",
        book_bid: float = 0.0,
        book_ask: float = 0.0,
    ) -> None:
        self._positions = positions or []
        self._exchange_id = exchange_id
        self._book_bid = book_bid
        self._book_ask = book_ask
        self.fetch_count = 0
        self.open_calls: list[tuple[str, str, float, str]] = []
        self.close_calls: list[PositionLeg] = []

    async def open_market_position(
        self, symbol: str, side: Literal["buy", "sell"], amount: float, client_order_id: str
    ) -> str:
        self.open_calls.append((symbol, side, amount, client_order_id))
        return "order-live-1"

    async def close_market_position(self, leg: PositionLeg) -> str:
        self.close_calls.append(leg)
        return "close-live-1"

    async def fetch_open_positions(self) -> list[PositionLeg]:
        return list(self._positions)

    async def fetch_order_book_once(self, symbol: str, limit: int) -> OrderBookSnapshot:
        self.fetch_count += 1
        return _order_book(self._exchange_id, symbol, self._book_bid, self._book_ask)


# ---------------------------------------------------------------------------
# Fake HedgedExecutionService
# ---------------------------------------------------------------------------

class _FakeExecService:
    """Fake that records open/close calls and returns configurable outcomes."""

    def __init__(
        self,
        open_status: ExecutionStatus = ExecutionStatus.success,
        gateways: dict[str, _FakeGateway] | None = None,
    ) -> None:
        self.open_calls: list[dict[str, Any]] = []
        self.close_calls: list[dict[str, Any]] = []
        self._open_status = open_status
        self._gateways = gateways or {
            SHORT_EX: _FakeGateway(exchange_id=SHORT_EX, book_bid=SHORT_PRICE, book_ask=SHORT_PRICE + 0.1),
            LONG_EX: _FakeGateway(exchange_id=LONG_EX, book_bid=LONG_PRICE - 0.1, book_ask=LONG_PRICE),
        }

    async def open(self, **kwargs: Any) -> ExecutionOutcome:
        self.open_calls.append(kwargs)
        return ExecutionOutcome(
            action="open", status=self._open_status,
            symbol=kwargs["symbol"], imbalance_pct=Decimal("0"),
        )

    async def close_all(self, **kwargs: Any) -> ExecutionOutcome:
        self.close_calls.append(kwargs)
        return ExecutionOutcome(
            action="close_all", status=ExecutionStatus.success,
            symbol=kwargs["symbol"], imbalance_pct=Decimal("0"),
        )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _make_trader(
    settings: Settings,
    screener: _FakeScreener,
    exec_service: _FakeExecService,
    cache: MarketDataCacheMemory,
) -> LiveAutoTrader:
    trader = LiveAutoTrader(
        settings=settings,
        screener_worker=screener,  # type: ignore[arg-type]
        execution_service=exec_service,  # type: ignore[arg-type]
        market_cache=cache,
        token_identity=None,
        gateways=exec_service._gateways,  # type: ignore[arg-type]
    )
    return trader


def _cache_with_data(
    short_bid: float = SHORT_PRICE,
    long_ask: float = LONG_PRICE,
    min_usdt: float = 5.0,
) -> MarketDataCacheMemory:
    cache = MarketDataCacheMemory()
    cache.put_quote(_quote(SHORT_EX, SYM, bid=short_bid, ask=short_bid + 0.1))
    cache.put_quote(_quote(LONG_EX, SYM, bid=long_ask - 0.1, ask=long_ask))
    cache.put_market_info(_market_info(min_usdt=min_usdt), SHORT_EX)
    cache.put_market_info(_market_info(min_usdt=min_usdt), LONG_EX)
    return cache


def _tickers(short: float = SHORT_PRICE, long: float = LONG_PRICE) -> dict[tuple[str, str], Ticker]:
    return {
        (SHORT_EX, SYM): _ticker(SYM, short, bid=short, ask=short + 0.1),
        (LONG_EX, SYM): _ticker(SYM, long, bid=long - 0.1, ask=long),
    }


# ===========================================================================
# Tests: open pass
# ===========================================================================

class TestOpenPass:
    def test_opens_when_spread_above_threshold(self) -> None:
        settings = _settings(screener_auto_trade_open_spread_pct=3.0)
        exec_svc = _FakeExecService()
        trader = _make_trader(settings, _FakeScreener(_tickers()), exec_svc, _cache_with_data())

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 1
        call = exec_svc.open_calls[0]
        assert call["symbol"] == SYM
        assert call["short_exchange_id"] == SHORT_EX
        assert call["long_exchange_id"] == LONG_EX
        assert call["notional_usdt"] >= Decimal("5")

    def test_candidate_scan_does_not_rest_fetch_before_open_gate(self) -> None:
        """Ranking uses cache/ticker; REST runs only on fresh open/close checks."""
        settings = _settings(screener_auto_trade_open_spread_pct=10.0)
        exec_svc = _FakeExecService()
        trader = _make_trader(settings, _FakeScreener(_tickers()), exec_svc, _cache_with_data())

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 0
        for gw in exec_svc._gateways.values():
            assert gw.fetch_count == 0

    def test_open_confirmation_fetches_fresh_order_books(self) -> None:
        settings = _settings(screener_auto_trade_open_spread_pct=3.0)
        exec_svc = _FakeExecService()
        trader = _make_trader(settings, _FakeScreener(_tickers()), exec_svc, _cache_with_data())

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 1
        assert exec_svc._gateways[SHORT_EX].fetch_count >= 1
        assert exec_svc._gateways[LONG_EX].fetch_count >= 1

    def test_skips_when_spread_below_threshold(self) -> None:
        settings = _settings(screener_auto_trade_open_spread_pct=10.0)  # 5% spread < 10%
        exec_svc = _FakeExecService()
        trader = _make_trader(settings, _FakeScreener(_tickers()), exec_svc, _cache_with_data())

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 0

    def test_skips_when_screener_not_live(self) -> None:
        exec_svc = _FakeExecService()
        screener = _FakeScreener(_tickers(), status="Loading")
        trader = _make_trader(_settings(), screener, exec_svc, _cache_with_data())

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 0

    def test_skips_when_market_info_missing(self) -> None:
        cache = MarketDataCacheMemory()
        cache.put_quote(_quote(SHORT_EX, SYM, bid=SHORT_PRICE, ask=SHORT_PRICE + 0.1))
        cache.put_quote(_quote(LONG_EX, SYM, bid=LONG_PRICE - 0.1, ask=LONG_PRICE))
        # no market info for either exchange
        exec_svc = _FakeExecService()
        trader = _make_trader(_settings(), _FakeScreener(_tickers()), exec_svc, cache)

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 0

    def test_skips_when_book_spread_dropped(self) -> None:
        """Ticker snapshot: 5% spread. Order book: collapsed to 0.1% → skip."""
        settings = _settings(screener_auto_trade_open_spread_pct=3.0)
        cache = _cache_with_data(short_bid=100.1, long_ask=100.0)
        exec_svc = _FakeExecService(gateways={
            SHORT_EX: _FakeGateway(exchange_id=SHORT_EX, book_bid=100.1, book_ask=100.2),
            LONG_EX: _FakeGateway(exchange_id=LONG_EX, book_bid=99.9, book_ask=100.0),
        })
        trader = _make_trader(settings, _FakeScreener(_tickers()), exec_svc, cache)

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 0

    def test_anomaly_spread_blocked(self) -> None:
        """Fresh spread > anomaly_max (20%) must be blocked."""
        settings = _settings(anomaly_max_spread_pct=20.0, screener_auto_trade_open_spread_pct=3.0)
        cache = _cache_with_data(short_bid=0.267, long_ask=0.071)
        tickers = {
            (SHORT_EX, SYM): _ticker(SYM, 0.267, bid=0.267, ask=0.268),
            (LONG_EX, SYM): _ticker(SYM, 0.071, bid=0.070, ask=0.071),
        }
        exec_svc = _FakeExecService(gateways={
            SHORT_EX: _FakeGateway(exchange_id=SHORT_EX, book_bid=0.267, book_ask=0.268),
            LONG_EX: _FakeGateway(exchange_id=LONG_EX, book_bid=0.070, book_ask=0.071),
        })
        trader = _make_trader(settings, _FakeScreener(tickers), exec_svc, cache)

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 0

    def test_max_positions_cap(self) -> None:
        settings = _settings(screener_auto_trade_max_positions=1)
        exec_svc = _FakeExecService()
        trader = _make_trader(settings, _FakeScreener(_tickers()), exec_svc, _cache_with_data())
        # Pre-fill one position
        trader._open_pairs[("OTHER/USDT:USDT", SHORT_EX, LONG_EX)] = 0.0

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 0

    def test_notional_uses_settings_floor_when_larger(self) -> None:
        """Settings floor 50 USDT > exchange min 5 USDT → notional = 50."""
        settings = _settings(screener_auto_trade_notional_usdt=50.0)
        exec_svc = _FakeExecService()
        trader = _make_trader(settings, _FakeScreener(_tickers()), exec_svc, _cache_with_data(min_usdt=5.0))

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 1
        assert exec_svc.open_calls[0]["notional_usdt"] == pytest.approx(Decimal("50"), abs=Decimal("1"))

    def test_notional_uses_exchange_min_when_larger(self) -> None:
        """Exchange min 30 USDT > settings floor 10 USDT → notional = 30."""
        settings = _settings(screener_auto_trade_notional_usdt=10.0)
        exec_svc = _FakeExecService()
        trader = _make_trader(settings, _FakeScreener(_tickers()), exec_svc, _cache_with_data(min_usdt=30.0))

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 1
        assert exec_svc.open_calls[0]["notional_usdt"] == pytest.approx(Decimal("30"), abs=Decimal("1"))

    def test_pair_tracked_after_successful_open(self) -> None:
        exec_svc = _FakeExecService(open_status=ExecutionStatus.success)
        trader = _make_trader(_settings(), _FakeScreener(_tickers()), exec_svc, _cache_with_data())

        asyncio.run(trader._tick())

        assert len(trader._open_pairs) == 1
        assert (SYM, SHORT_EX, LONG_EX) in trader._open_pairs

    def test_pair_not_tracked_on_failed_open(self) -> None:
        exec_svc = _FakeExecService(open_status=ExecutionStatus.failed)
        trader = _make_trader(_settings(), _FakeScreener(_tickers()), exec_svc, _cache_with_data())

        asyncio.run(trader._tick())

        assert len(trader._open_pairs) == 0

    def test_no_duplicate_open_for_same_symbol(self) -> None:
        exec_svc = _FakeExecService()
        trader = _make_trader(_settings(), _FakeScreener(_tickers()), exec_svc, _cache_with_data())
        # Already open
        trader._open_pairs[(SYM, SHORT_EX, LONG_EX)] = 0.0

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 0

    def test_skips_exchange_without_gateway(self) -> None:
        """If short_ex has no gateway in exec service → skip."""
        exec_svc = _FakeExecService(gateways={LONG_EX: _FakeGateway()})  # SHORT_EX missing
        trader = _make_trader(_settings(), _FakeScreener(_tickers()), exec_svc, _cache_with_data())

        asyncio.run(trader._tick())

        assert len(exec_svc.open_calls) == 0


# ===========================================================================
# Tests: close pass
# ===========================================================================

class TestClosePass:
    def test_closes_when_spread_collapses(self) -> None:
        settings = _settings(screener_auto_trade_close_spread_pct=0.5)
        # exit spread ≈ 0.1% — below threshold
        tickers = {
            (SHORT_EX, SYM): _ticker(SYM, 100.1, bid=100.0, ask=100.1),
            (LONG_EX, SYM): _ticker(SYM, 100.0, bid=100.0, ask=100.1),
        }
        exec_svc = _FakeExecService(gateways={
            SHORT_EX: _FakeGateway(exchange_id=SHORT_EX, book_bid=100.0, book_ask=100.1),
            LONG_EX: _FakeGateway(exchange_id=LONG_EX, book_bid=100.0, book_ask=100.1),
        })
        cache = MarketDataCacheMemory()
        cache.put_quote(_quote(SHORT_EX, SYM, bid=100.0, ask=100.1))
        cache.put_quote(_quote(LONG_EX, SYM, bid=100.0, ask=100.1))
        trader = _make_trader(settings, _FakeScreener(tickers), exec_svc, cache)
        trader._open_pairs[(SYM, SHORT_EX, LONG_EX)] = 0.0

        asyncio.run(trader._tick())

        assert len(exec_svc.close_calls) == 1
        assert exec_svc.close_calls[0]["symbol"] == SYM
        assert (SYM, SHORT_EX, LONG_EX) not in trader._open_pairs

    def test_does_not_close_when_spread_still_open(self) -> None:
        settings = _settings(screener_auto_trade_close_spread_pct=0.5)
        exec_svc = _FakeExecService()
        trader = _make_trader(settings, _FakeScreener(_tickers()), exec_svc, _cache_with_data())
        trader._open_pairs[(SYM, SHORT_EX, LONG_EX)] = 0.0

        asyncio.run(trader._tick())

        # spread is 5% >> close threshold 0.5% → should NOT close
        assert len(exec_svc.close_calls) == 0
        assert (SYM, SHORT_EX, LONG_EX) in trader._open_pairs


# ===========================================================================
# Tests: restore open pairs from exchange positions
# ===========================================================================

class TestRestoreOpenPairs:
    def test_restores_pair_from_short_and_long_positions(self) -> None:
        short_leg = _make_position_leg(SHORT_EX, SYM, "short")
        long_leg = _make_position_leg(LONG_EX, SYM, "long")
        gateways = {
            SHORT_EX: _FakeGateway(positions=[short_leg]),
            LONG_EX: _FakeGateway(positions=[long_leg]),
        }
        exec_svc = _FakeExecService(gateways=gateways)
        trader = _make_trader(_settings(), _FakeScreener({}), exec_svc, MarketDataCacheMemory())

        asyncio.run(trader._restore_open_pairs())

        assert (SYM, SHORT_EX, LONG_EX) in trader._open_pairs

    def test_does_not_restore_when_only_one_leg(self) -> None:
        """Only a short position on one exchange, no matching long → no pair."""
        short_leg = _make_position_leg(SHORT_EX, SYM, "short")
        gateways = {
            SHORT_EX: _FakeGateway(positions=[short_leg]),
            LONG_EX: _FakeGateway(positions=[]),
        }
        exec_svc = _FakeExecService(gateways=gateways)
        trader = _make_trader(_settings(), _FakeScreener({}), exec_svc, MarketDataCacheMemory())

        asyncio.run(trader._restore_open_pairs())

        assert len(trader._open_pairs) == 0

    def test_restores_multiple_symbols(self) -> None:
        sym2 = "ETH/USDT:USDT"
        gateways = {
            SHORT_EX: _FakeGateway(positions=[
                _make_position_leg(SHORT_EX, SYM, "short"),
                _make_position_leg(SHORT_EX, sym2, "short"),
            ]),
            LONG_EX: _FakeGateway(positions=[
                _make_position_leg(LONG_EX, SYM, "long"),
                _make_position_leg(LONG_EX, sym2, "long"),
            ]),
        }
        exec_svc = _FakeExecService(gateways=gateways)
        trader = _make_trader(_settings(), _FakeScreener({}), exec_svc, MarketDataCacheMemory())

        asyncio.run(trader._restore_open_pairs())

        assert len(trader._open_pairs) == 2
        assert (SYM, SHORT_EX, LONG_EX) in trader._open_pairs
        assert (sym2, SHORT_EX, LONG_EX) in trader._open_pairs

    def test_handles_fetch_exception_gracefully(self) -> None:
        """If one exchange throws, restoration continues with the others."""
        class _ErrorGateway:
            async def fetch_open_positions(self) -> list[PositionLeg]:
                raise RuntimeError("connection refused")

        long_leg = _make_position_leg(LONG_EX, SYM, "long")
        exec_svc = _FakeExecService(gateways={
            SHORT_EX: _ErrorGateway(),  # type: ignore[dict-item]
            LONG_EX: _FakeGateway(positions=[long_leg]),
        })
        trader = _make_trader(_settings(), _FakeScreener({}), exec_svc, MarketDataCacheMemory())

        # Must not raise
        asyncio.run(trader._restore_open_pairs())
        # No pair because short side errored out
        assert len(trader._open_pairs) == 0


# ===========================================================================
# Tests: _resolve_min_notional / _fresh_spread (same logic as ScreenerAutoTrader)
# ===========================================================================

class TestHelpers:
    def test_resolve_notional_returns_none_when_info_missing(self) -> None:
        exec_svc = _FakeExecService()
        trader = _make_trader(_settings(), _FakeScreener({}), exec_svc, MarketDataCacheMemory())
        result = trader._resolve_min_notional(SYM, SHORT_EX, LONG_EX, SHORT_PRICE, LONG_PRICE)
        assert result is None

    def test_resolve_notional_max_of_exchange_and_floor(self) -> None:
        settings = _settings(screener_auto_trade_notional_usdt=20.0)
        cache = MarketDataCacheMemory()
        cache.put_market_info(_market_info(min_usdt=10.0), SHORT_EX)
        cache.put_market_info(_market_info(min_usdt=15.0), LONG_EX)
        exec_svc = _FakeExecService()
        trader = _make_trader(settings, _FakeScreener({}), exec_svc, cache)
        result = trader._resolve_min_notional(SYM, SHORT_EX, LONG_EX, SHORT_PRICE, LONG_PRICE)
        assert result == pytest.approx(20.0)

    def test_fresh_spread_returns_correct_value(self) -> None:
        cache = MarketDataCacheMemory()
        cache.put_quote(_quote(SHORT_EX, SYM, bid=105.0, ask=105.1))
        cache.put_quote(_quote(LONG_EX, SYM, bid=99.9, ask=100.0))
        exec_svc = _FakeExecService()
        trader = _make_trader(_settings(), _FakeScreener({}), exec_svc, cache)
        result = trader._spread_resolver.entry_spread_sync(SYM, SHORT_EX, LONG_EX)
        assert result is not None
        _, _, spread = result
        assert abs(spread - 5.0) < 0.1
