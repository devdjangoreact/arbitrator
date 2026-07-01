from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SpreadSnapshot(BaseModel):
    """Live cross-exchange prices for one symbol."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    prices_by_exchange: dict[str, float]
    spread_pct: float | None
    high_exchange_id: str | None
    low_exchange_id: str | None
    updated_at: datetime
