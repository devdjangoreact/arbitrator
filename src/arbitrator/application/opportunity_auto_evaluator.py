from __future__ import annotations

from dataclasses import dataclass

from arbitrator.application.arbitrage_close_service import ArbitrageCloseService, ClosePairResult
from arbitrator.application.opportunity_accumulate_service import OpportunityAccumulateService
from arbitrator.domain.arbitrage_pair import ArbitragePair
from arbitrator.domain.opportunity_controls import OpportunityControls
from arbitrator.domain.opportunity_view import OpportunityView
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.domain.spread_snapshot import SpreadSnapshot


@dataclass(frozen=True, slots=True)
class AutoEvaluateResult:
    fired_accumulate: bool
    fired_close: bool
    accumulate_result: object | None
    close_result: ClosePairResult | None


class OpportunityAutoEvaluator:
    """Evaluates auto-accumulate and auto-close once per tick."""

    def __init__(
        self,
        accumulate_service: OpportunityAccumulateService,
        close_service: ArbitrageCloseService,
    ) -> None:
        self._accumulate_service = accumulate_service
        self._close_service = close_service

    def evaluate(
        self,
        view: OpportunityView,
        controls: OpportunityControls,
        snapshot: SpreadSnapshot,
        pair: ArbitragePair | None,
        short_leg: PositionLeg | None,
        long_leg: PositionLeg | None,
        long_price: float,
        *,
        already_closed_this_tick: bool,
    ) -> AutoEvaluateResult:
        spread_pct = snapshot.spread_pct
        fired_accumulate = False
        fired_close = False
        accumulate_result: object | None = None
        close_result: ClosePairResult | None = None

        if (
            controls.auto_accumulate
            and pair is not None
            and self._accumulate_service.can_accumulate(controls, spread_pct)
        ):
            suggestion = self._accumulate_service.suggest_notional(
                controls,
                short_leg,
                long_leg,
                long_price,
            )
            if suggestion.allowed and suggestion.notional_usdt > 0.0:
                accumulate_result = self._accumulate_service.accumulate(
                    view,
                    controls,
                    snapshot,
                    suggestion.notional_usdt,
                    short_leg,
                    long_leg,
                    long_price,
                )
                fired_accumulate = True

        if (
            controls.auto_close
            and pair is not None
            and not already_closed_this_tick
            and spread_pct is not None
            and spread_pct <= controls.min_close_spread_pct
        ):
            close_result = self._close_service.close_pair_sync(pair)
            fired_close = True

        return AutoEvaluateResult(
            fired_accumulate=fired_accumulate,
            fired_close=fired_close,
            accumulate_result=accumulate_result,
            close_result=close_result,
        )
