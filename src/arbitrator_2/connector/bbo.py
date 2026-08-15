from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Bbo:
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    exchange_ts_ms: int | None
    recv_ts_ns: int
    apply_ts_ns: int
