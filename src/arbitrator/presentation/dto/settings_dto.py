from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SettingsExchangeDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    exchange_id: str
    api_key_masked: str
    configured: bool
    has_secret: bool
    has_password: bool


class SettingsSnapshotDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    exchanges: list[SettingsExchangeDto]


class SettingsExchangeUpdateDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    exchange_id: str
    api_key: str
    api_secret: str = ""
    api_password: str = ""
