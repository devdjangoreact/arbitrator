from __future__ import annotations

from enum import StrEnum


class StrategyKind(StrEnum):
    """Canonical set of the 6 arbitrage strategies (see strategies-mechanics)."""

    futures_futures = "futures_futures"
    futures_spot_2ex = "futures_spot_2ex"
    futures_spot_1ex = "futures_spot_1ex"
    funding_ff = "funding_ff"
    funding_fs = "funding_fs"
    funding_diff_dates = "funding_diff_dates"
