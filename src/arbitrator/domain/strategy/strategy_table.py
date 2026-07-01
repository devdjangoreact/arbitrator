from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arbitrator.domain.strategy.strategy_kind import StrategyKind
from arbitrator.domain.strategy.strategy_result import StrategyResult


class StrategyTable(BaseModel):
    """All strategy results for one symbol plus the best by ``% to deposit``."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    results: dict[StrategyKind, StrategyResult]
    best_strategy_id: StrategyKind | None = None
    updated_at_ms: int
