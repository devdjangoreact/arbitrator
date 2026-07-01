from __future__ import annotations

from arbitrator.application.spread_evaluator import SpreadEvaluator
from arbitrator.config.settings import Settings
from arbitrator.domain.spread_calculator import SpreadCalculator


def test_spread_evaluator_open_and_close() -> None:
    settings = Settings(arb_open_spread_threshold_pct=4.0, arb_close_spread_threshold_pct=0.1)
    evaluator = SpreadEvaluator(settings)
    wide = SpreadCalculator.compute("BTC/USDT:USDT", {"mexc": 105.0, "bitget": 100.0})
    narrow = SpreadCalculator.compute("BTC/USDT:USDT", {"mexc": 100.05, "bitget": 100.0})
    assert evaluator.should_open(wide) is True
    assert evaluator.should_close(wide) is False
    assert evaluator.should_close(narrow) is True


def test_spread_evaluator_misconfigured() -> None:
    settings = Settings(arb_open_spread_threshold_pct=0.1, arb_close_spread_threshold_pct=0.5)
    evaluator = SpreadEvaluator(settings)
    assert evaluator.is_misconfigured() is True
