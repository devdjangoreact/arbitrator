from __future__ import annotations

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


def test_strategy_no_spot_marks_spot_strategies_unavailable(
    make_inputs, make_quote, make_funding, make_fee
) -> None:
    # Full futures + funding + fees, but no spot anywhere.
    inputs = make_inputs(
        short_exchange_id="a",
        long_exchange_id="b",
        futures_quotes={
            "a": make_quote("a", bid="1.05", ask="1.06"),
            "b": make_quote("b", bid="0.99", ask="1.00"),
        },
        funding={
            "a": make_funding("a", rate="0.01"),
            "b": make_funding("b", rate="0.001"),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
        leverage={"a": 10, "b": 10},
    )
    for calc in (FuturesSpot2exCalculator(), FuturesSpot1exCalculator(), FundingFsCalculator()):
        result = calc.compute(inputs)
        assert result.available is False
        assert result.unavailable_reason == "no_spot"

    # futures_futures / funding_ff do not need spot -> still available.
    assert FuturesFuturesCalculator().compute(inputs).available is True
    assert FundingFfCalculator().compute(inputs).available is True


def test_strategy_stale_settlement_blocks_funding(
    make_inputs, make_quote, make_funding, make_fee, now_ms
) -> None:
    inputs = make_inputs(
        short_exchange_id="a",
        long_exchange_id="b",
        futures_quotes={
            "a": make_quote("a", bid="1.00", ask="1.01"),
            "b": make_quote("b", bid="0.99", ask="1.00"),
        },
        funding={
            "a": make_funding("a", rate="0.02", next_settlement_ms=now_ms - 1_000),
            "b": make_funding("b", rate="0.001", next_settlement_ms=now_ms - 5_000),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
        leverage={"a": 10, "b": 10},
    )
    assert FundingFfCalculator().compute(inputs).unavailable_reason == "funding_ts_stale"
    assert FundingDiffDatesCalculator().compute(inputs).unavailable_reason == "funding_ts_stale"


def test_strategy_missing_fees_marks_unavailable(make_inputs, make_quote) -> None:
    inputs = make_inputs(
        short_exchange_id="a",
        long_exchange_id="b",
        futures_quotes={
            "a": make_quote("a", bid="1.10", ask="1.11"),
            "b": make_quote("b", bid="0.99", ask="1.00"),
        },
        fees={},
        leverage={"a": 10, "b": 10},
    )
    result = FuturesFuturesCalculator().compute(inputs)
    assert result.available is False
    assert result.unavailable_reason == "no_fees"


def test_strategy_stale_quotes_marks_unavailable(make_inputs, make_quote, make_fee) -> None:
    # A freshness-gated assembler drops stale quotes; the calculator sees them as absent.
    inputs = make_inputs(
        short_exchange_id="a",
        long_exchange_id="b",
        futures_quotes={
            "a": make_quote("a", bid=None, ask=None),
            "b": make_quote("b", bid="0.99", ask="1.00"),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
        leverage={"a": 10, "b": 10},
    )
    result = FuturesFuturesCalculator().compute(inputs)
    assert result.available is False
    assert result.unavailable_reason == "no_quotes"
