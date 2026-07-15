from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Literal

import pytest

from arbitrator.config.settings import Settings
from arbitrator.domain.account.closed_position_leg import ClosedPositionLeg
from arbitrator.domain.account.position_leg import PositionLeg
from arbitrator.domain.exchange.exchange_connection_status import ExchangeConnectionStatus
from arbitrator.domain.exchange.exchange_gateway import ExchangeGateway
from arbitrator.domain.market.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.market.trade_tick import TradeTick
from arbitrator.domain.universe.symbol_market_info import SymbolMarketInfo
from arbitrator.domain.universe.token_identity import CurrencyNetworkInfo


class MockGateway(ExchangeGateway):
    def __init__(
        self,
        *,
        open_legs: list[PositionLeg] | None = None,
        closed_legs: list[ClosedPositionLeg] | None = None,
    ) -> None:
        self._open = open_legs or []
        self._closed = closed_legs or []
        self.open_calls: list[tuple[str, str, float, str]] = []
        self.close_calls: list[PositionLeg] = []

    def watch_tickers(self, symbols):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def watch_order_book(
        self,
        symbol: str,
        limit: int,
    ) -> AsyncIterator[OrderBookSnapshot]:
        for _ in ():
            yield OrderBookSnapshot(
                exchange_id="mexc",
                symbol=symbol,
                timestamp_ms=None,
                bids=(),
                asks=(),
            )

    async def watch_trades(self, symbol: str) -> AsyncIterator[TradeTick]:
        for _ in ():
            yield TradeTick(
                exchange_id="mexc",
                symbol=symbol,
                timestamp_ms=0,
                price=1.0,
                amount=1.0,
                side="buy",
            )

    async def list_symbols(self) -> list[str]:
        return []

    async def fetch_symbol_market_info(self, symbol: str) -> SymbolMarketInfo | None:
        return None

    async def verify_connection(self) -> ExchangeConnectionStatus:
        return ExchangeConnectionStatus(
            exchange_id="mexc",
            display_name="MEXC",
            credentials_configured=True,
            authenticated=True,
            trading_enabled=True,
            usdt_balance=100.0,
            message="ok",
        )

    async def fetch_open_positions(self) -> list[PositionLeg]:
        return list(self._open)

    async def watch_open_positions(self) -> AsyncIterator[list[PositionLeg]]:
        while True:
            yield list(self._open)

    async def watch_usdt_balance(self) -> AsyncIterator[float | None]:
        while True:
            yield 100.0

    async def fetch_closed_positions(self, since_ms: int, symbols):  # type: ignore[no-untyped-def]
        return list(self._closed)

    async def fetch_funding_since(self, symbol: str, since_ms: int) -> float | None:
        return None

    async def fetch_funding_infos(self, symbols):  # type: ignore[no-untyped-def]
        return []

    async def fetch_fee_schedule(self, symbol: str):  # type: ignore[no-untyped-def]
        return None

    async def fetch_ticker(self, symbol: str):  # type: ignore[no-untyped-def]
        return None

    async def open_market_position(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        amount: float,
        client_order_id: str,
    ) -> str:
        self.open_calls.append((symbol, side, amount, client_order_id))
        return "order-1"

    async def close_market_position(self, leg: PositionLeg) -> str:
        self.close_calls.append(leg)
        return "close-1"

    async def fetch_currency_networks(
        self,
        base_codes: Sequence[str],
    ) -> dict[str, CurrencyNetworkInfo]:
        return {}

    async def common_currencies(self) -> dict[str, str]:
        return {}

    async def set_margin_mode(self, symbol: str, mode: str) -> None:
        return None

    async def fetch_order_book_once(self, symbol: str, limit: int) -> OrderBookSnapshot:
        return OrderBookSnapshot(
            exchange_id="mexc",
            symbol=symbol,
            timestamp_ms=None,
            bids=(),
            asks=(),
        )

    async def close(self) -> None:
        return None


import nest_asyncio

nest_asyncio.apply()

@pytest.fixture
def settings() -> Settings:
    return Settings()
