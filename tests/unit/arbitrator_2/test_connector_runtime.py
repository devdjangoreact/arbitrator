from __future__ import annotations

import asyncio
import time

from arbitrator_2.connector.connector_runtime import ConnectorRuntime
from arbitrator_2.connector.market_id import MarketId
from arbitrator_2.connector.market_kind import MarketKind
from tests.unit.arbitrator_2.fake_venue import FakeVenue


def test_runtime_applies_book_without_rest_and_emits_unified() -> None:
    asyncio.run(_run())


def test_venues_subscribe_in_parallel() -> None:
    asyncio.run(_parallel_subscribe())


def test_subscribe_isolates_adapter_error() -> None:
    asyncio.run(_isolate_error())


async def _parallel_subscribe() -> None:
    slow = FakeVenue("slow", load_delay=0.4)
    fast = FakeVenue("fast", load_delay=0.4)
    runtime = ConnectorRuntime([slow, fast], enable_trades=False)
    ms = MarketId("slow", MarketKind.PERP, "BTC/USDT:USDT")
    mf = MarketId("fast", MarketKind.PERP, "BTC/USDT:USDT")
    t0 = time.monotonic()
    results = await runtime.subscribe([ms, mf], timeout=5.0)
    assert time.monotonic() - t0 < 0.1
    assert all(err is None for _, err in results)
    for _ in range(80):
        if runtime.get_bbo(mf) is not None or runtime.get_bbo(ms) is not None:
            break
        await asyncio.sleep(0.01)
    assert time.monotonic() - t0 < 0.2
    for _ in range(80):
        if slow.load_calls == 1 and fast.load_calls == 1:
            break
        await asyncio.sleep(0.01)
    assert slow.load_calls == 1
    assert fast.load_calls == 1
    await runtime.close()


async def _isolate_error() -> None:
    bad = FakeVenue("bad", load_error=RuntimeError("boom"))
    good = FakeVenue("good")
    runtime = ConnectorRuntime([bad, good], enable_trades=False)
    mb = MarketId("bad", MarketKind.PERP, "BTC/USDT:USDT")
    mg = MarketId("good", MarketKind.PERP, "BTC/USDT:USDT")
    results = await runtime.subscribe([mb, mg], timeout=5.0)
    by_venue = {m.venue: err for m, err in results}
    assert by_venue["bad"] is None
    assert by_venue["good"] is None
    for _ in range(50):
        if runtime.get_bbo(mg) is not None and runtime.get_bbo(mb) is not None:
            break
        await asyncio.sleep(0.01)
    assert runtime.get_bbo(mg) is not None
    assert runtime.get_bbo(mb) is not None
    await runtime.close()


async def _run() -> None:
    venue = FakeVenue("binance")
    runtime = ConnectorRuntime([venue], enable_trades=False)
    market = MarketId("binance", MarketKind.PERP, "BTC/USDT:USDT")
    await runtime.subscribe([market])
    for _ in range(50):
        if runtime.get_bbo(market) is not None:
            break
        await asyncio.sleep(0.01)
    bbo = runtime.get_bbo(market)
    assert bbo is not None
    assert bbo.bid > 0
    tick = await asyncio.wait_for(runtime.next_unified(), timeout=1.0)
    assert tick.market == market
    assert tick.norm_ts_ns >= tick.apply_ts_ns
    await runtime.close()
