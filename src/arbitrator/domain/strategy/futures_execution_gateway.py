from __future__ import annotations

from typing import Literal, Protocol

from arbitrator.domain.position_leg import PositionLeg


class FuturesExecutionGateway(Protocol):
    """Narrow execution surface needed by ``HedgedExecutionService`` (DIP).

    Structurally satisfied by the concrete ``ExchangeGateway`` adapters, so the
    service depends only on the operations it uses and stays trivially testable
    with a fake gateway.
    """

    async def open_market_position(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        amount: float,
        client_order_id: str,
    ) -> str: ...

    async def close_market_position(self, leg: PositionLeg) -> str: ...

    async def fetch_open_positions(self) -> list[PositionLeg]: ...

    async def set_margin_mode(self, symbol: str, mode: str) -> None: ...
