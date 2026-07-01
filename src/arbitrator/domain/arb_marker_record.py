from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ArbMarkerRecord(BaseModel):
    """Local record linking both legs of an app-opened arbitrage pair."""

    model_config = ConfigDict(frozen=True)

    pair_id: str
    symbol: str
    short_exchange_id: str
    long_exchange_id: str
    short_client_order_id: str
    long_client_order_id: str
    opened_at: datetime
