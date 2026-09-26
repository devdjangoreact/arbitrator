---
description: "Task list for Screener History React UI Parity + Live Monitor Card Full Wiring"
---

# Tasks: Screener History React UI Parity + Live Monitor Card Full Wiring

**Input**: Design documents from `specs/011-screener-monitor-react-wiring/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: User story label — US1, US2, US3
- Exact file paths required in every task

---

## Phase 1: Foundational — Backend Data Model (blocking)

**Purpose**: Rename fields, extend dataclasses, and expand live_state. Must complete before any frontend or WS work.

**⚠️ CRITICAL**: All later phases depend on correct field names and live_state shape.

- [X] T001 Rename `short_ex`→`short_exchange`, `long_ex`→`long_exchange` in `MonitorConfig` dataclass; add `id`, `adjustment_mode`, `allowed_size_current_usdt`, `max_allowed_size_usdt` fields with defaults in `src/arbitrator/config/monitor_config_store.py`
- [X] T002 Add `__post_init__` migration fallback in `MonitorConfig` to read old `short_ex`/`long_ex` keys from persisted JSON in `src/arbitrator/config/monitor_config_store.py`
- [X] T003 Add `signal_time_seconds: int` and `max_spread_detected_at: float` fields to `HistoricalOpportunity` dataclass; update `_scan()` to set `max_spread_detected_at` when max spread is updated, compute `signal_time_seconds = int(time.time() - max_spread_detected_at)` in `src/arbitrator/application/market_data/historical_screener_worker.py`
- [X] T004 Update all callers of `MonitorConfig(short_ex=..., long_ex=...)` throughout codebase (grep for `short_ex`, `long_ex`) to use new field names in `src/arbitrator/`
- [X] T005 Update `HistoricalScreenerWorker.update_filters()` to accept `min_analysis_volume_usdt` (silently ignored with `logger.debug` log) and `push_interval_seconds: int` (stored in `StrategyUIConfig.historical_screener_push_interval_seconds`, default 5); update WS handler to pass the value in `src/arbitrator/application/market_data/historical_screener_worker.py` and `src/arbitrator/config/ui_config.py`
- [X] T037 Add `candle_interval_seconds: int = 5` to `StrategyUIConfig` in `src/arbitrator/config/ui_config.py`; add `price_deviation_filter_pct: float = 0.0` parameter to `HistoricalScreenerWorker.update_filters()` (stored in worker state, applied in `_scan()` to exclude symbols where `(price_max - price_min) / price_min * 100 < price_deviation_filter_pct` when filter > 0); extend `update_filters()` to also accept `candle_interval_seconds` and pass to candle fetching logic in `src/arbitrator/application/market_data/historical_screener_worker.py`

**Checkpoint**: `mypy --strict src/arbitrator` passes with zero errors after T001–T005, T037.

---

## Phase 2: Foundational — Backend live_state expansion (blocking)

**Purpose**: Expand `get_live_state()` to emit all FR-011 fields. Depends on Phase 1.

- [X] T006 Expand `HistoricalAutoTrader._live_state` dict structure and update `_tick()` to populate all FR-011 fields per monitor: `short_funding_rate`, `long_funding_rate`, `short_next_funding`, `long_next_funding`, `short_ask`, `long_ask`, `short_bid`, `long_bid`, `short_size`, `long_size`, `leverage`, `max_size_short`, `max_size_long`, `short_price`, `long_price`, `short_pnl`, `long_pnl`, `short_realized_pnl`, `long_realized_pnl`, `enter_spread_short`, `enter_spread_long`, `short_orders`, `long_orders` in `src/arbitrator/application/trading/historical_auto_trader.py`
- [X] T007 Add rolling min/max tracking per monitor for open_spread and close_spread; populate `open_spread_min`, `open_spread_max`, `close_spread_min`, `close_spread_max` in `_live_state` in `src/arbitrator/application/trading/historical_auto_trader.py`
- [X] T008 Change `_live_state` key from `symbol` to `f"{symbol}:{short_exchange}:{long_exchange}"` composite key throughout `HistoricalAutoTrader` in `src/arbitrator/application/trading/historical_auto_trader.py`
- [X] T009 Add `restart(monitor_id: str)` method to `HistoricalAutoTrader`: stop tick for that monitor, call read-only `fetch_open_orders` via gateway, recalculate live_state fields from real positions, resume tick in `src/arbitrator/application/trading/historical_auto_trader.py`
- [X] T038 Add `close_all_positions(monitor_id: str)` method to `HistoricalAutoTrader`: close all open orders/positions for the given monitor via gateway, emit `logger.info`; this method is called by the WS handler on `remove` command (FR-025) in `src/arbitrator/application/trading/historical_auto_trader.py`

- [X] T030 Write unit test — verify all 30 FR-011 fields present in `get_live_state()` for an active monitor in `tests/unit/test_historical_auto_trader_live_state.py`

**Checkpoint**: T030 test passes (red → green confirms FR-016 complete). `mypy --strict src/arbitrator` passes.

---

## Phase 3: Foundational — WebSocket handler updates (blocking)

**Purpose**: Update WS handler to use new field names, emit all new fields, handle `restart` cmd. Depends on Phase 1 + 2.

- [X] T010 Update `HistoricalScreenerWsHandler._send_update()` to serialize `opportunities` with new `signal_time_seconds` field; serialize `monitors` with new `MonitorConfig` field names (`short_exchange`, `long_exchange`, `id`, `adjustment_mode`, `allowed_size_current_usdt`); add `supports_analysis_volume_filter: false` to payload in `src/arbitrator/presentation/ws/historical_screener_ws_handler.py`
- [X] T011 Update `HistoricalScreenerWsHandler.handle()` to: pass `min_analysis_volume_usdt`, `push_interval_seconds`, `candle_interval_seconds`, and `price_deviation_filter_pct` from `update_filters` cmd to worker; handle new `restart` cmd by calling `auto_trader.restart(monitor_id)`; use composite `monitor_id` (`symbol:short_exchange:long_exchange`) for `remove` and `update_config` cmds; adjust WS push loop sleep to use `push_interval_seconds` from `StrategyUIConfig`; update `remove` handler to call `auto_trader.close_all_positions(monitor_id)` before removing the monitor (FR-025) in `src/arbitrator/presentation/ws/historical_screener_ws_handler.py`
- [X] T012 Update `add_monitor` cmd handler: validate uniqueness by `symbol+short_exchange+long_exchange` triplet; return `{"type": "error", "data": {"code": "duplicate_monitor", "monitor_id": "..."}}` on duplicate; use `MonitorConfig(short_exchange=..., long_exchange=...)` new field names in `src/arbitrator/presentation/ws/historical_screener_ws_handler.py`

**Checkpoint**: Start backend, connect to `/ws/historical_screener` via wscat or browser, verify push payload matches contract in `specs/011-screener-monitor-react-wiring/contracts/ws_historical_screener.md`.

---

## Phase 4: User Story 1 — History Screener Table (React)

**Goal**: Таблиця з реальними даними, правильними колонками, фільтрами, Start/Stop.

**Independent Test**: Запустити бекенд → відкрити Monitors → клікнути Start → таблиця заповнюється за ≤10 с, колонки відповідають FR-008, фільтр Spread скорочує список.

- [X] T013 [US1] Extend `OpportunityRow` interface and `MonitorConfig` interface in `src/arbitrator/presentation/react-ui/src/types/index.ts` with all new fields from data-model.md (`signal_time_seconds`, `max_historical_spread_pct`, `short_volume_24h`, `long_volume_24h`, `adjustment_mode`, `allowed_size_current_usdt`, etc.)
- [X] T014 [US1] Add `LiveStateEntry` and `LiveState` TypeScript interfaces and `HistoricalScreenerUpdate` payload interface to `src/arbitrator/presentation/react-ui/src/types/index.ts`
- [X] T015 [US1] Rewrite `HistoricalScreenerTable` component to render FR-008 columns: Symbol, Δ/exit cell (`current_spread_pct` + `max_historical_spread_pct`), Signal time, Exchanges with ⊘ indicator, Funding Rate (both), Next Funding (both), Funding Spread, Price (both), Volume 24h (both), Actions; use stable `key={\`${row.symbol}:${row.short_exchange}:${row.long_exchange}\`}` on each row — rows update in-place, no DOM recreate on each push (FR-001) in `src/arbitrator/presentation/react-ui/src/components/HistoricalScreenerTable.tsx`
- [X] T016 [P] [US1] Update `MonitorsPage` filter panel: rename "Time Window" → "Analysis Period (s)"; add "Refresh Interval (s)" input (default 5, min 1); add "Candle Interval (s)" dropdown (5 / 15 / 30 / 60, default 5); add "Price Deviation %" input (default 0.0, label "0 = off"); add "Min Analysis-Period Volume" input (disabled when `supports_analysis_volume_filter: false`); wire all filter inputs (`lookback_seconds`, `min_spread_pct`, `min_volume_usdt`, `min_analysis_volume_usdt`, `push_interval_seconds`, `candle_interval_seconds`, `price_deviation_filter_pct`) to `update_filters` WS command in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`
- [X] T017 [US1] Update `MonitorsPage` WS data handler: parse `HistoricalScreenerUpdate` payload; derive `⊘` active-monitor set from `monitors` array; pass it to `HistoricalScreenerTable` for column rendering in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`
- [X] T018 [US1] Update Start/Stop button states in `MonitorsPage` to reflect `status` field from WS payload (`Running` / `Idle` / `Stopping`) in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`

**Checkpoint**: Таблиця показує ≥1 рядок з реальними даними; колонки Δ/exit, Signal time, ⊘, Funding Rate присутні; фільтр Min Spread % змінює кількість рядків.

---

## Phase 5: User Story 2 — Fast Trade / Copy to Form card creation

**Goal**: Кнопки таблиці створюють картки правильно; дублікати блокуються; пін/зірка сортує.

**Independent Test**: Fast Trade → картка з'являється в Active стані; Copy to Form → картка в Stopped стані; повторний Fast Trade на тій самій парі → toast-попередження без дублікату; ⊘ з'являється в таблиці для активної пари.

- [X] T019 [US2] Update `handleFastTrade` and `handleCopyToForm` in `MonitorsPage` to send composite `monitor_id` (`symbol:short_exchange:long_exchange`); handle `duplicate_monitor` error response from backend by showing a warning toast in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`
- [X] T020 [US2] Add pin/star sort logic to `MonitorsPage`: maintain `pinnedIds: Set<string>` in local state; sort `monitors` array so pinned cards appear first in card grid in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`
- [X] T021 [US2] Add ★ toggle and 📌 icon to `LiveMonitorCard` header; add × close button that calls `onRemove(id)` callback prop (sends `remove` cmd with `monitor_id`); implement `onRemove` in `MonitorsPage` to send `{"cmd": "remove", "monitor_id": "..."}` — card disappears from UI when absent in next push (FR-025) in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx` and `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`

**Checkpoint**: Fast Trade → картка з'явилась; ⊘ в таблиці видно; повторний Fast Trade → toast; ★ клік → картка першою в grid; × клік → картка зникає після наступного пушу.

---

## Phase 6: User Story 3 — Live Monitor Card real-time data wiring

**Goal**: Усі поля картки показують реальні дані з `live_state`; chart оновлюється; параметри зберігаються.

**Independent Test**: Активна картка після одного WS-пуша показує числові значення (не "—") у всіх полях funding rate, ask, bid, leverage, spread; chart додає точку кожні 5 с; зміна Open Spread % зберігається після F5.

- [X] T022 [US3] Update `MonitorsPage` to extract `live_state` from WS payload and pass `liveState[config.id]` as a `liveData` prop to each `LiveMonitorCard` in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`
- [X] T023 [US3] Rewrite `LiveMonitorCard` exchange data section to use `liveData: LiveStateEntry | undefined` prop for all FR-011 fields; render "—" via `format.ts` utilities when field is `null`/`undefined` in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`
- [X] T024 [US3] Wire card header: symbol + ★ + 📌 + ⊘ per exchange + `SHORT_EXCHANGE ↓ – LONG_EXCHANGE ↑`; wire Side selector to `localConfig.side` with Auto/LONG/SHORT options and ✓ marker in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`
- [X] T025 [US3] Wire all editable config fields (Open Spread %, T open, Close Spread %, T close, Order Size + USDT equiv, Max orders, Allowed size display, Force Stop, Total Stop, Leverage, Adjustment notification) to `localConfig` state and `saveConfig()` calls in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`
- [X] T026 [US3] Wire Start/Stop/Restart buttons: Start → `update_config {is_active: true}`; Stop → `update_config {is_active: false}`; Restart → `restart` cmd with `monitor_id` in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`
- [X] T027 [US3] Wire open/close spread tracking section: `open_spread_current/min/max` and `close_spread_current/min/max` from `liveData` in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`
- [X] T028 [P] [US3] Create `SpreadChart` component: two lines on single Y-axis (red = open spread, green = close spread); accumulates buffer via `useRef` updated on each `liveData` change in `src/arbitrator/presentation/react-ui/src/components/SpreadChart.tsx`
- [X] T029 [US3] Integrate `SpreadChart` into `LiveMonitorCard` replacing the mock SVG chart section in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`

**Checkpoint**: SC-004 — усі поля картки показують реальні числа після першого пуша; SC-005 — chart накопичує точки; SC-006 — параметр зберігається після перезавантаження.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T031 [P] Write Playwright E2E test (mandatory gate — §10): start screener → table populates → Fast Trade → card active → live fields non-null → stop; test MUST include `page.on('pageerror', ...)` and `page.on('console', msg => msg.type() === 'error')` listeners — any JS error fails the test; add scenario: disconnect WS → reconnect → card still visible with updated data (FR-024) in `tests/e2e/test_monitors_page.py`
- [X] T039 [P] Write unit test for `HistoricalScreenerWorker.update_filters()`: verify `price_deviation_filter_pct=2.0` excludes symbols with deviation < 2%, and `price_deviation_filter_pct=0.0` passes all symbols in `tests/unit/test_historical_screener.py`
- [X] T040 [P] Write unit test for `close_all_positions()` in `HistoricalAutoTrader`: verify it calls gateway close methods for all open orders and removes the monitor_id from `_live_state` in `tests/unit/test_historical_auto_trader_close.py`
- [X] T032 [P] Run `mypy --strict src/arbitrator` and fix any type errors introduced by new fields
- [X] T033 [P] Run `ruff check src tests` and fix any lint issues
- [X] T034 [P] Run `pnpm --prefix src/arbitrator/presentation/react-ui tsc --noEmit` and fix TS errors
- [X] T035 Run `scripts/build_ui.py` to verify legacy vanilla-JS UI still builds without errors
- [X] T036 Run quickstart validation scenarios from `specs/011-screener-monitor-react-wiring/quickstart.md` end-to-end

---

## Phase 8: Convergence

- [X] T041 [US1] Fix `HistoricalScreenerTable` to render FR-008 "Δ: X% → exit Y%" as one combined cell: `current_spread_pct` (Δ) and `max_historical_spread_pct` (exit) in `src/arbitrator/presentation/react-ui/src/components/HistoricalScreenerTable.tsx` per FR-008 (partial)
- [X] T042 [US1] Add "Funding Spread" column to `HistoricalScreenerTable`: compute `short_funding_rate - long_funding_rate`, colour positive/negative via `pnlClass` in `src/arbitrator/presentation/react-ui/src/components/HistoricalScreenerTable.tsx` per FR-008 (missing)
- [X] T043 [US1] Pass `activeMonitorIds: Set<string>` prop from `MonitorsPage` (derived from `monitors` array as `new Set(monitors.map(m => m.id))`) to `HistoricalScreenerTable`; render ⊘ icon next to each exchange name in Exchanges column when `${opp.symbol}:${opp.short_exchange}:${opp.long_exchange}` is in the set in `src/arbitrator/presentation/react-ui/src/components/HistoricalScreenerTable.tsx` and `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx` per FR-008 (missing)
- [X] T044 [US1] Add `pushInterval` state (default 5) and "Refresh Interval (s)" input to `MonitorsPage` filter panel; add `push_interval_seconds: pushInterval` to `handleUpdateFilters` payload in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx` per FR-002 (missing)
- [X] T045 [US2] Handle `{"type": "error", "data": {"code": "duplicate_monitor"}}` in `MonitorsPage` WS `useEffect`; show a visible warning message (inline banner or toast) in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx` per FR-010 (missing)
- [X] T046 [US1] Add "Min Analysis-Period Volume (USDT)" input to `MonitorsPage` filter panel; disable the input when `data.supports_analysis_volume_filter === false`; wire value to `min_analysis_volume_usdt` in `handleUpdateFilters` in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx` per FR-006 (missing)
- [X] T047 [US1] Wire `screenerStatus` to Start/Stop button `disabled` prop in `MonitorsPage`: disable Start when `status === "Running"`, disable Stop when `status === "Idle"` in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx` per FR-007 (partial)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1** (MonitorConfig, HistoricalOpportunity): No prior deps — start immediately
- **Phase 2** (live_state expansion): Depends on Phase 1 (field rename must be done)
- **Phase 3** (WS handler): Depends on Phase 1 + Phase 2
- **Phase 4** (React table — US1): Depends on Phase 3 (WS payload shape must be final)
- **Phase 5** (card creation — US2): Depends on Phase 4 (table must render first)
- **Phase 6** (card wiring — US3): Depends on Phase 3 (live_state) + Phase 5 (cards exist)
- **Phase 7** (Polish): Depends on all implementation phases

### Critical Sequencing Note

**T001 → T004** must complete as a unit before any other task (field rename propagates everywhere). Do NOT start T006 until `mypy` passes after T001–T005, T037.

**T038** must complete before T011 (WS handler calls `close_all_positions`).

### Parallel Opportunities

- **Within Phase 1**: T003, T004, T005, T037 can run in parallel after T001+T002 complete
- **Within Phase 2**: T006 → T007 → T008 sequential (всі три в одному файлі `historical_auto_trader.py`); T009 та T038 можна паралельно з T007 (нові методи, різні ділянки файлу)
- **Phase 4 + Phase 5 setup**: T013, T014 [P] — different sections of types/index.ts (serialize separately then merge, or do sequentially to avoid conflict — RECOMMENDED: sequential)
- **Phase 6**: T028 (SpreadChart new file) [P] with T022 (MonitorsPage wiring)
- **Phase 7**: T030–T036, T039–T040 all [P]

---

## Implementation Strategy

### MVP (User Stories 1 + 2 only)

1. Complete Phases 1–3 (backend foundation)
2. Complete Phase 4 (table with live data)
3. Complete Phase 5 (card creation)
4. **VALIDATE**: Start screener → see real table → Fast Trade → see card → ⊘ shows → duplicate blocked
5. Ship MVP; card data wiring (US3) is the follow-up increment

### Full delivery

Add Phase 6 (card real-time wiring) + Phase 7 (tests + typecheck).

---

## Notes

- T001 is the most risky task (field rename + migration) — commit separately after `mypy` passes
- `[P]` tasks touch different files — safe to parallelize within a single phase
- Never mark two tasks `[P]` if they touch the same file (e.g., `MonitorsPage.tsx` — T016, T017, T018, T019, T020, T022 are sequential within that file)
- Backend changes (Phases 1–3) MUST be deployed before frontend changes (Phases 4–6) go live

---

## Phase 9: Convergence

- [X] T048 CRITICAL: Fix WS command protocol mismatch — `useWebSocket.ts:74` sends `{"type": cmd, "payload": {...}}` but `HistoricalScreenerWsHandler.handle()` reads `data.get("cmd")` (always None); update `historical_screener_ws_handler.py` to extract `cmd = data.get("type")` and unwrap `payload = data.get("payload", data)` for all field reads (`symbol`, `monitor_id`, filter fields, etc.), matching the envelope pattern used by all other WS handlers in the project per FR-007, FR-009, FR-015 (contradicts)

---

## Phase 10: Convergence

- [X] T049 CRITICAL: Remove "Opportunity" nav item and `OpportunityPage` import from `src/arbitrator/presentation/react-ui/src/App.tsx` — page no longer needed per user (missing)
- [X] T050 Move "Налаштування" nav item to last position in navItems array in `src/arbitrator/presentation/react-ui/src/App.tsx` per user UX requirement (missing)
- [X] T051 Add `max-h-[70vh] overflow-y-auto` to root div of `LiveMonitorCard` in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx` — card must not exceed 70% viewport height per user (missing)
- [X] T052 Remove hardcoded mock orders from `OrdersPage.tsx:14-87` — the `useEffect([], [])` initialiser that seeds fake DOGE/BTC orders must be deleted; page shows real data only from WS or empty state in `src/arbitrator/presentation/react-ui/src/pages/OrdersPage.tsx` (missing)
- [X] T053 Add error boundary component wrapping each page in `src/arbitrator/presentation/react-ui/src/App.tsx` — if ScreenerPage or MonitorsPage throws during render, display an error card instead of blank area; implement as a minimal `ErrorBoundary` class component in `src/arbitrator/presentation/react-ui/src/components/ErrorBoundary.tsx` (missing)
- [X] T020 [US2] Add pin/star sort logic to `MonitorsPage`: maintain `pinnedIds: Set<string>` in local state; sort `monitors` array so pinned cards appear first in card grid in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx` per FR-019 (partial)
- [X] T030 Write unit test — verify all 29 FR-011 fields present in `get_live_state()` for an active monitor in `tests/unit/test_historical_auto_trader_live_state.py` per FR-016 (partial)
- [X] T031 [P] Write Playwright E2E tests in `tests/e2e/test_monitors_page.py`: (1) start backend → open Monitors → click "Start Monitoring" → assert table has ≥1 row with numeric spread values from real backend data; (2) click "Fast Trade" → assert card appears with numeric funding_rate (not "—"); (3) click "Stop Monitoring" → assert status changes to "Idle"; (4) click × on card → assert card disappears; tests MUST use `page.on('pageerror', ...)` listener — any JS error fails; E2E data must come from real backend WS, no mocks per SC-001, SC-003, SC-004 (partial)
- [X] T035 Run `scripts/build_ui.py` to verify legacy vanilla-JS UI still builds without errors per FR-018 (partial)
- [X] T036 Run quickstart validation scenarios from `specs/011-screener-monitor-react-wiring/quickstart.md` end-to-end (partial)
- [X] T054 Add rule to `CLAUDE.md` under a new "UI Verification" section: "All React UI changes MUST be verified in the browser before marking the task done. E2E tests must use real backend data — no mocked WS responses. Each button action test must assert observable state change in the UI (table row count, card appearance, status label)." (missing)

---

## Phase 11: Convergence

- [X] T055 CRITICAL: Fix SpreadChart accumulation — remove `key={chartTick}` from `<SpreadChart>` in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx:403`; the `key` prop forces unmount/remount on every push, wiping the canvas buffer; SpreadChart already re-renders via its own `useEffect([openSpreads, closeSpreads])` — removing the key is sufficient per FR-013, SC-005 (contradicts)
- [X] T056 CRITICAL: Fix Start button — `LiveMonitorCard.tsx:66-73` sends `update_config {is_active: true}` which sets `MonitorConfig.is_active` flag but does NOT start the `HistoricalAutoTrader` thread; the auto-trader thread is started once at app boot and runs continuously — it evaluates `config.is_active` each tick; verify `HistoricalAutoTrader.start()` is called at boot in `src/arbitrator/application/app_runtime.py` (or wherever the runtime is initialised) and not gated on `historical_screener_enabled`; if the trader is not running, the Start button will never trigger ticks per FR-015 (contradicts)
- [X] T057 Add collapse/expand toggle to `LiveMonitorCard` header: add `const [collapsed, setCollapsed] = useState(false)` state; render a `▼`/`▶` chevron button next to the symbol name in the header; when collapsed, hide the `<div className="p-4 flex flex-col gap-4">` body entirely; reduce card header padding to `p-2` and font sizes to `text-xs`/`text-sm` across the card body to make content more compact per user req #1 and #3 in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx` (missing)
- [X] T058 Add collapse/expand toggle to `HistoricalScreenerTable`: add `const [collapsed, setCollapsed] = useState(false)` state in the component; render a `▼`/`▶` button next to "Found Opportunities" heading; when collapsed hide `<tbody>` and show only the heading row; reduce table row padding from default to `py-0.5 px-2` (`text-xs` rows) for compact density per user req #2 in `src/arbitrator/presentation/react-ui/src/components/HistoricalScreenerTable.tsx` (missing)
- [X] T059 Add "Spread History" button to each table row in `HistoricalScreenerTable` (Actions column, below "⚡ Fast Trade"); clicking it calls a new `onSpreadHistory(opp)` callback prop; implement `SpreadHistoryModal` component in `src/arbitrator/presentation/react-ui/src/components/SpreadHistoryModal.tsx` that renders three canvas charts stacked vertically: (1) price over time for short exchange (blue line), (2) price over time for long exchange (orange line), (3) spread diff over time (green/red); modal receives `opp: HistoricalOpportunity` as prop and pulls candle data from the `opportunities` payload's history fields if available, or shows "No history data" placeholder if fields absent; wire `onSpreadHistory` in `MonitorsPage` to show/hide the modal via `useState<HistoricalOpportunity | null>` per user req #4 in `src/arbitrator/presentation/react-ui/src/components/HistoricalScreenerTable.tsx`, `src/arbitrator/presentation/react-ui/src/components/SpreadHistoryModal.tsx`, and `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx` (missing)

---

## Phase 12: Convergence

- [X] T060 CRITICAL: Fix `ScreenerDataTable` exchange columns — BITGET/GATE/BINGX always show `-` because the component hardcodes 4 fixed exchange columns and only fills MEXC via `row.max_p`/`row.min_p` (global max/min, not per-exchange prices); add `prices: Record<string, { futures: number | null; spot: number | null }>` field to `ScreenerRow` interface in `src/arbitrator/presentation/react-ui/src/types/index.ts`; in `ScreenerSerializer.serialize()` (or the snapshot DTO `model_dump()` path in `screener_ws_handler.py` / `ScreenerWsHandler`) ensure each row's `prices` dict is included in the JSON payload; rewrite `ScreenerDataTable.tsx` exchange columns to be dynamic: derive the list of exchange ids from a new `exchanges: string[]` prop passed from `ScreenerPage` (from `data.exchanges` in the snapshot payload), render one `<th>`/`<td>` per exchange showing `row.prices[exchangeId]?.futures` formatted with `fmtNum` per FR-021, SC-001 in `src/arbitrator/presentation/react-ui/src/types/index.ts`, `src/arbitrator/presentation/react-ui/src/components/ScreenerDataTable.tsx`, and `src/arbitrator/presentation/react-ui/src/pages/ScreenerPage.tsx` (contradicts)

---

## Phase 13: Convergence

- [X] T061 CRITICAL: Fix all LiveMonitorCard fields empty at start — root cause: `liveState[config.id]` returns `undefined` because `config.id` is `""` on newly added monitors until first WS push; fix `MonitorsPage.tsx` to pass `liveState[config.id] ?? liveState[\`${config.symbol}:${config.short_exchange}:${config.long_exchange}\`]` as `liveState` prop so card receives data on the very first push; also verify `HistoricalAutoTrader._tick()` emits state for all active monitors (not only those with open positions) in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx` and `src/arbitrator/application/trading/historical_auto_trader.py` per FR-011, SC-004, SC-008 (partial)
- [X] T062 CRITICAL: Fix Bid/Ask always empty — verify `historical_auto_trader.py` `_tick()` emits `short_ask`, `long_ask`, `short_bid`, `long_bid` from `market_cache.get_quote()` for ALL active monitors regardless of whether a position is open; currently these fields may only be populated when `is_active=True` and the spread resolver runs — ensure the orderbook fetch runs for every monitor in `_live_state` update loop in `src/arbitrator/application/trading/historical_auto_trader.py` per FR-011, SC-008 (partial)
- [X] T063 [US3] Add pulsing active-monitor indicator to `LiveMonitorCard` header: add `<span>` with CSS animation `animate-pulse` and `bg-green-500 rounded-full w-2 h-2` classes next to symbol name; show when `config.is_active === true`, grey (`bg-gray-500`) when false; no new deps — Tailwind `animate-pulse` is already available in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx` per FR-027, SC-009 (missing)
- [X] T064 [US3] Fix SpreadChart not accumulating ticks — diagnose why `openSpreadHistory.current` stays empty: check that `liveState` prop reference changes on each WS push (not same object identity); if `MonitorsPage` mutates `liveState` in-place rather than creating a new object, the `useEffect([liveState])` in `LiveMonitorCard` never fires; fix `MonitorsPage.tsx` to spread `{...payload.live_state}` when setting state so each push creates a new object; also ensure `open_spread_current` and `close_spread_current` are non-null in the backend payload in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx` and `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx` per FR-013, SC-005 (partial)
- [X] T065 [US3] Fix `SpreadHistoryModal` — replace any text/table content with three canvas/Recharts line charts stacked vertically: (1) short exchange price over time (blue line), (2) long exchange price over time (orange line), (3) spread diff over time (green/red); if no history data available show "No history data" placeholder; remove all table/number rendering from the modal in `src/arbitrator/presentation/react-ui/src/components/SpreadHistoryModal.tsx` per FR-013, SC-010 (contradicts)
- [X] T066 [US3] Fix card layout — no internal scroll, 70% width: remove `overflow-y-auto` and `max-h-[65vh]` from `LiveMonitorCard` root div; add `w-[70vw] max-w-[70vw]` to the card or its modal/panel wrapper in `MonitorsPage`; ensure `SpreadChart` is at bottom occupying ~30% of card height (`h-[30%]` or fixed px consistent with card); all content must be visible at viewport ≥ 600px without scrollbar in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx` and `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx` per FR-026, SC-011 (contradicts)
- [X] T067 [US3] Fix `adjustment_mode` persistence — verify `HistoricalScreenerWsHandler.handle()` `update_config` branch reads `config.get("adjustment_mode")` and calls `self._store.update(monitor_id, adjustment_mode=...)` or equivalent; if missing, add the field to the `update_config` handler so clicking `Notify only`/`Adjust` in the card persists the value and it is reflected in the next push `monitors` array in `src/arbitrator/presentation/ws/historical_screener_ws_handler.py` and `src/arbitrator/config/monitor_config_store.py` per FR-028, SC-012 (partial)
