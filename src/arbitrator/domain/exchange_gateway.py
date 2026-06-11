from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

from arbitrator.domain.ticker import Ticker


class ExchangeGateway(ABC):
    @abstractmethod
    def watch_tickers(self, symbols: Sequence[str]) -> AsyncIterator[dict[str, Ticker]]:
        """Stream ticker updates for the given symbols over a single WebSocket
        subscription (or a transparent per-symbol fallback when the exchange
        does not expose a multi-ticker channel).

        Yields a mapping of ``{symbol: Ticker}`` containing only the symbols
        that received a fresh update on this iteration. Dynamic filtering
        (volume, spread, etc.) is the caller's responsibility.
        """
        raise NotImplementedError

    @abstractmethod
    async def list_symbols(self) -> list[str]:
        """Return all USDT-margined perpetual swap symbols available on this exchange."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
