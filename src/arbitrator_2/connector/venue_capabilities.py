from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VenueCapabilities:
    min_depth: int
    trades: bool
