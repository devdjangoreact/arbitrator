from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arbitrator.domain.order_book_level import OrderBookLevel


class OrderBookSnapshot(BaseModel):
    """Point-in-time order book for one symbol on one exchange."""

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    symbol: str
    timestamp_ms: int | None
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]
