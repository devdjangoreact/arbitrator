from __future__ import annotations

from arbitrator.application.arbitrage_pairing_service import OpenPositionsGrouped
from arbitrator.domain.opportunity_view import OpportunityView


class OpportunityRegistryService:
    """Builds ephemeral opportunity list from live exchange open positions."""

    def list_from_grouped(self, grouped: OpenPositionsGrouped) -> list[OpportunityView]:
        views: list[OpportunityView] = []
        for pair in grouped.pairs:
            if pair.short_leg.contracts <= 0.0 and pair.long_leg.contracts <= 0.0:
                continue
            views.append(
                OpportunityView(
                    symbol=pair.symbol,
                    short_exchange_id=pair.short_leg.exchange_id,
                    long_exchange_id=pair.long_leg.exchange_id,
                    pair_id=pair.pair_id,
                )
            )
        views.sort(key=lambda view: view.symbol)
        return views

    def find_matching(
        self,
        views: list[OpportunityView],
        candidate: OpportunityView,
    ) -> OpportunityView | None:
        key = candidate.focus_key()
        for view in views:
            if view.focus_key() == key:
                return view
        return None
