"""E2E: Screener page loads, shows rows, WS connects.

Run with:
    .venv\\Scripts\\python.exe -m pytest tests/e2e/ -v --timeout=30
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def page(browser_context, app_server):  # type: ignore[no-untyped-def]
    p = browser_context.new_page()
    p.on("console", lambda msg: print(f"Browser console [{msg.type}]: {msg.text}"))
    p.on("pageerror", lambda err: print(f"Browser error: {err}"))
    yield p
    p.close()


def test_screener_page_loads(page: Page, app_server: str) -> None:
    """App serves index.html at /."""
    page.goto(app_server)
    expect(page).to_have_title("Arbitrator")
    # React mounts and shows "Screener" heading
    expect(page.locator("h1").filter(has_text="Screener")).to_be_visible()


def test_screener_has_rows(page: Page, app_server: str) -> None:
    """Screener table must have at least one row after WS snapshot arrives."""
    page.goto(app_server)

    # Wait for the "Connected" badge (or no "Connecting..." badge)
    expect(page.locator("text=Connecting...")).to_be_hidden(timeout=10000)

    # Wait for the table rows to appear. In our DataTable, rows are inside tbody.
    # We skip the empty message row.
    try:
        # Wait for a table row that is NOT the empty message
        page.wait_for_selector("tbody tr:not(:has-text('Waiting for data stream...')):not(:has-text('No opportunities'))", timeout=10_000)
    except Exception:
        page.screenshot(path="screener_failed.png")
        raise

    rows = page.locator("tbody tr").all()
    assert len(rows) > 0, "Expected at least one screener row"


def test_screener_shows_spread(page: Page, app_server: str) -> None:
    """Each screener row must have a non-empty spread value."""
    page.goto(app_server)

    # Wait for rows
    page.wait_for_selector("tbody tr:not(:has-text('Waiting for data stream...'))", timeout=10_000)
    first_row = page.locator("tbody tr").first

    # In the new Screener React table, spread is a column with class 'text-right font-bold'
    # Or we can just look for the '%' sign
    spread_cell = first_row.locator("td").filter(has_text="%").first

    text = (spread_cell.inner_text() or "").strip()
    assert text not in ("", "—"), f"Spread cell is empty: {text!r}"


def test_health_endpoint(page: Page, app_server: str) -> None:
    """GET /health returns JSON with status=ok."""
    response = page.request.get(f"{app_server}/health")
    assert response.status == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "ui_data_mode" in data
