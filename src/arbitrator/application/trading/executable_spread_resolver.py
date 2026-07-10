from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from arbitrator.config.logger import logger
from arbitrator.domain.market.spread_calculator import SpreadCalculator
from arbitrator.domain.market.ticker import Ticker

if TYPE_CHECKING:

    from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
    from arbitrator.config.settings import Settings
    from arbitrator.domain.exchange.exchange_gateway import ExchangeGateway


@dataclass(frozen=True, slots=True)
class TopOfBook:
    """Best bid and ask for one venue (order-book top preferred over ticker)."""

    bid: float

    ask: float


class ExecutableSpreadResolver:
    """Resolve bid/ask for open/close spread decisions.



    Cached path (``fetch_fresh=False`` — screener ranking, candidate scan):

    1. Cached order-book top (``bids[0]`` / ``asks[0]``)

    2. Cached quote bid/ask

    3. Ticker ``bid`` + ``ask`` when both are present



    Fresh path (``fetch_fresh=True`` — open, close, DCA, funding protect):

    REST ``fetch_order_book_once`` when a gateway is available, then the cached

    path above as fallback.



    Never uses ``last`` — that field is 24h stats, not an executable quote.

    """

    def __init__(
        self,
        settings: Settings,
        cache: MarketDataCacheMemory,
        gateways: Mapping[str, ExchangeGateway] | None = None,
    ) -> None:

        self._settings = settings

        self._cache = cache

        self._gateways = gateways or {}

    def top_of_book_sync(
        self,
        exchange_id: str,
        symbol: str,
        ticker: Ticker | None = None,
        *,
        max_age_ms: float | None = None,
    ) -> TopOfBook | None:
        now_ms = time.time() * 1000

        book = self._cache.get_order_book(exchange_id, symbol)

        if book is not None and book.bids and book.asks:
            age_ms = now_ms - (book.timestamp_ms or 0)
            book_max = (self._settings.book_max_age_seconds * 1000) if max_age_ms is None else max_age_ms
            if book.timestamp_ms is None or age_ms <= book_max:
                return TopOfBook(bid=book.bids[0].price, ask=book.asks[0].price)

        quote = self._cache.get_quote(exchange_id, symbol, "futures")

        if quote is not None and quote.bid is not None and quote.ask is not None:
            age_ms = now_ms - quote.recv_time_ms
            quote_max = (self._settings.quote_max_age_seconds * 1000) if max_age_ms is None else max_age_ms
            if age_ms <= quote_max:
                bid = float(quote.bid)
                ask = float(quote.ask)
                if bid > 0.0 and ask > 0.0:
                    return TopOfBook(bid=bid, ask=ask)

        if (
            ticker is not None
            and ticker.bid is not None
            and ticker.ask is not None
            and ticker.bid > 0.0
            and ticker.ask > 0.0
        ):
            ticker_max = (self._settings.quote_max_age_seconds * 1000) if max_age_ms is None else max_age_ms
            if ticker.timestamp_ms is None or now_ms - ticker.timestamp_ms <= ticker_max:
                return TopOfBook(bid=ticker.bid, ask=ticker.ask)

        return None

    async def top_of_book(
        self,
        exchange_id: str,
        symbol: str,
        ticker: Ticker | None = None,
        *,
        fetch_fresh: bool = False,
    ) -> TopOfBook | None:

        if fetch_fresh:

            gateway = self._gateways.get(exchange_id)

            if gateway is not None:

                depth = self._settings.opportunity_order_book_depth

                try:

                    book = await gateway.fetch_order_book_once(symbol, depth)

                except Exception:

                    logger.exception(
                        "executable spread: order book fetch failed | ex={} sym={}",
                        exchange_id,
                        symbol,
                    )

                else:

                    if book.bids and book.asks:

                        self._cache.put_order_book(book)

                        return TopOfBook(bid=book.bids[0].price, ask=book.asks[0].price)

        return self.top_of_book_sync(exchange_id, symbol, ticker)

    def needs_rest_book(
        self,
        exchange_id: str,
        symbol: str,
        ticker: Ticker | None = None,
    ) -> bool:
        """True if we don't have a fresh cached order book with depth for this venue."""
        now_ms = time.time() * 1000
        book = self._cache.get_order_book(exchange_id, symbol)
        if book is not None and book.bids and book.asks:
            age_ms = now_ms - (book.timestamp_ms or 0)
            if book.timestamp_ms is not None and age_ms <= (self._settings.book_max_age_seconds * 1000):
                return False
        return True

    def should_rest_verify_entry(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        *,
        short_ticker: Ticker | None = None,
        long_ticker: Ticker | None = None,
    ) -> bool:
        """REST verify when a leg lacks a cached order book."""

        return self.needs_rest_book(short_ex, symbol, short_ticker) or self.needs_rest_book(
            long_ex,
            symbol,
            long_ticker,
        )

    async def entry_spread_for_open(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        *,
        short_ticker: Ticker | None = None,
        long_ticker: Ticker | None = None,
    ) -> tuple[float, float, float] | None:
        """Entry spread with REST only when a leg needs a fresh book."""

        fetch_fresh = self.should_rest_verify_entry(
            symbol,
            short_ex,
            long_ex,
            short_ticker=short_ticker,
            long_ticker=long_ticker,
        )
        return await self.entry_spread(
            symbol,
            short_ex,
            long_ex,
            short_ticker=short_ticker,
            long_ticker=long_ticker,
            fetch_fresh=fetch_fresh,
        )

    async def entry_spread(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        *,
        short_ticker: Ticker | None = None,
        long_ticker: Ticker | None = None,
        fetch_fresh: bool = False,
    ) -> tuple[float, float, float] | None:
        """Return ``(short_bid, long_ask, spread_pct)`` or None."""

        import asyncio
        short_book, long_book = await asyncio.gather(
            self.top_of_book(
                short_ex,
                symbol,
                short_ticker,
                fetch_fresh=fetch_fresh,
            ),
            self.top_of_book(
                long_ex,
                symbol,
                long_ticker,
                fetch_fresh=fetch_fresh,
            )
        )

        if short_book is None or long_book is None:
            return None

        spread = SpreadCalculator.entry_spread_pct(short_book.bid, long_book.ask)

        if spread is None:
            return None

        return short_book.bid, long_book.ask, spread

    def entry_spread_sync(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        *,
        short_ticker: Ticker | None = None,
        long_ticker: Ticker | None = None,
    ) -> tuple[float, float, float] | None:

        short_book = self.top_of_book_sync(short_ex, symbol, short_ticker)

        long_book = self.top_of_book_sync(long_ex, symbol, long_ticker)

        if short_book is None or long_book is None:

            return None

        spread = SpreadCalculator.entry_spread_pct(short_book.bid, long_book.ask)

        if spread is None:

            return None

        return short_book.bid, long_book.ask, spread

    async def exit_spread(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        *,
        short_ticker: Ticker | None = None,
        long_ticker: Ticker | None = None,
        fetch_fresh: bool = False,
    ) -> tuple[float, float, float] | None:
        """Return ``(short_ask, long_bid, spread_pct)`` or None."""

        import asyncio
        short_book, long_book = await asyncio.gather(
            self.top_of_book(
                short_ex,
                symbol,
                short_ticker,
                fetch_fresh=fetch_fresh,
            ),
            self.top_of_book(
                long_ex,
                symbol,
                long_ticker,
                fetch_fresh=fetch_fresh,
            )
        )

        if short_book is None or long_book is None:
            return None

        spread = SpreadCalculator.exit_spread_pct(short_book.ask, long_book.bid)

        if spread is None:
            return None

        return short_book.ask, long_book.bid, spread

    def exit_spread_sync(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        *,
        short_ticker: Ticker | None = None,
        long_ticker: Ticker | None = None,
    ) -> tuple[float, float, float] | None:

        short_book = self.top_of_book_sync(short_ex, symbol, short_ticker)

        long_book = self.top_of_book_sync(long_ex, symbol, long_ticker)

        if short_book is None or long_book is None:

            return None

        spread = SpreadCalculator.exit_spread_pct(short_book.ask, long_book.bid)

        if spread is None:

            return None

        return short_book.ask, long_book.bid, spread

    async def best_entry_pair(
        self,
        symbol: str,
        per_exchange_tickers: Mapping[str, Ticker],
        *,
        fetch_fresh: bool = False,
    ) -> tuple[str, str, float, float, float] | None:
        """Best cross-venue entry among exchanges with resolvable bid/ask."""

        bid_by_exchange: dict[str, float] = {}

        ask_by_exchange: dict[str, float] = {}

        for exchange_id, ticker in per_exchange_tickers.items():

            top = await self.top_of_book(
                exchange_id,
                symbol,
                ticker,
                fetch_fresh=fetch_fresh,
            )

            if top is None:

                continue

            bid_by_exchange[exchange_id] = top.bid

            ask_by_exchange[exchange_id] = top.ask

        return SpreadCalculator.best_executable_pair(bid_by_exchange, ask_by_exchange)

    def best_entry_pair_sync(
        self,
        symbol: str,
        per_exchange_tickers: Mapping[str, Ticker],
    ) -> tuple[str, str, float, float, float] | None:

        bid_by_exchange: dict[str, float] = {}

        ask_by_exchange: dict[str, float] = {}

        for exchange_id, ticker in per_exchange_tickers.items():

            top = self.top_of_book_sync(exchange_id, symbol, ticker)

            if top is None:

                continue

            bid_by_exchange[exchange_id] = top.bid

            ask_by_exchange[exchange_id] = top.ask

        return SpreadCalculator.best_executable_pair(bid_by_exchange, ask_by_exchange)
