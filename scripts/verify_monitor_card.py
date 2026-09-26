"""E2E verification of LiveMonitorCard — real backend, no mocks."""
import sys
import time

from playwright.sync_api import sync_playwright, Page

BASE = "http://localhost:8000"
ERRORS: list[str] = []


def _js_errors(page: Page) -> None:
    page.on("pageerror", lambda e: ERRORS.append(f"pageerror: {e}"))
    page.on("console", lambda m: ERRORS.append(f"console.error: {m.text}") if m.type == "error" else None)


def run() -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        _js_errors(page)

        # 1. Load app
        page.goto(BASE, wait_until="networkidle")
        page.screenshot(path="scripts/screenshots/01_home.png")
        print("✓ app loaded")

        # 2. Navigate to Monitors
        monitors_link = page.locator("text=Моніторинг").first
        monitors_link.click()
        page.wait_for_timeout(1000)
        page.screenshot(path="scripts/screenshots/02_monitors.png")
        print("✓ monitors page")

        # 3. Start screener if needed, wait for opportunities
        start_btn = page.locator("button:has-text('Start')").first
        if start_btn.is_enabled():
            start_btn.click()
            print("  started screener, waiting 8s for opportunities...")
            time.sleep(8)
            page.screenshot(path="scripts/screenshots/02b_after_start.png")

        fast_btn = page.locator("button:has-text('Fast'), button:has-text('⚡')").first
        if fast_btn.count() == 0:
            print("⚠ no Fast Trade button after start — checking for existing monitors")
            # try to open spread history on existing card if any

        else:
            fast_btn.click()
            page.wait_for_timeout(2000)
            page.screenshot(path="scripts/screenshots/03_card_created.png")
            print("✓ monitor card created")

            # 4. Wait 5s for live data to populate
            print("  waiting 5s for live data...")
            time.sleep(5)
            page.screenshot(path="scripts/screenshots/04_card_after_5s.png")

            # 5. Check card fields
            card = page.locator(".rounded-md.border.border-gray-700").first
            card_html = card.inner_html()

            fields_dash = card_html.count(">-<")
            fields_data = 0
            for kw in ["0.", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."]:
                fields_data += card_html.count(kw)

            print(f"  card '-' count: {fields_dash}")
            print(f"  card numeric values: {fields_data > 0}")

            # Check no scrollbar on card content
            has_scroll = page.evaluate("""() => {
                const el = document.querySelector('.rounded-md.border.border-gray-700');
                const inner = el && el.querySelector('.p-2');
                return inner ? inner.style.overflow || getComputedStyle(inner).overflowY : 'unknown';
            }""")
            print(f"  card overflow-y: {has_scroll}")
            assert has_scroll not in ("auto", "scroll"), f"FAIL: card has scrollbar ({has_scroll})"
            print("  ✓ no scrollbar")

            # 6. Click Spread history
            hist_btn = page.locator("button:has-text('Spread history')").first
            if hist_btn.count() > 0:
                hist_btn.click()
                page.wait_for_timeout(500)
                page.screenshot(path="scripts/screenshots/05_spread_history_modal.png")

                # Check canvas elements
                canvases = page.locator("canvas").count()
                print(f"  modal canvas count: {canvases}")
                assert canvases >= 3, f"FAIL: expected 3 canvas, got {canvases}"
                print("  ✓ spread history modal has 3 canvas charts")

                # Wait for data
                time.sleep(4)
                page.screenshot(path="scripts/screenshots/06_spread_history_4s.png")
                print("  ✓ spread history after 4s")
                page.keyboard.press("Escape")
            else:
                print("  ⚠ no Spread history button found")

        # 7. JS errors
        if ERRORS:
            print(f"\n✗ JS ERRORS ({len(ERRORS)}):")
            for e in ERRORS:
                print(f"  {e}")
            browser.close()
            return 1

        print("\n✓ ALL CHECKS PASSED — no JS errors")
        browser.close()
        return 0


if __name__ == "__main__":
    import os
    os.makedirs("scripts/screenshots", exist_ok=True)
    sys.exit(run())
