from __future__ import annotations

import asyncio

from arbitrator_2.connector.book_snapshot import BookSnapshot
from arbitrator_2.connector.market_id import MarketId


class NormalizeQueue:
    def __init__(self, maxsize: int = 1024) -> None:
        self._q: asyncio.Queue[tuple[MarketId, BookSnapshot]] = asyncio.Queue(maxsize=maxsize)
        self.dropped: int = 0

    def try_put(self, market: MarketId, snap: BookSnapshot) -> bool:
        try:
            self._q.put_nowait((market, snap))
            return True
        except asyncio.QueueFull:
            self.dropped += 1
            return False

    async def get(self) -> tuple[MarketId, BookSnapshot]:
        return await self._q.get()
