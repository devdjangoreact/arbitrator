# Feature Specification: Screener History React UI Parity + Live Monitor Card Full Wiring

**Feature Branch**: `011-screener-monitor-react-wiring`
**Created**: 2026-07-16
**Status**: Draft
**Input**: Bring the existing History Screener backend fully into the React UI with real-time data, replacing all mock/stub values on the Monitors page. Wire all Live Monitor Card fields to live backend data.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Filter and Browse the History Screener Table (Priority: P1)

A trader opens the Monitors page and sees a table of symbols sorted by the largest spread recorded during the configured analysis period. They set a minimum spread threshold, a minimum 24-hour volume, and a minimum analysis-period volume to narrow the list to actionable candidates.

**Why this priority**: The table is the entry point for all trading decisions on this page. Without accurate, live, filtered data it has no operational value.

**Independent Test**: Start the backend screener worker, open the Monitors page. Verify the table populates with live symbols within 10 seconds, sorts by max-period-spread descending, and updates every 5 seconds without user action.

**Acceptance Scenarios**:

1. **Given** the screener worker is running, **When** the Monitors page loads, **Then** the table shows symbols sorted by max-period-spread descending, refreshing automatically every 5 seconds.
2. **Given** the table is populated, **When** the user sets Min Spread % = 2.0 and applies the filter, **Then** only rows where the max-period-spread ≥ 2.0 % remain visible.
3. **Given** the table is populated, **When** the user sets Min 24h Volume = 1 000 000 USDT, **Then** only rows where at least one exchange's 24 h volume ≥ 1 000 000 USDT are shown.
4. **Given** the table is populated, **When** the user sets Min Analysis-Period Volume and applies the filter, **Then** only rows meeting that volume over the analysis window are shown.
5. **Given** the screener is stopped, **When** the user clicks "Start Monitoring", **Then** the worker starts and the table begins updating; clicking "Stop Monitoring" halts updates.
6. **Given** the user changes the Analysis Period from 1800 s to 900 s, **When** the filter is applied, **Then** the table re-sorts based on max-spread over the new 900 s window.

---

### User Story 2 — Open a Live Monitor Card from the Table (Priority: P1)

A trader spots a symbol with a high spread and clicks "Fast Trade" (or "Copy to Form") to create a Live Monitor Card pre-filled with that symbol's data.

**Why this priority**: The table drives card creation; without this flow the screener table is read-only.

**Acceptance Scenarios**:

1. **Given** a table row exists, **When** "Fast Trade" is clicked, **Then** a new Live Monitor Card appears below the table, pre-filled with the correct symbol, short exchange, and long exchange; the strategy starts automatically.
2. **Given** a table row exists, **When** "Copy to Form" is clicked, **Then** a new Live Monitor Card appears pre-filled but NOT started — the user must click Start manually.

---

### User Story 3 — Live Monitor Card Displays Real-Time Exchange Data (Priority: P1)

A trader watches an active Live Monitor Card. Every field — funding rates, ask/bid/size, leverage, P/L, realized PNL, open/close spread, order counts — reflects live data from the exchange. A chart plots open and close spread over time.

**Why this priority**: The card currently shows hardcoded placeholders; it must show live data to have any trading utility.

**Acceptance Scenarios**:

1. **Given** a card is active, **When** a new data push arrives from the backend, **Then** all exchange-data fields (funding rate, next funding, ask, bid, size, max size, price, P/L, realized PNL, enter spread, orders) update without a page reload.
2. **Given** a card is active, **When** the open spread changes, **Then** the chart adds a new data point for both open spread and close spread lines within the same update cycle.
3. **Given** a card shows live data but `live_state` for a field is absent or null, **Then** that field renders as "—" rather than crashing or showing a raw `undefined`.
4. **Given** a card is active, **When** the user edits a strategy parameter (e.g. Open Spread %, Order Size) and confirms, **Then** the change is sent to the backend and persists after the next push.
5. **Given** a card is active, **When** the user clicks "Stop", **Then** the backend halts monitoring and trading for that symbol, and the card reflects the stopped state.

---

### Edge Cases

- WebSocket disconnects mid-session: the connection reconnects automatically; cards do not freeze on stale values.
- Duplicate monitor attempt for the same symbol+exchange pair: backend rejects `add_monitor`; UI shows a warning and does not create a second card. The same symbol on a different exchange pair (e.g. BP on GATE–MEXC and BP on BITGET–MEXC) is allowed — each is a separate monitor instance.
- Analysis-period volume data is unavailable from the backend: the filter field is visible but disabled with a tooltip explaining it requires a backend update; the rest of the table works normally.
- Screener returns zero results matching the active filters: the table shows an empty-state message rather than a blank area.
- A monitor card is removed while a data push is in flight: the update is silently dropped; no error appears.

## Requirements *(mandatory)*

### Functional Requirements

**History Screener Table**

- **FR-001**: Table rows are sorted by `max_historical_spread_pct` descending on every update received from the backend.
- **FR-002**: Table data refreshes every 5 seconds automatically via the backend's existing push cadence — no polling by the frontend.
- **FR-003**: "Analysis Period (s)" input (default 1800) is sent as `lookback_seconds` in the `update_filters` command when the user blurs the field or presses Enter.
- **FR-004**: "Min Spread %" filter is sent as `min_spread_pct`; applied server-side; table shows only matching rows.
- **FR-005**: "Min 24h Volume (USDT)" filter is sent as `min_volume_usdt`; applied server-side using the larger of the two exchanges' 24 h volumes per row.
- **FR-006**: "Min Analysis-Period Volume (USDT)" filter is sent as `min_analysis_volume_usdt` if the backend supports the field; if the field is absent from the payload, the filter input is disabled with a label indicating it is not yet available.
- **FR-007**: "Start Monitoring" sends `{"cmd": "start"}`; "Stop Monitoring" sends `{"cmd": "stop"}` over the existing WebSocket. Button enabled/disabled state reflects the `status` field returned by the backend.
- **FR-008**: Table columns rendered per row:
  - **Symbol** — назва токена
  - **Δ: X% → exit Y%** — поточний спред (Δ) та максимальний спред за аналізований період (exit = max_historical_spread_pct); обидва в одній клітинці
  - **Signal time** — кількість секунд тому коли спред був на максимумі за аналізований період
  - **Exchanges** — short біржа ↓ / long біржа ↑; іконка ⊘ біля біржі якщо для цієї пари вже відкрита картка-монітор
  - **Funding Rate** — ставка фандингу на кожній біржі
  - **Next Funding** — час до наступного фандингу на кожній біржі (формат `HH:MM:SS (залишок) | інтервал`)
  - **Funding Spread** — різниця ставок фандингу між біржами
  - **Price** — поточна ціна на кожній біржі
  - **Volume USDT** — обсяг торгів за 24 год на кожній біржі в USDT
  - **Actions** — `Copy to Form` (створити картку без запуску) / `⚡ Fast Trade` (створити картку і одразу запустити)
- **FR-009**: "Copy to Form" creates a monitor card via `add_monitor` with `auto_start: false`; "Fast Trade" sends `add_monitor` with `auto_start: true`.

**Live Monitor Card**

- **FR-010**: Cards run in parallel — each monitors its own symbol+exchange pair independently. The uniqueness constraint is symbol+short_exchange+long_exchange: one active monitor per unique triplet. The same symbol on a different exchange pair is a distinct monitor and allowed. Backend rejects `add_monitor` for a duplicate triplet; frontend shows a warning toast.
  Each card receives its configuration from the `monitors` array and its live state from the `live_state` dict (keyed by `symbol+short_ex+long_ex` composite key), both passed as props from the parent page — the card opens no independent WebSocket connection.
- **FR-011**: The following fields are wired from `live_state[symbol]` and display "—" when absent or null: `short_funding_rate`, `long_funding_rate`, `short_next_funding`, `long_next_funding`, `short_ask`, `long_ask`, `short_bid`, `long_bid`, `short_size`, `long_size`, `leverage`, `max_size_short`, `max_size_long`, `short_price`, `long_price`, `short_pnl`, `long_pnl`, `short_realized_pnl`, `long_realized_pnl`, `enter_spread_short`, `enter_spread_long`, `short_orders`, `long_orders`, `open_spread_current`, `open_spread_min`, `open_spread_max`, `close_spread_current`, `close_spread_min`, `close_spread_max`.
- **FR-012**: Allowed Size display uses `allowed_size_current_usdt` and `max_allowed_size_usdt` from the monitor's config entry.
- **FR-013**: The spread chart plots two lines over time:
  - **Red line** — short exchange spread (short side price dynamics)
  - **Green line** — long exchange spread (long side price dynamics)
  Data points accumulate locally in the card instance. Chart updates on every incoming push.
- **FR-019**: Card header contains:
  - Symbol name (bold)
  - ★ icon — toggle "favourite": pinned cards appear first in the card grid (sorted before unpinned)
  - 📌 icon — pin card to top of list (same as favourite toggle)
  - ⊘ icon — appears next to each exchange name if a monitor card for this symbol+exchange is already active; serves as a visual indicator of active monitoring
  - Exchange pair: `SHORT_EXCHANGE ↓ – LONG_EXCHANGE ↑`

- **FR-020**: **Side** selector (`Auto` / `LONG` / `SHORT`) controls which exchange takes the short position and which takes the long:
  - `Auto` — backend automatically determines which exchange to short and which to long based on current funding rates, choosing the direction that avoids negative margin for the trader
  - `LONG` — first listed exchange is long, second is short
  - `SHORT` — first listed exchange is short, second is long
  A checkmark (✓) shows the currently active selection.

- **FR-014**: Editable card parameters (Side, Open Spread %, Open T, Close Spread %, Close T, Order Size, Max Orders, Leverage, Adjustment Mode, Force Stop, Total Stop) send an `update_config` command on blur/change. Detailed semantics:
  - **Open Spread %** — мінімальний спред при якому бекенд відкриває позицію
  - **T (Open)** — кількість послідовних тіків при яких спред має перевищувати поріг перед відкриттям ордера (захист від хибних спрацювань)
  - **Close Spread %** — спред при якому бекенд закриває позицію
  - **T (Close)** — кількість послідовних тіків підтвердження для закриття
  - **Order Size** — розмір одного ордера в базовій валюті; USDT-еквівалент відображається поряд (розраховується бекендом)
  - **Max orders** — максимальна кількість сіткових ордерів; `0` = необмежено (до досягнення Allowed size)
  - **Allowed size** — `поточний накопичений обсяг USDT / максимально дозволений обсяг USDT`; запобігає нарощуванню понад ліміт
  - **Force Stop** — чекбокс: примусово закрити всі відкриті позиції і зупинити стратегію негайно
  - **Total Stop** — чекбокс: глобальна зупинка всіх операцій для цього монітора (ширше ніж Force Stop — включає відмову від нових сигналів)
  - **Leverage** — кредитне плече на кожній біржі; редагується окремо; поряд відображається тип маржі (cross/isolated)
  - **Adjustment notification** — `Notify only` (тільки сповіщення якщо плече відрізняється від заданого) / `Adjust` (автоматично виставити потрібне плече)
- **FR-015**: Start / Stop / Restart buttons:
  - **Start** — activates the monitor: backend begins watching orderbook and evaluating spread conditions.
  - **Stop** — pauses the monitor: backend halts new order decisions; existing open orders remain untouched.
  - **Restart** — sends a `restart` command; backend re-connects to exchanges, fetches all currently open orders for the symbol, recalculates all live metrics (P/L, realized PNL, enter spread, orders count) from real positions, then resumes monitoring. Does NOT clear position state — open orders carry over.
  Card header reflects active/stopped/restarting state visually.

**Backend requirements**

- **FR-016**: `HistoricalAutoTrader.get_live_state()` must emit all fields listed in FR-011 for each active monitor. Missing fields are added; existing field names are not changed (backward-compatible).
- **FR-017**: The `update_filters` command handler accepts `min_analysis_volume_usdt`; if per-period volume tracking is not yet implemented in the screener worker, the parameter is silently ignored and a log line is emitted.
- **FR-018**: All WebSocket payload changes are additive — no existing field names are renamed or removed, preserving compatibility with the legacy vanilla-JS frontend.

### Key Entities

- **OpportunityRow** (frontend): symbol, short/long exchange, max_historical_spread_pct, current_spread_pct, funding rates, next funding times, funding spread, prices, 24h volumes per exchange.
- **MonitorConfig** (backend + frontend, extended): existing fields plus `adjustment_mode` (notify_only / adjust), `allowed_size_current_usdt`, `max_allowed_size_usdt`.
- **LiveState** (frontend, new type): per-symbol dict of all real-time exchange fields enumerated in FR-011.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The screener table populates with live symbols within 10 seconds of the user clicking "Start Monitoring".
- **SC-002**: The table is visibly re-sorted by max-period-spread descending on every 5-second refresh — no unsorted render is observable during a 60-second observation window.
- **SC-003**: Applying each filter (Min Spread %, Min 24h Volume, Analysis Period) changes the visible row count in the expected direction, verifiable against a known data set.
- **SC-004**: All Live Monitor Card fields previously showing hardcoded placeholders display live values within one 5-second push cycle after the card is created.
- **SC-005**: The spread chart accumulates at least one visible new data point per 5-second push cycle for an active card over a 60-second observation window.
- **SC-006**: A strategy parameter change (e.g. Open Spread %) made in the card persists — it is reflected in the next backend push and survives a page reload.
- **SC-007**: Zero unhandled JavaScript exceptions appear in the browser console during a complete session: start screener → fast trade a card → observe for 60 seconds → stop.

## Clarifications

### Session 2026-07-16

- Q: Does "Restart" clear in-memory state or reconnect and recover open orders? → A: Reconnect only — backend fetches open orders, recalculates all metrics from real positions, resumes monitoring without clearing state.
- Q: What does "Signal time" in the table row mean? → A: Кількість секунд тому коли спред був на максимальному значенні за аналізований період.
- Q: What does the ⊘ icon next to an exchange name mean? → A: Вказує що для цього символу і цієї біржі вже відкрита активна картка-монітор.
- Q: Can multiple cards exist for the same symbol? → A: Один монітор на унікальну трійку symbol+short_exchange+long_exchange; той самий символ на інших біржах — дозволений окремий монітор.
- Q: What does the 📌 icon on the card do? → A: Закріплює картку першою в списку (пін/фаворит).
- Q: What does the Side selector control? → A: Визначає напрям позиції з урахуванням маржі: Auto — бекенд обирає сам щоб уникнути від'ємної маржі; LONG/SHORT — задається вручну.
- Q: What do the two chart lines represent? → A: Червона лінія — шорт біржа; зелена лінія — лонг біржа.

## Assumptions

- The existing `/ws/historical_screener` WebSocket endpoint already sends a `live_state` top-level key in its push payload — confirmed in the existing backend handler.
- The `OpportunityChart` component accepts time-series data as props and can be reused without internal changes; only the wiring (prop values) changes.
- The exact schema of `live_state[symbol]` in the current backend implementation needs to be verified before FR-011 is finalised; fields listed are based on the existing spec and legacy-UI JS code.
- `min_analysis_volume_usdt` filtering may require a new metric to be tracked in the screener worker; if not present, the frontend filter is disabled gracefully — this is not a blocker for the rest of the feature.
- `adjustment_mode`, `allowed_size_current_usdt`, and `max_allowed_size_usdt` may not yet exist in `MonitorConfig`; they will be added during implementation with sensible defaults.
- The legacy vanilla-JS frontend under `presentation/static/` is frozen and must remain buildable; all backend payload changes are strictly additive.
