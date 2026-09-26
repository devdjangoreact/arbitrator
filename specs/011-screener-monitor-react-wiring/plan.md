# Implementation Plan: Screener History React UI Parity + Live Monitor Card Full Wiring

**Branch**: `011-screener-monitor-react-wiring` | **Date**: 2026-07-16 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/011-screener-monitor-react-wiring/spec.md`

## Summary

Wiring the existing History Screener backend to the React UI: replacing all hardcoded placeholders in `MonitorsPage` and `LiveMonitorCard` with live WebSocket data. The backend already pushes `opportunities` and `monitors` arrays every 5 seconds; the main gaps are (1) `live_state` dict lacks most exchange fields, (2) `HistoricalOpportunity` lacks `signal_time_seconds`, (3) `MonitorConfig` lacks `adjustment_mode` / `allowed_size_current_usdt`, and (4) the frontend types and card component need wiring to consume these fields. No new WS endpoints — all work is extension of the existing `/ws/historical_screener` channel.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5 / React 18 (frontend)

**Primary Dependencies**: FastAPI + WebSocket, ccxt.pro, Pydantic, uvicorn (backend); React 18, Vite, Tailwind CSS, Recharts (frontend)

**Storage**: JSON files via `MonitorConfigStore` (disk-backed, thread-locked)

**Testing**: pytest (backend unit + integration), Playwright (E2E per §9/§10)

**Target Platform**: Linux/Windows server + browser (Chrome/Firefox)

**Project Type**: Web service + React SPA

**Performance Goals**: WS payload ≤ 5s push cadence; card update latency ≤ one push cycle (5s)

**Constraints**: All payload changes additive (§18 / FR-018); no new WS endpoints (§11); `mypy --strict` + `ruff` must pass (§19)

**Scale/Scope**: Up to ~20 simultaneous monitor cards; screener table up to ~200 rows

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] §12 — 100% UI Parity: React card and table match the legacy monitors.html layout exactly; no fields dropped
- [x] §9/§10 — E2E via Playwright with live backend; no static-mock-only verification
- [x] §11 — Data Flow: all data via existing `/ws/historical_screener`; no new REST endpoints
- [x] §15 — Trading Safety: feature wires display and config params only; no new order-placement code introduced; `restart` command reconnects and reads — does NOT place orders
- [x] §16 — Market Universe: USDT-M perp symbols only (`BASE/USDT:USDT`); no universe change
- [x] §17 — Config SSoT: `adjustment_mode` → `MonitorConfig` (strategy-level config, not `Settings`); `allowed_size_current_usdt` is runtime state, lives in `MonitorConfig` dataclass
- [x] §18/§11 — Async: existing `_tick()` loop is async; no new sync I/O introduced
- [x] §19 — Typing Gate: all new Python fields typed; new TS types use `interface`, no `any`
- [x] §20 — Logging: Loguru singleton used; no `print()`
- [x] §21 — Dead Code: hardcoded placeholder values removed from `LiveMonitorCard.tsx` in the same change that wires live data

## Project Structure

### Documentation (this feature)

```text
specs/011-screener-monitor-react-wiring/
├── plan.md              # this file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # /speckit-tasks output
```

### Source Code (affected files)

```text
# Backend
src/arbitrator/
├── application/
│   ├── market_data/
│   │   └── historical_screener_worker.py   # add signal_time_seconds, min_analysis_volume_usdt filter
│   └── trading/
│       └── historical_auto_trader.py       # expand get_live_state() — all FR-011 fields
├── config/
│   └── monitor_config_store.py             # add adjustment_mode, allowed_size_current_usdt fields
└── presentation/
    └── ws/
        └── historical_screener_ws_handler.py  # wire restart cmd; expose new live_state fields

# Frontend
src/arbitrator/presentation/react-ui/src/
├── types/
│   └── index.ts                 # extend MonitorConfig; add OpportunityRow, LiveState interfaces
├── pages/
│   └── MonitorsPage.tsx         # pass live_state to cards; handle duplicate warning; pin sort
├── components/
│   ├── HistoricalScreenerTable.tsx  # new columns: Δ/exit, signal_time, ⊘ indicator
│   ├── LiveMonitorCard.tsx          # wire all FR-011 fields; pin/star; chart
│   └── SpreadChart.tsx              # new: two-line chart (open spread red, close spread green)

# Tests
tests/
├── unit/
│   └── test_historical_auto_trader_live_state.py  # new: verify all FR-011 fields emitted
└── e2e/
    └── test_monitors_page.py                       # new: Playwright E2E
```

## Complexity Tracking

No constitution violations requiring justification.

---

## Phase 0: Research

*Resolved unknowns from Technical Context and spec assumptions.*

### Bug Gap Analysis (added 2026-07-16)

Seven confirmed bugs in the current `LiveMonitorCard` implementation require targeted fixes:

| # | Bug | Root Cause | Fix Location |
|---|-----|-----------|-------------|
| 1 | All fields empty on start | `liveState[config.id]` key mismatch — `config.id` may be `""` before first push | `MonitorsPage.tsx` key lookup + ensure `config.id` set on `add_monitor` response |
| 2 | Bid/Ask always empty | `ls?.short_ask`/`ls?.short_bid` fields present in type but backend sends `None` until first tick | `historical_auto_trader.py` `_tick()` — ensure `short_ask`/`short_bid` always emitted |
| 3 | No active monitor indicator | FR-027 missing — no pulsing dot in card header | `LiveMonitorCard.tsx` header — add pulsing CSS dot keyed on `config.is_active` |
| 4 | SpreadChart no ticks | `openSpreadHistory.current` not triggering re-render because `liveState` prop reference not changing | `LiveMonitorCard.tsx` `useEffect` — verify `liveState` object identity changes each push |
| 5 | History click shows numbers | `SpreadHistoryModal` renders text/table instead of canvas charts | `SpreadHistoryModal.tsx` — replace table with three canvas/Recharts line charts |
| 6 | Card has internal scroll | `max-h-[65vh] overflow-y-auto` is wrong — all content must fit without scroll, card width ~70% | `LiveMonitorCard.tsx` root div — remove overflow-y, enforce 70% width, chart at bottom 30% |
| 7 | Notify only/Adjust not wired | `adjustment_mode` toggle fires `update_config` but `HistoricalScreenerWsHandler` may not persist it | Verify `update_config` handler in `historical_screener_ws_handler.py` writes `adjustment_mode` to store |
