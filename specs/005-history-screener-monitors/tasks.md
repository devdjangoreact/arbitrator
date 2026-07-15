---
description: "Task list for History Screener & Live Monitors implementation"
---

# Tasks: History Screener & Live Monitors

**Input**: Design documents from `/specs/005-history-screener-monitors/`
**Prerequisites**: plan.md, spec.md
**Status**: Partially Implemented. The backend screener and UI layout are complete. The remaining tasks focus on wiring real-time data and charts to the individual Live Monitoring Cards.

## Format: `[ID] [P?] [Phase] Description`
- **[P]**: Can run in parallel
- **[Phase]**: Which implementation phase this task belongs to

---

## Phase 1: Backend Data & WebSockets (FastAPI + Workers)
**Goal**: High-frequency screener worker and WebSocket pushing table data.
*Status: COMPLETED*

- [x] T001 [Phase 1] Refactor `HistoricalScreenerWorker` to use high-frequency memory buffer (`src/arbitrator/application/market_data/historical_screener_worker.py`).
- [x] T002 [Phase 1] Update opportunity data class to include max exit spread, funding rates, etc.
- [x] T003 [Phase 1] Implement start/stop controls for historical screener process.
- [x] T004 [Phase 1] Update `HistoricalScreenerWsHandler` to push table data every 5 seconds (`src/arbitrator/presentation/ws/historical_screener_ws_handler.py`).

---

## Phase 2: UI Structure (HTML/CSS)
**Goal**: Update "Monitors" tab with History table and Live Card template.
*Status: ALMOST COMPLETE (Missing strict CSS constraint)*

- [x] T005 [Phase 2] Redesign top section in `monitors.html` to match History Screener Table layout (inputs, Start/Stop buttons) (`src/arbitrator/presentation/static/partials/pages/monitors.html`).
- [x] T006 [Phase 2] Update table layout to be collapsible.
- [x] T007 [Phase 2] Update table headers and row template (Symbol, Spread, Exchanges, Funding, Price, Volume).
- [x] T008 [Phase 2] Create hidden HTML template for Live Monitoring Card.
- [x] T009 [Phase 2] Add CSS styling to `.table-scroll` in `app.css` to ensure *exactly* 20 rows are visible before internal scrolling kicks in (`src/arbitrator/presentation/static/css/app.css`).

---

## Phase 3: Frontend Logic (JavaScript)
**Goal**: Connect UI to WebSockets, handle user interactions, and render real-time charts/data.
*Status: IN PROGRESS (History Table logic is done; Live Card real-time logic is missing)*

- [x] T010 [Phase 3] Establish WebSocket connection to `historical_screener_ws_handler` in `monitors.js` (`src/arbitrator/presentation/static/js/render/monitors.js`).
- [x] T011 [Phase 3] Send filter parameters and Start/Stop commands from UI.
- [x] T012 [Phase 3] Render 5-second updates into the history table.
- [x] T013 [Phase 3] Implement `Copy to Form` interaction logic (clone template, populate static config, append to grid).
- [x] T014 [Phase 3] Implement `Fast Trade` interaction logic (clone template, append to grid).
- [x] T015 [P] [Phase 3] Establish WebSocket connection to `screener_ws_handler` for **each** active card to receive real-time ticker and orderbook updates (`src/arbitrator/presentation/static/js/render/monitors.js`).
- [x] T016 [P] [Phase 3] Update card UI with real-time data: Ask, Bid, Size, Leverage, Price, P/L, Realized PNL, current spread (`src/arbitrator/presentation/static/js/render/monitors.js`).
- [x] T017 [P] [Phase 3] Integrate `opportunity_chart.js` (or similar logic) to draw real-time line charts (Open Spread & Close Spread) on the `<canvas>` for each active card.
- [x] T018 [Phase 3] Implement UI visual feedback for `T` logic (tick confirmation countdown) when spread conditions are met.

---

## Phase 4: Testing & Integration
**Goal**: Ensure data flows correctly from backend to UI cards.

- [x] T019 [Phase 4] Create `pytest` cases for high-frequency screener logic (`tests/unit/test_historical_screener.py`).
- [ ] T020 [Phase 4] Integration Verification: Run `scripts/build_ui.py` and verify table limits visibility to ~20 rows.
- [ ] T021 [Phase 4] Integration Verification: Verify that "Fast Trade" correctly spawns a card, initiates live data flow, and populates the chart.