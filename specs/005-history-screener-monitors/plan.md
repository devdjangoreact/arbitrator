# Implementation Plan: History Screener & Live Monitors

## Phase 1: Backend Data & WebSockets (FastAPI + Workers)
1. **Screener Worker Updates (`src/arbitrator/application/market_data/historical_screener_worker.py`):**
   - Refactor from minutes-based OHLCV polling to a continuous or high-frequency (5s) memory buffer for evaluating spreads over a rolling window of N seconds.
   - Update the `HistoricalOpportunity` (or create `MonitorScreenerOpportunity`) to include: current spread, max exit spread, exchange details, funding rates, next funding time, current prices, and volume.
   - Introduce start/stop controls for this specific monitoring process (via WebSocket commands or REST).
2. **WebSocket Handlers (`src/arbitrator/presentation/ws/historical_screener_ws_handler.py`):**
   - Update to push table data every 5 seconds.
   - Ensure it can receive filter parameter updates (min spread, lookback seconds, min volume) dynamically.

## Phase 2: UI Structure (HTML/CSS)
1. **Update `monitors.html` Partial (`src/arbitrator/presentation/static/partials/pages/monitors.html`):**
   - Redesign the top section to match the "History Screener Table" layout. Add inputs for "Time Window (seconds)", "Min Spread %", and "Min 24h Vol".
   - Add "Start Monitoring" and "Stop Monitoring" buttons.
   - Update the table layout to be collapsible (already partially implemented, ensure toggle works).
   - Add CSS styling to the table container (`.table-scroll`) to ensure exactly 20 rows are visible before internal scrolling kicks in (using CSS `max-height` or viewport calculations).
   - Ensure the main page container has normal scrolling behavior so an unlimited number of Live Cards can be added below the table.
   - Update the table headers and row template to include: Symbol, Spread (Δ current -> exit max), Exchanges, Funding Rate, Next Funding, Funding Spread, Price, Volume USDT, and Actions (`Copy to Form`, `Fast Trade`).
2. **Create Live Monitoring Card Template:**
   - Create a hidden HTML template or JS structure for the Live Monitoring Card.
   - Include UI inputs for Side, Open/Close Spread (with T), Order Size, Max Orders, Force Stop, Total Stop, and Exchange-specific data (Ask, Bid, Funding, Leverage).
   - Add a canvas for the real-time spread chart.

## Phase 3: Frontend Logic (JavaScript)
1. **History Screener Logic:**
   - Establish a WebSocket connection to `historical_screener_ws_handler`.
   - Send filter parameters (Time Window, Min Spread, Vol) and commands (Start/Stop).
   - Render the incoming 5-second updates into the table. Allow unlimited rows internally, relying on CSS for the 20-row visible limit constraint.
2. **Card Interaction Logic (`Copy to Form` & `Fast Trade`):**
   - `Copy to Form`: Clone the template, populate initial symbol/exchange data, and append to the grid without starting the stream.
   - `Fast Trade`: Clone the template, append, and automatically invoke the connection/start logic for that symbol's live data.
3. **Card WebSocket & Charting:**
   - For each active card, establish a connection to `screener_ws_handler` to receive real-time ticker and orderbook updates.
   - Implement the `T` logic (tick confirmation) on the frontend for visual feedback (though execution logic should reside in the backend strategy engine).
   - Feed real-time spread data into the chart instance for that card.

## Phase 4: Testing & Integration
1. **Backend Tests:**
   - Create/update `pytest` cases in `tests/` verifying the new high-frequency screener logic and the extraction of current vs max spread.
2. **Integration Verification:**
   - Run `scripts/build_ui.py`.
   - Verify that the table correctly limits visibility to ~20 rows with internal scrolling, and the main page scrolls for cards.
   - Verify that clicking "Fast Trade" correctly spawns a card and initiates data flow.
