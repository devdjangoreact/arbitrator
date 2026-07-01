from __future__ import annotations

from decimal import Decimal

from arbitrator.domain.strategy.strategy_inputs import StrategyInputs
from arbitrator.domain.strategy.strategy_kind import StrategyKind
from arbitrator.domain.strategy.strategy_math import StrategyMath
from arbitrator.domain.strategy.strategy_result import StrategyResult

_HUNDRED = Decimal("100")


class FuturesSpot1exCalculator:
    """§1 Spot + futures on a single exchange (basis convergence).

    Long spot (by ``ask``) and short futures (by ``bid``) on the same venue;
    profit is the narrowing premium of futures over spot.
    """

    strategy_id: StrategyKind = StrategyKind.futures_spot_1ex

    def compute(self, inputs: StrategyInputs) -> StrategyResult:
        sid = self.strategy_id
        exchange_id = inputs.short_exchange_id
        futures_q = inputs.futures_quotes.get(exchange_id)
        if futures_q is None or futures_q.bid is None:
            return StrategyResult.unavailable(sid, "no_quotes")
        spot_q = inputs.spot_quotes.get(exchange_id)
        if spot_q is None or spot_q.ask is None:
            return StrategyResult.unavailable(sid, "no_spot")
        price_short = futures_q.bid
        price_long = spot_q.ask
        if price_long <= 0:
            return StrategyResult.unavailable(sid, "no_spot")

        fee = inputs.fees.get(exchange_id)
        if fee is None or fee.futures_taker is None or fee.spot_taker is None:
            return StrategyResult.unavailable(sid, "no_fees")

        volume = inputs.target_volume_usdt
        spread_pct = (price_short - price_long) / price_long * _HUNDRED
        gross = StrategyMath.gross_from_spread(spread_pct, volume)
        fees = StrategyMath.fee_total(
            volume,
            (fee.futures_taker, fee.futures_taker, fee.spot_taker, fee.spot_taker),
        )
        funding = self._funding(inputs, exchange_id, volume)
        costs = fees + funding
        net = gross - costs

        lev_futures = inputs.leverage.get(exchange_id, 1)
        deposit = inputs.deposit_usdt
        if deposit is None:
            deposit = StrategyMath.deposit(((volume, lev_futures), (volume, 1)))
        percent = StrategyMath.percent_to_deposit(net, deposit)

        return StrategyResult(
            strategy_id=sid,
            available=True,
            spread_pct=spread_pct,
            price_short=price_short,
            price_long=price_long,
            fees_usdt=fees,
            funding_usdt=funding,
            volume_usdt=volume,
            leverage=lev_futures,
            gross_profit_usdt=gross,
            costs_usdt=costs,
            costs_breakdown=StrategyMath.costs_breakdown_label(fees, funding),
            net_profit_usdt=net,
            percent_to_deposit=percent,
        )

    @staticmethod
    def _funding(inputs: StrategyInputs, exchange_id: str, volume: Decimal) -> Decimal:
        fund = inputs.funding.get(exchange_id)
        if fund is None or fund.rate is None:
            return Decimal("0")
        return StrategyMath.funding_cost((("short", fund.rate, volume),))
