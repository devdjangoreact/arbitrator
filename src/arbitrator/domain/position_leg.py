from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PositionLeg(BaseModel):
    """Single open USDT-M futures position leg."""

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    display_name: str
    symbol: str
    side: Literal["long", "short"]
    contracts: float
    contract_size: float
    entry_price: float
    mark_price: float | None
    opened_at: datetime
    unrealized_pnl: float | None
    accrued_funding: float | None
    opening_fee: float | None
    estimated_close_fee: float | None
    next_funding_at: datetime | None
    arb_marker_id: str | None
    position_id: str | None
