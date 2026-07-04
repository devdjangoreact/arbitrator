from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from decimal import Decimal

from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.quote import Quote


class SpotGateway(ABC):
    """Abstraction for spot market data and order placement."""

    @abstractmethod
    async def list_spot_symbols(self) -> list[str]:
        """Return all USDT spot symbols (e.g. BTC/USDT) available on this exchange."""
        raise NotImplementedError

    @abstractmethod
    def watch_spot_tickers(
        self, symbols: Sequence[str]
    ) -> AsyncIterator[dict[str, Quote]]:
        """Stream spot bid/ask/last for the given symbols.

        Yields a mapping of {symbol: Quote} for symbols with fresh updates.
        """
        raise NotImplementedError

    @abstractmethod
    async def fetch_spot_fee(self, symbol: str) -> FeeSchedule | None:
        """Return maker/taker fee for a spot market."""
        raise NotImplementedError

    @abstractmethod
    async def buy_spot_market(
        self, symbol: str, amount: float, client_order_id: str
    ) -> str:
        """Buy tokens at market price. Returns order id."""
        raise NotImplementedError

    @abstractmethod
    async def sell_spot_market(
        self, symbol: str, amount: float, client_order_id: str
    ) -> str:
        """Sell tokens at market price. Returns order id."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_balance(self, asset: str) -> Decimal:
        """Return available balance for the given asset (e.g. 'BTC')."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
