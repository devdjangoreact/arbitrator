"""E2E: React UI Parity & Stability

Ensures the new React UI loads without crashing, navigates correctly,
and maintains parity with expected elements.

Run with:
    python -m pytest tests/e2e/test_009_react_ui_parity.py -v
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

@pytest.fixture
def page(browser_context, app_server):  # type: ignore[no-untyped-def]
    p = browser_context.new_page()

    # We fail the test if the React app crashes and throws an unhandled exception
    errors = []
    p.on("pageerror", lambda err: errors.append(err.message))

    yield p

    if errors:
        pytest.fail(f"React UI crashed with errors: {errors}")
    p.close()

def test_react_ui_stability_and_navigation(page: Page) -> None:
    # Go to root (React UI)
    page.goto("http://127.0.0.1:8000/")

    # Give it a moment to load and connect WS
    page.wait_for_timeout(2000)

    # We should be on Screener by default
    expect(page.locator("text=Live Screener")).to_be_visible()
    expect(page.locator("text=Asset").first).to_be_visible()

    # Navigate to Settings
    page.click("text=Налаштування")
    page.wait_for_timeout(500)
    expect(page.locator("text=Біржі").first).to_be_visible()
    expect(page.locator("text=Live Auto-Trade").first).to_be_visible()

    # Navigate to Monitors
    page.click("text=Історія Скрінера")
    page.wait_for_timeout(500)
    expect(page.locator("text=Time Window (seconds)")).to_be_visible()
    expect(page.locator("text=Active Monitors")).to_be_visible()

    # Navigate to Opportunity
    page.click("text=Opportunity")
    page.wait_for_timeout(500)
    expect(page.locator("text=Trading Actions")).to_be_visible()
    expect(page.locator("text=Strategy Calculations")).to_be_visible()

    # Navigate to Orders
    page.click("text=Ордери")
    page.wait_for_timeout(500)
    expect(page.locator("text=Orders & Paper Trades")).to_be_visible()
    expect(page.locator("text=Total PnL")).to_be_visible()
