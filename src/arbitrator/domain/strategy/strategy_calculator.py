from __future__ import annotations

from typing import Protocol, runtime_checkable

from arbitrator.domain.strategy.strategy_inputs import StrategyInputs
from arbitrator.domain.strategy.strategy_kind import StrategyKind
from arbitrator.domain.strategy.strategy_result import StrategyResult


@runtime_checkable
class StrategyCalculator(Protocol):
    """One stateless calculator per strategy (Open/Closed, DIP).

    Implementations are pure: no I/O, ``Decimal`` only, computed off a frozen
    ``StrategyInputs`` snapshot. Missing/insufficient data -> an unavailable
    ``StrategyResult`` (never fabricated numbers).
    """

    strategy_id: StrategyKind

    def compute(self, inputs: StrategyInputs) -> StrategyResult: ...
