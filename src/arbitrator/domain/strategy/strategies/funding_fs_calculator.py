from __future__ import annotations

from decimal import Decimal

from arbitrator.domain.strategy.funding_info import FundingInfo
from arbitrator.domain.strategy.strategy_inputs import StrategyInputs
from arbitrator.domain.strategy.strategy_kind import StrategyKind
from arbitrator.domain.strategy.strategy_math import StrategyMath
from arbitrator.domain.strategy.strategy_result import StrategyResult

_HUNDRED = Decimal("100")


class FundingFsCalculator:
    """§6/§7 Funding + spot hedge (one UI strategy, two branches by spot location).

    The futures leg earns funding; spot hedges price. C11:
    - §6: spot and futures on the **same** exchange;
    - §7: spot on the cheapest **other** exchange (cross-basis is the only extra cost).
    When both branches resolve, the better ``% to deposit`` wins.
    """

    strategy_id: StrategyKind = StrategyKind.funding_fs

    def compute(self, inputs: StrategyInputs) -> StrategyResult:
        sid = self.strategy_id
        futures_ex = inputs.short_exchange_id
        futures_q = inputs.futures_quotes.get(futures_ex)
        if futures_q is None or futures_q.bid is None:
            return StrategyResult.unavailable(sid, "no_quotes")

        fund = inputs.funding.get(futures_ex)
        if fund is None or fund.rate is None:
            return StrategyResult.unavailable(sid, "no_funding")
        if fund.next_settlement_ms is None or fund.next_settlement_ms <= inputs.now_ms:
            return StrategyResult.unavailable(sid, "funding_ts_stale")

        futures_fee = inputs.fees.get(futures_ex)
        if futures_fee is None or futures_fee.futures_taker is None:
            return StrategyResult.unavailable(sid, "no_fees")

        same_ex = self._branch(inputs, futures_ex, futures_q.bid, fund, futures_ex, "§6")
        other_ex = self._other_branch(inputs, futures_ex, futures_q.bid, fund)

        candidates = [r for r in (same_ex, other_ex) if r is not None]
        if not candidates:
            return StrategyResult.unavailable(sid, "no_spot")
        return max(
            candidates,
            key=lambda r: r.percent_to_deposit if r.percent_to_deposit is not None else Decimal("-1e30"),
        )

    def _other_branch(
        self,
        inputs: StrategyInputs,
        futures_ex: str,
        futures_bid: Decimal,
        fund: FundingInfo,
    ) -> StrategyResult | None:
        cheapest_ex: str | None = None
        cheapest_ask: Decimal | None = None
        for ex_id, quote in inputs.spot_quotes.items():
            if ex_id == futures_ex or quote.ask is None or quote.ask <= 0:
                continue
            if cheapest_ask is None or quote.ask < cheapest_ask:
                cheapest_ask = quote.ask
                cheapest_ex = ex_id
        if cheapest_ex is None:
            return None
        return self._branch(inputs, futures_ex, futures_bid, fund, cheapest_ex, "§7")

    def _branch(
        self,
        inputs: StrategyInputs,
        futures_ex: str,
        futures_bid: Decimal,
        fund: FundingInfo,
        spot_ex: str,
        label: str,
    ) -> StrategyResult | None:
        spot_q = inputs.spot_quotes.get(spot_ex)
        if spot_q is None or spot_q.ask is None or spot_q.ask <= 0:
            return None
        spot_fee = inputs.fees.get(spot_ex)
        futures_fee = inputs.fees.get(futures_ex)
        if (
            spot_fee is None
            or futures_fee is None
            or spot_fee.spot_taker is None
            or futures_fee.futures_taker is None
            or fund.rate is None
        ):
            return None

        volume = inputs.target_volume_usdt
        spread_pct = abs(fund.rate) * _HUNDRED
        gross = StrategyMath.gross_from_spread(spread_pct, volume)
        fees = StrategyMath.fee_total(
            volume,
            (
                futures_fee.futures_taker,
                futures_fee.futures_taker,
                spot_fee.spot_taker,
                spot_fee.spot_taker,
            ),
        )
        funding = Decimal("0")
        costs = fees + funding
        net = gross - costs

        lev_futures = inputs.leverage.get(futures_ex, 1)
        deposit = inputs.deposit_usdt
        if deposit is None:
            deposit = StrategyMath.deposit(((volume, lev_futures), (volume, 1)))
        percent = StrategyMath.percent_to_deposit(net, deposit)

        return StrategyResult(
            strategy_id=self.strategy_id,
            available=True,
            spread_pct=spread_pct,
            price_short=futures_bid,
            price_long=spot_q.ask,
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
