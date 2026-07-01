from __future__ import annotations

from datetime import UTC

from arbitrator.domain.spread_calculator import SpreadCalculator


def test_spread_calculator_computes_pct() -> None:
    snapshot = SpreadCalculator.compute(
        "BTC/USDT:USDT",
        {"mexc": 105.0, "bitget": 100.0},
    )
    assert snapshot.spread_pct == 5.0
    assert snapshot.high_exchange_id == "mexc"
    assert snapshot.low_exchange_id == "bitget"


def test_spread_calculator_insufficient_prices() -> None:
    snapshot = SpreadCalculator.compute("BTC/USDT:USDT", {"mexc": 100.0})
    assert snapshot.spread_pct is None


def test_from_last_prices() -> None:
    snapshot = SpreadCalculator.from_last_prices(
        "ETH/USDT:USDT",
        ["mexc", "gate"],
        [2000.0, 2100.0],
    )
    assert snapshot.spread_pct is not None
    assert snapshot.updated_at.tzinfo is UTC
