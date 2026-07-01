from __future__ import annotations

from arbitrator.config.settings import Settings
from arbitrator.domain.arbitrage_pair import ArbitragePair
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.domain.spread_snapshot import SpreadSnapshot


class ArbitragePnlService:
    """Computes current and projected net PnL for open arbitrage pairs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def enrich_pair(self, pair: ArbitragePair, live: SpreadSnapshot | None) -> ArbitragePair:
        projected = self.projected_net_pnl(pair, live)
        return pair.model_copy(update={"projected_net_pnl": projected})

    def projected_net_pnl(
        self,
        pair: ArbitragePair,
        live: SpreadSnapshot | None,
    ) -> float | None:
        current = pair.combined_unrealized_pnl
        if current is None:
            current = self._sum_unrealized(pair.short_leg, pair.long_leg)
        if current is None:
            return None
        close_fees = self._close_fees(pair.short_leg, pair.long_leg)
        funding = pair.combined_accrued_funding or 0.0
        base = current + funding - close_fees
        return base

    @staticmethod
    def _sum_unrealized(short_leg: PositionLeg, long_leg: PositionLeg) -> float | None:
        if short_leg.unrealized_pnl is None and long_leg.unrealized_pnl is None:
            return None
        return (short_leg.unrealized_pnl or 0.0) + (long_leg.unrealized_pnl or 0.0)

    @staticmethod
    def _close_fees(short_leg: PositionLeg, long_leg: PositionLeg) -> float:
        total = 0.0
        for leg in (short_leg, long_leg):
            if leg.estimated_close_fee is not None:
                total += leg.estimated_close_fee
        return total
