from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class FeeSchedule(BaseModel):
    """Maker/taker fee fractions for futures and spot markets on one exchange."""

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    symbol: str
    futures_maker: Decimal | None
    futures_taker: Decimal | None
    spot_maker: Decimal | None
    spot_taker: Decimal | None
