from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OpportunityView(BaseModel):
    """Ephemeral descriptor for one opportunity analysis screen."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    short_exchange_id: str
    long_exchange_id: str
    pair_id: str | None = None

    def focus_key(self) -> tuple[str, str, str]:
        return (self.symbol, self.short_exchange_id, self.long_exchange_id)
