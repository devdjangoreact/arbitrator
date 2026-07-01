from __future__ import annotations

from pathlib import Path

from arbitrator.application.arbitrage_open_service import ArbitrageOpenService
from arbitrator.config.json_arb_markers_repository import JsonArbMarkersRepository
from arbitrator.config.settings import Settings
from arbitrator.domain.spread_calculator import SpreadCalculator


class _RecordingGateway:
    def __init__(self, exchange_id: str, display_name: str) -> None:
        self.exchange_id = exchange_id
        self.display_name = display_name
        self.calls: list[tuple[str, str, float, str]] = []

    async def open_market_position(self, symbol, side, amount, client_order_id):  # type: ignore[no-untyped-def]
        self.calls.append((symbol, side, amount, client_order_id))
        return "oid"

    async def close(self) -> None:
        return None


class _StubFactory:
    def __init__(self, short: _RecordingGateway, long: _RecordingGateway) -> None:
        self._map = {short.exchange_id: short, long.exchange_id: long}

    def create(self, exchange_id: str) -> object:
        from arbitrator.domain.named_exchange import NamedExchange

        gateway = self._map[exchange_id]
        return NamedExchange(
            exchange_id=gateway.exchange_id,
            display_name=gateway.display_name,
            gateway=gateway,  # type: ignore[arg-type]
        )


def test_open_service_places_short_and_long(tmp_path: Path) -> None:
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
    result = service.open_from_spread_sync(snapshot)
    assert result.success is True
    assert short_gw.calls[0][1] == "sell"
    assert long_gw.calls[0][1] == "buy"
    assert len(repo.load()) == 1
