from __future__ import annotations

from enum import StrEnum


class MarketKind(StrEnum):
    SPOT = "spot"
    PERP = "perp"
