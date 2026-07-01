from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ActionResultDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    message: str
    action: str | None = None
    exchange_id: str | None = None
    error_code: str | None = None


class AccumulateRequestDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    volume_usdt: float
    volume_pct: float | None = None


class PartialCloseRequestDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    volume_usdt: float
    volume_pct: float | None = None


class SetLeverageRequestDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    exchange_id: str
    leverage: int


class SetParamsRequestDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    active_strategy_id: str
    target_volume_usdt: float
    open_spread_threshold_pct: float
    close_spread_threshold_pct: float
    accumulate_volume_usdt: float
    accumulate_volume_pct: float
    close_volume_usdt: float
    close_volume_pct: float
    auto_accumulate_enabled: bool
    auto_close_enabled: bool
