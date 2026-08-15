from __future__ import annotations

import argparse
import asyncio

from arbitrator_2.connector.connector_runtime import ConnectorRuntime
from arbitrator_2.connector.market_id import MarketId
from arbitrator_2.connector.market_kind import MarketKind
from arbitrator_2.connector.connector_settings import ConnectorSettings
from arbitrator_2.connector.venue_registry import build_default_adapters, enabled_venues


def _markets() -> list[MarketId]:
    out: list[MarketId] = []
    for venue in enabled_venues():
        out.append(MarketId(venue, MarketKind.SPOT, "BTC/USDT"))
        out.append(MarketId(venue, MarketKind.PERP, "BTC/USDT:USDT"))
    return out


async def _run(seconds: float, trades: bool) -> None:
    settings = ConnectorSettings()
    venues = enabled_venues(settings)
    print(
        f"enabled_exchanges={list(venues)} book_depth={settings.book_depth} "
        f"http_proxy={settings.exchange_public_http_proxy!r} "
        f"ws_proxy={settings.exchange_public_ws_proxy!r}",
        flush=True,
    )
    adapters = build_default_adapters(settings)
    runtime = ConnectorRuntime(
        adapters, enable_trades=trades, book_depth=settings.book_depth
    )
    markets = _markets()
    for market in markets:
        print(f"subscribe {market.venue} {market.kind} {market.symbol} ...", flush=True)

    stop = asyncio.Event()

    async def _print_books() -> None:
        while not stop.is_set():
            try:
                tick = await asyncio.wait_for(runtime.next_unified(), timeout=0.25)
            except TimeoutError:
                continue
            lag_ms = (tick.apply_ts_ns - tick.recv_ts_ns) / 1_000_000.0
            bids = " ".join(f"{p:g}x{s:g}" for p, s in tick.bids)
            asks = " ".join(f"{p:g}x{s:g}" for p, s in tick.asks)
            print(
                f"{tick.market.venue:8} {tick.market.kind:4} {tick.market.symbol:16} "
                f"bids=[{bids}] asks=[{asks}] apply_lag_ms={lag_ms:.3f}",
                flush=True,
            )

    print_task = asyncio.create_task(_print_books())
    results = await runtime.subscribe(markets, timeout=20.0)
    ok: list[MarketId] = []
    for market, err in results:
        label = f"{market.venue} {market.kind} {market.symbol}"
        if err is None:
            print(f"ok {label}", flush=True)
            ok.append(market)
        else:
            print(f"ERROR {label}: {err!r}", flush=True)
            cause = err.__cause__
            if cause is not None:
                print(f"  cause: {cause!r}", flush=True)
    if not ok:
        print("no markets subscribed")
        stop.set()
        print_task.cancel()
        await asyncio.wait_for(runtime.close(), timeout=10.0)
        return
    print(f"streaming {len(ok)} markets for {seconds:.0f}s", flush=True)
    await asyncio.sleep(seconds)
    stop.set()
    await print_task
    snap = runtime.metrics_snapshot()
    print("---")
    print(
        f"updates={int(snap['updates'])} p50={snap['apply_lag_p50_ms']:.3f} "
        f"p95={snap['apply_lag_p95_ms']:.3f} first_bbo_ms={snap['first_bbo_ms']:.1f}"
    )
    try:
        await asyncio.wait_for(runtime.close(), timeout=10.0)
    except TimeoutError:
        print("close timeout", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--trades", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run(args.seconds, args.trades))


if __name__ == "__main__":
    main()
