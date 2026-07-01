from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from arbitrator.domain.position_leg import PositionLeg


def make_leg(
    *,
    exchange_id: str,
    side: Literal["long", "short"],
    symbol: str = "BTC/USDT:USDT",
    marker: str | None = None,
    opened_at: datetime | None = None,
) -> PositionLeg:
    return PositionLeg(
        exchange_id=exchange_id,
        display_name=exchange_id.upper(),
        symbol=symbol,
        side=side,
        contracts=1.0,
        contract_size=1.0,
        entry_price=100.0 if side == "long" else 105.0,
        mark_price=101.0 if side == "long" else 104.0,
        opened_at=opened_at or datetime.now(UTC),
        unrealized_pnl=1.0,
        accrued_funding=-0.1,
        opening_fee=0.05,
        estimated_close_fee=0.05,
        next_funding_at=None,
        arb_marker_id=marker,
        position_id="pos-1",
    )
