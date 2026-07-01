from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.helpers import make_leg

from arbitrator.application.arbitrage_pairing_service import ArbitragePairingService
from arbitrator.config.json_arb_markers_repository import JsonArbMarkersRepository
from arbitrator.config.settings import Settings
from arbitrator.domain.arb_marker_record import ArbMarkerRecord


def test_pair_by_heuristic(tmp_path: object) -> None:
    from pathlib import Path

    settings = Settings(arb_markers_path=Path(str(tmp_path)) / "markers.json")
    repo = JsonArbMarkersRepository(settings.arb_markers_path)
    service = ArbitragePairingService(settings, repo)
    opened = datetime.now(UTC)
    legs = [
        make_leg(exchange_id="mexc", side="short", opened_at=opened),
        make_leg(exchange_id="bitget", side="long", opened_at=opened + timedelta(seconds=30)),
    ]
    grouped = service.group_open(legs)
    assert len(grouped.pairs) == 1
    assert grouped.pairs[0].short_leg.side == "short"
    assert grouped.pairs[0].long_leg.side == "long"
    assert len(grouped.ungrouped) == 0


def test_pair_by_marker(tmp_path: object) -> None:
    from pathlib import Path

    settings = Settings(arb_markers_path=Path(str(tmp_path)) / "markers.json")
    repo = JsonArbMarkersRepository(settings.arb_markers_path)
    repo.append(
        ArbMarkerRecord(
            pair_id="abc123",
            symbol="BTC/USDT:USDT",
            short_exchange_id="mexc",
            long_exchange_id="bitget",
            short_client_order_id="ARB-abc123-S",
            long_client_order_id="ARB-abc123-L",
            opened_at=datetime.now(UTC),
        )
    )
    service = ArbitragePairingService(settings, repo)
    legs = [
        make_leg(exchange_id="mexc", side="short", marker="abc123"),
        make_leg(exchange_id="bitget", side="long", marker="abc123"),
    ]
    grouped = service.group_open(legs)
    assert len(grouped.pairs) == 1
    assert grouped.pairs[0].pair_id == "abc123"
