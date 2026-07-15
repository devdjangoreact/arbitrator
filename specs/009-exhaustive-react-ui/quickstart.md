# Quickstart & Validation

This guide outlines how to validate the completed Exhaustive React UI Parity feature without needing to deploy the full trading engine.

## Prerequisites

1.  Python 3.11+ environment (`.venv`).
2.  Node.js 18+ and `pnpm` installed.
3.  Playwright browsers installed (for visual validation).

## Scenario 1: Formatting Parity Validation

**Goal:** Ensure the `utils/format.ts` logic exactly matches the static UI.

1.  Run the frontend unit tests specifically for formatting:
    ```bash
    cd src/arbitrator/presentation/react-ui
    pnpm test format.test.ts
    ```
2.  **Expected Outcome:** All tests pass, validating rules like `fmtNum(null) === "—"`, `fmtPnl(1.2) === "+1.20"`, and `compactK(1500000) === "1.50M"`.

## Scenario 2: UI Visual Parity (Playwright)

**Goal:** Verify the React UI visually matches the static UI using Playwright.

1.  Ensure the backend is running and serving the *legacy* UI on port 8000.
2.  Start the new React UI development server on a different port (e.g., 5173).
3.  Run the visual regression test suite:
    ```bash
    cd src/arbitrator/presentation/react-ui
    npx playwright test visual-parity.spec.ts
    ```
4.  **Expected Outcome:** The tests navigate to both `/` (legacy) and `localhost:5173` (React), take screenshots of specific tables and cards (e.g., the `LiveMonitorCard`), and compare them. The pixel difference must be below the configured threshold.

## Scenario 3: Real-time Component Interaction

**Goal:** Verify interactive elements like "Copy to Form" and "Fast Trade" work.

1.  Start the backend with mock data enabled (refer to backend docs for mock flag).
2.  Open the React UI Monitors page (`/monitors`).
3.  Click "Copy to Form" on an item in the Historical Screener table.
4.  **Expected Outcome:** The inputs in the corresponding Live Monitor Card populate with the selected opportunity's data.
5.  Click "Fast Trade" on another item.
6.  **Expected Outcome:** A new Live Monitor Card appears immediately, and a WebSocket message (`cmd: "update_config"`) is visible in the browser's Network tab containing the config.