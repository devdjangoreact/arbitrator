from __future__ import annotations

from decimal import Decimal

from arbitrator.application.anomaly_guard import AnomalyGuard
from arbitrator.application.checklist_evaluator import ChecklistEvaluator
from arbitrator.application.signal_service import SignalService
from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.strategies.funding_ff_calculator import FundingFfCalculator
from arbitrator.domain.strategy.strategies.futures_futures_calculator import (
    FuturesFuturesCalculator,
)
from arbitrator.domain.strategy.strategy_engine import StrategyEngine
from arbitrator.domain.strategy.strategy_inputs import StrategyInputs
from arbitrator.domain.strategy.strategy_kind import StrategyKind

OPEN_THR = Decimal("4.0")
CLOSE_THR = Decimal("0.1")


def _service() -> SignalService:
    settings = Settings()
    return SignalService(ChecklistEvaluator(settings), AnomalyGuard(settings))


def _table(inputs: StrategyInputs):
    engine = StrategyEngine([FuturesFuturesCalculator(), FundingFfCalculator()])
    return engine.compute(inputs)


def _evaluate(
    service: SignalService,
    inputs: StrategyInputs,
    strategy_id: StrategyKind = StrategyKind.futures_futures,
):
    return service.evaluate(
        inputs=inputs,
        table=_table(inputs),
        active_strategy_id=strategy_id,
        open_threshold_pct=OPEN_THR,
        close_threshold_pct=CLOSE_THR,
        volume_usdt=Decimal("1000"),
    )


def test_open_signal_above_threshold_with_valid_checklist(
    make_inputs, make_quote, make_fee
) -> None:
    # 10% cross-price spread, within the 20% anomaly cap.
    inputs = make_inputs(
        futures_quotes={
            "a": make_quote("a", bid="1.10", ask="1.11"),
            "b": make_quote("b", bid="0.99", ask="1.00"),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
        leverage={"a": 10, "b": 10},
    )
    signal = _evaluate(_service(), inputs)
    assert signal.action.value == "open"
    assert signal.blocked is False
    assert signal.checklist is not None and signal.checklist.passed


def test_close_signal_below_close_threshold(make_inputs, make_quote, make_fee) -> None:
    # Tiny spread: 0.05% <= close threshold 0.1% -> close.
    inputs = make_inputs(
        futures_quotes={
            "a": make_quote("a", bid="1.0005", ask="1.0006"),
            "b": make_quote("b", bid="0.9999", ask="1.0000"),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
        leverage={"a": 10, "b": 10},
    )
    signal = _evaluate(_service(), inputs)
    assert signal.action.value == "close"


def test_anomalous_spread_blocks_open(make_inputs, make_quote, make_fee) -> None:
    # 30% spread exceeds the 20% anomaly cap -> blocked, no open.
    inputs = make_inputs(
        futures_quotes={
            "a": make_quote("a", bid="1.30", ask="1.31"),
            "b": make_quote("b", bid="0.99", ask="1.00"),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
        leverage={"a": 10, "b": 10},
    )
    signal = _evaluate(_service(), inputs)
    assert signal.action.value == "none"
    assert signal.blocked is True
    assert signal.block_reason == "anomalous_spread"


def test_failed_checklist_blocks_open(make_inputs, make_quote, make_fee) -> None:
    # Wide spread would open, but the short leg quotes a different asset.
    inputs = make_inputs(
        futures_quotes={
            "a": make_quote("a", bid="1.10", ask="1.11", symbol="OTHER/USDT:USDT"),
            "b": make_quote("b", bid="0.99", ask="1.00"),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
        leverage={"a": 10, "b": 10},
    )
    signal = _evaluate(_service(), inputs)
    assert signal.action.value == "none"
    assert signal.blocked is True
    assert signal.block_reason is not None and "same_asset" in signal.block_reason


def test_stale_funding_blocks_funding_strategy(
    make_inputs, make_quote, make_funding, make_fee, now_ms
) -> None:
    # funding_ff active, but next settlement is in the past -> strategy unavailable, no open.
    inputs = make_inputs(
        futures_quotes={
            "a": make_quote("a", bid="1.10", ask="1.11"),
            "b": make_quote("b", bid="0.99", ask="1.00"),
        },
        funding={
            "a": make_funding("a", rate="0.02", next_settlement_ms=now_ms - 1_000),
            "b": make_funding("b", rate="0.001", next_settlement_ms=now_ms - 5_000),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
        leverage={"a": 10, "b": 10},
    )
    signal = _evaluate(_service(), inputs, strategy_id=StrategyKind.funding_ff)
    assert signal.action.value == "none"
    assert signal.blocked is True


def test_checklist_funding_ts_valid_for_non_funding_strategy(
    make_inputs, make_quote, make_fee
) -> None:
    settings = Settings()
    inputs = make_inputs(
        futures_quotes={
            "a": make_quote("a", bid="1.10", ask="1.11"),
            "b": make_quote("b", bid="0.99", ask="1.00"),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
    )
    checklist = ChecklistEvaluator(settings).evaluate(inputs, StrategyKind.futures_futures)
    # No funding data present, but the non-funding strategy does not require it.
    assert checklist.funding_ts_valid is True
    assert checklist.passed is True
