from __future__ import annotations

import threading
from typing import Literal

from arbitrator.domain.market.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.funding_info import FundingInfo
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.universe.symbol_market_info import SymbolMarketInfo


class MarketDataCacheMemory:
    """Thread-safe in-process L1 cache of the latest exchange snapshots.

    Implements the ``MarketDataCache`` read protocol and adds writers used by the
    stream workers / fee snapshot service. All values are immutable domain models
    already converted to ``Decimal``; freshness is decided by callers via the
    ``recv_time_ms`` each value carries.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._quotes: dict[tuple[str, str, str], Quote] = {}
        self._funding: dict[tuple[str, str], FundingInfo] = {}
        self._fees: dict[tuple[str, str], FeeSchedule] = {}
        self._market_info: dict[tuple[str, str], SymbolMarketInfo] = {}
        self._order_books: dict[tuple[str, str], OrderBookSnapshot] = {}
        self._usdt_balances: dict[str, float] = {}

    def put_usdt_balance(self, exchange_id: str, balance: float) -> None:
        with self._lock:
            self._usdt_balances[exchange_id] = balance

    def get_usdt_balance(self, exchange_id: str) -> float | None:
        with self._lock:
            return self._usdt_balances.get(exchange_id)

    def put_quote(self, quote: Quote) -> None:
        key = (quote.exchange_id, quote.symbol, quote.market_type)
        with self._lock:
            self._quotes[key] = quote

    def put_funding(self, funding: FundingInfo) -> None:
        with self._lock:
            self._funding[(funding.exchange_id, funding.symbol)] = funding

    def put_fees(self, fees: FeeSchedule) -> None:
        with self._lock:
            self._fees[(fees.exchange_id, fees.symbol)] = fees

    def get_quote(
        self,
        exchange_id: str,
        symbol: str,
        market_type: Literal["futures", "spot"],
    ) -> Quote | None:
        with self._lock:
            return self._quotes.get((exchange_id, symbol, market_type))

    def get_funding(self, exchange_id: str, symbol: str) -> FundingInfo | None:
        with self._lock:
            return self._funding.get((exchange_id, symbol))

    def get_fees(self, exchange_id: str, symbol: str) -> FeeSchedule | None:
        with self._lock:
            return self._fees.get((exchange_id, symbol))

    def put_market_info(self, info: SymbolMarketInfo, exchange_id: str) -> None:
        with self._lock:
            self._market_info[(exchange_id, info.unified_symbol)] = info

    def get_market_info(self, exchange_id: str, symbol: str) -> SymbolMarketInfo | None:
        with self._lock:
            return self._market_info.get((exchange_id, symbol))

    def put_order_book(self, book: OrderBookSnapshot) -> None:
        with self._lock:
            self._order_books[(book.exchange_id, book.symbol)] = book

    def get_order_book(self, exchange_id: str, symbol: str) -> OrderBookSnapshot | None:
        with self._lock:
            return self._order_books.get((exchange_id, symbol))

    def clear_symbol(self, exchange_id: str, symbol: str) -> None:
        """Remove all cached data for a specific symbol on an exchange."""
        with self._lock:
            self._quotes.pop((exchange_id, symbol, "futures"), None)
            self._quotes.pop((exchange_id, symbol, "spot"), None)
            self._order_books.pop((exchange_id, symbol), None)
            self._funding.pop((exchange_id, symbol), None)
            self._fees.pop((exchange_id, symbol), None)
            self._market_info.pop((exchange_id, symbol), None)

    def clear_executable(self, exchange_id: str, symbol: str) -> None:
        """Drop stale quotes and order books only (keep market info, fees, funding)."""
        with self._lock:
            self._quotes.pop((exchange_id, symbol, "futures"), None)
            self._quotes.pop((exchange_id, symbol, "spot"), None)
            self._order_books.pop((exchange_id, symbol), None)
