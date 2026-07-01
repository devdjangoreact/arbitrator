from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExchangeConnectionStatus(BaseModel):
    """Result of validating exchange API credentials and account access."""

    model_config = ConfigDict(frozen=True)

    exchange_id: str
    display_name: str
    credentials_configured: bool
    authenticated: bool
    trading_enabled: bool
    usdt_balance: float | None
    message: str | None
