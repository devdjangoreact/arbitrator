"""E2E: Opportunity page — navigate, check exchange cards, simulate paper trade via WS.

Run with:
    .venv\\Scripts\\python.exe -m pytest tests/e2e/test_opportunity_paper.py -v --timeout=30
"""
from __future__ import annotations

import asyncio
import json

import pytest
import websockets  # type: ignore[import]
from playwright.sync_api import Page, expect


APP_WS = "ws://127.0.0.1:8000"
MOCK_SYMBOL = "DOGE"
MOCK_SHORT = "mexc"
MOCK_LONG = "bingx"


@pytest.fixture
def page(browser_context, app_server):  # type: ignore[no-untyped-def]
    p = browser_context.new_page()
    yield p
    p.close()


def test_opportunity_page_loads(page: Page, app_server: str) -> None:
    """Navigate to opportunity page via screener row click or direct URL."""
    page.goto(app_server)
    page.wait_for_selector("#screenerTable tbody tr", timeout=10_000)
    # click first row to navigate to opportunity page
    first_row = page.query_selector("#screenerTable tbody tr")
    if first_row:
        first_row.click()
    else:
        # direct nav fallback
        page.evaluate(
            "window.location.hash = '#opportunity?symbol=DOGE&short=mexc&long=bingx'"
        )
    # wait for opportunity page section
    opp = page.wait_for_selector(
        "#opportunityPage, [data-page='opportunity'], .strategy-table",
        timeout=10_000,
        state="visible",
    )
    assert opp is not None, "Opportunity page section not visible"


def test_opportunity_ws_snapshot(app_server: str) -> None:
    """WS /ws/opportunity sends a snapshot within 5 seconds."""

    async def _run() -> dict[str, object]:
        uri = (
            f"{APP_WS}/ws/opportunity"
            f"?symbol={MOCK_SYMBOL}&short={MOCK_SHORT}&long={MOCK_LONG}"
        )
        async with websockets.connect(uri) as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            return json.loads(raw)  # type: ignore[return-value]

    msg = asyncio.run(_run())
    assert msg.get("type") == "opportunity.snapshot", f"Got: {msg.get('type')}"
    payload = msg.get("payload", {})
    assert "strategy_rows" in payload, "snapshot missing strategy_rows"
    assert "exchange_cards" in payload, "snapshot missing exchange_cards"


def test_opportunity_ws_set_params(app_server: str) -> None:
    """WS accepts opportunity.set_params and returns action_result."""

    async def _run() -> dict[str, object]:
        uri = (
            f"{APP_WS}/ws/opportunity"
            f"?symbol={MOCK_SYMBOL}&short={MOCK_SHORT}&long={MOCK_LONG}"
        )
        async with websockets.connect(uri) as ws:
            # consume initial snapshot
            await asyncio.wait_for(ws.recv(), timeout=5.0)
            # send set_params command
            cmd = {
                "type": "opportunity.set_params",
                "payload": {
                    "active_strategy_id": "futures_futures",
                    "target_volume_usdt": 300.0,
                    "open_spread_threshold_pct": 0.5,
                    "close_spread_threshold_pct": 0.05,
                },
            }
            await ws.send(json.dumps(cmd))
            # read until we get action_result
            for _ in range(10):
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                msg = json.loads(raw)
                if msg.get("type") == "opportunity.action_result":
                    return msg
        return {}

    msg = asyncio.run(_run())
    assert msg.get("type") == "opportunity.action_result", f"No action_result, got: {msg}"
    assert msg["payload"]["success"] is True  # type: ignore[index]


def test_opportunity_ws_accumulate_mock(app_server: str) -> None:
    """In mock_data mode, accumulate command is accepted and returns action_result."""

    async def _run() -> dict[str, object]:
        uri = (
            f"{APP_WS}/ws/opportunity"
            f"?symbol={MOCK_SYMBOL}&short={MOCK_SHORT}&long={MOCK_LONG}"
        )
        async with websockets.connect(uri) as ws:
            await asyncio.wait_for(ws.recv(), timeout=5.0)  # snapshot
            await ws.send(
                json.dumps(
                    {
                        "type": "opportunity.accumulate",
                        "payload": {"volume_usdt": 100.0},
                    }
                )
            )
            for _ in range(10):
                raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                msg = json.loads(raw)
                if msg.get("type") == "opportunity.action_result":
                    return msg
        return {}

    msg = asyncio.run(_run())
    assert msg.get("type") == "opportunity.action_result"


def test_orders_ws_snapshot(app_server: str) -> None:
    """WS /ws/orders sends orders.snapshot."""

    async def _run() -> dict[str, object]:
        async with websockets.connect(f"{APP_WS}/ws/orders") as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            return json.loads(raw)  # type: ignore[return-value]

    msg = asyncio.run(_run())
    assert msg.get("type") == "orders.snapshot", f"Got: {msg.get('type')}"
    payload = msg.get("payload", {})
    assert "summary" in payload


def test_screener_ws_snapshot(app_server: str) -> None:
    """WS /ws/screener sends screener.snapshot with rows."""

    async def _run() -> dict[str, object]:
        async with websockets.connect(f"{APP_WS}/ws/screener") as ws:
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            return json.loads(raw)  # type: ignore[return-value]

    msg = asyncio.run(_run())
    assert msg.get("type") == "screener.snapshot"
    payload = msg.get("payload", {})
    assert "rows" in payload
    assert len(payload["rows"]) > 0, "Screener snapshot has no rows"
