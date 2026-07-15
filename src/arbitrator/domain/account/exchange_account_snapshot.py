from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arbitrator.domain.account.open_order_leg import OpenOrderLeg
from arbitrator.domain.account.position_leg import PositionLeg
from arbitrator.domain.exchange.exchange_connection_status import ExchangeConnectionStatus


class ExchangeAccountSnapshot(BaseModel):
    """Read-only account view for one exchange (no trading side effects)."""

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    display_name: str
    connection: ExchangeConnectionStatus
    positions: tuple[PositionLeg, ...]
    open_orders: tuple[OpenOrderLeg, ...]
    swap_symbols_count: int | None
