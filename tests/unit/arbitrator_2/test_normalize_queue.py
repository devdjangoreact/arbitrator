from __future__ import annotations

from arbitrator_2.connector.book_snapshot import BookSnapshot
from arbitrator_2.connector.market_id import MarketId
from arbitrator_2.connector.market_kind import MarketKind
from arbitrator_2.connector.normalize_queue import NormalizeQueue


def test_try_put_returns_false_when_full_and_does_not_block() -> None:
    q = NormalizeQueue(maxsize=1)
    market = MarketId("binance", MarketKind.SPOT, "BTC/USDT")
    snap = BookSnapshot(((1.0, 1.0),), ((2.0, 1.0),), None, 1, 2)
    assert q.try_put(market, snap) is True
    assert q.try_put(market, snap) is False
    assert q.dropped == 1
