# Research: 001-mockup-ui

**Date**: 2026-06-30  
**Status**: Complete

## R1: UI stack

**Decision**: Static HTML/CSS/JS + **WebSocket as sole UI↔server channel**. FastAPI serves static files + WS only.

**Rationale**: Вимога: немає REST API для браузера; біржовий REST лише в application layer.

---

## R2: CSS organization

**Decision**: `templates/**/*.css` → `static/css/app.css`.

---

## R3: WebSocket message format (bidirectional)

**Decision**: JSON `{ type, payload }` в обидва боки.  
Server push: snapshots, summaries, `*.action_result`.  
Client commands: filters, reconnect, trading, settings save.

**Alternatives considered**:
- FastAPI REST `/api/*` для UI — **відхилено** за вимогою користувача.

---

## R4: Screener table computation

**Decision**: `ScreenerTableService` + `StrategyProfitService` в `application/`.

---

## R5: Settings save from UI

**Decision**: WS `/ws/settings` — command `settings.save_exchange`; сервер оновлює runtime Settings / `.env`.  
Snapshot `settings.snapshot` — masked keys.

**Alternatives considered**:
- `POST /api/settings` — відхилено (REST API для UI).

---

## R6: Opportunity worker lifecycle

**Decision**: One `OpportunityStreamWorker` per opportunity WS connection.

---

## R7: Chart

**Decision**: Canvas in `opportunity_chart.js`, data from WS snapshot.

---

## R11: UI data mode (mock vs live)

**Decision**: `Settings.ui_data_mode` — `mock_data` (default) | `live`.

| Mode | Workers | WS data source |
|------|---------|----------------|
| `mock_data` | не стартують | `MockDataProvider` — animated tick + in-memory commands |
| `live` | `*StreamWorker` | serializers ← application |

**Rationale**: фронтенд можна перевірити без API ключів і бірж; команди змінюють mock-стан.

Документ: [contracts/mock-data.md](./contracts/mock-data.md).

---

## R8: Frontend modules

`core/` (`app_state.js`, `ws_client.js`, `dom.js`, `delta_router.js`), `render/` (`screener.js`, `opportunity.js`, `opportunity_chart.js`, `order_book.js`, `orders.js`, `settings.js`, `format.js`, `order_groups.js`).

---

## R9: Exchange REST vs UI WebSocket

**Decision**: Розділити два поняття:

| Шар | Протокол | Призначення |
|-----|----------|-------------|
| Browser ↔ FastAPI | **WebSocket only** | UI data + user commands |
| Application ↔ Exchange | **watch_* (WS)** + **fetch_* (REST fallback)** | Ринкові дані, позиції, ордери, leverage |

Документ: `.cursor/rules/exchange-data.mdc` (рівень проєкту).

**Rationale**: Біржі не завжди стримлять усе (positions на MEXC, set_leverage, place order). REST залишається в ccxt adapters / application services — не експонується як HTTP API до фронтенду.

---

## R10: Static file serving

**Decision**: `GET /` + `StaticFiles` — не вважається «REST API»; лише доставка HTML/CSS/JS. Опційно `GET /health` для ops.
