from __future__ import annotations

from decimal import Decimal

from arbitrator.domain.strategy.strategy_inputs import StrategyInputs
from arbitrator.domain.strategy.strategy_kind import StrategyKind
from arbitrator.domain.strategy.strategy_math import StrategyMath
from arbitrator.domain.strategy.strategy_result import StrategyResult

_HUNDRED = Decimal("100")


class FundingDiffDatesCalculator:
    """§5 Funding settlement-time difference.

    Earn on the **early** exchange (high ``|rate|``, settles soon), hedge on the
    **late** one (its funding does not accrue before we close). Gross =
    ``|rate_early|`` income; close after the early settlement.
    """

    strategy_id: StrategyKind = StrategyKind.funding_diff_dates

    def compute(self, inputs: StrategyInputs) -> StrategyResult:
        sid = self.strategy_id
        short_q = inputs.futures_quotes.get(inputs.short_exchange_id)
        long_q = inputs.futures_quotes.get(inputs.long_exchange_id)
        if short_q is None or long_q is None or short_q.bid is None or long_q.ask is None:
            return StrategyResult.unavailable(sid, "no_quotes")

        short_f = inputs.funding.get(inputs.short_exchange_id)
        long_f = inputs.funding.get(inputs.long_exchange_id)
        if short_f is None or long_f is None or short_f.rate is None or long_f.rate is None:
            return StrategyResult.unavailable(sid, "no_funding")
        short_ts = short_f.next_settlement_ms
        long_ts = long_f.next_settlement_ms
        if short_ts is None or long_ts is None:
            return StrategyResult.unavailable(sid, "funding_ts_stale")
        if short_ts == long_ts:
            return StrategyResult.unavailable(sid, "no_settlement_gap")

        early_ts = min(short_ts, long_ts)
        if early_ts <= inputs.now_ms:
            return StrategyResult.unavailable(sid, "funding_ts_stale")
        early_rate = short_f.rate if short_ts <= long_ts else long_f.rate

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
        spread_pct = abs(early_rate) * _HUNDRED
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
        funding = Decimal("0")
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
            price_short=short_q.bid,
            price_long=long_q.ask,
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
