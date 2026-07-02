from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PaperOrder(BaseModel):
    """Simulated order record written to paper_orders.json."""

    model_config = ConfigDict(frozen=True)

    order_id: str
    pair_id: str
    symbol: str
    exchange_id: str
    side: Literal["buy", "sell"]
    action: Literal["open", "close"]
    amount: float
    price: float
    notional_usdt: float
    status: Literal["filled", "closed"]
    opened_at: datetime
    closed_at: datetime | None = None
    pnl_usdt: float | None = None
    entry_price: float | None = None
    spread_pct_entry: float | None = None
    spread_pct_exit: float | None = None
    open_fee_usdt: float = 0.0
    close_fee_usdt: float = 0.0
    accrued_funding_usdt: float = 0.0
    net_pnl_usdt: float | None = None
    close_price: float | None = None
