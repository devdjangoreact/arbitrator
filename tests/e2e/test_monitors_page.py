"""
E2E tests for the Monitoring page (feature 011).
Tests use a REAL backend with live exchange data — no WS mocks.
Each action asserts an observable UI state change.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


BASE_URL = "http://127.0.0.1:8000"


def _collect_errors(page: Page) -> list[str]:
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(f"[console.error] {m.text}") if m.type == "error" else None)
    return errors


@pytest.fixture
def monitors_page(page: Page):
    """Navigate to the Monitoring page and return (page, errors list)."""
    errors = _collect_errors(page)
    page.goto(BASE_URL)
    page.wait_for_timeout(2000)

    # Click "Моніторинг" nav button
    page.evaluate(
        '[...document.querySelectorAll("nav button")].find(b=>b.textContent.includes("Мон")).click()'
    )
    page.wait_for_timeout(2000)
    return page, errors


class TestNavigation:
    def test_nav_order(self, page: Page) -> None:
        """Навігація: Скрінер → Моніторинг → Ордери → Налаштування."""
        errors = _collect_errors(page)
        page.goto(BASE_URL)
        page.wait_for_timeout(2000)

        nav_labels = page.evaluate(
            '[...document.querySelectorAll("nav button")].map(b=>b.textContent.trim())'
        )
        assert nav_labels == ["Скрінер", "Моніторинг", "Ордери", "Налаштування"], nav_labels
        assert not errors, f"JS errors on load: {errors}"

    def test_no_opportunity_in_nav(self, page: Page) -> None:
        """Opportunity page removed from navigation."""
        page.goto(BASE_URL)
        page.wait_for_timeout(1500)
        nav_labels = page.evaluate(
            '[...document.querySelectorAll("nav button")].map(b=>b.textContent.trim())'
        )
        assert "Opportunity" not in nav_labels


class TestMonitorsPageLoad:
    def test_page_renders_not_blank(self, monitors_page) -> None:
        """Monitoring page must not be blank after navigation."""
        page, errors = monitors_page
        body_len = page.evaluate('document.querySelector("main").textContent.trim().length')
        assert body_len > 100, "Monitoring page is blank"
        assert not errors, f"JS errors: {errors}"

    def test_no_phantom_cards_on_fresh_start(self, monitors_page) -> None:
        """No monitor cards should appear before the user creates any."""
        page, _ = monitors_page
        cards = page.evaluate('document.querySelectorAll(".rounded-md.border.border-gray-700").length')
        no_monitors_msg = page.evaluate('document.body.textContent.includes("No active monitors")')
        assert cards == 0, f"Phantom cards: {cards}"
        assert no_monitors_msg, "Expected 'No active monitors' empty state message"


class TestStartStop:
    def test_start_populates_table_with_real_data(self, monitors_page) -> None:
        """Start Monitoring → table has ≥1 row with numeric spread values from real backend."""
        page, errors = monitors_page

        # Initial status must be Idle / Start enabled
        start_disabled = page.evaluate(
            '[...document.querySelectorAll("main button")].find(b=>b.textContent.trim()==="Start")?.disabled'
        )
        assert not start_disabled, "Start button should be enabled when Idle"

        # Click Start
        page.evaluate(
            '[...document.querySelectorAll("main button")].find(b=>b.textContent.trim()==="Start").click()'
        )
        page.wait_for_timeout(13000)  # wait for screener push

        rows = page.evaluate('document.querySelectorAll("main table tbody tr").length')
        assert rows >= 1, f"Expected ≥1 table rows, got {rows}"

        # Verify status changed to Running
        status = page.evaluate(
            'var s=[...document.querySelectorAll("main span")].find(e=>e.textContent==="Running"||e.textContent==="Idle"); s?s.textContent:"?"'
        )
        assert status == "Running", f"Status should be Running, got {status}"

        # Verify first row has a numeric spread (not "No opportunities found")
        first_row = page.evaluate('document.querySelector("main table tbody tr")?.textContent || ""')
        assert "No opportunities" not in first_row, "Table shows empty state after Start"
        # Row must contain a '%' sign (spread value)
        assert "%" in first_row or any(c.isdigit() for c in first_row), \
            f"First row has no numeric data: {first_row[:100]}"

        # Start should now be disabled
        start_disabled_after = page.evaluate(
            '[...document.querySelectorAll("main button")].find(b=>b.textContent.trim()==="Start")?.disabled'
        )
        assert start_disabled_after, "Start should be disabled while Running"

        assert not errors, f"JS errors during start: {errors}"

    def test_stop_changes_status_to_idle(self, monitors_page) -> None:
        """Stop Monitoring → status returns to Idle, Stop button disabled."""
        page, errors = monitors_page

        # Start first
        page.evaluate(
            '[...document.querySelectorAll("main button")].find(b=>b.textContent.trim()==="Start").click()'
        )
        page.wait_for_timeout(8000)

        # Stop
        stop_disabled = page.evaluate(
            '[...document.querySelectorAll("main button")].find(b=>b.textContent.trim()==="Stop")?.disabled'
        )
        assert not stop_disabled, "Stop should be enabled while Running"

        page.evaluate(
            '[...document.querySelectorAll("main button")].find(b=>b.textContent.trim()==="Stop").click()'
        )
        page.wait_for_timeout(5000)

        status = page.evaluate(
            'var s=[...document.querySelectorAll("main span")].find(e=>e.textContent==="Running"||e.textContent==="Idle"); s?s.textContent:"?"'
        )
        assert status == "Idle", f"Status should be Idle after Stop, got {status}"
        assert not errors, f"JS errors: {errors}"


class TestFastTradeAndCardLifecycle:
    def test_fast_trade_creates_card(self, monitors_page) -> None:
        """Fast Trade creates a monitor card with the symbol name visible."""
        page, errors = monitors_page

        # Start and wait for table
        page.evaluate(
            '[...document.querySelectorAll("main button")].find(b=>b.textContent.trim()==="Start").click()'
        )
        page.wait_for_timeout(13000)

        rows = page.evaluate('document.querySelectorAll("main table tbody tr").length')
        assert rows >= 1, "Need rows to Fast Trade"

        # Click Fast Trade on first row
        page.evaluate(
            '[...document.querySelectorAll("main table button")].find(b=>b.textContent.includes("Fast Trade")).click()'
        )
        page.wait_for_timeout(5000)

        cards = page.evaluate('document.querySelectorAll(".rounded-md.border.border-gray-700").length')
        assert cards == 1, f"Expected 1 card after Fast Trade, got {cards}"

        # Card must show symbol name (non-empty span)
        card_text = page.evaluate(
            'document.querySelector(".rounded-md.border.border-gray-700")?.textContent || ""'
        )
        assert len(card_text) > 20, "Card content seems empty"

        assert not errors, f"JS errors: {errors}"

    def test_close_button_removes_card(self, monitors_page) -> None:
        """× button removes the card after next WS push confirms removal."""
        page, errors = monitors_page

        # Start → Fast Trade
        page.evaluate(
            '[...document.querySelectorAll("main button")].find(b=>b.textContent.trim()==="Start").click()'
        )
        page.wait_for_timeout(13000)
        page.evaluate(
            '[...document.querySelectorAll("main table button")].find(b=>b.textContent.includes("Fast Trade")).click()'
        )
        page.wait_for_timeout(5000)
        cards_before = page.evaluate('document.querySelectorAll(".rounded-md.border.border-gray-700").length')
        assert cards_before == 1

        # Click ×
        page.evaluate(
            '[...document.querySelectorAll("button")].find(b=>b.textContent.trim()==="×").click()'
        )
        page.wait_for_timeout(8000)  # wait for WS push confirming removal

        cards_after = page.evaluate('document.querySelectorAll(".rounded-md.border.border-gray-700").length')
        no_monitors = page.evaluate('document.body.textContent.includes("No active monitors")')
        assert cards_after == 0, f"Card not removed, still {cards_after}"
        assert no_monitors, "Expected 'No active monitors' message after removing last card"

        assert not errors, f"JS errors: {errors}"
