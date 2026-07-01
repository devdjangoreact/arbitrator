# Mock data mode (`UI_DATA_MODE=mock_data`)

**Призначення**: запустити FastAPI + WebSocket + static frontend **без бірж і ccxt**,
з реалістичними snapshot-ами для перевірки UI.

**Відповіді на уточнення (2026-06-30)**:

| Питання | Рішення |
|---------|---------|
| Режим за замовчуванням | `mock_data` |
| Анімація | так — ціни, chart points, стакани тикають |
| WS-команди | in-memory стан → наступний snapshot відображає зміни |

---

## 1. Settings

| Field | Env | Default | Значення |
|-------|-----|---------|----------|
| `ui_data_mode` | `UI_DATA_MODE` | `mock_data` | `mock_data` \| `live` |
| `mock_tick_seconds` | `MOCK_TICK_SECONDS` | `1.0` | інтервал анімації mock |
| `screener_ws_push_seconds` | … | `1.0` | інтервал push WS (обидва режими) |
| `opportunity_poll_seconds` | … | `1.0` | … |

У `mock_data`:

- **не стартують** `ScreenerStreamWorker`, `OpportunityStreamWorker`, `AccountStreamWorker` (ніяких ccxt).
- WS handlers використовують `MockDataProvider`.

У `live`:

- workers як у [plan.md](../plan.md); `MockDataProvider` не використовується.

---

## 2. FastAPI endpoints (заглушки + static)

**Не REST API для даних** — лише доставка файлів, health і WebSocket.

| Method | Path | Режим | Призначення |
|--------|------|-------|-------------|
| GET | `/` | обидва | `static/index.html` |
| GET | `/static/*` | обидва | CSS, JS |
| GET | `/health` | обидва | liveness + режим |
| WS | `/ws/screener` | обидва | `screener.snapshot` then `screener.delta` |
| WS | `/ws/opportunity?symbol=&short=&long=` | обидва | `opportunity.snapshot` then `opportunity.delta`; symbol in query |
| WS | `/ws/orders` | обидва | `orders.snapshot`, `orders.summary` |
| WS | `/ws/settings` | обидва | `settings.snapshot` |

### `GET /health` response

```json
{
  "status": "ok",
  "ui_data_mode": "mock_data",
  "ws_endpoints": [
    "/ws/screener",
    "/ws/opportunity?symbol=&short=&long=",
    "/ws/orders",
    "/ws/settings"
  ]
}
```

---

## 3. `MockDataProvider` (presentation layer)

**Файл**: `src/arbitrator/presentation/mock/mock_data_provider.py`  
**Клас**: `MockDataProvider` — один екземпляр на процес (inject через `main.py`).  
**Калькулятор**: `mock_strategy_calculator.py` (`MockStrategyCalculator`) — масштабує seed-значення стратегій від поточного спреду/basis.

### 3.1 Відповідальність

| Метод | Повертає |
|-------|----------|
| `screener_snapshot()` | `ScreenerSnapshotDto` |
| `opportunity_snapshot(symbol, short_ex, long_ex)` | `OpportunitySnapshotDto` |
| `orders_snapshot(filter)` | `OrdersSnapshotDto` |
| `orders_summary()` | `OrdersSummaryDto` |
| `settings_snapshot()` | `SettingsSnapshotDto` |
| `tick()` | оновлює внутрішній стан (ціни, chart ring, books) |
| `apply_screener_filters(...)` | in-memory filters |
| `apply_opportunity_params(...)` | in-memory params |
| `accumulate(...)`, `close_partial(...)`, `close_all(...)` | змінює mock positions/orders |
| `save_exchange(...)` | оновлює masked keys / flags |
| `set_leverage(...)` | оновлює leverage на картці |

Базові значення — з `src/arbitrator/data/mock_data.json` (seed для `UI_DATA_MODE=mock_data`).

### 3.2 Анімація (`tick()`)

Кожні `mock_tick_seconds`:

1. **Screener rows**: ±0.05–0.15% random walk на fut/spot ціни; перерахунок `spread_pct`, `spread_delta`, `max/min`, **6 колонок стратегій** (`strategy_profits`) від поточних цін.
2. **Opportunity strategy table**: перерахунок `strategy_rows` (spread, prices_label, gross/net, `% до депозиту`) від цін символу; рядки з `unavailable_reason` лишаються `N/A`.
3. **Opportunity chart**: append точка в ring buffer (4 серії); `last_price` оновлюється (delta `chart_series[]`).
4. **Order books**: зсув best bid/ask ±1 tick; перерахунок `fill_pct`, `total`, `mid_price`.
5. **Funding countdown**: `funding_countdown_sec -= 1` (reset при 0).

### 3.3 In-memory команди

| Command | Ефект у mock |
|---------|--------------|
| `screener.set_filters` | зберігає filters; table filter client/server |
| `screener.reconnect` | `status`: connecting → filtered за 1 tick |
| `opportunity.set_params` | оновлює `params` у snapshot |
| `opportunity.set_leverage` | leverage на картці + strategy rows |
| `opportunity.accumulate` | +volume до open group; `accumulated_volume_usdt` ↑ |
| `opportunity.close_partial` | −volume; можливий partial close |
| `opportunity.close_all` | group → `closed`, counts оновлюються |
| `orders.set_filter` | echo `filter` у snapshot |
| `settings.save_exchange` | `configured=true`, masked key |

Усі команди → `*.action_result` `{ success: true, message }` + негайний push snapshot (де застосовно).

### 3.4 Політики (зафіксовано)

| Питання | Рішення |
|---------|---------|
| `settings.save_exchange` у mock | **in-memory** до рестарту; persist у `.env` лише в `live` |
| Стан mock | **один** `MockDataProvider` на процес (узгоджені screener/orders/opportunity) |
| CORS | **ні** на MVP — frontend і API same-origin (`127.0.0.1:8000`) |

---

## 4. WS handler pattern (заглушка → mock/live)

```text
on connect:
  if settings.ui_data_mode == "mock_data":
      loop: provider.tick(); send snapshot (first) or delta; sleep(push_interval)
  else:
      delegate to *StreamWorker + serializer

on client message:
  if mock_data:
      provider.apply_*(); send action_result; send snapshot
  else:
      application service
```

**Opportunity WS**: у mock — один `MockDataProvider` на з'єднання (symbol/short/long з query);
worker lifecycle не потрібен.

---

## 5. Підключення фронтенду (перевірка)

### 5.1 Запуск

```bash
# .env або за замовчуванням
UI_DATA_MODE=mock_data
poetry run python main.py
```

Відкрити: `http://127.0.0.1:8000`

### 5.2 WebSocket URLs (браузер / DevTools)

| Екран | URL |
|-------|-----|
| Screener | `ws://127.0.0.1:8000/ws/screener` |
| Opportunity | `ws://127.0.0.1:8000/ws/opportunity?symbol=DOGE%2FUSDT&short=mexc&long=bingx` |
| Orders | `ws://127.0.0.1:8000/ws/orders` |
| Settings | `ws://127.0.0.1:8000/ws/settings` |

### 5.3 Перше повідомлення (приклади)

Див. §6 — скорочені JSON; повні поля — [data-model.md](../data-model.md).

### 5.4 Чеклист перевірки UI

| # | Дія | Очікування |
|---|-----|------------|
| M1 | `GET /health` | `ui_data_mode: mock_data` |
| M2 | Screener WS | ≥5 рядків, ціни змінюються кожну ~1 с |
| M3 | Min spread filter | таблиця фільтрується; state зберігається |
| M4 | Open Opportunity | WS opportunity; chart + 4 books анімуються |
| M5 | Добрати 50 USDT | `action_result` success; volume ↑ у params/orders |
| M6 | Orders page | 2 open / 14 closed; sidebar badge |
| M7 | Settings save | masked key; `configured: true` |
| M8 | `UI_DATA_MODE=live` | workers стартують; mock provider вимкнений |

---

## 6. Базові mock fixtures (seed)

Символи screener: `DOGE/USDT`, `SOL/USDT`, `XRP/USDT`, `ADA/USDT`, `TON/USDT`.  
Біржі: `mexc`, `bitget`, `gate`, `bingx`.

Opportunity default focus: `DOGE/USDT`, short `mexc`, long `bingx`.

Orders summary seed: `open_count: 2`, `closed_count: 14` (як макет).

Settings seed: 4 біржі, `api_key_masked: "••••••••••••"`, `configured: false` (до save).

Детальні seed-об'єкти зберігаються у
`src/arbitrator/data/mock_data.json`; `MockDataProvider` читає цей JSON і
формує in-memory стан без хардкоду значень у Python-коді.

---

## 7. Файли імплементації (додаток до plan)

| Файл | Роль |
|------|------|
| `config/settings.py` | `ui_data_mode`, `mock_tick_seconds` |
| `presentation/mock/mock_data_provider.py` | стан + tick + snapshots |
| `presentation/ws/*_ws_handler.py` | mock/live гілка |
| `presentation/fastapi_app.py` | routes, static, register WS |
| `main.py` | inject provider; skip workers у mock |
