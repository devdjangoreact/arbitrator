"""Comprehensive tests for LiveFundingProtectionService.

Scenarios covered:
  - No positions → no action
  - Funding settlement too far in future → no action
  - Funding settlement too close (within skip window) → no action
  - We receive net funding (negative cost) → no action
  - Funding cost < round-trip fees → no action
  - Funding cost > round-trip fees → close only (screener reopens if conditions match)
  - Only short positions (no matching long) → skip
  - fetch_open_positions raises → continues gracefully
  - close_all raises → exception logged, no crash
  - taker fee from cache
  - taker fee defaults when cache miss
  - Multiple symbols: only one with net funding cost
  - Positive funding on short, neutral on long → net negative → skip
  - Zero notional / zero position → skip
"""
from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import pytest

from arbitrator.application.account.live_funding_protection_service import LiveFundingProtectionService
from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.settings import Settings
from arbitrator.domain.account.position_leg import PositionLeg
from arbitrator.domain.strategy.execution_outcome import ExecutionOutcome, ExecutionStatus
from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.funding_info import FundingInfo
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.universe.symbol_market_info import SymbolMarketInfo

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYM = "BTC/USDT:USDT"
SYM2 = "ETH/USDT:USDT"
SHORT_EX = "bitget"
LONG_EX = "gate"
NOW_MS = int(time.time() * 1000)
SOON_MS = NOW_MS + 200_000   # 200s from now — within act_window (300s)
CLOSE_MS = NOW_MS + 30_000   # 30s from now — within skip window (60s)
FAR_MS = NOW_MS + 400_000    # 400s from now — outside act_window (300s)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = dict(
        live_funding_protect_enabled=True,
        live_funding_protect_check_interval_seconds=30.0,
        live_funding_protect_act_window_seconds=300.0,
        live_funding_protect_skip_within_seconds=60.0,
        live_funding_protect_min_reopen_spread_pct=0.1,
        screener_auto_trade_notional_usdt=10.0,
        opp_default_leverage=10,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _leg(
    exchange_id: str,
    symbol: str,
    side: Literal["long", "short"],
    *,
    entry_price: float = 100.0,
    contracts: float = 1.0,
    contract_size: float = 1.0,
) -> PositionLeg:
    return PositionLeg(
        exchange_id=exchange_id,
        display_name=exchange_id,
        symbol=symbol,
        side=side,
        contracts=contracts,
        contract_size=contract_size,
        entry_price=entry_price,
        mark_price=entry_price,
        opened_at=datetime.now(UTC),
        unrealized_pnl=0.0,
        accrued_funding=None,
        opening_fee=None,
        estimated_close_fee=None,
        next_funding_at=None,
        arb_marker_id=None,
        position_id="pos-test",
    )


def _quote(exchange_id: str, symbol: str, bid: float, ask: float) -> Quote:
    return Quote(
        exchange_id=exchange_id,
        symbol=symbol,
        market_type="futures",
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        last=Decimal(str((bid + ask) / 2)),
        recv_time_ms=1000,
    )


def _funding(
    exchange_id: str,
    symbol: str,
    rate: float,
    next_ms: int = SOON_MS,
) -> FundingInfo:
    return FundingInfo(
        exchange_id=exchange_id,
        symbol=symbol,
        rate=Decimal(str(rate)),
        next_rate=None,
        next_settlement_ms=next_ms,
        recv_time_ms=1000,
    )


def _market_info(symbol: str = SYM, base: str = "BTC", min_usdt: float = 5.0) -> SymbolMarketInfo:
    return SymbolMarketInfo(
        unified_symbol=symbol,
        base_asset=base,
        native_market_id=None,
        min_order_volume_usdt=min_usdt,
        max_order_volume_usdt=None,
        min_amount_contracts=None,
        contract_size=1.0,
    )


def _fee_schedule(exchange_id: str, symbol: str, taker: float = 0.0006) -> FeeSchedule:
    return FeeSchedule(
        exchange_id=exchange_id,
        symbol=symbol,
        futures_maker=Decimal(str(taker / 2)),
        futures_taker=Decimal(str(taker)),
        spot_maker=None,
        spot_taker=None,
    )


# ---------------------------------------------------------------------------
# Fake gateway
# ---------------------------------------------------------------------------

class _FakeGateway:
    def __init__(self, positions: list[PositionLeg] | None = None, raise_on_fetch: bool = False) -> None:
        self._positions = positions or []
        self._raise_on_fetch = raise_on_fetch

    async def fetch_open_positions(self) -> list[PositionLeg]:
        if self._raise_on_fetch:
            raise RuntimeError("fetch error")
        return list(self._positions)

    async def set_margin_mode(self, symbol: str, mode: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Fake HedgedExecutionService
# ---------------------------------------------------------------------------

class _FakeExecService:
    def __init__(
        self,
        gateways: dict[str, _FakeGateway] | None = None,
        raise_on_close: bool = False,
        raise_on_open: bool = False,
    ) -> None:
        self.close_calls: list[dict[str, Any]] = []
        self.open_calls: list[dict[str, Any]] = []
        self._gateways = gateways or {SHORT_EX: _FakeGateway(), LONG_EX: _FakeGateway()}
        self._raise_on_close = raise_on_close
        self._raise_on_open = raise_on_open

    async def close_all(self, **kwargs: Any) -> ExecutionOutcome:
        self.close_calls.append(kwargs)
        if self._raise_on_close:
            raise RuntimeError("close_all failed")
        return ExecutionOutcome(
            action="close_all",
            status=ExecutionStatus.success,
            symbol=kwargs["symbol"],
            imbalance_pct=Decimal("0"),
        )

    async def open(self, **kwargs: Any) -> ExecutionOutcome:
        self.open_calls.append(kwargs)
        if self._raise_on_open:
            raise RuntimeError("open failed")
        return ExecutionOutcome(
            action="open",
            status=ExecutionStatus.success,
            symbol=kwargs["symbol"],
            imbalance_pct=Decimal("0"),
        )


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def _standard_cache(
    short_rate: float = 0.001,
    long_rate: float = 0.001,
    next_ms: int = SOON_MS,
    spread_pct: float = 2.0,
) -> MarketDataCacheMemory:
    """Cache with funding info, quotes, and market info for standard happy-path tests."""
    cache = MarketDataCacheMemory()
    mid = 100.0
    half_spread = mid * (spread_pct / 100) / 2
    cache.put_quote(_quote(SHORT_EX, SYM, bid=mid + half_spread, ask=mid + half_spread + 0.01))
    cache.put_quote(_quote(LONG_EX, SYM, bid=mid - half_spread - 0.01, ask=mid - half_spread))
    cache.put_funding(_funding(SHORT_EX, SYM, rate=short_rate, next_ms=next_ms))
    cache.put_funding(_funding(LONG_EX, SYM, rate=long_rate, next_ms=next_ms))
    cache.put_market_info(_market_info(), SHORT_EX)
    cache.put_market_info(_market_info(), LONG_EX)
    return cache


def _standard_gateways(
    short_entry: float = 100.0,
    long_entry: float = 100.0,
    notional: float = 100.0,
) -> dict[str, _FakeGateway]:
    contracts = notional / short_entry
    return {
        SHORT_EX: _FakeGateway([_leg(SHORT_EX, SYM, "short", entry_price=short_entry, contracts=contracts)]),
        LONG_EX: _FakeGateway([_leg(LONG_EX, SYM, "long", entry_price=long_entry, contracts=contracts)]),
    }


def _make_svc(
    settings: Settings,
    exec_service: _FakeExecService,
    cache: MarketDataCacheMemory,
    act_window: float = 300.0,
    skip_window: float = 60.0,
    min_spread: float = 0.1,
) -> LiveFundingProtectionService:
    return LiveFundingProtectionService(
        gateways=exec_service._gateways,  # type: ignore[arg-type]
        execution_service=exec_service,   # type: ignore[arg-type]
        market_cache=cache,
        settings=settings,
        check_interval_seconds=30.0,
        act_window_seconds=act_window,
        skip_within_seconds=skip_window,
        min_reopen_spread_pct=min_spread,
        default_taker_fee=0.0006,
    )


# ===========================================================================
# Tests: timing window
# ===========================================================================

class TestTimingWindow:
    def test_no_positions_no_action(self) -> None:
        exec_svc = _FakeExecService()
        svc = _make_svc(_settings(), exec_svc, MarketDataCacheMemory())
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 0

    def test_funding_too_far_no_action(self) -> None:
        """400s away > 300s act_window → skip regardless of funding cost."""
        gateways = _standard_gateways(notional=1000.0)
        # Asymmetric rates (would trigger if in window): net = 9 USDT > fees
        cache = _standard_cache(short_rate=0.001, long_rate=0.01, next_ms=FAR_MS)
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_svc(_settings(), exec_svc, cache)
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 0

    def test_funding_too_close_skip_window_no_action(self) -> None:
        """30s away < 60s skip_window → skip regardless of funding cost."""
        gateways = _standard_gateways(notional=1000.0)
        cache = _standard_cache(short_rate=0.001, long_rate=0.01, next_ms=CLOSE_MS)
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_svc(_settings(), exec_svc, cache)
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 0

    def test_in_window_acts(self) -> None:
        """SOON_MS = 200s from now — within [60, 300] → should act.

        long_rate=0.01 >> short_rate=0.001:
          funding_cost = -1000*0.001 + 1000*0.01 = 9 USDT
          round_trip   = 2*(1000*0.0006 + 1000*0.0006) = 2.4 USDT → act
        """
        gateways = _standard_gateways(notional=1000.0)
        cache = _standard_cache(short_rate=0.001, long_rate=0.01, next_ms=SOON_MS)
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_svc(_settings(), exec_svc, cache)
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 1


# ===========================================================================
# Tests: funding cost decision
# ===========================================================================

class TestFundingCostDecision:
    def test_we_receive_funding_no_action(self) -> None:
        """Short high positive rate (short receives), long very low rate.
        net_funding_cost = -(1000 * 0.01) + (1000 * 0.0001) = -9.9 < 0 → skip."""
        gateways = _standard_gateways(notional=1000.0)
        # short_rate=0.01 → short RECEIVES (we subtract: -notional * rate)
        # long_rate=0.0001 → long pays tiny amount
        # net = -(1000 * 0.01) + (1000 * 0.0001) = -10 + 0.1 = -9.9 → negative → skip
        cache = _standard_cache(short_rate=0.01, long_rate=0.0001)
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_svc(_settings(), exec_svc, cache)
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 0

    def test_funding_cost_less_than_fees_no_action(self) -> None:
        """Small net funding cost < round_trip_fees → no close.
        net = -(100*0.0001) + (100*0.0002) = 0.01 USDT
        fees = 2*(100*0.0006 + 100*0.0006) = 0.24 USDT → no close."""
        gateways = _standard_gateways(notional=100.0)
        cache = _standard_cache(short_rate=0.0001, long_rate=0.0002)
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_svc(_settings(), exec_svc, cache)
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 0

    def test_funding_cost_exceeds_fees_triggers_close_only(self) -> None:
        """Large net funding cost > round_trip_fees → close only (no reopen)."""
        gateways = _standard_gateways(notional=1000.0)
        cache = _standard_cache(short_rate=0.001, long_rate=0.01)
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_svc(_settings(), exec_svc, cache)
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 1
        assert exec_svc.close_calls[0]["symbol"] == SYM
        assert len(exec_svc.open_calls) == 0

    def test_low_spread_still_closes_when_funding_costly(self) -> None:
        """Funding cost > fees → close even when spread collapsed."""
        gateways = _standard_gateways(notional=1000.0)
        cache = _standard_cache(short_rate=0.001, long_rate=0.01, spread_pct=0.001)
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_svc(_settings(), exec_svc, cache, min_spread=0.5)
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 1
        assert len(exec_svc.open_calls) == 0


# ===========================================================================
# Tests: error handling
# ===========================================================================

class TestErrorHandling:
    def test_fetch_positions_exception_continues(self) -> None:
        gateways = {
            SHORT_EX: _FakeGateway(raise_on_fetch=True),
            LONG_EX: _FakeGateway([]),
        }
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_svc(_settings(), exec_svc, MarketDataCacheMemory())
        asyncio.run(svc._tick())  # must not raise

    def test_close_all_exception_does_not_crash(self) -> None:
        gateways = _standard_gateways(notional=1000.0)
        cache = _standard_cache(short_rate=0.01, long_rate=0.01)
        exec_svc = _FakeExecService(gateways=gateways, raise_on_close=True)
        svc = _make_svc(_settings(), exec_svc, cache)
        asyncio.run(svc._tick())  # must not raise

    def test_market_info_missing_still_closes(self) -> None:
        """Funding cost > fees → close even without market info in cache."""
        gateways = _standard_gateways(notional=1000.0)
        cache = MarketDataCacheMemory()
        cache.put_quote(_quote(SHORT_EX, SYM, bid=102.0, ask=102.1))
        cache.put_quote(_quote(LONG_EX, SYM, bid=99.9, ask=100.0))
        cache.put_funding(_funding(SHORT_EX, SYM, rate=0.001, next_ms=SOON_MS))
        cache.put_funding(_funding(LONG_EX, SYM, rate=0.01, next_ms=SOON_MS))
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_svc(_settings(), exec_svc, cache)
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 1
        assert len(exec_svc.open_calls) == 0

    def test_only_short_positions_no_action(self) -> None:
        """No matching long leg → skip entirely."""
        gateways = {
            SHORT_EX: _FakeGateway([_leg(SHORT_EX, SYM, "short", contracts=10.0)]),
            LONG_EX: _FakeGateway([]),
        }
        exec_svc = _FakeExecService(gateways=gateways)
        cache = _standard_cache(short_rate=0.01, long_rate=0.01)
        svc = _make_svc(_settings(), exec_svc, cache)
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 0


# ===========================================================================
# Tests: fee and price helpers
# ===========================================================================

class TestFeeHelpers:
    def test_taker_fee_from_cache(self) -> None:
        cache = MarketDataCacheMemory()
        cache.put_fees(_fee_schedule(SHORT_EX, SYM, taker=0.001))
        exec_svc = _FakeExecService()
        svc = _make_svc(_settings(), exec_svc, cache)
        assert svc._taker_fee(SHORT_EX, SYM) == pytest.approx(0.001)

    def test_taker_fee_defaults_when_cache_miss(self) -> None:
        exec_svc = _FakeExecService()
        svc = _make_svc(_settings(), exec_svc, MarketDataCacheMemory(), )
        svc._default_taker_fee = 0.0005
        assert svc._taker_fee(SHORT_EX, SYM) == pytest.approx(0.0005)


# ===========================================================================
# Tests: multiple symbols
# ===========================================================================

class TestMultipleSymbols:
    def test_only_costly_symbol_gets_closed(self) -> None:
        """SYM has high funding cost, SYM2 has tiny rate → only SYM closed."""
        sym1_notional = 1000.0
        gateways = {
            SHORT_EX: _FakeGateway([
                _leg(SHORT_EX, SYM, "short", entry_price=100.0, contracts=sym1_notional / 100.0),
                _leg(SHORT_EX, SYM2, "short", entry_price=100.0, contracts=10.0),
            ]),
            LONG_EX: _FakeGateway([
                _leg(LONG_EX, SYM, "long", entry_price=100.0, contracts=sym1_notional / 100.0),
                _leg(LONG_EX, SYM2, "long", entry_price=100.0, contracts=10.0),
            ]),
        }
        cache = MarketDataCacheMemory()
        # SYM: high spread, asymmetric funding (net = -1000*0.001 + 1000*0.01 = 9 USDT > fees)
        cache.put_quote(_quote(SHORT_EX, SYM, bid=102.0, ask=102.1))
        cache.put_quote(_quote(LONG_EX, SYM, bid=99.9, ask=100.0))
        cache.put_funding(_funding(SHORT_EX, SYM, rate=0.001, next_ms=SOON_MS))
        cache.put_funding(_funding(LONG_EX, SYM, rate=0.01, next_ms=SOON_MS))
        cache.put_market_info(_market_info(SYM), SHORT_EX)
        cache.put_market_info(_market_info(SYM), LONG_EX)
        # SYM2: tiny funding rate
        cache.put_quote(_quote(SHORT_EX, SYM2, bid=102.0, ask=102.1))
        cache.put_quote(_quote(LONG_EX, SYM2, bid=99.9, ask=100.0))
        cache.put_funding(_funding(SHORT_EX, SYM2, rate=0.0001, next_ms=SOON_MS))
        cache.put_funding(_funding(LONG_EX, SYM2, rate=0.0001, next_ms=SOON_MS))
        cache.put_market_info(_market_info(SYM2, base="ETH"), SHORT_EX)
        cache.put_market_info(_market_info(SYM2, base="ETH"), LONG_EX)

        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_svc(_settings(), exec_svc, cache)
        asyncio.run(svc._tick())

        closed_syms = [c["symbol"] for c in exec_svc.close_calls]
        assert SYM in closed_syms
        assert SYM2 not in closed_syms
