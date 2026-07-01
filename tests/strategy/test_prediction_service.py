from __future__ import annotations

from decimal import Decimal

from arbitrator.application.prediction_service import PredictionService
from arbitrator.config.settings import Settings


def _history(*values: str) -> list[Decimal]:
    return [Decimal(v) for v in values]


def _enabled_service() -> PredictionService:
    return PredictionService(Settings(prediction_enabled=True))


def test_stable_widening_spread_scores_high() -> None:
    service = _enabled_service()
    score = service.predict(_history("1.0", "1.1", "1.2", "1.3", "1.4"))
    assert score.enabled is True
    assert score.score is not None
    assert score.score > Decimal("0.5")
    assert score.trend == Decimal("0.4")


def test_chaotic_spread_scores_lower_than_stable_widening() -> None:
    service = _enabled_service()
    stable = service.predict(_history("1.0", "1.1", "1.2", "1.3", "1.4"))
    chaotic = service.predict(_history("1.0", "2.0", "0.5", "1.8", "1.4"))
    assert stable.score is not None and chaotic.score is not None
    assert chaotic.score < stable.score


def test_disabled_prediction_returns_empty_score() -> None:
    service = PredictionService(Settings())  # prediction_enabled defaults to False
    score = service.predict(_history("1.0", "1.2", "1.4"), seconds_to_funding=120)
    assert score.enabled is False
    assert score.score is None
    # Even disabled, the reported context (time to funding) is preserved for display.
    assert score.seconds_to_funding == 120


def test_insufficient_history_has_no_score_but_stays_enabled() -> None:
    service = _enabled_service()
    score = service.predict(_history("1.0"))
    assert score.enabled is True
    assert score.score is None
    assert score.sample_size == 1
