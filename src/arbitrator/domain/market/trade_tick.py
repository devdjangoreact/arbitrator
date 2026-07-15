from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class TradeTick(BaseModel):
    """Single aggressor trade event for chart tape bubbles."""

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    symbol: str
    timestamp_ms: int
    price: float
    amount: float
    side: Literal["buy", "sell"]
