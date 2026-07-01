from __future__ import annotations

from dataclasses import dataclass

from arbitrator.application.arbitrage_open_service import ArbitrageOpenService, OpenPairResult
from arbitrator.config.settings import Settings
from arbitrator.domain.opportunity_controls import OpportunityControls
from arbitrator.domain.opportunity_view import OpportunityView
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.domain.spread_calculator import SpreadCalculator
from arbitrator.domain.spread_snapshot import SpreadSnapshot


@dataclass(frozen=True, slots=True)
class SuggestedAccumulate:
    notional_usdt: float
    allowed: bool
    message: str | None


class OpportunityAccumulateService:
    """Gradual accumulate sizing and execution for one opportunity."""

    def __init__(self, settings: Settings, open_service: ArbitrageOpenService) -> None:
        self._settings = settings
        self._open_service = open_service

    def suggest_notional(
        self,
        controls: OpportunityControls,
        short_leg: PositionLeg | None,
        long_leg: PositionLeg | None,
        long_price: float,
    ) -> SuggestedAccumulate:
        if long_price <= 0.0:
            return SuggestedAccumulate(0.0, False, "Invalid price for sizing")
        current_notional = self._current_notional(short_leg, long_leg)
        remaining = max(0.0, controls.max_notional_usdt - current_notional)
        if remaining <= 0.0:
            return SuggestedAccumulate(0.0, False, "Max notional reached")
        step = min(remaining, self._settings.opp_accumulate_step_usdt)
        if step <= 0.0:
            return SuggestedAccumulate(0.0, False, "Nothing to accumulate")
        return SuggestedAccumulate(step, True, None)

    def can_accumulate(self, controls: OpportunityControls, spread_pct: float | None) -> bool:
        if spread_pct is None:
            return False
        return spread_pct >= controls.accumulate_spread_threshold_pct

    def accumulate(
        self,
        view: OpportunityView,
        controls: OpportunityControls,
        snapshot: SpreadSnapshot,
        notional_usdt: float,
        short_leg: PositionLeg | None,
        long_leg: PositionLeg | None,
        long_price: float,
    ) -> OpenPairResult:
        spread = SpreadCalculator.compute(view.symbol, snapshot.prices_by_exchange)
        if not self.can_accumulate(controls, spread.spread_pct):
            return OpenPairResult(
                pair_id="",
                symbol=view.symbol,
                short_exchange_id=view.short_exchange_id,
                long_exchange_id=view.long_exchange_id,
                short_order_id=None,
                long_order_id=None,
                success=False,
                message="Spread below accumulate threshold",
            )
        current_notional = self._current_notional(short_leg, long_leg)
        if current_notional + notional_usdt > controls.max_notional_usdt:
            return OpenPairResult(
                pair_id="",
                symbol=view.symbol,
                short_exchange_id=view.short_exchange_id,
                long_exchange_id=view.long_exchange_id,
                short_order_id=None,
                long_order_id=None,
                success=False,
                message="Would exceed max notional",
            )
        return self._open_service.open_with_notional_sync(snapshot, notional_usdt)

    @staticmethod
    def _current_notional(
        short_leg: PositionLeg | None,
        long_leg: PositionLeg | None,
    ) -> float:
        notionals: list[float] = []
        for leg in (short_leg, long_leg):
            if leg is None:
                continue
            mark = leg.mark_price if leg.mark_price is not None else leg.entry_price
            notionals.append(abs(leg.contracts) * leg.contract_size * mark)
        if not notionals:
            return 0.0
        return max(notionals)
