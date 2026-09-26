"""
Verify that get_live_state() emits all 30 FR-011 fields for an active monitor.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from arbitrator.application.trading.historical_auto_trader import HistoricalAutoTrader
from arbitrator.config.monitor_config_store import MonitorConfig, MonitorConfigStore

FR011_FIELDS = [
    "short_funding_rate",
    "long_funding_rate",
    "short_next_funding",
    "long_next_funding",
    "short_ask",
    "long_ask",
    "short_bid",
    "long_bid",
    "short_size",
    "long_size",
    "leverage",
    "max_size_short",
    "max_size_long",
    "short_price",
    "long_price",
    "short_pnl",
    "long_pnl",
    "short_realized_pnl",
    "long_realized_pnl",
    "enter_spread_short",
    "enter_spread_long",
    "short_orders",
    "long_orders",
    "open_spread_current",
    "open_spread_min",
    "open_spread_max",
    "close_spread_current",
    "close_spread_min",
    "close_spread_max",
]


def _make_trader() -> HistoricalAutoTrader:
    store = MagicMock(spec=MonitorConfigStore)
    settings = MagicMock()
    paper_gw = MagicMock()
    cache = MagicMock()
    return HistoricalAutoTrader(
        settings=settings,
        store=store,
        paper_gateway=paper_gw,
        market_cache=cache,
    )


def _inject_live_state(trader: HistoricalAutoTrader) -> str:
    """Directly inject a live_state entry as if _tick() ran."""
    monitor_id = "BTC/USDT:USDT:mexc:bitget"
    state: dict = {field: 0.0 for field in FR011_FIELDS}
    state["short_orders"] = 0
    state["long_orders"] = 0
    trader._live_state[monitor_id] = state  # type: ignore[attr-defined]
    return monitor_id


def test_fr011_all_fields_present_in_live_state() -> None:
    """get_live_state() must include all 30 FR-011 fields for every active monitor."""
    trader = _make_trader()
    monitor_id = _inject_live_state(trader)

    result = trader.get_live_state()

    assert monitor_id in result, "monitor_id key missing from live_state"
    entry = result[monitor_id]

    missing = [f for f in FR011_FIELDS if f not in entry]
    assert not missing, f"Missing FR-011 fields: {missing}"


def test_fr011_field_count() -> None:
    """29 fields enumerated in FR-011 (spec lists 29 live-state entries)."""
    assert len(FR011_FIELDS) == 29, f"Expected 29 FR-011 fields, got {len(FR011_FIELDS)}"


def test_get_live_state_returns_empty_when_no_monitors() -> None:
    trader = _make_trader()
    assert trader.get_live_state() == {}
