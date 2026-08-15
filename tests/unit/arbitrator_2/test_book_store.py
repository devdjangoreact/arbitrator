from __future__ import annotations

from arbitrator_2.connector.book_store import BookStore
from arbitrator_2.connector.market_id import MarketId
from arbitrator_2.connector.market_kind import MarketKind


def test_apply_default_keeps_one_level() -> None:
    store = BookStore()
    market = MarketId("binance", MarketKind.PERP, "BTC/USDT:USDT")
    recv = 1_000_000_000
    snap = store.apply(
        market,
        [[100.0, 2.0], [99.0, 5.0]],
        [[101.0, 3.0], [102.0, 4.0]],
        1,
        recv,
    )
    assert snap is not None
    assert snap.bids == ((100.0, 2.0),)
    assert snap.asks == ((101.0, 3.0),)
    bbo = store.get_bbo(market)
    assert bbo is not None
    assert bbo.bid == 100.0
    assert bbo.apply_ts_ns >= recv


def test_apply_keeps_requested_depth() -> None:
    store = BookStore(depth=2)
    market = MarketId("binance", MarketKind.SPOT, "BTC/USDT")
    snap = store.apply(
        market,
        [[100.0, 2.0], [99.0, 5.0], [98.0, 1.0]],
        [[101.0, 3.0], [102.0, 4.0], [103.0, 7.0]],
        None,
        1,
    )
    assert snap is not None
    assert snap.bids == ((100.0, 2.0), (99.0, 5.0))
    assert snap.asks == ((101.0, 3.0), (102.0, 4.0))
