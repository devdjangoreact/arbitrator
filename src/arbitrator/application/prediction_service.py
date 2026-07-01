from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.prediction_score import PredictionScore

_ZERO = Decimal("0")
_ONE = Decimal("1")
_HALF = Decimal("0.5")


class PredictionService:
    """Computes a lightweight advisory score from a short spread history.

    Pure and side-effect free. The heuristic rewards a *stable widening* spread
    and penalizes chaotic movement:

        score = clamp01(0.5 + 0.5*trend_norm) * (0.5 + 0.5*stability)

    where ``trend_norm`` is the net change relative to the mean level and
    ``stability = 1 - volatility``. Gated by ``Settings.prediction_enabled``;
    when disabled it returns an empty score and never blocks core calc (FR-016).
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def predict(
        self,
        spread_history: Sequence[Decimal],
        seconds_to_funding: int | None = None,
    ) -> PredictionScore:
        if not self._settings.prediction_enabled:
            return PredictionScore(enabled=False, seconds_to_funding=seconds_to_funding)

        history = list(spread_history)
        n = len(history)
        if n < 2:
            return PredictionScore(
                enabled=True,
                seconds_to_funding=seconds_to_funding,
                sample_size=n,
            )

        trend = history[-1] - history[0]
        mean = sum(history, _ZERO) / Decimal(n)
        mean_abs = abs(mean)
        stability = self._stability(history, mean, mean_abs)
        trend_norm = self._clamp(trend / mean_abs, -_ONE, _ONE) if mean_abs > _ZERO else _ZERO
        score = self._clamp(_HALF + _HALF * trend_norm, _ZERO, _ONE) * (_HALF + _HALF * stability)

        return PredictionScore(
            enabled=True,
            score=self._clamp(score, _ZERO, _ONE),
            trend=trend,
            stability=stability,
            seconds_to_funding=seconds_to_funding,
            sample_size=n,
        )

    def _stability(
        self,
        history: list[Decimal],
        mean: Decimal,
        mean_abs: Decimal,
    ) -> Decimal:
        if mean_abs == _ZERO:
            return _ZERO
        variance = sum(((value - mean) ** 2 for value in history), _ZERO) / Decimal(len(history))
        stdev = variance.sqrt()
        volatility = stdev / mean_abs
        return self._clamp(_ONE - volatility, _ZERO, _ONE)

    @staticmethod
    def _clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
        if value < low:
            return low
        if value > high:
            return high
        return value
