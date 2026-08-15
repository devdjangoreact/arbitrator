from __future__ import annotations

from dataclasses import dataclass

from arbitrator_2.connector.market_id import MarketId


@dataclass(frozen=True, slots=True)
class UnifiedTick:
    market: MarketId
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]
    exchange_ts_ms: int | None
    recv_ts_ns: int
    apply_ts_ns: int
    norm_ts_ns: int
