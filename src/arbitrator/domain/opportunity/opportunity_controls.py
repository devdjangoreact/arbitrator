from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OpportunityControls(BaseModel):
    """Per-opportunity trading parameters (session memory only)."""

    model_config = ConfigDict(frozen=True)

    accumulate_spread_threshold_pct: float = Field(gt=0.0)
    max_notional_usdt: float = Field(gt=0.0)
    leverage: int = Field(ge=1)
    min_close_spread_pct: float = Field(ge=0.0)
    auto_accumulate: bool = False
    auto_close: bool = False
