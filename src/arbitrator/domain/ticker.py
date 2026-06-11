from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Ticker(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    last: float | None
    high_24h: float | None
    low_24h: float | None
    base_volume_24h: float | None
    quote_volume_24h: float | None
    timestamp_ms: int | None

    @property
    def base_asset(self) -> str:
        return self.symbol.split("/")[0] if "/" in self.symbol else self.symbol

    @property
    def quote_asset(self) -> str:
        parts = self.symbol.split("/")
        if len(parts) <= 1:
            return ""
        return parts[1].split(":")[0]
