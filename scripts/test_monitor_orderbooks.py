"""Test watch_order_book for all (exchange, symbol) pairs from monitor_configs.json.

Connects to each exchange via the project's CcxtBase gateway (same path as
MonitorBookStreamWorker), waits up to TIMEOUT_SECS for the first non-empty
order book update, and reports the result.

Usage:
    .venv\Scripts\python.exe scripts/test_monitor_orderbooks.py
    .venv\Scripts\python.exe scripts/test_monitor_orderbooks.py --timeout 15
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from arbitrator.config.settings import Settings
from arbitrator.exchanges.factory import Factory

TIMEOUT_SECS = 20
LIMIT = 20


async def test_one(factory: Factory, exchange_id: str, symbol: str, timeout: int) -> dict:
    gateway = factory.create(exchange_id).gateway
    result: dict = {"exchange": exchange_id, "symbol": symbol, "status": "timeout", "bid": None, "ask": None, "error": None}
    try:
        async def _stream() -> None:
            async for book in gateway.watch_order_book(symbol, LIMIT):
                if book.bids and book.asks:
                    result["status"] = "ok"
                    result["bid"] = float(book.bids[0].price)
                    result["ask"] = float(book.asks[0].price)
                    return
                # got a book but empty — keep waiting
                result["status"] = "empty_book"

        await asyncio.wait_for(_stream(), timeout=timeout)
    except asyncio.TimeoutError:
        pass  # status stays "timeout" or "empty_book"
    except Exception as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            await gateway.close()
        except Exception:
            pass
    return result


async def main(timeout: int) -> None:
    settings = Settings(_env_file=str(_ROOT / ".env"))
    factory = Factory(settings)

    configs_path = _ROOT / "src" / "arbitrator" / "data" / "monitor_configs.json"
    configs = json.loads(configs_path.read_text())

    # Collect unique (exchange, symbol) pairs
    pairs: set[tuple[str, str]] = set()
    for cfg in configs.values():
        pairs.add((cfg["short_exchange"], cfg["symbol"]))
        pairs.add((cfg["long_exchange"], cfg["symbol"]))

    sorted_pairs = sorted(pairs)
    print(f"Testing {len(sorted_pairs)} (exchange, symbol) pairs — timeout={timeout}s each\n")

    # Preload markets so gateways skip REST load_markets
    exchange_ids = sorted({ex for ex, _ in sorted_pairs})
    print(f"Preloading markets for: {exchange_ids}")
    factory.preload_markets(exchange_ids)
    print("Markets preloaded.\n")

    tasks = [test_one(factory, ex, sym, timeout) for ex, sym in sorted_pairs]
    results = await asyncio.gather(*tasks)

    ok = [r for r in results if r["status"] == "ok"]
    fail = [r for r in results if r["status"] != "ok"]

    print("=" * 65)
    print(f"PASS ({len(ok)}/{len(results)})")
    print("=" * 65)
    for r in ok:
        print(f"  [OK]     {r['exchange']:8} {r['symbol']:25}  bid={r['bid']}  ask={r['ask']}")

    if fail:
        print()
        print(f"FAIL ({len(fail)}/{len(results)})")
        print("=" * 65)
        for r in fail:
            detail = r["error"] or r["status"]
            print(f"  [FAIL]   {r['exchange']:8} {r['symbol']:25}  {detail}")

    print()
    return 0 if not fail else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test watch_order_book for all monitor pairs.")
    parser.add_argument("--timeout", type=int, default=TIMEOUT_SECS, help="Seconds to wait per pair")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.timeout)))
