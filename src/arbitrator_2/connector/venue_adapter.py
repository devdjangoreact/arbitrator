from __future__ import annotations

from typing import Protocol

from arbitrator_2.connector.market_id import MarketId
from arbitrator_2.connector.market_kind import MarketKind


class VenueAdapter(Protocol):
    venue_id: str

    async def close(self) -> None: ...

    async def load_markets(self, kind: MarketKind) -> None: ...

    async def watch_book(self, market: MarketId) -> dict[str, object]: ...

    async def watch_trades(self, market: MarketId) -> list[object]: ...
