from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from arbitrator.domain.strategy.strategy_kind import StrategyKind


class StrategyResult(BaseModel):
    """Outcome of one strategy for one symbol.

    ``available=False`` carries ``unavailable_reason`` and leaves the numeric
    fields ``None`` (no fabrication, FR-003). All money/price fields keep full
    ``Decimal`` precision; rounding happens only at the serializer edge (FR-005).
    """

    model_config = ConfigDict(frozen=True)

    strategy_id: StrategyKind
    available: bool
    unavailable_reason: str | None = None
    spread_pct: Decimal | None = None
    price_short: Decimal | None = None
    price_long: Decimal | None = None
    fees_usdt: Decimal | None = None
    funding_usdt: Decimal | None = None
    volume_usdt: Decimal | None = None
    leverage: int | None = None
    gross_profit_usdt: Decimal | None = None
    costs_usdt: Decimal | None = None
    costs_breakdown: str | None = None
    net_profit_usdt: Decimal | None = None
    percent_to_deposit: Decimal | None = None

    @classmethod
    def unavailable(cls, strategy_id: StrategyKind, reason: str) -> StrategyResult:
        return cls(strategy_id=strategy_id, available=False, unavailable_reason=reason)
