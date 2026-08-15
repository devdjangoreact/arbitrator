from __future__ import annotations

from arbitrator_2.connector.connector_settings import ConnectorSettings
from arbitrator_2.connector.venue_registry import build_default_adapters, enabled_venues


def test_adapters_follow_enabled_exchanges() -> None:
    settings = ConnectorSettings(enabled_exchanges=["binance", "gate"])
    adapters = build_default_adapters(settings)
    assert [a.venue_id for a in adapters] == ["binance", "gate"]
    assert enabled_venues(settings) == ("binance", "gate")
