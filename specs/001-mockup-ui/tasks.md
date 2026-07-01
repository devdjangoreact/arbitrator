# Tasks: 001-mockup-ui

**Input**: [spec.md](./spec.md) · [plan.md](./plan.md) · [ui-backend-catalog.md](./contracts/ui-backend-catalog.md)  
**Architecture**: UI ↔ server **WebSocket only**; exchange REST in `application/` only.

## Phase 1: Setup

- [X] T001 Create `src/arbitrator/presentation/static/css/` and merge CSS from `templates/` into `static/css/app.css`
- [X] T002 [P] Create `src/arbitrator/presentation/static/js/app.js` and `app_state.js` — nav, `showPage()`, AppState
- [X] T003 [P] Create `src/arbitrator/presentation/static/js/ws_client.js` — connect, send, reconnect, message dispatch
- [X] T004 Add to `settings.py` and `.env.example`: `ui_data_mode` (default `mock_data`), `mock_tick_seconds`, `screener_ws_push_seconds`
- [X] T005 Update `static/index.html` — link CSS/JS (placeholder until full port)

---

## Phase 2: Foundational (mock WS — можна перевірити UI без бірж)

**Test**: `UI_DATA_MODE=mock_data` → `GET /health` → `ui_data_mode: mock_data`; WS push snapshots; **no** `/api/*`; **no** ccxt.

- [X] T006 Create DTOs: `presentation/dto/screener_dto.py`, `opportunity_dto.py`, `orders_dto.py`, `settings_dto.py`, `trading_dto.py`
- [X] T007 Refactor `fastapi_app.py` — lifespan, static mount (`GET /`), extended `/health`, register WS routes
- [X] T007a [P] Create `presentation/mock/mock_data_provider.py` — seed from maket, `tick()`, in-memory command handlers (see [mock-data.md](./contracts/mock-data.md))
- [X] T008 Wire `main.py` — inject `MockDataProvider`; start `*StreamWorker` **only** when `ui_data_mode=live`
- [X] T009 Implement WS handlers with mock/live branch: `ws/screener_ws_handler.py`, `opportunity_ws_handler.py`, `orders_ws_handler.py`, `settings_ws_handler.py`
- [X] T009a [P] Minimal `static/js/ws_client.js` + stub render in `screener.js` / `app.js` — prove WS → DOM path in mock mode

**Checkpoint**: Browser opens `/`; all 4 WS endpoints push animated mock data; commands update in-memory state.

---

## Phase 3: User Story 1 — Screener (P1)

- [ ] T010 [US1] Port `#page-screener` HTML from `maket/index.html` into `static/index.html`
- [ ] T011 [US1] Create `application/screener_table_service.py` and `application/strategy_profit_service.py`
- [ ] T012 [US1] Create `presentation/serializers/screener_serializer.py`
- [ ] T013 [US1] `/ws/screener` — mock: provider loop; live: worker + `screener_serializer.py`
- [ ] T014 [US1] Create `static/js/screener.js` — WS client, table render, filter/reconnect commands
- [ ] T015 [US1] Wire Open Opportunity → AppState + `showPage('opportunity')`

---

## Phase 4: User Story 2 — Opportunity (P1)

- [ ] T016 [US2] Port `#page-opportunity` HTML into `static/index.html`
- [ ] T017 [US2] Create `presentation/serializers/opportunity_serializer.py`
- [ ] T018 [US2] `/ws/opportunity/{symbol}` — mock: provider; live: worker lifecycle
- [X] T019 [P] [US2] Create `static/js/render/opportunity_chart.js` and `order_book.js`
- [ ] T020 [US2] Create `static/js/opportunity.js` — render + WS commands (`accumulate`, `close_partial`, `close_all`, `set_params`, `set_leverage`)
- [ ] T021 [US2] Wire trading commands to `OpportunityAccumulateService`, `ArbitrageCloseService` (exchange REST inside application)
- [ ] T022 [US2] Funding countdown + focused orders from WS snapshot

---

## Phase 5: User Story 3 — Orders (P2)

- [ ] T023 [US3] Port `#page-orders` HTML into `static/index.html`
- [ ] T024 [US3] Create `presentation/serializers/orders_serializer.py`
- [ ] T025 [US3] Implement `/ws/orders` — `orders.snapshot`, `orders.summary` push, `orders.set_filter` in `orders_ws_handler.py`
- [ ] T026 [US3] Create `static/js/orders.js` — render ord-grid, filter via WS command
- [ ] T027 [US3] Sidebar `Orders · N` from `orders.summary` in `app.js`

---

## Phase 6: User Story 4 — Settings (P3)

- [ ] T028 [US4] Port `#page-settings` HTML into `static/index.html`
- [ ] T029 [US4] Implement `/ws/settings` — `settings.snapshot`, `settings.save_exchange` in `settings_ws_handler.py`
- [ ] T030 [US4] Create `static/js/settings.js` — load snapshot, send save command

---

## Phase 7: Polish

- [ ] T031 Empty states in screener/orders JS
- [ ] T032 [P] Unit tests: `tests/presentation/test_screener_serializer.py`, `tests/application/test_screener_table_service.py`
- [ ] T033 Run mypy + ruff; verify no `presentation/api/` routers; document `UI_DATA_MODE=live` in quickstart

---

## Phase 8: Live mode (optional after UI verified in mock)

- [ ] T034 [US1] `ScreenerTableService` + live branch in screener WS
- [ ] T035 [US2] `OpportunityStreamWorker` + live opportunity WS + trading services
- [ ] T036 [US3] Live orders from `OpportunityRegistryService` / account stream

---

## Summary

| Phase | Tasks | Count |
|-------|-------|-------|
| Setup | T001–T005 | 5 |
| Foundational + mock | T006–T009, T007a, T009a | 7 |
| US1 Screener | T010–T015 | 6 |
| US2 Opportunity | T016–T022 | 7 |
| US3 Orders | T023–T027 | 5 |
| US4 Settings | T028–T030 | 3 |
| Polish | T031–T033 | 3 |
| Live mode | T034–T036 | 3 |
| **Total** | | **39** |

**MVP (UI перевірка без бірж)**: Phase 1–2 + T010–T014 (mock WS + Screener UI).

**MVP (повний UI на mock)**: Phase 1–6 на `mock_data`, без T034–T036.

**Next**: `/speckit-implement`
