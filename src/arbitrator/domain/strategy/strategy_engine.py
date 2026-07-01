from __future__ import annotations

from collections.abc import Sequence

from arbitrator.domain.strategy.strategy_calculator import StrategyCalculator
from arbitrator.domain.strategy.strategy_inputs import StrategyInputs
from arbitrator.domain.strategy.strategy_kind import StrategyKind
from arbitrator.domain.strategy.strategy_result import StrategyResult
from arbitrator.domain.strategy.strategy_table import StrategyTable


class StrategyEngine:
    """Runs every injected calculator off one frozen snapshot and ranks results.

    Stateless and pure: each calculator decides its own availability and metrics;
    the engine only assembles the table and selects ``best_strategy_id`` by the
    highest ``% to deposit`` among available strategies (C1/FR-004/FR-020).
    """

    def __init__(self, calculators: Sequence[StrategyCalculator]) -> None:
        self._calculators = tuple(calculators)

    def compute(self, inputs: StrategyInputs) -> StrategyTable:
        results: dict[StrategyKind, StrategyResult] = {}
        for calculator in self._calculators:
            results[calculator.strategy_id] = calculator.compute(inputs)
        return StrategyTable(
            symbol=inputs.symbol,
            results=results,
            best_strategy_id=self._best(results),
            updated_at_ms=inputs.now_ms,
        )

    @staticmethod
    def _best(results: dict[StrategyKind, StrategyResult]) -> StrategyKind | None:
        best_id: StrategyKind | None = None
        best_pct = None
        for strategy_id, result in results.items():
            if not result.available or result.percent_to_deposit is None:
                continue
            if best_pct is None or result.percent_to_deposit > best_pct:
                best_pct = result.percent_to_deposit
                best_id = strategy_id
        return best_id
