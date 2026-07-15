from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class OpenOrderLeg(BaseModel):
    """Single open USDT-M swap order (read-only snapshot)."""

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    order_type: str
    price: float | None
    amount: float | None
    filled: float | None
    remaining: float | None
    status: str | None
    timestamp_ms: int | None
