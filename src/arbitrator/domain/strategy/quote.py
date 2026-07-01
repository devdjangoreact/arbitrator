from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Quote(BaseModel):
    """Best bid/ask/last snapshot for one market on one exchange (Decimal domain)."""

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    symbol: str
    market_type: Literal["futures", "spot"]
    bid: Decimal | None
    ask: Decimal | None
    last: Decimal | None
    recv_time_ms: int
