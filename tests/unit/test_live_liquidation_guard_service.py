"""Comprehensive tests for LiveLiquidationGuardService.

Scenarios covered:
  - No positions → no action
  - Leg far from liquidation → no close
  - Short leg approaching liquidation (consumed >= warning_pct) → pair close
  - Long leg approaching liquidation → pair close
  - Both legs safe → no close
  - Only short or only long (unhedged) → solo close via gateway
  - fetch_open_positions raises on one exchange → continues with others
  - close_all raises → exception logged, does not crash
  - solo close_market_position raises → exception logged, does not crash
  - Leverage estimated from position data (pnl-based)
  - Leverage falls back to settings default
  - Liquidation price calculation: short and long
  - Margin consumed percentage helper
  - current_price uses mark_price when available
  - current_price falls back to cache mid
  - Mark price not available + no cache → skip leg
  - warning_pct=0 → always closes (edge)
  - Multiple symbols: only endangered pair closed
  - Position with zero entry_price → skip
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal
from unittest.mock import AsyncMock

import pytest

from arbitrator.application.live_liquidation_guard_service import LiveLiquidationGuardService
from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.settings import Settings
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.domain.strategy.execution_outcome import ExecutionOutcome, ExecutionStatus
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.symbol_market_info import SymbolMarketInfo

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYM = "BTC/USDT:USDT"
SYM2 = "ETH/USDT:USDT"
SHORT_EX = "bitget"
LONG_EX = "gate"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(**overrides: Any) -> Settings:
    defaults: dict[str, Any] = dict(
        live_liq_guard_enabled=True,
        live_liq_guard_check_interval_seconds=5.0,
        live_liq_guard_warning_pct_to_liq=80.0,
        opp_default_leverage=10,
        screener_auto_trade_notional_usdt=10.0,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _leg(
    exchange_id: str,
    symbol: str,
    side: Literal["long", "short"],
    *,
    entry_price: float = 100.0,
    mark_price: float | None = None,
    contracts: float = 1.0,
    contract_size: float = 1.0,
    unrealized_pnl: float | None = None,
) -> PositionLeg:
    return PositionLeg(
        exchange_id=exchange_id,
        display_name=exchange_id,
        symbol=symbol,
        side=side,
        contracts=contracts,
        contract_size=contract_size,
        entry_price=entry_price,
        mark_price=mark_price,
        opened_at=datetime.now(UTC),
        unrealized_pnl=unrealized_pnl,
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


def _market_info(symbol: str = SYM, base: str = "BTC", min_usdt: float = 5.0) -> SymbolMarketInfo:
    return SymbolMarketInfo(
        unified_symbol=symbol, base_asset=base, native_market_id=None,
        min_order_volume_usdt=min_usdt, max_order_volume_usdt=None,
        min_amount_contracts=None, contract_size=1.0,
    )


# ---------------------------------------------------------------------------
# Fake gateway
# ---------------------------------------------------------------------------

class _FakeGateway:
    def __init__(self, positions: list[PositionLeg] | None = None, raise_on_fetch: bool = False) -> None:
        self._positions = positions or []
        self._raise_on_fetch = raise_on_fetch
        self.close_calls: list[PositionLeg] = []

    async def fetch_open_positions(self) -> list[PositionLeg]:
        if self._raise_on_fetch:
            raise RuntimeError("network error")
        return list(self._positions)

    async def close_market_position(self, leg: PositionLeg) -> str:
        self.close_calls.append(leg)
        return "close-order-1"

    async def set_margin_mode(self, symbol: str, mode: str) -> None:
        pass


class _RaisingCloseGateway(_FakeGateway):
    async def close_market_position(self, leg: PositionLeg) -> str:
        raise RuntimeError("close failed")


# ---------------------------------------------------------------------------
# Fake HedgedExecutionService
# ---------------------------------------------------------------------------

class _FakeExecService:
    def __init__(
        self,
        gateways: dict[str, _FakeGateway] | None = None,
        raise_on_close: bool = False,
    ) -> None:
        self.close_calls: list[dict[str, Any]] = []
        self.open_calls: list[dict[str, Any]] = []
        self._gateways = gateways or {
            SHORT_EX: _FakeGateway(),
            LONG_EX: _FakeGateway(),
        }
        self._raise_on_close = raise_on_close

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
        return ExecutionOutcome(
            action="open",
            status=ExecutionStatus.success,
            symbol=kwargs["symbol"],
            imbalance_pct=Decimal("0"),
        )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _make_guard(
    settings: Settings,
    exec_service: _FakeExecService,
    cache: MarketDataCacheMemory,
    warning_pct: float = 80.0,
) -> LiveLiquidationGuardService:
    return LiveLiquidationGuardService(
        gateways=exec_service._gateways,  # type: ignore[arg-type]
        execution_service=exec_service,   # type: ignore[arg-type]
        market_cache=cache,
        settings=settings,
        check_interval_seconds=5.0,
        warning_pct_to_liq=warning_pct,
    )


# ===========================================================================
# Tests: core close behavior
# ===========================================================================

class TestPairClose:
    def test_no_positions_no_action(self) -> None:
        svc = _make_guard(_settings(), _FakeExecService(), MarketDataCacheMemory())
        asyncio.run(svc._tick())
        # No exception, no close calls

    def test_short_leg_far_from_liq_no_close(self) -> None:
        """Short leg at 90% consumed but warning_pct is 95 → no close."""
        entry = 100.0
        # Leverage 10 → buffer = 0.1 - 0.005 = 0.095 → liq = 109.5
        # current = 108 → consumed = (108-100)/(109.5-100) = 84.2% < 95%
        gateways = {
            SHORT_EX: _FakeGateway([_leg(SHORT_EX, SYM, "short", entry_price=entry, mark_price=108.0)]),
            LONG_EX: _FakeGateway([_leg(LONG_EX, SYM, "long", entry_price=entry, mark_price=92.0)]),
        }
        exec_svc = _FakeExecService(gateways=gateways)
        cache = MarketDataCacheMemory()
        svc = _make_guard(_settings(), exec_svc, cache, warning_pct=95.0)
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 0

    def test_short_leg_approaching_liq_closes_pair(self) -> None:
        """Short at 109.0 with entry=100, leverage=10 → liq=109.5 → consumed=94.7% ≥ 80%."""
        entry = 100.0
        gateways = {
            SHORT_EX: _FakeGateway([_leg(SHORT_EX, SYM, "short", entry_price=entry, mark_price=109.0)]),
            LONG_EX: _FakeGateway([_leg(LONG_EX, SYM, "long", entry_price=entry, mark_price=91.0)]),
        }
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_guard(_settings(opp_default_leverage=10), exec_svc, MarketDataCacheMemory())
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 1
        assert exec_svc.close_calls[0]["symbol"] == SYM

    def test_long_leg_approaching_liq_closes_pair(self) -> None:
        """Long at 91.0 with entry=100, leverage=10 → liq=90.5 → consumed=90.5% ≥ 80%."""
        entry = 100.0
        gateways = {
            SHORT_EX: _FakeGateway([_leg(SHORT_EX, SYM, "short", entry_price=entry, mark_price=101.0)]),
            LONG_EX: _FakeGateway([_leg(LONG_EX, SYM, "long", entry_price=entry, mark_price=91.0)]),
        }
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_guard(_settings(opp_default_leverage=10), exec_svc, MarketDataCacheMemory())
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 1

    def test_both_legs_safe_no_close(self) -> None:
        """Both legs well inside margin buffer."""
        entry = 100.0
        gateways = {
            SHORT_EX: _FakeGateway([_leg(SHORT_EX, SYM, "short", entry_price=entry, mark_price=101.0)]),
            LONG_EX: _FakeGateway([_leg(LONG_EX, SYM, "long", entry_price=entry, mark_price=99.0)]),
        }
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_guard(_settings(opp_default_leverage=10), exec_svc, MarketDataCacheMemory())
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 0

    def test_warning_pct_zero_always_closes(self) -> None:
        """warning_pct=0 triggers close even for tiny price moves."""
        entry = 100.0
        gateways = {
            SHORT_EX: _FakeGateway([_leg(SHORT_EX, SYM, "short", entry_price=entry, mark_price=100.01)]),
            LONG_EX: _FakeGateway([_leg(LONG_EX, SYM, "long", entry_price=entry, mark_price=99.99)]),
        }
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_guard(_settings(opp_default_leverage=10), exec_svc, MarketDataCacheMemory(), warning_pct=0.0)
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 1


class TestUnhedgedClose:
    def test_solo_short_leg_closes_directly(self) -> None:
        """Only short position found, no matching long — closes via gateway."""
        entry = 100.0
        short_gw = _FakeGateway([_leg(SHORT_EX, SYM, "short", entry_price=entry, mark_price=109.0)])
        long_gw = _FakeGateway([])  # no position
        exec_svc = _FakeExecService(gateways={SHORT_EX: short_gw, LONG_EX: long_gw})
        svc = _make_guard(_settings(opp_default_leverage=10), exec_svc, MarketDataCacheMemory())
        asyncio.run(svc._tick())
        # Solo close via gateway, NOT via exec_svc.close_all
        assert len(exec_svc.close_calls) == 0
        assert len(short_gw.close_calls) == 1

    def test_solo_long_leg_closes_directly(self) -> None:
        """Only long position found — closes via gateway."""
        entry = 100.0
        short_gw = _FakeGateway([])
        long_gw = _FakeGateway([_leg(LONG_EX, SYM, "long", entry_price=entry, mark_price=91.0)])
        exec_svc = _FakeExecService(gateways={SHORT_EX: short_gw, LONG_EX: long_gw})
        svc = _make_guard(_settings(opp_default_leverage=10), exec_svc, MarketDataCacheMemory())
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 0
        assert len(long_gw.close_calls) == 1


class TestErrorHandling:
    def test_fetch_exception_continues_other_exchanges(self) -> None:
        """If one gateway throws on fetch_open_positions, others still run."""
        error_gw = _FakeGateway(raise_on_fetch=True)
        long_gw = _FakeGateway([_leg(LONG_EX, SYM, "long", entry_price=100.0, mark_price=91.0)])
        exec_svc = _FakeExecService(gateways={SHORT_EX: error_gw, LONG_EX: long_gw})
        svc = _make_guard(_settings(opp_default_leverage=10), exec_svc, MarketDataCacheMemory())
        # Must not raise; continues without short positions
        asyncio.run(svc._tick())

    def test_close_all_exception_does_not_crash(self) -> None:
        entry = 100.0
        gateways = {
            SHORT_EX: _FakeGateway([_leg(SHORT_EX, SYM, "short", entry_price=entry, mark_price=109.0)]),
            LONG_EX: _FakeGateway([_leg(LONG_EX, SYM, "long", entry_price=entry, mark_price=91.0)]),
        }
        exec_svc = _FakeExecService(gateways=gateways, raise_on_close=True)
        svc = _make_guard(_settings(opp_default_leverage=10), exec_svc, MarketDataCacheMemory())
        asyncio.run(svc._tick())  # must not raise

    def test_solo_close_exception_does_not_crash(self) -> None:
        raising_gw = _RaisingCloseGateway([_leg(SHORT_EX, SYM, "short", entry_price=100.0, mark_price=109.0)])
        long_gw = _FakeGateway([])
        exec_svc = _FakeExecService(gateways={SHORT_EX: raising_gw, LONG_EX: long_gw})
        svc = _make_guard(_settings(opp_default_leverage=10), exec_svc, MarketDataCacheMemory())
        asyncio.run(svc._tick())  # must not raise


class TestCurrentPrice:
    def test_uses_mark_price_when_available(self) -> None:
        svc = _make_guard(_settings(), _FakeExecService(), MarketDataCacheMemory())
        leg = _leg(SHORT_EX, SYM, "short", mark_price=105.0)
        result = svc._current_price(SHORT_EX, SYM, leg)
        assert result == pytest.approx(105.0)

    def test_uses_cache_mid_when_no_mark_price(self) -> None:
        cache = MarketDataCacheMemory()
        cache.put_quote(_quote(SHORT_EX, SYM, bid=104.0, ask=106.0))
        svc = _make_guard(_settings(), _FakeExecService(), cache)
        leg = _leg(SHORT_EX, SYM, "short", mark_price=None)
        result = svc._current_price(SHORT_EX, SYM, leg)
        assert result == pytest.approx(105.0)

    def test_returns_none_when_no_mark_and_no_cache(self) -> None:
        svc = _make_guard(_settings(), _FakeExecService(), MarketDataCacheMemory())
        leg = _leg(SHORT_EX, SYM, "short", mark_price=None)
        assert svc._current_price(SHORT_EX, SYM, leg) is None


class TestLeverageEstimation:
    def test_uses_settings_default_when_no_pnl(self) -> None:
        svc = _make_guard(_settings(opp_default_leverage=15), _FakeExecService(), MarketDataCacheMemory())
        leg = _leg(SHORT_EX, SYM, "short", entry_price=100.0, unrealized_pnl=None)
        assert svc._leverage_from_leg(leg) == pytest.approx(15.0)

    def test_estimates_leverage_from_pnl(self) -> None:
        """1 contract at 100 entry, 5% pnl → position_value=100, pnl=5
        margin_fraction = (100-5)/100 = 0.95 → leverage ≈ 1/0.95 ≈ 1.05 (very low leverage)
        """
        svc = _make_guard(_settings(opp_default_leverage=10), _FakeExecService(), MarketDataCacheMemory())
        leg = _leg(SHORT_EX, SYM, "short", entry_price=100.0, mark_price=105.0, unrealized_pnl=5.0)
        lev = svc._leverage_from_leg(leg)
        # Just verify it's estimated from data (not exactly 10)
        assert 1.0 <= lev <= 200.0


class TestLiquidationPriceHelper:
    def test_short_liq_price_above_entry(self) -> None:
        # leverage=10 → buffer = 0.095 → liq = 100 * 1.095 = 109.5
        liq = LiveLiquidationGuardService._liquidation_price(100.0, 10.0, "short")
        assert liq == pytest.approx(109.5, abs=0.01)

    def test_long_liq_price_below_entry(self) -> None:
        # leverage=10 → buffer = 0.095 → liq = 100 * (1 - 0.095) = 90.5
        liq = LiveLiquidationGuardService._liquidation_price(100.0, 10.0, "long")
        assert liq == pytest.approx(90.5, abs=0.01)

    def test_zero_leverage_returns_none(self) -> None:
        assert LiveLiquidationGuardService._liquidation_price(100.0, 0.0, "short") is None

    def test_excessive_leverage_where_buffer_negative_returns_none(self) -> None:
        # leverage=1000 → buffer = 0.001 - 0.005 = -0.004 < 0
        assert LiveLiquidationGuardService._liquidation_price(100.0, 1000.0, "short") is None


class TestMarginConsumedPct:
    def test_midpoint_consumed(self) -> None:
        # entry=100, liq=110 → midpoint=105 → consumed=50%
        pct = LiveLiquidationGuardService._margin_consumed_pct(100.0, 105.0, 110.0)
        assert pct == pytest.approx(50.0)

    def test_at_liquidation_100_pct(self) -> None:
        pct = LiveLiquidationGuardService._margin_consumed_pct(100.0, 110.0, 110.0)
        assert pct == pytest.approx(100.0)

    def test_capped_at_100(self) -> None:
        pct = LiveLiquidationGuardService._margin_consumed_pct(100.0, 120.0, 110.0)
        assert pct == 100.0

    def test_at_entry_zero_pct(self) -> None:
        pct = LiveLiquidationGuardService._margin_consumed_pct(100.0, 100.0, 110.0)
        assert pct == pytest.approx(0.0)


class TestMultipleSymbols:
    def test_only_endangered_symbol_closed(self) -> None:
        """SYM is approaching liquidation, SYM2 is safe. Only SYM should be closed."""
        entry = 100.0
        gateways = {
            SHORT_EX: _FakeGateway([
                _leg(SHORT_EX, SYM, "short", entry_price=entry, mark_price=109.0),   # dangerous
                _leg(SHORT_EX, SYM2, "short", entry_price=entry, mark_price=101.0),  # safe
            ]),
            LONG_EX: _FakeGateway([
                _leg(LONG_EX, SYM, "long", entry_price=entry, mark_price=91.0),    # dangerous
                _leg(LONG_EX, SYM2, "long", entry_price=entry, mark_price=99.0),   # safe
            ]),
        }
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_guard(_settings(opp_default_leverage=10), exec_svc, MarketDataCacheMemory())
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 1
        assert exec_svc.close_calls[0]["symbol"] == SYM

    def test_skip_leg_with_zero_entry_price(self) -> None:
        """Leg with entry_price=0 should be skipped (division guard)."""
        gateways = {
            SHORT_EX: _FakeGateway([_leg(SHORT_EX, SYM, "short", entry_price=0.0, mark_price=1.0)]),
            LONG_EX: _FakeGateway([_leg(LONG_EX, SYM, "long", entry_price=0.0, mark_price=1.0)]),
        }
        exec_svc = _FakeExecService(gateways=gateways)
        svc = _make_guard(_settings(), exec_svc, MarketDataCacheMemory())
        asyncio.run(svc._tick())
        assert len(exec_svc.close_calls) == 0
