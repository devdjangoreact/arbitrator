# Implementation Plan: UI макет Arbitrator (001-mockup-ui)

**Branch**: `001-mockup-ui`  
**Spec**: [spec.md](./spec.md)  
**Created**: 2026-06-30  
**Status**: Plan complete — [tasks.md](./tasks.md) ready for `/speckit-implement`

## Summary

Перенести повний UI з `maket/index.html` у робочий додаток: **static HTML/CSS/JS + WebSocket (єдиний канал UI)**.  
FastAPI віддає статику (`index.html`, CSS, JS) і **лише WebSocket** — без `/api/*` REST для браузера.

**REST (ccxt `fetch_*`)** — project policy in `.cursor/rules/exchange-data.mdc` (application layer only).

**Підхід**: shell → **mock WS (default)** → screener/opportunity/orders/settings WS → live workers.

## Mock data mode (default)

`UI_DATA_MODE=mock_data` (default) — FastAPI + WebSocket віддають **анімовані mock snapshot-и**
без ccxt. Команди змінюють in-memory стан. Деталі: [contracts/mock-data.md](./contracts/mock-data.md).

`UI_DATA_MODE=live` — реальні `*StreamWorker` + serializers (як раніше).

## Technical Context

| Параметр | Значення |
|----------|----------|
| **Мова** | Python 3.11+ |
| **Сервер** | FastAPI + uvicorn — static files + WebSocket |
| **UI ↔ сервер** | **Тільки WebSocket** (дані, команди, відповіді) |
| **UI ↔ біржа** | Ніколи напряму; лише через application workers |
| **Біржа REST** | ccxt `fetch_*` / `set_leverage` / orders — в application, не в presentation HTTP |
| **Біржа WebSocket** | ccxt.pro `watch_*` у `*StreamWorker` (background threads) |
| **Frontend** | `presentation/static/` |
| **Режим даних** | `Settings.ui_data_mode`: `mock_data` (default) \| `live` |
| **Mock provider** | `presentation/mock/mock_data_provider.py` |

## Constitution Check

| Принцип | Відповідність |
|---------|---------------|
| Clean Architecture | ✅ WS handlers → application; ccxt лише exchanges/application |
| WS for live exchange data | ✅ |
| REST poll only when no watch* | ✅ `exchange-data.mdc` |
| No browser REST API | ✅ |

**Gate**: PASS

## Architecture Overview

```text
Browser (static/index.html + js/)
    │  WebSocket only (/ws/screener, /ws/opportunity, /ws/orders, /ws/settings)
    │  HTTP GET /  + /static/*  (лише файли, не API)
    ▼
presentation/
    ├── fastapi_app.py              # lifespan, static mount, WS routes, /health
    ├── mock/
    │   └── mock_data_provider.py   # mock_data mode: snapshots + tick + in-memory cmds
    ├── ws/
    │   ├── screener_ws_handler.py
    │   ├── opportunity_ws_handler.py
    │   ├── orders_ws_handler.py
    │   └── settings_ws_handler.py
    ├── serializers/
    └── static/
application/
    ├── *StreamWorker               # watch_* → біржа WS
    ├── *Service                    # fetch_* → біржа REST (fallback / orders / leverage)
    └── screener_table_service.py
exchanges/                          # ccxt adapters
```

## Phase 1: Design Artifacts

| Артефакт | Шлях |
|----------|------|
| **UI ↔ Backend catalog** | [contracts/ui-backend-catalog.md](./contracts/ui-backend-catalog.md) |
| **WS protocol** | [contracts/ws-ui-protocol.md](./contracts/ws-ui-protocol.md) |
| **Mock data mode** | [contracts/mock-data.md](./contracts/mock-data.md) |
| WS contracts | [contracts/ws-messages.md](./contracts/ws-messages.md) |
| Data model | [data-model.md](./data-model.md) |
| Research | [research.md](./research.md) |
| Quickstart | [quickstart.md](./quickstart.md) |

## Implementation Phases

### Phase A — App shell, mock WS & assets

1. `Settings.ui_data_mode` + `mock_tick_seconds`; `.env.example`.
2. `MockDataProvider` — seed з макету, `tick()`, in-memory commands.
3. `FastApiApp` — static, `/health` (mode + ws list), WS handlers **mock branch**.
4. Порт `maket/index.html` → `static/index.html`; `ws_client.js` + мінімальний render.
5. Перевірка: [quickstart.md](./quickstart.md) § Mock mode.

### Phase B — Screener (WS)

1. `ScreenerTableService` + `StrategyProfitService` (**live only**).
2. `/ws/screener` — mock: `MockDataProvider`; live: worker + serializer.
3. Client commands: `screener.set_filters`, `screener.reconnect`.
4. `screener.js` — render + commands.

### Phase C — Opportunity (WS)

1. `/ws/opportunity/{symbol}` — snapshots + books + chart.
2. Commands: `accumulate`, `close_partial`, `close_all`, `set_params`, `set_leverage`.
3. Leverage / orders → application services → **exchange REST** where needed.

### Phase D — Orders & Settings (WS)

1. `/ws/orders` — `orders.snapshot`, `orders.summary`, `orders.set_filter`.
2. `/ws/settings` — `settings.snapshot`, `settings.save_exchange`.
3. Sidebar badge — з `orders.summary` push.

### Phase E — Live mode wiring

1. WS handlers — гілка `live`: workers + serializers.
2. `main.py` — старт workers лише при `ui_data_mode=live`.

### Phase F — Polish

1. WS reconnect у браузері, empty states, tests serializers/services.

## Generated Artifacts

- [research.md](./research.md)
- [data-model.md](./data-model.md)
- [contracts/ws-messages.md](./contracts/ws-messages.md)
- [contracts/ws-messages.md](./contracts/ws-messages.md)
- [quickstart.md](./quickstart.md)
- [tasks.md](./tasks.md)

## Next Step

`/speckit-implement` — tasks T001+
