from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ClosedPositionLeg(BaseModel):
    """Closed futures position leg with realized metrics."""

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    display_name: str
    symbol: str
    side: Literal["long", "short"]
    realized_pnl: float | None
    commission: float | None
    funding: float | None
    contracts: float | None = None
    contract_size: float = 1.0
    entry_price: float | None = None
    exit_price: float | None = None
    opened_at: datetime | None
    closed_at: datetime
    arb_marker_id: str | None
    position_id: str | None
