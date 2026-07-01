from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tests.unit.test_arbitrage_open_service import _RecordingGateway, _StubFactory

from arbitrator.application.arbitrage_close_service import ArbitrageCloseService
from arbitrator.application.arbitrage_open_service import ArbitrageOpenService
from arbitrator.application.opportunity_accumulate_service import OpportunityAccumulateService
from arbitrator.config.json_arb_markers_repository import JsonArbMarkersRepository
from arbitrator.config.settings import Settings
from arbitrator.domain.arbitrage_pair import ArbitragePair
from arbitrator.domain.opportunity_controls import OpportunityControls
from arbitrator.domain.opportunity_view import OpportunityView
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.domain.spread_calculator import SpreadCalculator


def test_open_with_notional_uses_custom_size(tmp_path: Path) -> None:
    settings = Settings(
        arb_markers_path=tmp_path / "markers.json",
        arb_default_notional_usdt=100.0,
    )
    short_gw = _RecordingGateway("mexc", "MEXC")
    long_gw = _RecordingGateway("bitget", "Bitget")
    factory = _StubFactory(short_gw, long_gw)
    repo = JsonArbMarkersRepository(settings.arb_markers_path)
    service = ArbitrageOpenService(settings, factory, repo)  # type: ignore[arg-type]
    snapshot = SpreadCalculator.compute(
        "BTC/USDT:USDT",
        {"mexc": 105.0, "bitget": 100.0},
    )
    result = service.open_with_notional_sync(snapshot, 250.0)
    assert result.success is True
    assert long_gw.calls[0][2] == 2.5


def test_accumulate_service_respects_max_notional(tmp_path: Path) -> None:
    settings = Settings(
        arb_markers_path=tmp_path / "markers.json",
        opp_default_max_notional_usdt=500.0,
        opp_accumulate_step_usdt=100.0,
    )
    short_gw = _RecordingGateway("mexc", "MEXC")
    long_gw = _RecordingGateway("bitget", "Bitget")
    factory = _StubFactory(short_gw, long_gw)
    repo = JsonArbMarkersRepository(settings.arb_markers_path)
    open_service = ArbitrageOpenService(settings, factory, repo)  # type: ignore[arg-type]
    accumulate = OpportunityAccumulateService(settings, open_service)
    controls = OpportunityControls(
        accumulate_spread_threshold_pct=1.0,
        max_notional_usdt=100.0,
        leverage=10,
        min_close_spread_pct=0.1,
    )
    view = OpportunityView(
        symbol="BTC/USDT:USDT",
        short_exchange_id="mexc",
        long_exchange_id="bitget",
    )
    snapshot = SpreadCalculator.compute(
        "BTC/USDT:USDT",
        {"mexc": 105.0, "bitget": 100.0},
    )
    suggestion = accumulate.suggest_notional(controls, None, None, 100.0)
    assert suggestion.allowed is True
    assert suggestion.notional_usdt == 100.0
    blocked = accumulate.accumulate(
        view,
        controls,
        snapshot,
        150.0,
        None,
        None,
        100.0,
    )
    assert blocked.success is False


def test_close_pair_partial_reduces_contracts() -> None:
    short = PositionLeg(
        exchange_id="mexc",
        display_name="MEXC",
        symbol="BTC/USDT:USDT",
        side="short",
        contracts=2.0,
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
    pair = ArbitragePair(
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

    short_close = _CloseGateway("mexc", "MEXC")
    long_close = _CloseGateway("bitget", "Bitget")
    factory = _StubFactory(short_close, long_close)
    service = ArbitrageCloseService(factory)  # type: ignore[arg-type]
    result = service.close_pair_partial_sync(pair, 50.0)
    assert result.all_success is True
    assert short_close.close_calls[0].contracts == 1.0
    assert long_close.close_calls[0].contracts == 1.0
