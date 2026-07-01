from __future__ import annotations

from dataclasses import dataclass

from arbitrator.presentation.dto.opportunity_dto import StrategyCalculationRowDto
from arbitrator.presentation.dto.screener_dto import StrategyProfitsDto

_STRATEGY_IDS: tuple[str, ...] = (
    "futures_futures",
    "futures_spot_2ex",
    "futures_spot_1ex",
    "funding_ff",
    "funding_fs",
    "funding_diff_dates",
)


@dataclass(frozen=True, slots=True)
class MockExchangePrices:
    futures: float
    spot: float


@dataclass(frozen=True, slots=True)
class MockOpportunityRowTemplate:
    strategy_id: str
    strategy_label: str
    base_spread_pct: float
    base_gross_usdt: float | None
    base_costs_usdt: float
    base_fees_usdt: float
    base_funding_usdt: float
    base_net_usdt: float | None
    base_percent_to_deposit: float | None
    costs_breakdown: str
    unavailable_reason: str | None


@dataclass(frozen=True, slots=True)
class MockScreenerStrategyCalibration:
    base_profits: StrategyProfitsDto
    base_metrics: dict[str, float]


class MockStrategyCalculator:
    """Scale mock strategy numbers from seed baselines as live prices move."""

    @staticmethod
    def strategy_ids() -> tuple[str, ...]:
        return _STRATEGY_IDS

    @staticmethod
    def spread_metric(
        strategy_id: str,
        prices: dict[str, MockExchangePrices],
        short_exchange_id: str,
        long_exchange_id: str,
    ) -> float:
        short_prices = prices.get(short_exchange_id)
        long_prices = prices.get(long_exchange_id)
        if short_prices is None or long_prices is None:
            return 0.0
        if strategy_id == "futures_futures":
            return MockStrategyCalculator._cross_pct(short_prices.futures, long_prices.futures)
        if strategy_id == "futures_spot_2ex":
            return MockStrategyCalculator._cross_pct(short_prices.futures, long_prices.spot)
        if strategy_id == "futures_spot_1ex":
            return MockStrategyCalculator._cross_pct(short_prices.futures, short_prices.spot)
        if strategy_id in {"funding_ff", "funding_diff_dates"}:
            return MockStrategyCalculator._cross_pct(short_prices.futures, long_prices.futures)
        if strategy_id == "funding_fs":
            return MockStrategyCalculator._cross_pct(short_prices.futures, long_prices.spot)
        return 0.0

    @staticmethod
    def screener_profits(
        prices: dict[str, MockExchangePrices],
        short_exchange_id: str,
        long_exchange_id: str,
        calibration: MockScreenerStrategyCalibration,
    ) -> StrategyProfitsDto:
        scaled: dict[str, float | None] = {}
        base = calibration.base_profits
        for strategy_id in _STRATEGY_IDS:
            base_metric = calibration.base_metrics.get(strategy_id, 0.0)
            current_metric = MockStrategyCalculator.spread_metric(
                strategy_id,
                prices,
                short_exchange_id,
                long_exchange_id,
            )
            base_net = getattr(base, strategy_id)
            if base_net is None:
                scaled[strategy_id] = None
                continue
            scaled[strategy_id] = MockStrategyCalculator._scale_value(
                base_net,
                base_metric,
                current_metric,
            )
        return StrategyProfitsDto(
            futures_futures=scaled["futures_futures"],
            futures_spot_2ex=scaled["futures_spot_2ex"],
            futures_spot_1ex=scaled["futures_spot_1ex"],
            funding_ff=scaled["funding_ff"],
            funding_fs=scaled["funding_fs"],
            funding_diff_dates=scaled["funding_diff_dates"],
        )

    @staticmethod
    def opportunity_rows(
        prices: dict[str, MockExchangePrices],
        short_exchange_id: str,
        long_exchange_id: str,
        volume_usdt: float,
        leverage: int,
        reference_volume_usdt: float,
        templates: list[MockOpportunityRowTemplate],
    ) -> list[StrategyCalculationRowDto]:
        volume_ratio = volume_usdt / reference_volume_usdt if reference_volume_usdt > 0.0 else 1.0
        rows: list[StrategyCalculationRowDto] = []
        for template in templates:
            if template.unavailable_reason is not None:
                rows.append(
                    StrategyCalculationRowDto(
                        strategy_id=template.strategy_id,
                        strategy_label=template.strategy_label,
                        spread_pct=template.base_spread_pct,
                        prices_label="—",
                        fees_usdt=template.base_fees_usdt,
                        funding_usdt=template.base_funding_usdt,
                        volume_usdt=volume_usdt,
                        leverage=leverage,
                        gross_profit_usdt=None,
                        costs_usdt=template.base_costs_usdt,
                        costs_breakdown=template.costs_breakdown,
                        net_profit_usdt=None,
                        percent_to_deposit=None,
                        unavailable_reason=template.unavailable_reason,
                    )
                )
                continue

            current_spread = MockStrategyCalculator.spread_metric(
                template.strategy_id,
                prices,
                short_exchange_id,
                long_exchange_id,
            )
            ratio = (
                current_spread / template.base_spread_pct
                if template.base_spread_pct > 0.0
                else 1.0
            )
            base_gross = template.base_gross_usdt if template.base_gross_usdt is not None else 0.0
            gross = MockStrategyCalculator._scale_value(
                base_gross * volume_ratio,
                template.base_spread_pct,
                current_spread,
            )
            costs = round(template.base_costs_usdt * volume_ratio, 2)
            fees = round(template.base_fees_usdt * volume_ratio, 2)
            funding = round(template.base_funding_usdt * volume_ratio * ratio, 2)
            net = round(gross - costs, 2)
            percent = None
            if template.base_percent_to_deposit is not None:
                percent = MockStrategyCalculator._scale_value(
                    template.base_percent_to_deposit * volume_ratio,
                    template.base_spread_pct,
                    current_spread,
                )
            rows.append(
                StrategyCalculationRowDto(
                    strategy_id=template.strategy_id,
                    strategy_label=template.strategy_label,
                    spread_pct=round(current_spread, 2),
                    prices_label=MockStrategyCalculator._prices_label(
                        template.strategy_id,
                        prices,
                        short_exchange_id,
                        long_exchange_id,
                    ),
                    fees_usdt=fees,
                    funding_usdt=funding,
                    volume_usdt=volume_usdt,
                    leverage=leverage,
                    gross_profit_usdt=gross,
                    costs_usdt=costs,
                    costs_breakdown=template.costs_breakdown,
                    net_profit_usdt=net,
                    percent_to_deposit=percent,
                    unavailable_reason=None,
                )
            )
        return rows

    @staticmethod
    def build_screener_calibration(
        prices: dict[str, MockExchangePrices],
        short_exchange_id: str,
        long_exchange_id: str,
        base_profits: StrategyProfitsDto,
    ) -> MockScreenerStrategyCalibration:
        base_metrics = {
            strategy_id: MockStrategyCalculator.spread_metric(
                strategy_id,
                prices,
                short_exchange_id,
                long_exchange_id,
            )
            for strategy_id in _STRATEGY_IDS
        }
        return MockScreenerStrategyCalibration(
            base_profits=base_profits,
            base_metrics=base_metrics,
        )

    @staticmethod
    def build_opportunity_templates(
        seed_rows: list[dict[str, object]],
    ) -> list[MockOpportunityRowTemplate]:
        templates: list[MockOpportunityRowTemplate] = []
        for row_data in seed_rows:
            gross_raw = row_data.get("gross_profit_usdt")
            net_raw = row_data.get("net_profit_usdt")
            pct_raw = row_data.get("percent_to_deposit")
            reason_raw = row_data.get("unavailable_reason")
            gross = float(gross_raw) if isinstance(gross_raw, (int, float)) else None
            net = float(net_raw) if isinstance(net_raw, (int, float)) else None
            percent = float(pct_raw) if isinstance(pct_raw, (int, float)) else None
            reason = str(reason_raw) if reason_raw is not None else None
            templates.append(
                MockOpportunityRowTemplate(
                    strategy_id=str(row_data.get("strategy_id", "")),
                    strategy_label=str(row_data.get("strategy_label", "")),
                    base_spread_pct=float(row_data.get("spread_pct", 0.0)),
                    base_gross_usdt=gross,
                    base_costs_usdt=float(row_data.get("costs_usdt", 0.0)),
                    base_fees_usdt=float(row_data.get("fees_usdt", 0.0)),
                    base_funding_usdt=float(row_data.get("funding_usdt", 0.0)),
                    base_net_usdt=net,
                    base_percent_to_deposit=percent,
                    costs_breakdown=str(row_data.get("costs_breakdown", "")),
                    unavailable_reason=reason,
                )
            )
        return templates

    @staticmethod
    def _cross_pct(high_price: float, low_price: float) -> float:
        if low_price <= 0.0:
            return 0.0
        return (high_price - low_price) / low_price * 100.0

    @staticmethod
    def _scale_value(
        base_value: float | None,
        base_metric: float,
        current_metric: float,
    ) -> float | None:
        if base_value is None:
            return None
        if base_metric <= 0.0:
            return round(base_value, 2)
        return round(base_value * (current_metric / base_metric), 2)

    @staticmethod
    def _prices_label(
        strategy_id: str,
        prices: dict[str, MockExchangePrices],
        short_exchange_id: str,
        long_exchange_id: str,
    ) -> str:
        short_prices = prices.get(short_exchange_id)
        long_prices = prices.get(long_exchange_id)
        if short_prices is None or long_prices is None:
            return "— / —"
        if strategy_id == "futures_futures":
            return (
                f"{MockStrategyCalculator._fmt_price(short_prices.futures)} / "
                f"{MockStrategyCalculator._fmt_price(long_prices.futures)}"
            )
        if strategy_id == "futures_spot_2ex":
            return (
                f"{MockStrategyCalculator._fmt_price(short_prices.futures)} / "
                f"{MockStrategyCalculator._fmt_price(long_prices.spot)}"
            )
        if strategy_id == "futures_spot_1ex":
            return (
                f"{MockStrategyCalculator._fmt_price(short_prices.futures)} / "
                f"{MockStrategyCalculator._fmt_price(short_prices.spot)}"
            )
        if strategy_id in {"funding_ff", "funding_diff_dates"}:
            return (
                f"{MockStrategyCalculator._fmt_price(short_prices.futures)} / "
                f"{MockStrategyCalculator._fmt_price(long_prices.futures)}"
            )
        if strategy_id == "funding_fs":
            return (
                f"{MockStrategyCalculator._fmt_price(short_prices.futures)} / "
                f"{MockStrategyCalculator._fmt_price(long_prices.spot)}"
            )
        return "— / —"

    @staticmethod
    def _fmt_price(value: float) -> str:
        if value >= 100.0:
            return f"{value:.2f}"
        return f"{value:.4f}"
