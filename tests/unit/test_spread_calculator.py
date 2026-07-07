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


def test_entry_and_exit_spread_pct() -> None:
    assert SpreadCalculator.entry_spread_pct(105.0, 100.0) == 5.0
    assert SpreadCalculator.exit_spread_pct(100.5, 100.0) == 0.5


def test_best_executable_pair_picks_cross_venue_max_spread() -> None:
    best = SpreadCalculator.best_executable_pair(
        {"bitget": 105.0, "gate": 104.0},
        {"bitget": 105.5, "gate": 100.0},
    )
    assert best is not None
    short_ex, long_ex, short_bid, long_ask, spread = best
    assert short_ex == "bitget"
    assert long_ex == "gate"
    assert short_bid == 105.0
    assert long_ask == 100.0
    assert spread == 5.0


def test_best_executable_pair_swaps_legs_when_spread_negative() -> None:
    """When A bid < B ask, the best pair is short B / long A (leg swap)."""
    best = SpreadCalculator.best_executable_pair(
        {"bitget": 99.0, "gate": 101.0},
        {"bitget": 100.0, "gate": 102.0},
    )
    assert best is not None
    short_ex, long_ex, short_bid, long_ask, spread = best
    assert short_ex == "gate"
    assert long_ex == "bitget"
    assert short_bid == 101.0
    assert long_ask == 100.0
    assert spread == 1.0


def test_best_executable_pair_requires_different_exchanges() -> None:
    assert SpreadCalculator.best_executable_pair(
        {"bitget": 105.0},
        {"bitget": 100.0},
    ) is None
