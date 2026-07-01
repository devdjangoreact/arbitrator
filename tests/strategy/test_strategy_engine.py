from __future__ import annotations

from decimal import Decimal

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
from arbitrator.domain.strategy.strategy_kind import StrategyKind


def _engine() -> StrategyEngine:
    return StrategyEngine(
        [
            FuturesFuturesCalculator(),
            FuturesSpot2exCalculator(),
            FuturesSpot1exCalculator(),
            FundingFfCalculator(),
            FundingFsCalculator(),
            FundingDiffDatesCalculator(),
        ]
    )


def test_strategy_engine_mixed_availability_and_best(
    make_inputs, make_quote, make_funding, make_fee, now_ms
) -> None:
    inputs = make_inputs(
        short_exchange_id="a",
        long_exchange_id="b",
        futures_quotes={
            "a": make_quote("a", bid="1.10", ask="1.11"),
            "b": make_quote("b", bid="0.99", ask="1.00"),
        },
        funding={
            "a": make_funding("a", rate="0.02", next_settlement_ms=now_ms + 60_000),
            "b": make_funding("b", rate="0.001", next_settlement_ms=now_ms + 3_600_000),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
        target_volume_usdt="1000",
        leverage={"a": 10, "b": 10},
    )
    table = _engine().compute(inputs)

    assert len(table.results) == 6
    # No spot anywhere -> spot strategies unavailable.
    assert table.results[StrategyKind.futures_spot_2ex].available is False
    assert table.results[StrategyKind.futures_spot_1ex].available is False
    assert table.results[StrategyKind.funding_fs].available is False
    # Futures-only strategies are available.
    assert table.results[StrategyKind.futures_futures].available is True
    assert table.results[StrategyKind.funding_ff].available is True
    assert table.results[StrategyKind.funding_diff_dates].available is True

    # Best = highest % to deposit among available (futures_futures here).
    assert table.best_strategy_id == StrategyKind.futures_futures
    assert table.results[StrategyKind.futures_futures].percent_to_deposit == Decimal("39.5")


def test_strategy_engine_preserves_decimal_precision(
    make_inputs, make_quote, make_fee
) -> None:
    # 1/3-style spread keeps full Decimal precision internally (no early rounding).
    inputs = make_inputs(
        short_exchange_id="a",
        long_exchange_id="b",
        futures_quotes={
            "a": make_quote("a", bid="1.00", ask="1.01"),
            "b": make_quote("b", bid="2.99", ask="3.00"),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
        target_volume_usdt="1000",
        leverage={"a": 10, "b": 10},
    )
    result = _engine().compute(inputs).results[StrategyKind.futures_futures]
    assert isinstance(result.spread_pct, Decimal)
    assert isinstance(result.net_profit_usdt, Decimal)
    # (1.00 - 3.00) / 3.00 * 100 -> repeating decimal, must not be pre-rounded to 2 places.
    assert result.spread_pct is not None
    assert str(result.spread_pct) not in {"-66.67", "-66.66"}
