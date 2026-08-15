from __future__ import annotations

import time

from arbitrator_2.connector.bbo import Bbo
from arbitrator_2.connector.book_snapshot import BookSnapshot
from arbitrator_2.connector.market_id import MarketId


class BookStore:
    def __init__(self, depth: int = 1) -> None:
        self._depth = max(1, depth)
        self._books: dict[MarketId, BookSnapshot] = {}

    def apply(
        self,
        market: MarketId,
        bids: object,
        asks: object,
        exchange_ts_ms: int | None,
        recv_ts_ns: int,
    ) -> BookSnapshot | None:
        bid_lvls = _levels(bids, self._depth)
        ask_lvls = _levels(asks, self._depth)
        if not bid_lvls or not ask_lvls:
            return None
        snap = BookSnapshot(
            bids=bid_lvls,
            asks=ask_lvls,
            exchange_ts_ms=exchange_ts_ms,
            recv_ts_ns=recv_ts_ns,
            apply_ts_ns=time.monotonic_ns(),
        )
        self._books[market] = snap
        return snap

    def get_bbo(self, market: MarketId) -> Bbo | None:
        snap = self._books.get(market)
        return None if snap is None else snap.to_bbo()


def _levels(raw: object, depth: int) -> tuple[tuple[float, float], ...]:
    if not isinstance(raw, list):
        return ()
    out: list[tuple[float, float]] = []
    for row in raw[:depth]:
        if not isinstance(row, (list, tuple)) or len(row) < 2:
            continue
        out.append((float(row[0]), float(row[1])))
    return tuple(out)
