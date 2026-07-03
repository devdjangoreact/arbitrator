"""Generate demo paper orders for different strategies.

Usage:
    .venv\\Scripts\\python.exe scripts/demo_paper_orders.py

Creates sample paper orders in data/paper_orders_demo.json showing
all 6 strategy kinds. Does NOT touch the real paper_orders.json.
"""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from arbitrator.domain.paper_order import PaperOrder

_OUT = Path(__file__).resolve().parent.parent / "src" / "arbitrator" / "data" / "paper_orders_demo.json"


def _order(
    *,
    pair_id: str,
    symbol: str,
    exchange_id: str,
    side: str,
    amount: float,
    price: float,
    strategy_kind: str,
    status: str = "filled",
    spread_pct: float | None = None,
) -> dict[str, object]:
    notional = amount * price
    fee = round(notional * 0.0005, 6)
    return PaperOrder(
        order_id=uuid.uuid4().hex[:12],
        pair_id=pair_id,
        symbol=symbol,
        exchange_id=exchange_id,
        side=side,
        action="open",
        amount=amount,
        price=price,
        notional_usdt=notional,
        status=status,
        opened_at=datetime.now(UTC),
        entry_price=price,
        spread_pct_entry=spread_pct,
        open_fee_usdt=fee,
        strategy_kind=strategy_kind,
    ).model_dump(mode="json")


def main() -> None:
    orders: list[dict[str, object]] = []

    # §3 Futures-Futures: short mexc, long bitget
    pid = uuid.uuid4().hex[:12]
    orders.append(_order(pair_id=pid, symbol="BTC/USDT:USDT", exchange_id="mexc", side="sell", amount=0.001, price=63500.0, strategy_kind="futures_futures", spread_pct=0.15))
    orders.append(_order(pair_id=pid, symbol="BTC/USDT:USDT", exchange_id="bitget", side="buy", amount=0.001, price=63400.0, strategy_kind="futures_futures", spread_pct=0.15))

    # §2 Futures-Spot 2-exchange: short futures mexc, long spot bitget
    pid = uuid.uuid4().hex[:12]
    orders.append(_order(pair_id=pid, symbol="ETH/USDT:USDT", exchange_id="mexc", side="sell", amount=0.05, price=3450.0, strategy_kind="futures_spot_2ex", spread_pct=0.12))
    orders.append(_order(pair_id=pid, symbol="ETH/USDT:USDT", exchange_id="bitget", side="buy", amount=0.05, price=3446.0, strategy_kind="futures_spot_2ex", spread_pct=0.12))

    # §1 Futures-Spot 1-exchange: short futures, long spot on same exchange
    pid = uuid.uuid4().hex[:12]
    orders.append(_order(pair_id=pid, symbol="SOL/USDT:USDT", exchange_id="bitget", side="sell", amount=1.0, price=145.5, strategy_kind="futures_spot_1ex", spread_pct=0.08))
    orders.append(_order(pair_id=pid, symbol="SOL/USDT:USDT", exchange_id="bitget", side="buy", amount=1.0, price=145.3, strategy_kind="futures_spot_1ex", spread_pct=0.08))

    # §4 Funding-FF: both legs futures, profit from funding rate difference
    pid = uuid.uuid4().hex[:12]
    orders.append(_order(pair_id=pid, symbol="DOGE/USDT:USDT", exchange_id="gate", side="sell", amount=100.0, price=0.125, strategy_kind="funding_ff", spread_pct=0.04))
    orders.append(_order(pair_id=pid, symbol="DOGE/USDT:USDT", exchange_id="bingx", side="buy", amount=100.0, price=0.1248, strategy_kind="funding_ff", spread_pct=0.04))

    # §6 Funding-FS: futures hedge + spot
    pid = uuid.uuid4().hex[:12]
    orders.append(_order(pair_id=pid, symbol="AVAX/USDT:USDT", exchange_id="mexc", side="sell", amount=3.0, price=26.8, strategy_kind="funding_fs", spread_pct=0.06))
    orders.append(_order(pair_id=pid, symbol="AVAX/USDT:USDT", exchange_id="mexc", side="buy", amount=3.0, price=26.7, strategy_kind="funding_fs", spread_pct=0.06))

    # §5 Funding different dates: both futures, different settlement schedules
    pid = uuid.uuid4().hex[:12]
    orders.append(_order(pair_id=pid, symbol="LINK/USDT:USDT", exchange_id="bitget", side="sell", amount=5.0, price=14.2, strategy_kind="funding_diff_dates", spread_pct=0.03))
    orders.append(_order(pair_id=pid, symbol="LINK/USDT:USDT", exchange_id="gate", side="buy", amount=5.0, price=14.18, strategy_kind="funding_diff_dates", spread_pct=0.03))

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(orders, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Demo orders written to {_OUT}")
    print(f"  {len(orders)} legs ({len(orders) // 2} pairs)")
    print("  Strategies: futures_futures, futures_spot_2ex, futures_spot_1ex, funding_ff, funding_fs, funding_diff_dates")


if __name__ == "__main__":
    main()
