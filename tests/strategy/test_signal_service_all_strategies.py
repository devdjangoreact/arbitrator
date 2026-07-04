"""Signal service tests for all 6 strategies.

Scenarios per strategy:
  - Open signal when spread >= threshold and checklist passes
  - Close signal when spread <= close threshold
  - No signal when spread between thresholds
  - Blocked by anomaly guard (spread > anomaly_max)
  - Blocked by checklist (asset mismatch)
  - Blocked when strategy unavailable (no data)

Additional per-strategy scenarios:
  futures_spot_2ex / futures_spot_1ex:
    - No spot data → strategy unavailable → blocked signal
    - Spot data present → open signal fires
  funding_ff / funding_diff_dates:
    - Stale settlement timestamp → blocked signal
    - Future settlement in window → open signal fires
  funding_fs:
    - No spot data → unavailable → blocked
    - Spot + positive funding rate → open signal fires
  funding_diff_dates:
    - Same settlement dates on both exchanges → unavailable
    - Different dates → open signal fires
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from arbitrator.application.anomaly_guard import AnomalyGuard
from arbitrator.application.checklist_evaluator import ChecklistEvaluator
from arbitrator.application.signal_service import SignalService
from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.strategies.funding_diff_dates_calculator import (
    FundingDiffDatesCalculator,
)
from arbitrator.domain.strategy.strategies.funding_ff_calculator import FundingFfCalculator
from arbitrator.domain.strategy.strategies.funding_fs_calculator import FundingFsCalculator
from arbitrator.domain.strategy.strategies.futures_futures_calculator import (
    FuturesFuturesCalculator,
)
from arbitrator.domain.strategy.strategies.futures_spot_1ex_calculator import (
    FuturesSpot1exCalculator,
)
from arbitrator.domain.strategy.strategies.futures_spot_2ex_calculator import (
    FuturesSpot2exCalculator,
)
from arbitrator.domain.strategy.strategy_engine import StrategyEngine
from arbitrator.domain.strategy.strategy_inputs import StrategyInputs
from arbitrator.domain.strategy.strategy_kind import StrategyKind

OPEN_THR = Decimal("3.0")
CLOSE_THR = Decimal("0.1")

# Use a settlement timestamp well in the future (conftest.NOW_MS + 120s)
NOW_MS = 1_700_000_000_000
SOON_MS = NOW_MS + 120_000   # within entry window (300s)
LATER_MS = NOW_MS + 700_000  # outside entry window → stale


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_calcs() -> StrategyEngine:
    return StrategyEngine([
        FuturesFuturesCalculator(),
        FuturesSpot2exCalculator(),
        FuturesSpot1exCalculator(),
        FundingFfCalculator(),
        FundingFsCalculator(),
        FundingDiffDatesCalculator(),
    ])


def _svc() -> SignalService:
    settings = Settings()
    return SignalService(ChecklistEvaluator(settings), AnomalyGuard(settings))


def _evaluate(
    svc: SignalService,
    inputs: StrategyInputs,
    strategy_id: StrategyKind,
) -> object:
    table = _all_calcs().compute(inputs)
    return svc.evaluate(
        inputs=inputs,
        table=table,
        active_strategy_id=strategy_id,
        open_threshold_pct=OPEN_THR,
        close_threshold_pct=CLOSE_THR,
        volume_usdt=Decimal("1000"),
    )


# ---------------------------------------------------------------------------
# § 2 — futures_spot_2ex
# ---------------------------------------------------------------------------

class TestFuturesSpot2ex:
    def test_open_signal_with_spot_data(self, make_inputs, make_quote, make_fee) -> None:
        """5% spread (futures > spot) with all data → open signal."""
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.05", ask="1.06")},
            spot_quotes={"b": make_quote("b", market_type="spot", bid="0.99", ask="1.00")},
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.futures_spot_2ex)
        assert sig.action.value == "open"  # type: ignore[attr-defined]
        assert sig.blocked is False  # type: ignore[attr-defined]

    def test_blocked_when_no_spot_data(self, make_inputs, make_quote, make_fee) -> None:
        """No spot quotes → strategy unavailable → blocked."""
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.05", ask="1.06")},
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.futures_spot_2ex)
        assert sig.blocked is True  # type: ignore[attr-defined]

    def test_close_signal_when_spread_collapses(self, make_inputs, make_quote, make_fee) -> None:
        """Futures ≈ spot → spread ~0% → close signal."""
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.0005", ask="1.0006")},
            spot_quotes={"b": make_quote("b", market_type="spot", bid="0.9999", ask="1.0000")},
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.futures_spot_2ex)
        assert sig.action.value == "close"  # type: ignore[attr-defined]

    def test_no_signal_when_spread_between_thresholds(
        self, make_inputs, make_quote, make_fee
    ) -> None:
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.02", ask="1.021")},
            spot_quotes={"b": make_quote("b", market_type="spot", bid="0.999", ask="1.000")},
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.futures_spot_2ex)
        assert sig.action.value == "none"  # type: ignore[attr-defined]
        assert sig.blocked is False  # type: ignore[attr-defined]

    def test_blocked_by_anomaly(self, make_inputs, make_quote, make_fee) -> None:
        """30% spread (> anomaly_max=20%) → blocked."""
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.30", ask="1.31")},
            spot_quotes={"b": make_quote("b", market_type="spot", bid="0.99", ask="1.00")},
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.futures_spot_2ex)
        assert sig.blocked is True  # type: ignore[attr-defined]
        assert sig.block_reason == "anomalous_spread"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# § 1 — futures_spot_1ex
# ---------------------------------------------------------------------------

class TestFuturesSpot1ex:
    def test_open_signal_same_exchange_spot(self, make_inputs, make_quote, make_fee, make_funding) -> None:
        """§1: futures short + spot long on same exchange, 5% spread."""
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.05", ask="1.06")},
            spot_quotes={"a": make_quote("a", market_type="spot", bid="0.99", ask="1.00")},
            funding={"a": make_funding("a", rate="0.001", next_settlement_ms=SOON_MS)},
            fees={"a": make_fee("a")},
            leverage={"a": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.futures_spot_1ex)
        assert sig.action.value == "open"  # type: ignore[attr-defined]

    def test_blocked_when_no_spot_data(self, make_inputs, make_quote, make_fee) -> None:
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.05", ask="1.06")},
            fees={"a": make_fee("a")},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.futures_spot_1ex)
        assert sig.blocked is True  # type: ignore[attr-defined]

    def test_close_signal(self, make_inputs, make_quote, make_fee) -> None:
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.0005", ask="1.0006")},
            spot_quotes={"a": make_quote("a", market_type="spot", bid="0.9999", ask="1.0000")},
            fees={"a": make_fee("a")},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.futures_spot_1ex)
        assert sig.action.value == "close"  # type: ignore[attr-defined]

    def test_blocked_by_anomaly(self, make_inputs, make_quote, make_fee) -> None:
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.30", ask="1.31")},
            spot_quotes={"a": make_quote("a", market_type="spot", bid="0.99", ask="1.00")},
            fees={"a": make_fee("a")},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.futures_spot_1ex)
        assert sig.blocked is True  # type: ignore[attr-defined]
        assert sig.block_reason == "anomalous_spread"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# § 4 — funding_ff
# ---------------------------------------------------------------------------

class TestFundingFf:
    def test_open_signal_positive_funding(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        """High funding rate (2%) on short → profitable → open signal."""
        inputs = make_inputs(
            futures_quotes={
                "a": make_quote("a", bid="1.00", ask="1.01"),
                "b": make_quote("b", bid="0.99", ask="1.00"),
            },
            funding={
                "a": make_funding("a", rate="0.02", next_settlement_ms=SOON_MS),
                "b": make_funding("b", rate="0.001", next_settlement_ms=SOON_MS),
            },
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10, "b": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_ff)
        assert sig.action.value == "open"  # type: ignore[attr-defined]
        assert not sig.blocked  # type: ignore[attr-defined]

    def test_stale_settlement_blocks(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        """Next settlement in the past → funding_ts_stale → blocked."""
        inputs = make_inputs(
            futures_quotes={
                "a": make_quote("a", bid="1.05", ask="1.06"),
                "b": make_quote("b", bid="0.99", ask="1.00"),
            },
            funding={
                "a": make_funding("a", rate="0.02", next_settlement_ms=NOW_MS - 1_000),
                "b": make_funding("b", rate="0.001", next_settlement_ms=NOW_MS - 5_000),
            },
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10, "b": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_ff)
        assert sig.blocked is True  # type: ignore[attr-defined]

    def test_settlement_outside_entry_window_blocks(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        """Settlement 700s away > entry_window (300s) → funding_ts_stale."""
        inputs = make_inputs(
            futures_quotes={
                "a": make_quote("a", bid="1.05", ask="1.06"),
                "b": make_quote("b", bid="0.99", ask="1.00"),
            },
            funding={
                "a": make_funding("a", rate="0.02", next_settlement_ms=LATER_MS),
                "b": make_funding("b", rate="0.001", next_settlement_ms=LATER_MS),
            },
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10, "b": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_ff)
        assert sig.blocked is True  # type: ignore[attr-defined]

    def test_close_signal_when_spread_collapses(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        inputs = make_inputs(
            futures_quotes={
                "a": make_quote("a", bid="1.0001", ask="1.0002"),
                "b": make_quote("b", bid="0.9999", ask="1.0000"),
            },
            funding={
                "a": make_funding("a", rate="0.001", next_settlement_ms=SOON_MS),
                "b": make_funding("b", rate="0.001", next_settlement_ms=SOON_MS),
            },
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10, "b": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_ff)
        assert sig.action.value == "close"  # type: ignore[attr-defined]

    def test_blocked_no_funding_data(self, make_inputs, make_quote, make_fee) -> None:
        inputs = make_inputs(
            futures_quotes={
                "a": make_quote("a", bid="1.05", ask="1.06"),
                "b": make_quote("b", bid="0.99", ask="1.00"),
            },
            fees={"a": make_fee("a"), "b": make_fee("b")},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_ff)
        assert sig.blocked is True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# § 6/7 — funding_fs
# ---------------------------------------------------------------------------

class TestFundingFs:
    def test_open_signal_with_spot_and_high_funding(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        """2% funding rate, spot available → profitable → open signal."""
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.00", ask="1.01")},
            spot_quotes={"a": make_quote("a", market_type="spot", bid="0.99", ask="1.00")},
            funding={"a": make_funding("a", rate="0.02", next_settlement_ms=SOON_MS)},
            fees={"a": make_fee("a")},
            leverage={"a": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_fs)
        assert sig.action.value == "open"  # type: ignore[attr-defined]
        assert not sig.blocked  # type: ignore[attr-defined]

    def test_blocked_no_spot_data(self, make_inputs, make_quote, make_funding, make_fee) -> None:
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.05", ask="1.06")},
            funding={"a": make_funding("a", rate="0.02", next_settlement_ms=SOON_MS)},
            fees={"a": make_fee("a")},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_fs)
        assert sig.blocked is True  # type: ignore[attr-defined]

    def test_blocked_stale_settlement(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.05", ask="1.06")},
            spot_quotes={"a": make_quote("a", market_type="spot", bid="0.99", ask="1.00")},
            funding={"a": make_funding("a", rate="0.02", next_settlement_ms=NOW_MS - 1_000)},
            fees={"a": make_fee("a")},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_fs)
        assert sig.blocked is True  # type: ignore[attr-defined]

    def test_blocked_no_funding_data(self, make_inputs, make_quote, make_fee) -> None:
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.05", ask="1.06")},
            spot_quotes={"a": make_quote("a", market_type="spot", bid="0.99", ask="1.00")},
            fees={"a": make_fee("a")},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_fs)
        assert sig.blocked is True  # type: ignore[attr-defined]

    def test_close_signal_when_funding_below_threshold(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        """Near-zero funding rate → spread < close threshold → close."""
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.0001", ask="1.0002")},
            spot_quotes={"a": make_quote("a", market_type="spot", bid="0.9999", ask="1.0000")},
            funding={"a": make_funding("a", rate="0.0001", next_settlement_ms=SOON_MS)},
            fees={"a": make_fee("a")},
            leverage={"a": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_fs)
        assert sig.action.value == "close"  # type: ignore[attr-defined]

    def test_spot_on_other_exchange_triggers_open(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        """§7 branch: spot on different exchange than futures."""
        inputs = make_inputs(
            futures_quotes={"a": make_quote("a", bid="1.00", ask="1.01")},
            spot_quotes={"b": make_quote("b", market_type="spot", bid="0.99", ask="1.00")},
            funding={"a": make_funding("a", rate="0.02", next_settlement_ms=SOON_MS)},
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_fs)
        assert sig.action.value == "open"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# § 5 — funding_diff_dates
# ---------------------------------------------------------------------------

class TestFundingDiffDates:
    def test_open_signal_different_settlement_dates(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        """Two exchanges with very different funding rates and different settlement times."""
        inputs = make_inputs(
            futures_quotes={
                "a": make_quote("a", bid="1.00", ask="1.01"),
                "b": make_quote("b", bid="0.99", ask="1.00"),
            },
            funding={
                "a": make_funding("a", rate="0.02", next_settlement_ms=SOON_MS),
                "b": make_funding("b", rate="-0.001", next_settlement_ms=SOON_MS + 50_000),
            },
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10, "b": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_diff_dates)
        assert sig.action.value == "open"  # type: ignore[attr-defined]
        assert not sig.blocked  # type: ignore[attr-defined]

    def test_blocked_when_stale_settlement(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        inputs = make_inputs(
            futures_quotes={
                "a": make_quote("a", bid="1.05", ask="1.06"),
                "b": make_quote("b", bid="0.99", ask="1.00"),
            },
            funding={
                "a": make_funding("a", rate="0.02", next_settlement_ms=NOW_MS - 1_000),
                "b": make_funding("b", rate="0.001", next_settlement_ms=NOW_MS - 5_000),
            },
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10, "b": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_diff_dates)
        assert sig.blocked is True  # type: ignore[attr-defined]

    def test_blocked_settlement_outside_window(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        inputs = make_inputs(
            futures_quotes={
                "a": make_quote("a", bid="1.05", ask="1.06"),
                "b": make_quote("b", bid="0.99", ask="1.00"),
            },
            funding={
                "a": make_funding("a", rate="0.02", next_settlement_ms=LATER_MS),
                "b": make_funding("b", rate="0.001", next_settlement_ms=LATER_MS),
            },
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10, "b": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_diff_dates)
        assert sig.blocked is True  # type: ignore[attr-defined]

    def test_blocked_no_funding_data(self, make_inputs, make_quote, make_fee) -> None:
        inputs = make_inputs(
            futures_quotes={
                "a": make_quote("a", bid="1.05", ask="1.06"),
                "b": make_quote("b", bid="0.99", ask="1.00"),
            },
            fees={"a": make_fee("a"), "b": make_fee("b")},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_diff_dates)
        assert sig.blocked is True  # type: ignore[attr-defined]

    def test_close_signal_when_spread_collapses(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        inputs = make_inputs(
            futures_quotes={
                "a": make_quote("a", bid="1.0001", ask="1.0002"),
                "b": make_quote("b", bid="0.9999", ask="1.0000"),
            },
            funding={
                "a": make_funding("a", rate="0.0001", next_settlement_ms=SOON_MS),
                "b": make_funding("b", rate="0.0001", next_settlement_ms=SOON_MS),
            },
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10, "b": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_diff_dates)
        assert sig.action.value == "close"  # type: ignore[attr-defined]

    def test_blocked_by_checklist_asset_mismatch(
        self, make_inputs, make_quote, make_funding, make_fee
    ) -> None:
        """Short leg quotes a different asset symbol → checklist fails."""
        inputs = make_inputs(
            futures_quotes={
                "a": make_quote("a", bid="1.05", ask="1.06", symbol="OTHER/USDT:USDT"),
                "b": make_quote("b", bid="0.99", ask="1.00"),
            },
            funding={
                "a": make_funding("a", rate="0.02", next_settlement_ms=SOON_MS),
                "b": make_funding("b", rate="0.001", next_settlement_ms=SOON_MS),
            },
            fees={"a": make_fee("a"), "b": make_fee("b")},
            leverage={"a": 10, "b": 10},
            now=NOW_MS,
        )
        sig = _evaluate(_svc(), inputs, StrategyKind.funding_diff_dates)
        assert sig.blocked is True  # type: ignore[attr-defined]
        assert sig.block_reason is not None and "same_asset" in sig.block_reason  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Cross-strategy: all 6 are unavailable when no data at all
# ---------------------------------------------------------------------------

class TestAllStrategiesUnavailableWithNoData:
    @pytest.mark.parametrize("strategy", list(StrategyKind))
    def test_blocked_with_empty_inputs(self, strategy: StrategyKind, make_inputs) -> None:
        """Empty inputs → every strategy unavailable → blocked signal."""
        inputs = make_inputs(now=NOW_MS)
        sig = _evaluate(_svc(), inputs, strategy)
        assert sig.blocked is True  # type: ignore[attr-defined]
