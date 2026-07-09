"""Audit paper_orders.json against OHLCV history.

Actions:
    1. Structural check: find unhedged pairs (orphan single legs or
       mismatched filled+closed) and anomalous spreads > 20%.
    2. OHLCV validation: fetch 1m candles from ccxt and verify that
       recorded entry_price (and computed exit_price) fall within the
       candle high/low at opened_at / closed_at timestamps.
    3. PnL statistics over all closed pairs.
    4. With --fix: write synthetic close records for unhedged filled legs
       (uses last available OHLCV close as exit price) and save the file.

Usage:
    .venv\\Scripts\\python.exe scripts\\audit_paper_orders.py
    .venv\\Scripts\\python.exe scripts\\audit_paper_orders.py --fix
    .venv\\Scripts\\python.exe scripts\\audit_paper_orders.py --fix --output report.json
    .venv\\Scripts\\python.exe scripts\\audit_paper_orders.py --orders path/to/other.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ccxt.async_support as ccxt_async

# -
# Configuration
# -

ANOMALY_MAX_SPREAD_PCT: float = 20.0  # spread_pct_entry above this is flagged
PRICE_TOLERANCE_PCT: float = 5.0  # allow +/-5% vs candle high/low for mark-price drift
CANDLE_TIMEFRAME: str = "1m"
CANDLE_MARGIN_MIN: int = 3  # fetch N minutes before/after the trade
FETCH_CONCURRENCY: int = 8  # max simultaneous ccxt sessions

# -
# Types
# -

PaperOrder = dict  # raw JSON object from paper_orders.json

FetchKey = tuple[str, str]  # (exchange_id, symbol)


class Candle(TypedDict):
    ts: int
    open: float
    high: float
    low: float
    close: float


# -
# OHLCV helpers
# -


async def fetch_candles(
    exchange_id: str,
    symbol: str,
    since_ms: int,
    until_ms: int,
) -> list[Candle]:
    """Fetch 1m OHLCV candles for a time window; returns empty list on error."""
    exchange = getattr(ccxt_async, exchange_id, None)
    if exchange is None:
        return []
    client = exchange({"options": {"defaultType": "swap"}, "enableRateLimit": True})
    candles: list[Candle] = []
    try:
        await client.load_markets()
        if symbol not in client.markets:
            return []
        cursor = since_ms
        while cursor <= until_ms:
            raw = await client.fetch_ohlcv(symbol, CANDLE_TIMEFRAME, since=cursor, limit=500)
            if not raw:
                break
            for row in raw:
                if row[0] > until_ms + 60_000:
                    break
                candles.append(
                    Candle(
                        ts=int(row[0]),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                    )
                )
            if len(raw) < 500 or raw[-1][0] >= until_ms:
                break
            cursor = raw[-1][0] + 60_000
    except Exception as exc:
        print(f"  WARN  {exchange_id}:{symbol} | {exc}")
    finally:
        await client.close()
    return candles


def candle_at(candles: list[Candle], ts_ms: int) -> Candle | None:
    """Return the 1m candle containing ts_ms, or nearest within 5 min."""
    for c in candles:
        if c["ts"] <= ts_ms < c["ts"] + 60_000:
            return c
    if not candles:
        return None
    nearest = min(candles, key=lambda c: abs(c["ts"] - ts_ms))
    if abs(nearest["ts"] - ts_ms) <= 5 * 60_000:
        return nearest
    return None


def validate_price(price: float, candle: Candle | None) -> tuple[bool, str]:
    """Return (valid, reason_string).  valid=True if price is within tolerance."""
    if candle is None:
        return True, "no_candle"
    lo = candle["low"] * (1 - PRICE_TOLERANCE_PCT / 100)
    hi = candle["high"] * (1 + PRICE_TOLERANCE_PCT / 100)
    if lo <= price <= hi:
        return True, "ok"
    pct = (price - candle["close"]) / candle["close"] * 100
    return (
        False,
        f"price={price:.6g} outside candle [{candle['low']:.6g}, {candle['high']:.6g}]"
        f" ({pct:+.1f}% from close)",
    )


# -
# Math helpers
# -


def compute_exit_price(order: PaperOrder) -> float | None:
    """Reverse-engineer exit price from pnl_usdt + entry_price + amount."""
    pnl = order.get("pnl_usdt")
    entry = order.get("entry_price") or order.get("price")
    amount = order.get("amount")
    if pnl is None or not entry or not amount:
        return None
    if order["side"] == "sell":
        return float(entry) - float(pnl) / float(amount)
    return float(entry) + float(pnl) / float(amount)


def parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


# -
# Synthetic close
# -


def make_synthetic_close(order: PaperOrder, exit_price: float) -> PaperOrder:
    """Return an updated copy of order with synthetic close data."""
    entry = float(order["entry_price"] or order["price"])
    amount = float(order["amount"])
    notional = float(order.get("notional_usdt") or 100.0)

    if order["side"] == "sell":
        pnl = (entry - exit_price) * amount
    else:
        pnl = (exit_price - entry) * amount

    close_fee = round(notional * 0.0005, 6)  # 0.05% taker estimate
    funding = float(order.get("accrued_funding_usdt") or 0.0)
    open_fee = float(order.get("open_fee_usdt") or 0.0)
    net_pnl = pnl - open_fee - close_fee + funding

    updated = dict(order)
    updated["status"] = "closed"
    updated["closed_at"] = iso_now()
    updated["pnl_usdt"] = round(pnl, 4)
    updated["spread_pct_exit"] = None  # unknown - unhedged forced close
    updated["close_fee_usdt"] = close_fee
    updated["net_pnl_usdt"] = round(net_pnl, 4)
    return updated


# -
# Core audit
# -


async def run_audit(
    orders_path: Path,
    fix: bool,
    output_path: Path | None,
) -> None:
    sep = "=" * 64
    print(f"\n{sep}")
    print("  PAPER ORDER AUDIT")
    print(f"  File : {orders_path}")
    print(f"  Fix  : {fix}")
    print(f"{sep}\n")

    with open(orders_path) as f:
        orders: list[PaperOrder] = json.load(f)

    # - 1. Structural classification -
    pairs: dict[str, list[PaperOrder]] = defaultdict(list)
    for o in orders:
        pairs[o["pair_id"]].append(o)

    orphan_pids: list[str] = []  # only 1 leg found
    mismatched_pids: list[str] = []  # 1 filled + 1 closed
    open_pids: list[str] = []  # both legs filled (normal open)
    closed_pids: list[str] = []  # both legs closed
    anomaly_pids: list[str] = []  # any leg has spread_pct_entry > threshold

    for pid, legs in pairs.items():
        statuses = {leg["status"] for leg in legs}
        if any((leg.get("spread_pct_entry") or 0.0) > ANOMALY_MAX_SPREAD_PCT for leg in legs):
            anomaly_pids.append(pid)
        if len(legs) == 1:
            orphan_pids.append(pid)
        elif len(legs) == 2:
            if statuses == {"filled"}:
                open_pids.append(pid)
            elif statuses == {"closed"}:
                closed_pids.append(pid)
            elif "filled" in statuses and "closed" in statuses:
                mismatched_pids.append(pid)

    unhedged_pids = set(orphan_pids) | set(mismatched_pids)
    unhedged_legs: list[PaperOrder] = [
        leg for pid in unhedged_pids for leg in pairs[pid] if leg["status"] == "filled"
    ]

    print("- Structure -")
    print(f"  Total orders     : {len(orders)}")
    print(f"  Total pairs      : {len(pairs)}")
    print(f"  Closed pairs     : {len(closed_pids)}")
    print(f"  Open pairs       : {len(open_pids)}")
    print(f"  Orphan pairs     : {len(orphan_pids)}")
    print(f"  Mismatched pairs : {len(mismatched_pids)}")
    print(f"  Anomaly spread   : {len(anomaly_pids)} pairs  (>{ANOMALY_MAX_SPREAD_PCT}%)")

    if unhedged_legs:
        print()
        for leg in unhedged_legs:
            print(
                f"  UNHEDGED  {leg['pair_id']}  {leg['symbol']}  "
                f"{leg['exchange_id']}  {leg['side']}  opened={leg.get('opened_at', '?')}"
            )

    # - 2. Build OHLCV fetch plan -
    fetch_ranges: dict[FetchKey, tuple[int, int]] = {}
    for o in orders:
        key: FetchKey = (o["exchange_id"], o["symbol"])
        opened_dt = parse_dt(o.get("opened_at"))
        closed_dt = parse_dt(o.get("closed_at"))
        if not opened_dt:
            continue
        since_ms = int((opened_dt - timedelta(minutes=CANDLE_MARGIN_MIN)).timestamp() * 1000)
        ref_dt = closed_dt if closed_dt else opened_dt
        until_ms = int((ref_dt + timedelta(minutes=CANDLE_MARGIN_MIN)).timestamp() * 1000)
        if key in fetch_ranges:
            s0, u0 = fetch_ranges[key]
            fetch_ranges[key] = (min(s0, since_ms), max(u0, until_ms))
        else:
            fetch_ranges[key] = (since_ms, until_ms)

    print("\n- OHLCV Fetch -")
    print(f"  Fetching 1m candles for {len(fetch_ranges)} (exchange, symbol) pairs ...")

    sem = asyncio.Semaphore(FETCH_CONCURRENCY)
    candle_cache: dict[FetchKey, list[Candle]] = {}

    async def fetch_bounded(key: FetchKey) -> tuple[FetchKey, list[Candle]]:
        async with sem:
            exchange_id, symbol = key
            since_ms, until_ms = fetch_ranges[key]
            result = await fetch_candles(exchange_id, symbol, since_ms, until_ms)
            return key, result

    raw_results = await asyncio.gather(
        *[fetch_bounded(k) for k in fetch_ranges],
        return_exceptions=True,
    )
    fetch_errors = 0
    for r in raw_results:
        if isinstance(r, Exception):
            fetch_errors += 1
            print(f"  ERROR  {r}")
        else:
            key, candles = r
            candle_cache[key] = candles
            status = f"{len(candles)} candles" if candles else "NO DATA"
            print(f"  {key[0]:8s}  {key[1]:30s}  {status}")

    # - 3. Validate each order against OHLCV -
    print("\n- Price Validation -")

    flags: list[dict] = []
    validation: list[dict] = []
    entry_ok = entry_fail = entry_skip = 0
    exit_ok = exit_fail = exit_skip = 0

    for o in orders:
        rec: dict = {
            "order_id": o["order_id"],
            "pair_id": o["pair_id"],
            "symbol": o["symbol"],
            "exchange_id": o["exchange_id"],
            "side": o["side"],
            "status": o["status"],
            "spread_pct_entry": o.get("spread_pct_entry"),
            "entry_valid": None,
            "exit_valid": None,
            "issues": [],
        }

        # Anomaly spread
        spread = o.get("spread_pct_entry") or 0.0
        if spread > ANOMALY_MAX_SPREAD_PCT:
            msg = f"anomaly_spread={spread:.2f}%"
            rec["issues"].append(msg)
            flags.append({"order_id": o["order_id"], "type": "anomaly_spread", "detail": msg})

        key: FetchKey = (o["exchange_id"], o["symbol"])
        candles = candle_cache.get(key, [])

        # Entry price validation
        entry_price = o.get("entry_price") or o.get("price")
        opened_dt = parse_dt(o.get("opened_at"))
        if entry_price and opened_dt and candles:
            c = candle_at(candles, int(opened_dt.timestamp() * 1000))
            valid, reason = validate_price(float(entry_price), c)
            rec["entry_valid"] = valid
            if valid:
                entry_ok += 1
            else:
                entry_fail += 1
                rec["issues"].append(f"entry:{reason}")
                flags.append(
                    {"order_id": o["order_id"], "type": "entry_price_invalid", "detail": reason}
                )
        else:
            entry_skip += 1

        # Exit price validation (closed orders only)
        if o["status"] == "closed":
            closed_dt = parse_dt(o.get("closed_at"))
            exit_price = compute_exit_price(o)
            if exit_price and closed_dt and candles:
                c = candle_at(candles, int(closed_dt.timestamp() * 1000))
                valid, reason = validate_price(exit_price, c)
                rec["exit_valid"] = valid
                if valid:
                    exit_ok += 1
                else:
                    exit_fail += 1
                    rec["issues"].append(f"exit:{reason}")
                    flags.append(
                        {"order_id": o["order_id"], "type": "exit_price_invalid", "detail": reason}
                    )
            else:
                exit_skip += 1

        validation.append(rec)

    print(f"  Entry - OK:{entry_ok}  INVALID:{entry_fail}  SKIP:{entry_skip}")
    print(f"  Exit  - OK:{exit_ok}  INVALID:{exit_fail}  SKIP:{exit_skip}")

    # - 4. PnL statistics -
    print("\n- PnL Statistics -")

    pair_net_pnls: list[float] = []
    pair_hold_secs: list[float] = []
    wins = losses = breakeven = 0

    for pid in closed_pids:
        legs = pairs[pid]
        net = sum((leg.get("net_pnl_usdt") or 0.0) for leg in legs)
        pair_net_pnls.append(net)
        if net > 0.001:
            wins += 1
        elif net < -0.001:
            losses += 1
        else:
            breakeven += 1

        open_times = [parse_dt(leg.get("opened_at")) for leg in legs if leg.get("opened_at")]
        close_times = [parse_dt(leg.get("closed_at")) for leg in legs if leg.get("closed_at")]
        if open_times and close_times:
            hold = (max(close_times) - min(open_times)).total_seconds()
            pair_hold_secs.append(hold)

    n = len(pair_net_pnls)
    total_net = sum(pair_net_pnls)
    avg_net = total_net / n if n else 0.0
    win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0.0
    avg_hold = sum(pair_hold_secs) / len(pair_hold_secs) if pair_hold_secs else 0.0

    print(f"  Closed pairs      : {n}")
    print(f"  Total net PnL     : {total_net:+.2f} USDT")
    print(f"  Avg PnL / pair    : {avg_net:+.2f} USDT")
    print(f"  Win / Loss / Break: {wins} / {losses} / {breakeven}")
    print(f"  Win rate          : {win_rate:.1f}%")
    print(f"  Avg hold time     : {avg_hold:.1f}s  ({avg_hold / 60:.1f} min)")
    if pair_net_pnls:
        print(f"  Best pair         : {max(pair_net_pnls):+.2f} USDT")
        print(f"  Worst pair        : {min(pair_net_pnls):+.2f} USDT")

    # distribution buckets
    buckets = {"<-1": 0, "-1..0": 0, "0..1": 0, "1..5": 0, ">5": 0}
    for v in pair_net_pnls:
        if v < -1:
            buckets["<-1"] += 1
        elif v < 0:
            buckets["-1..0"] += 1
        elif v < 1:
            buckets["0..1"] += 1
        elif v < 5:
            buckets["1..5"] += 1
        else:
            buckets[">5"] += 1
    print("  PnL distribution  :", "  ".join(f"{k}:{v}" for k, v in buckets.items()))

    # - 5. Anomaly list -
    if flags:
        print(f"\n- Flags ({len(flags)}) -")
        shown: set[str] = set()
        for fl in flags:
            key_str = f"{fl['type']}:{fl['order_id']}"
            if key_str in shown:
                continue
            shown.add(key_str)
            print(f"  [{fl['type']:30s}] {fl['order_id']}  {fl['detail']}")
    else:
        print("\n- Flags -")
        print("  None.")

    # - 6. Fix unhedged legs -
    fix_results: list[dict] = []

    if fix and unhedged_legs:
        print(f"\n- Fix Unhedged ({len(unhedged_legs)} legs) -")
        order_map = {o["order_id"]: i for i, o in enumerate(orders)}

        for leg in unhedged_legs:
            key: FetchKey = (leg["exchange_id"], leg["symbol"])
            candles = candle_cache.get(key, [])
            if not candles:
                print(f"  SKIP  {leg['order_id']}  no OHLCV data")
                fix_results.append(
                    {"order_id": leg["order_id"], "action": "skipped", "reason": "no_ohlcv"}
                )
                continue

            last_candle = max(candles, key=lambda c: c["ts"])
            exit_price = last_candle["close"]
            updated = make_synthetic_close(leg, exit_price)

            idx = order_map.get(leg["order_id"])
            if idx is not None:
                orders[idx] = updated

            pnl = updated["pnl_usdt"]
            print(
                f"  CLOSED  {leg['order_id']}  {leg['symbol']}  {leg['side']} "
                f"@ {exit_price:.6g}  pnl={pnl:+.2f} USDT"
            )
            fix_results.append(
                {
                    "order_id": leg["order_id"],
                    "action": "closed",
                    "exit_price": exit_price,
                    "pnl_usdt": pnl,
                    "net_pnl_usdt": updated["net_pnl_usdt"],
                }
            )

        with open(orders_path, "w") as f:
            json.dump(orders, f, indent=2)
        print(f"  Saved  {orders_path}")

    elif unhedged_legs and not fix:
        print(
            f"\n  NOTE: {len(unhedged_legs)} unhedged leg(s) found. Run with --fix to close them."
        )

    # - 7. Optional JSON report -
    if output_path:
        report = {
            "summary": {
                "total_orders": len(orders),
                "total_pairs": len(pairs),
                "closed_pairs": len(closed_pids),
                "open_pairs": len(open_pids),
                "orphan_pairs": len(orphan_pids),
                "mismatched_pairs": len(mismatched_pids),
                "anomaly_pairs": len(anomaly_pids),
                "ohlcv_fetch_errors": fetch_errors,
                "entry_price_ok": entry_ok,
                "entry_price_invalid": entry_fail,
                "entry_price_skipped": entry_skip,
                "exit_price_ok": exit_ok,
                "exit_price_invalid": exit_fail,
                "exit_price_skipped": exit_skip,
                "total_net_pnl_usdt": round(total_net, 2),
                "avg_pnl_per_pair_usdt": round(avg_net, 2),
                "win_rate_pct": round(win_rate, 1),
                "wins": wins,
                "losses": losses,
                "breakeven": breakeven,
                "avg_hold_sec": round(avg_hold, 1),
                "pnl_distribution": buckets,
            },
            "flags": flags,
            "fix_results": fix_results,
            "validation": validation,
        }
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n  Report saved -> {output_path}")

    print(f"\n{sep}\n")


# -
# Entry point
# -


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit paper_orders.json against OHLCV history.")
    parser.add_argument(
        "--orders",
        type=Path,
        default=Path("src/arbitrator/data/paper_orders.json"),
        help="Path to paper_orders.json",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Close unhedged filled legs with synthetic exit price and save the file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Write full JSON audit report to this path",
    )
    args = parser.parse_args()
    asyncio.run(run_audit(args.orders, args.fix, args.output))


if __name__ == "__main__":
    main()
