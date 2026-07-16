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

- [ ] T001 Rename `short_ex`→`short_exchange`, `long_ex`→`long_exchange` in `MonitorConfig` dataclass; add `id`, `adjustment_mode`, `allowed_size_current_usdt`, `max_allowed_size_usdt` fields with defaults in `src/arbitrator/config/monitor_config_store.py`
- [ ] T002 Add `__post_init__` migration fallback in `MonitorConfig` to read old `short_ex`/`long_ex` keys from persisted JSON in `src/arbitrator/config/monitor_config_store.py`
- [ ] T003 Add `signal_time_seconds: int` and `max_spread_detected_at: float` fields to `HistoricalOpportunity` dataclass; update `_scan()` to set `max_spread_detected_at` when max spread is updated, compute `signal_time_seconds = int(time.time() - max_spread_detected_at)` in `src/arbitrator/application/market_data/historical_screener_worker.py`
- [ ] T004 Update all callers of `MonitorConfig(short_ex=..., long_ex=...)` throughout codebase (grep for `short_ex`, `long_ex`) to use new field names in `src/arbitrator/`
- [ ] T005 Update `HistoricalScreenerWorker.update_filters()` to accept `min_analysis_volume_usdt` (silently ignored with `logger.debug` log) and `push_interval_seconds: int` (stored in `StrategyUIConfig.historical_screener_push_interval_seconds`, default 5); update WS handler to pass the value in `src/arbitrator/application/market_data/historical_screener_worker.py` and `src/arbitrator/config/ui_config.py`
- [ ] T037 Add `candle_interval_seconds: int = 5` to `StrategyUIConfig` in `src/arbitrator/config/ui_config.py`; add `price_deviation_filter_pct: float = 0.0` parameter to `HistoricalScreenerWorker.update_filters()` (stored in worker state, applied in `_scan()` to exclude symbols where `(price_max - price_min) / price_min * 100 < price_deviation_filter_pct` when filter > 0); extend `update_filters()` to also accept `candle_interval_seconds` and pass to candle fetching logic in `src/arbitrator/application/market_data/historical_screener_worker.py`

**Checkpoint**: `mypy --strict src/arbitrator` passes with zero errors after T001–T005, T037.

---

## Phase 2: Foundational — Backend live_state expansion (blocking)

**Purpose**: Expand `get_live_state()` to emit all FR-011 fields. Depends on Phase 1.

- [ ] T006 Expand `HistoricalAutoTrader._live_state` dict structure and update `_tick()` to populate all FR-011 fields per monitor: `short_funding_rate`, `long_funding_rate`, `short_next_funding`, `long_next_funding`, `short_ask`, `long_ask`, `short_bid`, `long_bid`, `short_size`, `long_size`, `leverage`, `max_size_short`, `max_size_long`, `short_price`, `long_price`, `short_pnl`, `long_pnl`, `short_realized_pnl`, `long_realized_pnl`, `enter_spread_short`, `enter_spread_long`, `short_orders`, `long_orders` in `src/arbitrator/application/trading/historical_auto_trader.py`
- [ ] T007 Add rolling min/max tracking per monitor for open_spread and close_spread; populate `open_spread_min`, `open_spread_max`, `close_spread_min`, `close_spread_max` in `_live_state` in `src/arbitrator/application/trading/historical_auto_trader.py`
- [ ] T008 Change `_live_state` key from `symbol` to `f"{symbol}:{short_exchange}:{long_exchange}"` composite key throughout `HistoricalAutoTrader` in `src/arbitrator/application/trading/historical_auto_trader.py`
- [ ] T009 Add `restart(monitor_id: str)` method to `HistoricalAutoTrader`: stop tick for that monitor, call read-only `fetch_open_orders` via gateway, recalculate live_state fields from real positions, resume tick in `src/arbitrator/application/trading/historical_auto_trader.py`
- [ ] T038 Add `close_all_positions(monitor_id: str)` method to `HistoricalAutoTrader`: close all open orders/positions for the given monitor via gateway, emit `logger.info`; this method is called by the WS handler on `remove` command (FR-025) in `src/arbitrator/application/trading/historical_auto_trader.py`

- [ ] T030 Write unit test — verify all 30 FR-011 fields present in `get_live_state()` for an active monitor in `tests/unit/test_historical_auto_trader_live_state.py`

**Checkpoint**: T030 test passes (red → green confirms FR-016 complete). `mypy --strict src/arbitrator` passes.

---

## Phase 3: Foundational — WebSocket handler updates (blocking)

**Purpose**: Update WS handler to use new field names, emit all new fields, handle `restart` cmd. Depends on Phase 1 + 2.

- [ ] T010 Update `HistoricalScreenerWsHandler._send_update()` to serialize `opportunities` with new `signal_time_seconds` field; serialize `monitors` with new `MonitorConfig` field names (`short_exchange`, `long_exchange`, `id`, `adjustment_mode`, `allowed_size_current_usdt`); add `supports_analysis_volume_filter: false` to payload in `src/arbitrator/presentation/ws/historical_screener_ws_handler.py`
- [ ] T011 Update `HistoricalScreenerWsHandler.handle()` to: pass `min_analysis_volume_usdt`, `push_interval_seconds`, `candle_interval_seconds`, and `price_deviation_filter_pct` from `update_filters` cmd to worker; handle new `restart` cmd by calling `auto_trader.restart(monitor_id)`; use composite `monitor_id` (`symbol:short_exchange:long_exchange`) for `remove` and `update_config` cmds; adjust WS push loop sleep to use `push_interval_seconds` from `StrategyUIConfig`; update `remove` handler to call `auto_trader.close_all_positions(monitor_id)` before removing the monitor (FR-025) in `src/arbitrator/presentation/ws/historical_screener_ws_handler.py`
- [ ] T012 Update `add_monitor` cmd handler: validate uniqueness by `symbol+short_exchange+long_exchange` triplet; return `{"type": "error", "data": {"code": "duplicate_monitor", "monitor_id": "..."}}` on duplicate; use `MonitorConfig(short_exchange=..., long_exchange=...)` new field names in `src/arbitrator/presentation/ws/historical_screener_ws_handler.py`

**Checkpoint**: Start backend, connect to `/ws/historical_screener` via wscat or browser, verify push payload matches contract in `specs/011-screener-monitor-react-wiring/contracts/ws_historical_screener.md`.

---

## Phase 4: User Story 1 — History Screener Table (React)

**Goal**: Таблиця з реальними даними, правильними колонками, фільтрами, Start/Stop.

**Independent Test**: Запустити бекенд → відкрити Monitors → клікнути Start → таблиця заповнюється за ≤10 с, колонки відповідають FR-008, фільтр Spread скорочує список.

- [ ] T013 [US1] Extend `OpportunityRow` interface and `MonitorConfig` interface in `src/arbitrator/presentation/react-ui/src/types/index.ts` with all new fields from data-model.md (`signal_time_seconds`, `max_historical_spread_pct`, `short_volume_24h`, `long_volume_24h`, `adjustment_mode`, `allowed_size_current_usdt`, etc.)
- [ ] T014 [US1] Add `LiveStateEntry` and `LiveState` TypeScript interfaces and `HistoricalScreenerUpdate` payload interface to `src/arbitrator/presentation/react-ui/src/types/index.ts`
- [ ] T015 [US1] Rewrite `HistoricalScreenerTable` component to render FR-008 columns: Symbol, Δ/exit cell (`current_spread_pct` + `max_historical_spread_pct`), Signal time, Exchanges with ⊘ indicator, Funding Rate (both), Next Funding (both), Funding Spread, Price (both), Volume 24h (both), Actions in `src/arbitrator/presentation/react-ui/src/components/HistoricalScreenerTable.tsx`
- [ ] T016 [P] [US1] Update `MonitorsPage` filter panel: rename "Time Window" → "Analysis Period (s)"; add "Refresh Interval (s)" input (default 5, min 1); add "Candle Interval (s)" dropdown (5 / 15 / 30 / 60, default 5); add "Price Deviation %" input (default 0.0, label "0 = off"); add "Min Analysis-Period Volume" input (disabled when `supports_analysis_volume_filter: false`); wire all filter inputs (`lookback_seconds`, `min_spread_pct`, `min_volume_usdt`, `min_analysis_volume_usdt`, `push_interval_seconds`, `candle_interval_seconds`, `price_deviation_filter_pct`) to `update_filters` WS command in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`
- [ ] T017 [US1] Update `MonitorsPage` WS data handler: parse `HistoricalScreenerUpdate` payload; derive `⊘` active-monitor set from `monitors` array; pass it to `HistoricalScreenerTable` for column rendering in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`
- [ ] T018 [US1] Update Start/Stop button states in `MonitorsPage` to reflect `status` field from WS payload (`Running` / `Idle` / `Stopping`) in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`

**Checkpoint**: Таблиця показує ≥1 рядок з реальними даними; колонки Δ/exit, Signal time, ⊘, Funding Rate присутні; фільтр Min Spread % змінює кількість рядків.

---

## Phase 5: User Story 2 — Fast Trade / Copy to Form card creation

**Goal**: Кнопки таблиці створюють картки правильно; дублікати блокуються; пін/зірка сортує.

**Independent Test**: Fast Trade → картка з'являється в Active стані; Copy to Form → картка в Stopped стані; повторний Fast Trade на тій самій парі → toast-попередження без дублікату; ⊘ з'являється в таблиці для активної пари.

- [ ] T019 [US2] Update `handleFastTrade` and `handleCopyToForm` in `MonitorsPage` to send composite `monitor_id` (`symbol:short_exchange:long_exchange`); handle `duplicate_monitor` error response from backend by showing a warning toast in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`
- [ ] T020 [US2] Add pin/star sort logic to `MonitorsPage`: maintain `pinnedIds: Set<string>` in local state; sort `monitors` array so pinned cards appear first in card grid in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`
- [ ] T021 [US2] Add ★ toggle and 📌 icon to `LiveMonitorCard` header; add × close button that calls `onRemove(id)` callback prop (sends `remove` cmd with `monitor_id`); implement `onRemove` in `MonitorsPage` to send `{"cmd": "remove", "monitor_id": "..."}` — card disappears from UI when absent in next push (FR-025) in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx` and `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`

**Checkpoint**: Fast Trade → картка з'явилась; ⊘ в таблиці видно; повторний Fast Trade → toast; ★ клік → картка першою в grid; × клік → картка зникає після наступного пушу.

---

## Phase 6: User Story 3 — Live Monitor Card real-time data wiring

**Goal**: Усі поля картки показують реальні дані з `live_state`; chart оновлюється; параметри зберігаються.

**Independent Test**: Активна картка після одного WS-пуша показує числові значення (не "—") у всіх полях funding rate, ask, bid, leverage, spread; chart додає точку кожні 5 с; зміна Open Spread % зберігається після F5.

- [ ] T022 [US3] Update `MonitorsPage` to extract `live_state` from WS payload and pass `liveState[config.id]` as a `liveData` prop to each `LiveMonitorCard` in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`
- [ ] T023 [US3] Rewrite `LiveMonitorCard` exchange data section to use `liveData: LiveStateEntry | undefined` prop for all FR-011 fields; render "—" via `format.ts` utilities when field is `null`/`undefined` in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`
- [ ] T024 [US3] Wire card header: symbol + ★ + 📌 + ⊘ per exchange + `SHORT_EXCHANGE ↓ – LONG_EXCHANGE ↑`; wire Side selector to `localConfig.side` with Auto/LONG/SHORT options and ✓ marker in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`
- [ ] T025 [US3] Wire all editable config fields (Open Spread %, T open, Close Spread %, T close, Order Size + USDT equiv, Max orders, Allowed size display, Force Stop, Total Stop, Leverage, Adjustment notification) to `localConfig` state and `saveConfig()` calls in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`
- [ ] T026 [US3] Wire Start/Stop/Restart buttons: Start → `update_config {is_active: true}`; Stop → `update_config {is_active: false}`; Restart → `restart` cmd with `monitor_id` in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`
- [ ] T027 [US3] Wire open/close spread tracking section: `open_spread_current/min/max` and `close_spread_current/min/max` from `liveData` in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`
- [ ] T028 [P] [US3] Create `SpreadChart` component: two `recharts` `Line`s on single Y-axis (red = open spread, green = close spread); dashed reference lines at configured `open_spread_pct` and `close_spread_pct`; accumulates `SpreadChartPoint[]` via `useRef` buffer updated on each `liveData` change in `src/arbitrator/presentation/react-ui/src/components/SpreadChart.tsx`
- [ ] T029 [US3] Integrate `SpreadChart` into `LiveMonitorCard` replacing the mock SVG chart section; pass `open_spread_pct` and `close_spread_pct` from `localConfig` as reference line props in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`

**Checkpoint**: SC-004 — усі поля картки показують реальні числа після першого пуша; SC-005 — chart накопичує точки; SC-006 — параметр зберігається після перезавантаження.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T031 [P] Write Playwright E2E test (mandatory gate — §10): start screener → table populates → Fast Trade → card active → live fields non-null → stop; test MUST include `page.on('pageerror', ...)` and `page.on('console', msg => msg.type() === 'error')` listeners — any JS error fails the test; add scenario: disconnect WS → reconnect → card still visible with updated data (FR-024) in `tests/e2e/test_monitors_page.py`
- [ ] T039 [P] Write unit test for `HistoricalScreenerWorker.update_filters()`: verify `price_deviation_filter_pct=2.0` excludes symbols with deviation < 2%, and `price_deviation_filter_pct=0.0` passes all symbols in `tests/unit/test_historical_screener_worker_filters.py`
- [ ] T040 [P] Write unit test for `close_all_positions()` in `HistoricalAutoTrader`: verify it calls gateway close methods for all open orders and removes the monitor_id from `_live_state` in `tests/unit/test_historical_auto_trader_close.py`
- [ ] T032 [P] Run `mypy --strict src/arbitrator` and fix any type errors introduced by new fields
- [ ] T033 [P] Run `ruff check src tests` and fix any lint issues
- [ ] T034 [P] Run `pnpm --prefix src/arbitrator/presentation/react-ui tsc --noEmit` and fix TS errors
- [ ] T035 Run `scripts/build_ui.py` to verify legacy vanilla-JS UI still builds without errors
- [ ] T036 Run quickstart validation scenarios from `specs/011-screener-monitor-react-wiring/quickstart.md` end-to-end

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
