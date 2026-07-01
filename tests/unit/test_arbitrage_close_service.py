from __future__ import annotations

from datetime import UTC, datetime

from tests.unit.test_arbitrage_open_service import _RecordingGateway, _StubFactory

from arbitrator.application.arbitrage_close_service import ArbitrageCloseService
from arbitrator.domain.arbitrage_pair import ArbitragePair
from arbitrator.domain.position_leg import PositionLeg


def _pair() -> ArbitragePair:
    short = PositionLeg(
        exchange_id="mexc",
        display_name="MEXC",
        symbol="BTC/USDT:USDT",
        side="short",
        contracts=1.0,
        contract_size=1.0,
        entry_price=100.0,
        mark_price=100.0,
        opened_at=datetime.now(UTC),
        unrealized_pnl=0.0,
        accrued_funding=0.0,
        opening_fee=0.0,
        estimated_close_fee=0.0,
        next_funding_at=None,
        arb_marker_id="p1",
        position_id="1",
    )
    long = short.model_copy(
        update={"exchange_id": "bitget", "display_name": "Bitget", "side": "long"},
    )
    return ArbitragePair(
        pair_id="p1",
        symbol="BTC/USDT:USDT",
        short_leg=short,
        long_leg=long,
        combined_unrealized_pnl=0.0,
        combined_accrued_funding=0.0,
        projected_net_pnl=None,
        is_complete=True,
    )


class _CloseGateway(_RecordingGateway):
    def __init__(self, exchange_id: str, display_name: str) -> None:
        super().__init__(exchange_id, display_name)
        self.close_calls: list[PositionLeg] = []

    async def close_market_position(self, leg: PositionLeg) -> str:
        self.close_calls.append(leg)
        return "close-1"


def test_close_pair_closes_both_legs() -> None:
    short_gw = _CloseGateway("mexc", "MEXC")
    long_gw = _CloseGateway("bitget", "Bitget")
    factory = _StubFactory(short_gw, long_gw)
    service = ArbitrageCloseService(factory)  # type: ignore[arg-type]
    result = service.close_pair_sync(_pair())
    assert result.all_success is True
    assert len(short_gw.close_calls) == 1
    assert len(long_gw.close_calls) == 1
