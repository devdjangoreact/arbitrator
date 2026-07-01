from __future__ import annotations

from arbitrator.config.settings import Settings
from arbitrator.domain.spread_snapshot import SpreadSnapshot


class SpreadEvaluator:
    """Evaluates open/close spread thresholds."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def should_open(self, snapshot: SpreadSnapshot) -> bool:
        spread = snapshot.spread_pct
        return spread is not None and spread >= self._settings.arb_open_spread_threshold_pct

    def should_close(self, snapshot: SpreadSnapshot) -> bool:
        spread = snapshot.spread_pct
        return spread is not None and spread <= self._settings.arb_close_spread_threshold_pct

    def is_misconfigured(self) -> bool:
        return (
            self._settings.arb_open_spread_threshold_pct
            <= self._settings.arb_close_spread_threshold_pct
        )
