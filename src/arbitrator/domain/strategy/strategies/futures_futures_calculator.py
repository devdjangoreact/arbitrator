from __future__ import annotations

from decimal import Decimal

from arbitrator.domain.strategy.strategy_inputs import StrategyInputs
from arbitrator.domain.strategy.strategy_kind import StrategyKind
from arbitrator.domain.strategy.strategy_math import StrategyMath
from arbitrator.domain.strategy.strategy_result import StrategyResult

_HUNDRED = Decimal("100")


class FuturesFuturesCalculator:
    """§3 Futures-futures cross-price spread.

    Short the higher-priced venue (by ``bid``), long the cheaper one (by ``ask``);
    profit is convergence of the cross price spread. Both legs are futures.
    """

    strategy_id: StrategyKind = StrategyKind.futures_futures

    def compute(self, inputs: StrategyInputs) -> StrategyResult:
        sid = self.strategy_id
        short_q = inputs.futures_quotes.get(inputs.short_exchange_id)
        long_q = inputs.futures_quotes.get(inputs.long_exchange_id)
        if short_q is None or long_q is None or short_q.bid is None or long_q.ask is None:
            return StrategyResult.unavailable(sid, "no_quotes")
        price_short = short_q.bid
        price_long = long_q.ask
        if price_long <= 0:
            return StrategyResult.unavailable(sid, "no_quotes")

        fee_short = inputs.fees.get(inputs.short_exchange_id)
        fee_long = inputs.fees.get(inputs.long_exchange_id)
        if (
            fee_short is None
            or fee_long is None
            or fee_short.futures_taker is None
            or fee_long.futures_taker is None
        ):
            return StrategyResult.unavailable(sid, "no_fees")

        volume = inputs.target_volume_usdt
        spread_pct = (price_short - price_long) / price_long * _HUNDRED
        gross = StrategyMath.gross_from_spread(spread_pct, volume)
        fees = StrategyMath.fee_total(
            volume,
            (
                fee_short.futures_taker,
                fee_short.futures_taker,
                fee_long.futures_taker,
                fee_long.futures_taker,
            ),
        )
        funding = self._funding(inputs, volume)
        costs = fees + funding
        net = gross - costs

        lev_short = inputs.leverage.get(inputs.short_exchange_id, 1)
        lev_long = inputs.leverage.get(inputs.long_exchange_id, 1)
        deposit = inputs.deposit_usdt
        if deposit is None:
            deposit = StrategyMath.deposit(((volume, lev_short), (volume, lev_long)))
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
            leverage=lev_short,
            gross_profit_usdt=gross,
            costs_usdt=costs,
            costs_breakdown=StrategyMath.costs_breakdown_label(fees, funding),
            net_profit_usdt=net,
            percent_to_deposit=percent,
        )

    @staticmethod
    def _funding(inputs: StrategyInputs, volume: Decimal) -> Decimal:
        legs: list[tuple[str, Decimal, Decimal]] = []
        short_f = inputs.funding.get(inputs.short_exchange_id)
        long_f = inputs.funding.get(inputs.long_exchange_id)
        if short_f is not None and short_f.rate is not None:
            legs.append(("short", short_f.rate, volume))
        if long_f is not None and long_f.rate is not None:
            legs.append(("long", long_f.rate, volume))
        return StrategyMath.funding_cost(tuple(legs))
