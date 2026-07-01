from __future__ import annotations

from decimal import Decimal

from arbitrator.domain.strategy.strategy_inputs import StrategyInputs
from arbitrator.domain.strategy.strategy_kind import StrategyKind
from arbitrator.domain.strategy.strategy_math import StrategyMath
from arbitrator.domain.strategy.strategy_result import StrategyResult

_HUNDRED = Decimal("100")


class FuturesSpot2exCalculator:
    """§2 Spot + futures on two exchanges (basis convergence).

    Long spot on the long exchange (by ``ask``), short futures on the short
    exchange (by ``bid``); profit is the narrowing basis between the two venues.
    """

    strategy_id: StrategyKind = StrategyKind.futures_spot_2ex

    def compute(self, inputs: StrategyInputs) -> StrategyResult:
        sid = self.strategy_id
        futures_q = inputs.futures_quotes.get(inputs.short_exchange_id)
        if futures_q is None or futures_q.bid is None:
            return StrategyResult.unavailable(sid, "no_quotes")
        spot_q = inputs.spot_quotes.get(inputs.long_exchange_id)
        if spot_q is None or spot_q.ask is None:
            return StrategyResult.unavailable(sid, "no_spot")
        price_short = futures_q.bid
        price_long = spot_q.ask
        if price_long <= 0:
            return StrategyResult.unavailable(sid, "no_spot")

        fee_futures = inputs.fees.get(inputs.short_exchange_id)
        fee_spot = inputs.fees.get(inputs.long_exchange_id)
        if (
            fee_futures is None
            or fee_spot is None
            or fee_futures.futures_taker is None
            or fee_spot.spot_taker is None
        ):
            return StrategyResult.unavailable(sid, "no_fees")

        volume = inputs.target_volume_usdt
        spread_pct = (price_short - price_long) / price_long * _HUNDRED
        gross = StrategyMath.gross_from_spread(spread_pct, volume)
        fees = StrategyMath.fee_total(
            volume,
            (
                fee_futures.futures_taker,
                fee_futures.futures_taker,
                fee_spot.spot_taker,
                fee_spot.spot_taker,
            ),
        )
        funding = self._funding(inputs, volume)
        costs = fees + funding
        net = gross - costs

        lev_futures = inputs.leverage.get(inputs.short_exchange_id, 1)
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
    def _funding(inputs: StrategyInputs, volume: Decimal) -> Decimal:
        short_f = inputs.funding.get(inputs.short_exchange_id)
        if short_f is None or short_f.rate is None:
            return Decimal("0")
        return StrategyMath.funding_cost((("short", short_f.rate, volume),))
