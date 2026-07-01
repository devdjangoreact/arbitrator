from __future__ import annotations

from arbitrator.presentation.dto.screener_dto import StrategyProfitsDto
from arbitrator.presentation.mock.mock_strategy_calculator import (
    MockExchangePrices,
    MockOpportunityRowTemplate,
    MockScreenerStrategyCalibration,
    MockStrategyCalculator,
)


def test_screener_profits_scale_with_spread() -> None:
    prices = {
        "mexc": MockExchangePrices(futures=0.2124, spot=0.2118),
        "bingx": MockExchangePrices(futures=0.2098, spot=0.2092),
    }
    calibration = MockScreenerStrategyCalibration(
        base_profits=StrategyProfitsDto(
            futures_futures=18.4,
            futures_spot_2ex=12.1,
            futures_spot_1ex=8.5,
            funding_ff=22.3,
            funding_fs=15.6,
            funding_diff_dates=9.8,
        ),
        base_metrics={
            "futures_futures": 1.24,
            "futures_spot_2ex": 1.53,
            "futures_spot_1ex": 0.28,
            "funding_ff": 1.24,
            "funding_fs": 1.53,
            "funding_diff_dates": 1.24,
        },
    )
    base = MockStrategyCalculator.screener_profits(prices, "mexc", "bingx", calibration)
    wider_prices = {
        "mexc": MockExchangePrices(futures=0.2200, spot=0.2118),
        "bingx": MockExchangePrices(futures=0.2098, spot=0.2092),
    }
    wider = MockStrategyCalculator.screener_profits(wider_prices, "mexc", "bingx", calibration)
    assert wider.futures_futures != base.futures_futures
    assert wider.futures_futures > base.futures_futures


def test_opportunity_rows_update_spread_and_prices_label() -> None:
    prices = {
        "mexc": MockExchangePrices(futures=0.2124, spot=0.2118),
        "bingx": MockExchangePrices(futures=0.2098, spot=0.2092),
    }
    templates = [
        MockOpportunityRowTemplate(
            strategy_id="futures_futures",
            strategy_label="Фючерс-фючерс",
            base_spread_pct=0.83,
            base_gross_usdt=18.4,
            base_costs_usdt=2.15,
            base_fees_usdt=0.84,
            base_funding_usdt=-0.12,
            base_net_usdt=16.25,
            base_percent_to_deposit=2.36,
            costs_breakdown="0.84 + 0.12 + 1.19",
            unavailable_reason=None,
        )
    ]
    rows = MockStrategyCalculator.opportunity_rows(
        prices,
        "mexc",
        "bingx",
        volume_usdt=320.0,
        leverage=10,
        reference_volume_usdt=320.0,
        templates=templates,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.spread_pct != 0.83
    assert "0.2124" in row.prices_label
    assert row.net_profit_usdt is not None
    assert row.percent_to_deposit is not None


def test_opportunity_rows_keep_unavailable_static() -> None:
    templates = [
        MockOpportunityRowTemplate(
            strategy_id="futures_spot_1ex",
            strategy_label="Фючерс-спот 1 біржа",
            base_spread_pct=0.28,
            base_gross_usdt=None,
            base_costs_usdt=0.0,
            base_fees_usdt=0.0,
            base_funding_usdt=0.0,
            base_net_usdt=None,
            base_percent_to_deposit=None,
            costs_breakdown="—",
            unavailable_reason="no_spot",
        )
    ]
    prices = {
        "mexc": MockExchangePrices(futures=0.2200, spot=0.2118),
        "bingx": MockExchangePrices(futures=0.2098, spot=0.2092),
    }
    rows = MockStrategyCalculator.opportunity_rows(
        prices,
        "mexc",
        "bingx",
        volume_usdt=320.0,
        leverage=10,
        reference_volume_usdt=320.0,
        templates=templates,
    )
    assert rows[0].unavailable_reason == "no_spot"
    assert rows[0].net_profit_usdt is None
    assert rows[0].prices_label == "—"
