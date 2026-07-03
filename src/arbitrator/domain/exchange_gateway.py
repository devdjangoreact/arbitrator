from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from typing import Literal

from arbitrator.domain.closed_position_leg import ClosedPositionLeg
from arbitrator.domain.exchange_connection_status import ExchangeConnectionStatus
from arbitrator.domain.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.funding_info import FundingInfo
from arbitrator.domain.symbol_market_info import SymbolMarketInfo
from arbitrator.domain.ticker import Ticker
from arbitrator.domain.token_identity import CurrencyNetworkInfo
from arbitrator.domain.trade_tick import TradeTick


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
        """Return all USDT-M perpetual swap symbols available on this exchange."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_symbol_market_info(self, symbol: str) -> SymbolMarketInfo | None:
        """Return unified symbol identity and min/max order notional (USDT) for a swap market."""
        raise NotImplementedError

    @abstractmethod
    async def verify_connection(self) -> ExchangeConnectionStatus:
        """Validate configured credentials, trading access, and USDT swap balance."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_open_positions(self) -> list[PositionLeg]:
        """Return all non-zero USDT-M swap positions for the authenticated account."""
        raise NotImplementedError

    @abstractmethod
    def watch_open_positions(self) -> AsyncIterator[list[PositionLeg]]:
        """Stream open USDT-M swap positions (WebSocket when supported, else REST poll)."""
        raise NotImplementedError

    @abstractmethod
    def watch_usdt_balance(self) -> AsyncIterator[float | None]:
        """Stream USDT wallet balance (WebSocket when supported, else REST poll)."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_closed_positions(
        self,
        since_ms: int,
        symbols: Sequence[str],
    ) -> list[ClosedPositionLeg]:
        """Return closed USDT-M swap position history since ``since_ms``.

        When ``symbols`` is empty, fetches full account history from the exchange.
        """
        raise NotImplementedError

    @abstractmethod
    async def fetch_funding_since(self, symbol: str, since_ms: int) -> float | None:
        """Sum funding fee payments since ``since_ms`` for ``symbol``, or None if unsupported."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_funding_infos(self, symbols: Sequence[str]) -> list[FundingInfo]:
        """Return current funding rate + next settlement for the given swap symbols.

        One-shot REST snapshot (no matching ``watch*`` channel). Symbols with no
        data are simply omitted; callers degrade those strategies to ``N/A``.
        """
        raise NotImplementedError

    @abstractmethod
    async def fetch_fee_schedule(self, symbol: str) -> FeeSchedule | None:
        """Return the maker/taker fee fractions for a swap market, or None if unknown."""
        raise NotImplementedError

    @abstractmethod
    async def open_market_position(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        amount: float,
        client_order_id: str,
    ) -> str:
        """Open a market position; returns exchange order id."""
        raise NotImplementedError

    @abstractmethod
    async def close_market_position(self, leg: PositionLeg) -> str:
        """Close an open leg via reduce-only market order; returns exchange order id."""
        raise NotImplementedError

    @abstractmethod
    def watch_order_book(
        self,
        symbol: str,
        limit: int,
    ) -> AsyncIterator[OrderBookSnapshot]:
        """Stream order book updates for a single symbol."""
        raise NotImplementedError

    @abstractmethod
    def watch_trades(self, symbol: str) -> AsyncIterator[TradeTick]:
        """Stream trade tape events for a single symbol."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_currency_networks(
        self,
        base_codes: Sequence[str],
    ) -> dict[str, CurrencyNetworkInfo]:
        """Return network/contract info for the given base currency codes.

        Calls exchange.fetchCurrencies() and extracts for each requested code:
          currency['networks'][net_key]['id']  — raw id field (may be None,
          may be a contract address or just a chain name like "ERC20").

        Returns only codes that are present in the exchange response.
        Codes absent from the exchange (delisted, no spot currency entry) are
        silently omitted — callers treat missing entries as unavailable.

        Note: fetchCurrencies() requires no credentials on most exchanges but
        may be gated (e.g. Binance returns empty without auth).  Callers should
        handle empty results gracefully.
        """
        raise NotImplementedError

    @abstractmethod
    async def common_currencies(self) -> dict[str, str]:
        """Return the exchange's ccxt commonCurrencies remapping table.

        This is the dict ccxt uses to normalise exchange-native codes to
        unified codes (e.g. {'BIFI': 'BIFI2', 'LUNA': 'LUNC'}).
        An empty dict means no remappings are configured for this exchange.
        """
        raise NotImplementedError

    @abstractmethod
    async def set_margin_mode(self, symbol: str, mode: str) -> None:
        """Set margin mode (e.g. 'cross') for a swap symbol before opening a position.

        Called once per (exchange, symbol) before the first position is opened.
        Implementations must tolerate "already set" responses without raising.
        """
        raise NotImplementedError

    @abstractmethod
    async def fetch_order_book_once(self, symbol: str, limit: int) -> OrderBookSnapshot:
        """One-shot REST fetch of the order book for a single symbol."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        raise NotImplementedError
