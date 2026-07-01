from __future__ import annotations

from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict

from arbitrator.domain.strategy.checklist_result import ChecklistResult
from arbitrator.domain.strategy.strategy_kind import StrategyKind


class SignalAction(str, Enum):
    """Signal kinds emitted by ``SignalService`` for the active strategy."""

    open = "open"
    close = "close"
    none = "none"


class TradeSignal(BaseModel):
    """Open/close decision for the active strategy on one symbol (FR-008).

    A ``none`` action with ``blocked=True`` carries the ``block_reason`` (stale
    funding, failed checklist item, anomaly, unavailable strategy). No numeric
    field is fabricated: ``spread_pct`` is ``None`` when the strategy could not
    be computed.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    strategy_id: StrategyKind
    action: SignalAction
    short_exchange_id: str
    long_exchange_id: str
    spread_pct: Decimal | None
    open_threshold_pct: Decimal
    close_threshold_pct: Decimal
    volume_usdt: Decimal
    checklist: ChecklistResult | None = None
    blocked: bool = False
    block_reason: str | None = None
