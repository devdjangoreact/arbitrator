from __future__ import annotations

from datetime import UTC, datetime

from arbitrator.application.arbitrage_pairing_service import OpenPositionsGrouped
from arbitrator.application.opportunity_registry_service import OpportunityRegistryService
from arbitrator.domain.arbitrage_pair import ArbitragePair
from arbitrator.domain.opportunity_view import OpportunityView
from arbitrator.domain.position_leg import PositionLeg


def _leg(exchange_id: str, side: str) -> PositionLeg:
    return PositionLeg(
        exchange_id=exchange_id,
        display_name=exchange_id,
        symbol="BTC/USDT:USDT",
        side="short" if side == "short" else "long",
        contracts=1.0,
        contract_size=1.0,
        entry_price=100.0,
        mark_price=101.0,
        opened_at=datetime.now(UTC),
        unrealized_pnl=1.0,
        accrued_funding=0.0,
        opening_fee=0.1,
        estimated_close_fee=0.1,
        next_funding_at=None,
        arb_marker_id="pair1",
        position_id="p1",
    )


def test_registry_lists_paired_opportunities() -> None:
    pair = ArbitragePair(
        pair_id="pair1",
        symbol="BTC/USDT:USDT",
        short_leg=_leg("mexc", "short"),
        long_leg=_leg("bitget", "long"),
        combined_unrealized_pnl=2.0,
        combined_accrued_funding=0.0,
        projected_net_pnl=None,
        is_complete=True,
    )
    views = OpportunityRegistryService().list_from_grouped(
        OpenPositionsGrouped(pairs=(pair,), ungrouped=())
    )
    assert len(views) == 1
    assert views[0].short_exchange_id == "mexc"


def test_registry_find_matching() -> None:
    view = OpportunityView(
        symbol="BTC/USDT:USDT",
        short_exchange_id="mexc",
        long_exchange_id="bitget",
    )
    found = OpportunityRegistryService().find_matching([view], view)
    assert found is not None
