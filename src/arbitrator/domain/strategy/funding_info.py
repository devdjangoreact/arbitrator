from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class FundingInfo(BaseModel):
    """Funding rate snapshot for a futures market: current rate, next rate, next settlement."""

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    symbol: str
    rate: Decimal | None
    next_rate: Decimal | None
    next_settlement_ms: int | None
    recv_time_ms: int
