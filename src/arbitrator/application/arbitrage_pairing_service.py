from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from arbitrator.config.settings import Settings
from arbitrator.domain.arb_marker_record import ArbMarkerRecord
from arbitrator.domain.arb_markers_repository import ArbMarkersRepository
from arbitrator.domain.arbitrage_pair import ArbitragePair
from arbitrator.domain.closed_arbitrage_group import ClosedArbitrageGroup
from arbitrator.domain.closed_position_leg import ClosedPositionLeg
from arbitrator.domain.position_leg import PositionLeg


@dataclass(frozen=True, slots=True)
class OpenPositionsGrouped:
    pairs: tuple[ArbitragePair, ...]
    ungrouped: tuple[PositionLeg, ...]


@dataclass(frozen=True, slots=True)
class ClosedPositionsGrouped:
    groups: tuple[ClosedArbitrageGroup, ...]
    ungrouped: tuple[ClosedPositionLeg, ...]


class ArbitragePairingService:
    """Groups short+long legs into arbitrage pairs (marker-first, then heuristic)."""

    def __init__(self, settings: Settings, markers: ArbMarkersRepository) -> None:
        self._settings = settings
        self._markers = markers

    def group_open(self, legs: list[PositionLeg]) -> OpenPositionsGrouped:
        remaining = list(legs)
        pairs: list[ArbitragePair] = []
        marker_records = self._markers.load()
        pairs.extend(self._pair_by_markers(remaining, marker_records))
        pairs.extend(self._pair_by_heuristic(remaining))
        return OpenPositionsGrouped(
            pairs=tuple(pairs),
            ungrouped=tuple(remaining),
        )

    def group_closed(self, legs: list[ClosedPositionLeg]) -> ClosedPositionsGrouped:
        remaining = list(legs)
        groups: list[ClosedArbitrageGroup] = []
        marker_records = self._markers.load()
        groups.extend(self._group_closed_by_markers(remaining, marker_records))
        groups.extend(self._group_closed_by_heuristic(remaining))
        return ClosedPositionsGrouped(
            groups=tuple(groups),
            ungrouped=tuple(remaining),
        )

    def _pair_by_markers(
        self,
        remaining: list[PositionLeg],
        records: list[ArbMarkerRecord],
    ) -> list[ArbitragePair]:
        pairs: list[ArbitragePair] = []
        for record in records:
            short_candidates = [
                leg
                for leg in remaining
                if leg.arb_marker_id == record.pair_id
                and leg.side == "short"
                and leg.exchange_id == record.short_exchange_id
                and leg.symbol == record.symbol
            ]
            long_candidates = [
                leg
                for leg in remaining
                if leg.arb_marker_id == record.pair_id
                and leg.side == "long"
                and leg.exchange_id == record.long_exchange_id
                and leg.symbol == record.symbol
            ]
            if not short_candidates or not long_candidates:
                continue
            short_leg = short_candidates[0]
            long_leg = long_candidates[0]
            pair = self._build_open_pair(record.pair_id, short_leg, long_leg)
            pairs.append(pair)
            self._consume_open(remaining, short_leg)
            self._consume_open(remaining, long_leg)
        return pairs

    def _pair_by_heuristic(self, remaining: list[PositionLeg]) -> list[ArbitragePair]:
        pairs: list[ArbitragePair] = []
        window = timedelta(seconds=self._settings.arb_pairing_window_seconds)
        shorts = [leg for leg in remaining if leg.side == "short"]
        longs = [leg for leg in remaining if leg.side == "long"]
        for short_leg in list(shorts):
            if short_leg not in remaining:
                continue
            match: PositionLeg | None = None
            for long_leg in longs:
                if long_leg not in remaining:
                    continue
                if long_leg.symbol != short_leg.symbol:
                    continue
                if long_leg.exchange_id == short_leg.exchange_id:
                    continue
                delta = abs(long_leg.opened_at - short_leg.opened_at)
                if delta <= window:
                    match = long_leg
                    break
            if match is None:
                continue
            pair_id = f"heuristic-{short_leg.symbol}-{short_leg.exchange_id}-{match.exchange_id}"
            pairs.append(self._build_open_pair(pair_id, short_leg, match))
            self._consume_open(remaining, short_leg)
            self._consume_open(remaining, match)
        return pairs

    def _group_closed_by_markers(
        self,
        remaining: list[ClosedPositionLeg],
        records: list[ArbMarkerRecord],
    ) -> list[ClosedArbitrageGroup]:
        groups: list[ClosedArbitrageGroup] = []
        for record in records:
            short_leg = self._find_closed_leg(
                remaining,
                record.pair_id,
                "short",
                record.short_exchange_id,
                record.symbol,
            )
            long_leg = self._find_closed_leg(
                remaining,
                record.pair_id,
                "long",
                record.long_exchange_id,
                record.symbol,
            )
            if short_leg is None or long_leg is None:
                continue
            groups.append(self._build_closed_group(record.pair_id, short_leg, long_leg))
            self._consume_closed(remaining, short_leg)
            self._consume_closed(remaining, long_leg)
        return groups

    def _group_closed_by_heuristic(
        self,
        remaining: list[ClosedPositionLeg],
    ) -> list[ClosedArbitrageGroup]:
        groups: list[ClosedArbitrageGroup] = []
        window = timedelta(seconds=self._settings.arb_pairing_window_seconds)
        shorts = [leg for leg in remaining if leg.side == "short"]
        longs = [leg for leg in remaining if leg.side == "long"]
        for short_leg in list(shorts):
            if short_leg not in remaining:
                continue
            match: ClosedPositionLeg | None = None
            for long_leg in longs:
                if long_leg not in remaining:
                    continue
                if long_leg.symbol != short_leg.symbol:
                    continue
                if long_leg.exchange_id == short_leg.exchange_id:
                    continue
                opened_short = short_leg.opened_at or short_leg.closed_at
                opened_long = long_leg.opened_at or long_leg.closed_at
                if abs(opened_short - opened_long) <= window:
                    match = long_leg
                    break
            if match is None:
                continue
            pair_id = f"closed-{short_leg.symbol}-{short_leg.exchange_id}-{match.exchange_id}"
            groups.append(self._build_closed_group(pair_id, short_leg, match))
            self._consume_closed(remaining, short_leg)
            self._consume_closed(remaining, match)
        return groups

    @staticmethod
    def _find_closed_leg(
        legs: list[ClosedPositionLeg],
        pair_id: str,
        side: str,
        exchange_id: str,
        symbol: str,
    ) -> ClosedPositionLeg | None:
        for leg in legs:
            if (
                leg.arb_marker_id == pair_id
                and leg.side == side
                and leg.exchange_id == exchange_id
                and leg.symbol == symbol
            ):
                return leg
        return None

    @staticmethod
    def _build_open_pair(
        pair_id: str,
        short_leg: PositionLeg,
        long_leg: PositionLeg,
    ) -> ArbitragePair:
        combined_unrealized = ArbitragePairingService._sum_optional(
            short_leg.unrealized_pnl,
            long_leg.unrealized_pnl,
        )
        combined_funding = ArbitragePairingService._sum_optional(
            short_leg.accrued_funding,
            long_leg.accrued_funding,
        )
        return ArbitragePair(
            pair_id=pair_id,
            symbol=short_leg.symbol,
            short_leg=short_leg,
            long_leg=long_leg,
            combined_unrealized_pnl=combined_unrealized,
            combined_accrued_funding=combined_funding,
            projected_net_pnl=None,
            is_complete=True,
        )

    @staticmethod
    def _build_closed_group(
        pair_id: str,
        short_leg: ClosedPositionLeg,
        long_leg: ClosedPositionLeg,
    ) -> ClosedArbitrageGroup:
        net = ArbitragePairingService._net_closed_profit(short_leg, long_leg)
        return ClosedArbitrageGroup(
            pair_id=pair_id,
            symbol=short_leg.symbol,
            short_leg=short_leg,
            long_leg=long_leg,
            combined_net_profit=net,
        )

    @staticmethod
    def _net_closed_profit(
        short_leg: ClosedPositionLeg,
        long_leg: ClosedPositionLeg,
    ) -> float | None:
        parts: list[float] = []
        for leg in (short_leg, long_leg):
            if leg.realized_pnl is not None:
                parts.append(leg.realized_pnl)
            if leg.funding is not None:
                parts.append(leg.funding)
            if leg.commission is not None:
                parts.append(-abs(leg.commission))
        if not parts:
            return None
        return sum(parts)

    @staticmethod
    def _sum_optional(left: float | None, right: float | None) -> float | None:
        if left is None and right is None:
            return None
        return (left or 0.0) + (right or 0.0)

    @staticmethod
    def _consume_open(legs: list[PositionLeg], target: PositionLeg) -> None:
        if target in legs:
            legs.remove(target)

    @staticmethod
    def _consume_closed(legs: list[ClosedPositionLeg], target: ClosedPositionLeg) -> None:
        if target in legs:
            legs.remove(target)
