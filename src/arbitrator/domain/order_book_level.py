from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OrderBookLevel(BaseModel):
    """Single bid or ask level in an order book."""

    model_config = ConfigDict(frozen=True)

    price: float
    size: float
