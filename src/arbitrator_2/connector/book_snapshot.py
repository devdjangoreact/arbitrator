from __future__ import annotations

from dataclasses import dataclass

from arbitrator_2.connector.bbo import Bbo


@dataclass(frozen=True, slots=True)
class BookSnapshot:
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]
    exchange_ts_ms: int | None
    recv_ts_ns: int
    apply_ts_ns: int

    def to_bbo(self) -> Bbo:
        bid = self.bids[0]
        ask = self.asks[0]
        return Bbo(
            bid=bid[0],
            ask=ask[0],
            bid_size=bid[1],
            ask_size=ask[1],
            exchange_ts_ms=self.exchange_ts_ms,
            recv_ts_ns=self.recv_ts_ns,
            apply_ts_ns=self.apply_ts_ns,
        )
