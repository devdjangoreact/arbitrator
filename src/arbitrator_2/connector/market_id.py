from __future__ import annotations

from dataclasses import dataclass

from arbitrator_2.connector.market_kind import MarketKind


@dataclass(frozen=True, slots=True)
class MarketId:
    venue: str
    kind: MarketKind
    symbol: str
