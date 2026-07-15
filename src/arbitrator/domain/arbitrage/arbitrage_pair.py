from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arbitrator.domain.account.position_leg import PositionLeg


class ArbitragePair(BaseModel):
    """Linked short + long legs on different exchanges for the same symbol."""

    model_config = ConfigDict(frozen=True)

    pair_id: str
    symbol: str
    short_leg: PositionLeg
    long_leg: PositionLeg
    combined_unrealized_pnl: float | None
    combined_accrued_funding: float | None
    projected_net_pnl: float | None
    is_complete: bool
