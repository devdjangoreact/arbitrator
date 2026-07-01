from __future__ import annotations

from decimal import Decimal

from arbitrator.domain.strategy.strategies.funding_diff_dates_calculator import (
    FundingDiffDatesCalculator,
)
from arbitrator.domain.strategy.strategies.funding_ff_calculator import FundingFfCalculator
from arbitrator.domain.strategy.strategies.funding_fs_calculator import FundingFsCalculator
from arbitrator.domain.strategy.strategies.futures_futures_calculator import (
    FuturesFuturesCalculator,
)
from arbitrator.domain.strategy.strategies.futures_spot_1ex_calculator import (
    FuturesSpot1exCalculator,
)
from arbitrator.domain.strategy.strategies.futures_spot_2ex_calculator import (
    FuturesSpot2exCalculator,
)


def test_strategy_futures_futures_numeric(make_inputs, make_quote, make_fee) -> None:
    inputs = make_inputs(
        short_exchange_id="a",
        long_exchange_id="b",
        futures_quotes={
            "a": make_quote("a", bid="1.10", ask="1.11"),
            "b": make_quote("b", bid="0.99", ask="1.00"),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
        target_volume_usdt="1000",
        leverage={"a": 10, "b": 10},
    )
    result = FuturesFuturesCalculator().compute(inputs)
    assert result.available is True
    assert result.spread_pct == Decimal("10")
    assert result.gross_profit_usdt == Decimal("100")
    assert result.fees_usdt == Decimal("2")
    assert result.net_profit_usdt == Decimal("98")
    assert result.percent_to_deposit == Decimal("49")


def test_strategy_futures_spot_2ex_numeric(make_inputs, make_quote, make_fee) -> None:
    inputs = make_inputs(
        short_exchange_id="a",
        long_exchange_id="b",
        futures_quotes={"a": make_quote("a", bid="1.05", ask="1.06")},
        spot_quotes={"b": make_quote("b", market_type="spot", bid="0.99", ask="1.00")},
        fees={"a": make_fee("a"), "b": make_fee("b")},
        target_volume_usdt="1000",
        leverage={"a": 10},
    )
    result = FuturesSpot2exCalculator().compute(inputs)
    assert result.available is True
    assert result.spread_pct == Decimal("5")
    assert result.gross_profit_usdt == Decimal("50")
    assert result.fees_usdt == Decimal("2")
    assert result.net_profit_usdt == Decimal("48")
    # deposit = 1000/10 (futures) + 1000/1 (spot) = 1100
    assert result.percent_to_deposit == Decimal("48") / Decimal("1100") * Decimal("100")


def test_strategy_futures_spot_1ex_numeric(make_inputs, make_quote, make_fee) -> None:
    inputs = make_inputs(
        short_exchange_id="a",
        long_exchange_id="a",
        futures_quotes={"a": make_quote("a", bid="1.04", ask="1.05")},
        spot_quotes={"a": make_quote("a", market_type="spot", bid="0.99", ask="1.00")},
        fees={"a": make_fee("a")},
        target_volume_usdt="1000",
        leverage={"a": 10},
    )
    result = FuturesSpot1exCalculator().compute(inputs)
    assert result.available is True
    assert result.spread_pct == Decimal("4")
    assert result.gross_profit_usdt == Decimal("40")
    assert result.fees_usdt == Decimal("2")
    assert result.net_profit_usdt == Decimal("38")


def test_strategy_funding_ff_numeric(make_inputs, make_quote, make_funding, make_fee) -> None:
    # §4 example: |MEXC -2.0%| - |Gate +0.69%| = 1.31% spread on 5000 USDT.
    inputs = make_inputs(
        short_exchange_id="mexc",
        long_exchange_id="gate",
        futures_quotes={
            "mexc": make_quote("mexc", bid="1.00", ask="1.01"),
            "gate": make_quote("gate", bid="0.99", ask="1.00"),
        },
        funding={
            "mexc": make_funding("mexc", rate="-0.02"),
            "gate": make_funding("gate", rate="0.0069"),
        },
        fees={"mexc": make_fee("mexc"), "gate": make_fee("gate")},
        target_volume_usdt="5000",
        leverage={"mexc": 10, "gate": 10},
    )
    result = FundingFfCalculator().compute(inputs)
    assert result.available is True
    assert result.spread_pct == Decimal("1.31")
    assert result.gross_profit_usdt == Decimal("65.5")
    assert result.fees_usdt == Decimal("10")
    assert result.net_profit_usdt == Decimal("55.5")
    assert result.percent_to_deposit == Decimal("5.55")


def test_strategy_funding_fs_numeric(make_inputs, make_quote, make_funding, make_fee) -> None:
    # §6 example: rate +0.80% on 5000 USDT, spot hedge same exchange.
    inputs = make_inputs(
        short_exchange_id="a",
        long_exchange_id="b",
        futures_quotes={"a": make_quote("a", bid="1.802", ask="1.803")},
        spot_quotes={"a": make_quote("a", market_type="spot", bid="1.799", ask="1.800")},
        funding={"a": make_funding("a", rate="0.008")},
        fees={"a": make_fee("a")},
        target_volume_usdt="5000",
        leverage={"a": 10},
    )
    result = FundingFsCalculator().compute(inputs)
    assert result.available is True
    assert result.spread_pct == Decimal("0.8")
    assert result.gross_profit_usdt == Decimal("40")
    assert result.fees_usdt == Decimal("10")
    assert result.net_profit_usdt == Decimal("30")
    assert result.costs_breakdown == "10.00 + 0.00"


def test_strategy_funding_diff_dates_numeric(
    make_inputs, make_quote, make_funding, make_fee, now_ms
) -> None:
    # §5 example: |rate_early| = 2.0% on 5000 USDT; early settles first.
    inputs = make_inputs(
        short_exchange_id="a",
        long_exchange_id="b",
        futures_quotes={
            "a": make_quote("a", bid="1.00", ask="1.01"),
            "b": make_quote("b", bid="0.99", ask="1.00"),
        },
        funding={
            "a": make_funding("a", rate="-0.02", next_settlement_ms=now_ms + 60_000),
            "b": make_funding("b", rate="0.001", next_settlement_ms=now_ms + 3_600_000),
        },
        fees={"a": make_fee("a"), "b": make_fee("b")},
        target_volume_usdt="5000",
        leverage={"a": 10, "b": 10},
    )
    result = FundingDiffDatesCalculator().compute(inputs)
    assert result.available is True
    assert result.spread_pct == Decimal("2")
    assert result.gross_profit_usdt == Decimal("100")
    assert result.fees_usdt == Decimal("10")
    assert result.net_profit_usdt == Decimal("90")
    assert result.percent_to_deposit == Decimal("9")
