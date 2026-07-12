# Spec: History Screener & Live Monitors

## 1. Overview
The goal is to update the "Monitors" tab to include two primary components:
1. **History Screener Table (Top):** A table displaying filtered tokens where the spread between two exchanges exceeded a specified parameter over a given time window. The table updates at least every 5 seconds.
2. **Live Monitoring Cards (Bottom):** Cards that provide real-time monitoring and automated trading (Futures-Futures strategy) based on specific spread parameters.
*Note: The entire page will be scrollable to accommodate any number of generated Live Monitoring Cards.*

## 2. History Screener Table (Top)

### 2.1 Filters & Controls
- **Spread Filter:** Minimum spread percentage.
- **Time Window Filter:** Number of seconds to look back for the spread condition.
- **Volume Filter:** Minimum 24-hour volume.
- **Commands:** "Start Monitoring" and "Stop Monitoring" to begin/halt the background screener process. The process fetches and updates the table every 5 seconds.

### 2.2 Table Display
- **Layout:** The table container should be collapsible/expandable.
- **Capacity & Scrolling:** The UI should visibly display up to 20 rows at a time. An internal scrollbar allows scrolling through an unlimited number of rows that meet the filter criteria.
- **Sorting:** Sorted by spread (descending) and applied filters.
- **Row Data (per symbol/exchange pair):**
  - **Symbol:** Token name (e.g., GUA) + Spread Delta (e.g., Δ: 1.5% -> exit 2.12%) + Mini Sparkline + Settings icon. 
    - *Note:* The "exit 2.12%" is the maximum spread value recorded during the period, while "1.5%" is the current spread.
  - **Exchanges:** Exchange 1 (e.g., BINANCE ↓) and Exchange 2 (e.g., GATEIO ↑).
  - **Funding Rate:** Current funding rate for each exchange.
  - **Next Funding:** Time until the next funding event for each exchange.
  - **Funding Spread:** Difference in funding rates between the two exchanges.
  - **Price:** Current price on each exchange.
  - **Volume USDT:** 24-hour volume on each exchange.
  - **Actions:**
    - `Copy to Form`: Opens a Live Monitoring Card WITHOUT starting the live monitoring stream automatically.
    - `Fast Trade`: Opens a Live Monitoring Card AND immediately starts the live monitoring/trading stream for the symbol (simulates clicking "Start" on the card).

## 3. Live Monitoring Card (Bottom)

When a card is opened via the table actions, it provides live tracking and execution for a specific symbol/pair.
Strategy: **Futures-Futures** (trading perp vs perp).

### 3.1 Card Parameters
- **Side:** `Auto` (automatically decides Long/Short based on conditions), `LONG`, or `SHORT`.
- **Open Spread:** Target spread to open a position. Includes a tolerance/threshold (`T`).
  - *Note:* `T` represents the number of consecutive ticks the spread condition must be confirmed before a decision to open/close is made.
- **Close Spread:** Target spread to close a position. Includes a tolerance/threshold (`T`).
- **Order Size:** Size of the order in base currency and its USDT equivalent.
- **Max Orders:** Maximum number of separate orders/grids allowed. 
  - *Note:* If set to `0`, it means unlimited grid orders until the `Allowed size` limit is reached.
- **Allowed Size:** Current accumulated size / Maximum allowed size.
- **Force Stop:** Checkbox to force close/stop the strategy immediately.
- **Total Stop:** Checkbox to stop the strategy based on a global condition.
- **Status Controls:** `Start`, `Stop`, `Restart` buttons.

### 3.2 Live Exchange Data (Per Exchange)
- **Funding rate & Next Funding:** Real-time funding data.
- **Ask / Bid:** Real-time orderbook top levels.
- **Size:** Orderbook size at the top level.
- **Leverage:** Configurable leverage (e.g., 10x cross), with an adjustment notification setting (Notify only / Adjust).
- **Max size / Price / P/L / Realized PNL / Enter spread / Orders:** Execution and position statistics.

### 3.3 Spread Tracking & Visualization
- **Live Spread Display:** Shows real-time `Open spread` (Current, Min, Max) and `Close spread` (Current, Min, Max).
- **Live Chart:** A real-time line chart plotting the open spread and close spread dynamically over time.

## 4. Testing
- Write tests for UI components and data flow, especially for the interaction between the history screener row buttons (`Copy to Form` / `Fast Trade`) and the dynamic creation of Live Monitoring Cards.

