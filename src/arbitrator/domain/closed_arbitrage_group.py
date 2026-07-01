from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arbitrator.domain.closed_position_leg import ClosedPositionLeg


class ClosedArbitrageGroup(BaseModel):
    """Closed short + long legs grouped as one arbitrage outcome."""

    model_config = ConfigDict(frozen=True)

    pair_id: str
    symbol: str
    short_leg: ClosedPositionLeg
    long_leg: ClosedPositionLeg
    combined_net_profit: float | None
