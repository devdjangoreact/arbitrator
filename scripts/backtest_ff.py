"""Futures-Futures strategy backtest on historical OHLCV data.

Usage:
    .venv/Scripts/python.exe scripts/backtest_ff.py \\
        --symbol BTC/USDT:USDT \\
        --short mexc \\
        --long bingx \\
        --days 30 \\
        --volume 500 \\
        --spread-open 0.3 \\
        --spread-close 0.05 \\
        --output backtest_result.json

Algorithm:
    1. Fetch 1h OHLCV from both exchanges via ccxt (no API key needed for public).
    2. Align candles by timestamp.
    3. For each candle pair compute FF spread: (short_close - long_close) / long_close * 100.
    4. Simulate: open on spread >= open_threshold, close on spread <= close_threshold.
    5. Write JSON report with all trades and aggregated metrics.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

# add project src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ccxt.async_support as ccxt_async  # noqa: E402

from arbitrator.domain.strategy.strategy_math import StrategyMath  # noqa: E402


class Candle(TypedDict):
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Trade:
    trade_id: int
    open_ts: int
    close_ts: int | None
    open_spread_pct: float
    close_spread_pct: float | None
    short_entry: float
    long_entry: float
    short_exit: float | None
    long_exit: float | None
    volume_usdt: float
    gross_usdt: float | None
    fees_usdt: float | None
    net_usdt: float | None
    status: str  # "closed" | "open"


async def fetch_ohlcv(
    exchange_id: str,
    symbol: str,
    since_ms: int,
    limit_per_request: int = 500,
) -> list[Candle]:
    exchange = getattr(ccxt_async, exchange_id)(
        {"options": {"defaultType": "swap"}, "enableRateLimit": True}
    )
    candles: list[Candle] = []
    try:
        await exchange.load_markets()
        cursor = since_ms
        while True:
            raw = await exchange.fetch_ohlcv(symbol, "1h", since=cursor, limit=limit_per_request)
            if not raw:
                break
            for row in raw:
                candles.append(
                    Candle(
                        ts=int(row[0]),
                        open=float(row[1]),
                        high=float(row[2]),
                        low=float(row[3]),
                        close=float(row[4]),
                        volume=float(row[5]),
                    )
                )
            if len(raw) < limit_per_request:
                break
            cursor = raw[-1][0] + 1
    finally:
        await exchange.close()
    return candles


def align_candles(
    short_candles: list[Candle],
    long_candles: list[Candle],
) -> list[tuple[Candle, Candle]]:
    long_by_ts = {c["ts"]: c for c in long_candles}
    aligned = []
    for sc in short_candles:
        lc = long_by_ts.get(sc["ts"])
        if lc is not None:
            aligned.append((sc, lc))
    return aligned


def simulate(
    aligned: list[tuple[Candle, Candle]],
    volume_usdt: float,
    spread_open_pct: float,
    spread_close_pct: float,
    fee_rate: float = 0.0005,
) -> list[Trade]:
    trades: list[Trade] = []
    in_trade: Trade | None = None
    trade_id = 0

    for sc, lc in aligned:
        short_price = sc["close"]
        long_price = lc["close"]
        if long_price <= 0:
            continue
        spread = (short_price - long_price) / long_price * 100

        if in_trade is None:
            if spread >= spread_open_pct:
                trade_id += 1
                in_trade = Trade(
                    trade_id=trade_id,
                    open_ts=sc["ts"],
                    close_ts=None,
                    open_spread_pct=round(spread, 4),
                    close_spread_pct=None,
                    short_entry=short_price,
                    long_entry=long_price,
                    short_exit=None,
                    long_exit=None,
                    volume_usdt=volume_usdt,
                    gross_usdt=None,
                    fees_usdt=None,
                    net_usdt=None,
                    status="open",
                )
        else:
            if spread <= spread_close_pct:
                entry_spread = Decimal(str(in_trade.open_spread_pct))
                exit_spread = Decimal(str(spread))
                vol = Decimal(str(volume_usdt))
                gross = float(StrategyMath.gross_from_spread(entry_spread - exit_spread, vol))
                fees = float(
                    StrategyMath.fee_total(
                        vol,
                        (
                            Decimal(str(fee_rate)),
                            Decimal(str(fee_rate)),
                            Decimal(str(fee_rate)),
                            Decimal(str(fee_rate)),
                        ),
                    )
                )
                net = gross - fees
                in_trade.close_ts = sc["ts"]
                in_trade.close_spread_pct = round(spread, 4)
                in_trade.short_exit = short_price
                in_trade.long_exit = long_price
                in_trade.gross_usdt = round(gross, 4)
                in_trade.fees_usdt = round(fees, 4)
                in_trade.net_usdt = round(net, 4)
                in_trade.status = "closed"
                trades.append(in_trade)
                in_trade = None

    if in_trade is not None:
        trades.append(in_trade)

    return trades


def build_report(
    trades: list[Trade],
    symbol: str,
    short_ex: str,
    long_ex: str,
    days: int,
    volume_usdt: float,
    spread_open_pct: float,
    spread_close_pct: float,
    candle_count: int,
) -> dict[str, object]:
    closed = [t for t in trades if t.status == "closed"]
    wins = [t for t in closed if t.net_usdt is not None and t.net_usdt > 0]
    losses = [t for t in closed if t.net_usdt is not None and t.net_usdt <= 0]
    total_net = sum(t.net_usdt for t in closed if t.net_usdt is not None)
    total_gross = sum(t.gross_usdt for t in closed if t.gross_usdt is not None)
    total_fees = sum(t.fees_usdt for t in closed if t.fees_usdt is not None)
    max_drawdown = min((t.net_usdt for t in closed if t.net_usdt is not None), default=0.0)

    return {
        "meta": {
            "symbol": symbol,
            "short_exchange": short_ex,
            "long_exchange": long_ex,
            "days": days,
            "volume_usdt": volume_usdt,
            "spread_open_pct": spread_open_pct,
            "spread_close_pct": spread_close_pct,
            "candles_aligned": candle_count,
            "generated_at": datetime.now(UTC).isoformat(),
        },
        "summary": {
            "total_trades": len(trades),
            "closed_trades": len(closed),
            "open_trades": len(trades) - len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": round(len(wins) / len(closed) * 100, 1) if closed else 0.0,
            "total_net_usdt": round(total_net, 4),
            "total_gross_usdt": round(total_gross, 4),
            "total_fees_usdt": round(total_fees, 4),
            "max_single_loss_usdt": round(max_drawdown, 4),
            "avg_net_per_trade_usdt": round(total_net / len(closed), 4) if closed else 0.0,
        },
        "trades": [asdict(t) for t in trades],
    }


async def run(args: argparse.Namespace) -> None:
    since_ms = int(
        (datetime.now(UTC) - timedelta(days=args.days)).timestamp() * 1000
    )
    print(f"Fetching OHLCV: {args.symbol} | {args.short} vs {args.long} | {args.days}d...")

    short_candles, long_candles = await asyncio.gather(
        fetch_ohlcv(args.short, args.symbol, since_ms),
        fetch_ohlcv(args.long, args.symbol, since_ms),
    )
    print(f"  {args.short}: {len(short_candles)} candles")
    print(f"  {args.long}:  {len(long_candles)} candles")

    aligned = align_candles(short_candles, long_candles)
    print(f"  Aligned: {len(aligned)} candle pairs")

    if not aligned:
        print("ERROR: no aligned candles — check symbol availability on both exchanges")
        sys.exit(1)

    trades = simulate(
        aligned,
        volume_usdt=args.volume,
        spread_open_pct=args.spread_open,
        spread_close_pct=args.spread_close,
        fee_rate=args.fee_rate,
    )
    report = build_report(
        trades,
        symbol=args.symbol,
        short_ex=args.short,
        long_ex=args.long,
        days=args.days,
        volume_usdt=args.volume,
        spread_open_pct=args.spread_open,
        spread_close_pct=args.spread_close,
        candle_count=len(aligned),
    )

    output_path = Path(args.output)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    s = report["summary"]
    print(
        f"\nBacktest done → {output_path}\n"
        f"  Trades closed: {s['closed_trades']} | open: {s['open_trades']}\n"  # type: ignore[index]
        f"  Win rate: {s['win_rate_pct']}%\n"  # type: ignore[index]
        f"  Net PnL: {s['total_net_usdt']} USDT  (gross={s['total_gross_usdt']}, fees={s['total_fees_usdt']})\n"  # type: ignore[index]
        f"  Avg per trade: {s['avg_net_per_trade_usdt']} USDT\n"  # type: ignore[index]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="FF strategy backtest")
    parser.add_argument("--symbol", default="BTC/USDT:USDT", help="USDT-M swap symbol")
    parser.add_argument("--short", default="mexc", help="short exchange id")
    parser.add_argument("--long", default="bingx", help="long exchange id")
    parser.add_argument("--days", type=int, default=30, help="look-back window in days")
    parser.add_argument("--volume", type=float, default=500.0, help="notional USDT per trade")
    parser.add_argument("--spread-open", type=float, default=0.3, help="open threshold %")
    parser.add_argument("--spread-close", type=float, default=0.05, help="close threshold %")
    parser.add_argument("--fee-rate", type=float, default=0.0005, help="taker fee rate (0.05%)")
    parser.add_argument("--output", default="backtest_result.json", help="output JSON path")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
