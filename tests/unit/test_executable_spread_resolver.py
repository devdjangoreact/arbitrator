from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from arbitrator.application.executable_spread_resolver import ExecutableSpreadResolver
from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.settings import Settings
from arbitrator.domain.order_book_level import OrderBookLevel
from arbitrator.domain.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.ticker import Ticker

if TYPE_CHECKING:
    from arbitrator.domain.exchange_gateway import ExchangeGateway

SYM = "BTC/USDT:USDT"
EX_A = "bitget"
EX_B = "gate"


def _ticker(bid: float, ask: float) -> Ticker:
    return Ticker(
        symbol=SYM,
        last=(bid + ask) / 2,
        bid=bid,
        ask=ask,
        high_24h=ask,
        low_24h=bid,
        base_volume_24h=1.0,
        quote_volume_24h=1_000_000.0,
        timestamp_ms=1,
    )


def _quote(exchange_id: str, bid: float, ask: float) -> Quote:
    return Quote(
        exchange_id=exchange_id,
        symbol=SYM,
        market_type="futures",
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        last=Decimal(str((bid + ask) / 2)),
        recv_time_ms=1,
    )


class _CountingGateway:
    exchange_id: str

    def __init__(self, exchange_id: str, bid: float, ask: float) -> None:
        self.exchange_id = exchange_id
        self._bid = bid
        self._ask = ask
        self.fetch_count = 0

    async def fetch_order_book_once(self, symbol: str, limit: int) -> OrderBookSnapshot:
        self.fetch_count += 1
        return OrderBookSnapshot(
            exchange_id=self.exchange_id,
            symbol=symbol,
            timestamp_ms=1,
            bids=(OrderBookLevel(price=self._bid, size=100.0),),
            asks=(OrderBookLevel(price=self._ask, size=100.0),),
        )


def test_top_of_book_sync_prefers_cached_order_book() -> None:
    cache = MarketDataCacheMemory()
    cache.put_order_book(
        OrderBookSnapshot(
            exchange_id=EX_A,
            symbol=SYM,
            timestamp_ms=1,
            bids=(OrderBookLevel(price=105.0, size=1.0),),
            asks=(OrderBookLevel(price=105.5, size=1.0),),
        )
    )
    resolver = ExecutableSpreadResolver(Settings(), cache)
    top = resolver.top_of_book_sync(EX_A, SYM, _ticker(99.0, 100.0))
    assert top is not None
    assert top.bid == 105.0
    assert top.ask == 105.5


def test_top_of_book_sync_falls_back_to_cache_quote() -> None:
    cache = MarketDataCacheMemory()
    cache.put_quote(_quote(EX_A, 104.0, 104.5))
    resolver = ExecutableSpreadResolver(Settings(), cache)
    top = resolver.top_of_book_sync(EX_A, SYM, None)
    assert top is not None
    assert top.bid == 104.0
    assert top.ask == 104.5


def test_fetch_fresh_false_skips_rest() -> None:
    cache = MarketDataCacheMemory()
    gw = _CountingGateway(EX_A, 105.0, 105.1)
    gateways: dict[str, ExchangeGateway] = {EX_A: gw}  # type: ignore[dict-item]
    resolver = ExecutableSpreadResolver(Settings(), cache, gateways)

    top = asyncio.run(
        resolver.top_of_book(EX_A, SYM, _ticker(100.0, 100.1), fetch_fresh=False)
    )

    assert top is not None
    assert top.bid == 100.0
    assert gw.fetch_count == 0


def test_fetch_fresh_true_calls_rest() -> None:
    cache = MarketDataCacheMemory()
    gw = _CountingGateway(EX_A, 106.0, 106.2)
    gateways: dict[str, ExchangeGateway] = {EX_A: gw}  # type: ignore[dict-item]
    resolver = ExecutableSpreadResolver(Settings(), cache, gateways)

    top = asyncio.run(
        resolver.top_of_book(EX_A, SYM, _ticker(100.0, 100.1), fetch_fresh=True)
    )

    assert top is not None
    assert top.bid == 106.0
    assert top.ask == 106.2
    assert gw.fetch_count == 1


def test_best_entry_pair_sync_uses_cache_not_rest() -> None:
    cache = MarketDataCacheMemory()
    cache.put_quote(_quote(EX_A, 105.0, 105.1))
    cache.put_quote(_quote(EX_B, 100.0, 100.1))
    gw_a = _CountingGateway(EX_A, 200.0, 200.1)
    gw_b = _CountingGateway(EX_B, 50.0, 50.1)
    gateways: dict[str, ExchangeGateway] = {  # type: ignore[dict-item]
        EX_A: gw_a,
        EX_B: gw_b,
    }
    resolver = ExecutableSpreadResolver(Settings(), cache, gateways)
    tickers = {EX_A: _ticker(1.0, 1.1), EX_B: _ticker(1.0, 1.1)}

    best = resolver.best_entry_pair_sync(SYM, tickers)

    assert best is not None
    assert best[4] == pytest.approx(4.895, rel=1e-3)
    assert gw_a.fetch_count == 0
    assert gw_b.fetch_count == 0


def test_should_rest_verify_skips_below_prefilter() -> None:
    settings = Settings(
        screener_rest_prefilter_spread_pct=2.0,
        screener_book_stream_exchanges=["mexc"],
    )
    cache = MarketDataCacheMemory()
    resolver = ExecutableSpreadResolver(settings, cache)
    assert resolver.should_rest_verify_entry(
        SYM,
        "mexc",
        EX_B,
        1.5,
        short_ticker=_ticker(105.0, 105.1),
        long_ticker=_ticker(100.0, 100.1),
    ) is False


def test_should_rest_verify_when_book_venue_lacks_cache() -> None:
    settings = Settings(
        screener_rest_prefilter_spread_pct=2.0,
        screener_book_stream_exchanges=["mexc"],
    )
    cache = MarketDataCacheMemory()
    cache.put_quote(_quote(EX_B, 100.0, 100.1))
    resolver = ExecutableSpreadResolver(settings, cache)
    assert resolver.should_rest_verify_entry(
        SYM,
        "mexc",
        EX_B,
        3.0,
        short_ticker=_ticker(105.0, 105.1),
        long_ticker=_ticker(100.0, 100.1),
    ) is True


def test_entry_spread_for_open_skips_rest_when_prefilter_not_met() -> None:
    settings = Settings(
        screener_rest_prefilter_spread_pct=2.0,
        screener_book_stream_exchanges=["mexc"],
    )
    cache = MarketDataCacheMemory()
    cache.put_quote(_quote(EX_B, 100.0, 100.1))
    gw = _CountingGateway("mexc", 106.0, 106.1)
    gateways: dict[str, ExchangeGateway] = {"mexc": gw}  # type: ignore[dict-item]
    resolver = ExecutableSpreadResolver(settings, cache, gateways)

    result = asyncio.run(
        resolver.entry_spread_for_open(
            SYM,
            "mexc",
            EX_B,
            1.0,
            short_ticker=_ticker(105.0, 105.1),
            long_ticker=_ticker(100.0, 100.1),
        )
    )

    assert result is None
    assert gw.fetch_count == 0


def test_entry_spread_for_open_fetches_rest_above_prefilter() -> None:
    settings = Settings(
        screener_rest_prefilter_spread_pct=2.0,
        screener_book_stream_exchanges=["mexc"],
    )
    cache = MarketDataCacheMemory()
    cache.put_quote(_quote(EX_B, 100.0, 100.1))
    gw = _CountingGateway("mexc", 106.0, 106.1)
    gateways: dict[str, ExchangeGateway] = {"mexc": gw}  # type: ignore[dict-item]
    resolver = ExecutableSpreadResolver(settings, cache, gateways)

    result = asyncio.run(
        resolver.entry_spread_for_open(
            SYM,
            "mexc",
            EX_B,
            3.0,
            short_ticker=_ticker(105.0, 105.1),
            long_ticker=_ticker(100.0, 100.1),
        )
    )

    assert result is not None
    assert result[0] == 106.0
    assert gw.fetch_count == 1
