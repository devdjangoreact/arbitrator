from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ExecutionStatus(str, Enum):
    """Terminal status of a hedged execution attempt."""

    success = "success"
    partial = "partial"
    failed = "failed"
    rolled_back = "rolled_back"
    simulated = "simulated"


class LegExecution(BaseModel):
    """One leg of a hedged action, with the *actual* filled amount from the exchange.

    ``filled_amount`` is derived from exchange position state (FR-012), never
    from the requested intent. ``ok`` is false when the order was rejected or
    could not be placed.
    """

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    side: Literal["buy", "sell"]
    symbol: str
    requested_amount: Decimal
    filled_amount: Decimal
    order_id: str | None = None
    ok: bool = True
    message: str | None = None


class ExecutionOutcome(BaseModel):
    """Result of a hedged open/accumulate/close action on both legs (US4).

    ``imbalance_pct`` is the residual leg imbalance after the action; callers
    compare it against ``Settings.leg_imbalance_tolerance_pct`` (SC-006).
    ``rolled_back`` marks a compensated one-leg failure (no unhedged exposure).
    """

    model_config = ConfigDict(frozen=True)

    action: str
    status: ExecutionStatus
    symbol: str
    short_leg: LegExecution | None = None
    long_leg: LegExecution | None = None
    imbalance_pct: Decimal | None = None
    rolled_back: bool = False
    message: str | None = None
    pair_id: str | None = None
