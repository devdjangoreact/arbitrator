from __future__ import annotations

import asyncio

from arbitrator_2.connector.market_id import MarketId
from arbitrator_2.connector.market_kind import MarketKind


class FakeVenue:
    def __init__(
        self,
        venue_id: str,
        *,
        load_delay: float = 0.0,
        load_error: BaseException | None = None,
    ) -> None:
        self.venue_id = venue_id
        self.load_delay = load_delay
        self.load_error = load_error
        self.load_calls = 0
        self._loaded: set[MarketKind] = set()
        self._gate = asyncio.Event()
        self._sent = False

    async def close(self) -> None:
        self._gate.set()

    async def load_markets(self, kind: MarketKind) -> None:
        if kind in self._loaded:
            return
        self.load_calls += 1
        if self.load_delay > 0:
            await asyncio.sleep(self.load_delay)
        if self.load_error is not None:
            raise self.load_error
        self._loaded.add(kind)

    async def watch_book(self, market: MarketId) -> dict[str, object]:
        _ = market
        if not self._sent:
            self._sent = True
            return {"bids": [[100.0, 2.0]], "asks": [[101.0, 3.0]], "timestamp": 1}
        await self._gate.wait()
        return {"bids": [[100.0, 2.0]], "asks": [[101.0, 3.0]], "timestamp": 1}

    async def watch_trades(self, market: MarketId) -> list[object]:
        _ = market
        raise NotImplementedError("trades disabled")
