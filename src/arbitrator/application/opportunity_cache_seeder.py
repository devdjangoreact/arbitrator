from __future__ import annotations

from typing import Literal

from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.opportunity_stream_worker import OpportunityStreamState
from arbitrator.domain.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.strategy.strategy_math import StrategyMath
from arbitrator.domain.ticker import Ticker


class OpportunityCacheSeeder:
    """Push live opportunity stream snapshots into the shared market cache."""

    @staticmethod
    def seed(
        cache: MarketDataCacheMemory,
        stream_state: OpportunityStreamState,
        swap_symbol: str,
        now_ms: int,
    ) -> None:
        for exchange_id, ticker in stream_state.tickers.items():
            OpportunityCacheSeeder._put_ticker_quote(
                cache,
                exchange_id=exchange_id,
                symbol=swap_symbol,
                market_type="futures",
                ticker=ticker,
                now_ms=now_ms,
            )
        for book_key, book in stream_state.books.items():
            market_type = OpportunityCacheSeeder._market_type_from_key(book_key)
            if market_type is None:
                continue
            OpportunityCacheSeeder._put_book_quote(
                cache,
                book=book,
                symbol=swap_symbol,
                market_type=market_type,
                now_ms=now_ms,
            )

    @staticmethod
    def _put_ticker_quote(
        cache: MarketDataCacheMemory,
        *,
        exchange_id: str,
        symbol: str,
        market_type: Literal["futures", "spot"],
        ticker: Ticker,
        now_ms: int,
    ) -> None:
        cache.put_quote(
            Quote(
                exchange_id=exchange_id,
                symbol=symbol,
                market_type=market_type,
                bid=StrategyMath.to_decimal(ticker.bid),
                ask=StrategyMath.to_decimal(ticker.ask),
                last=StrategyMath.to_decimal(ticker.last),
                recv_time_ms=now_ms,
            )
        )

    @staticmethod
    def _put_book_quote(
        cache: MarketDataCacheMemory,
        *,
        book: OrderBookSnapshot,
        symbol: str,
        market_type: Literal["futures", "spot"],
        now_ms: int,
    ) -> None:
        bid = book.bids[0].price if book.bids else None
        ask = book.asks[0].price if book.asks else None
        if bid is None and ask is None:
            return
        last = None
        if bid is not None and ask is not None:
            last = (bid + ask) / 2.0
        cache.put_quote(
            Quote(
                exchange_id=book.exchange_id,
                symbol=symbol,
                market_type=market_type,
                bid=StrategyMath.to_decimal(bid),
                ask=StrategyMath.to_decimal(ask),
                last=StrategyMath.to_decimal(last),
                recv_time_ms=book.timestamp_ms if book.timestamp_ms is not None else now_ms,
            )
        )

    @staticmethod
    def _market_type_from_key(book_key: str) -> Literal["futures", "spot"] | None:
        if book_key.endswith(":futures"):
            return "futures"
        if book_key.endswith(":spot"):
            return "spot"
        return None
