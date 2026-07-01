from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ExchangeCredentials(BaseModel):
    """API credentials for a single exchange account."""

    model_config = ConfigDict(frozen=True)

    api_key: str
    api_secret: str
    password: str = ""

    def is_complete(self, *, requires_password: bool = False) -> bool:
        if not self.api_key or not self.api_secret:
            return False
        return not (requires_password and not self.password)
