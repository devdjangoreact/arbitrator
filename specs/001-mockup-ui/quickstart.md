# Quickstart: 001-mockup-ui validation

## Prerequisites

```bash
poetry install
# за замовчуванням UI_DATA_MODE=mock_data (без бірж)
poetry run python main.py
```

Відкрити `http://127.0.0.1:8000`

Перевірка режиму:

```bash
curl http://127.0.0.1:8000/health
# {"status":"ok","ui_data_mode":"mock_data","ws_endpoints":[...]}
```

## Mock mode (default) — швидка перевірка WS

| WS URL | Перше повідомлення |
|--------|-------------------|
| `ws://127.0.0.1:8000/ws/screener` | `screener.snapshot` — 5 rows, animated |
| `ws://127.0.0.1:8000/ws/opportunity?symbol=DOGE%2FUSDT&short=mexc&long=bingx` | `opportunity.snapshot` — chart + 4 books |
| `ws://127.0.0.1:8000/ws/orders` | `orders.snapshot` — 2 open, 14 closed |
| `ws://127.0.0.1:8000/ws/settings` | `settings.snapshot` — 4 exchanges |

Деталі mock: [contracts/mock-data.md](./contracts/mock-data.md) §5.

## Live mode

```bash
UI_DATA_MODE=live poetry run python main.py
```

Потрібні API keys у `.env`; workers підключаються до бірж.

## Architecture check

- DevTools → Network: **немає** запитів до `/api/*`
- Є WebSocket: `/ws/screener`, `/ws/opportunity/...`, `/ws/orders`, `/ws/settings`

## Phase M — Mock mode (перед live)

| Step | Action | Expected |
|------|--------|----------|
| M1 | `GET /health` | `ui_data_mode: mock_data` |
| M2 | Screener WS | ціни змінюються ~1/s |
| M3 | `screener.set_filters` | таблиця/фільтр оновлюються |
| M4 | Opportunity WS | chart + books анімуються |
| M5 | `opportunity.accumulate` | volume ↑ у наступному snapshot |
| M6 | `settings.save_exchange` | `configured: true` |

## Phase A — Shell

| Step | Expected |
|------|------------|
| Sidebar 4 пункти | Nav працює без reload |
| Layout ≈ `maket/index.html` | Візуальна відповідність |

## Phase B — Screener (WS)

| Step | Action | Expected |
|------|--------|----------|
| B1 | Відкрити Screener | WS connected, `screener.snapshot` |
| B2 | Змінити Min spread | `screener.set_filters` → оновлена таблиця |
| B3 | Reconnect | `screener.reconnect` → status Connecting → filtered |
| B4 | Open Opportunity | Перехід на Opportunity |

## Phase C — Opportunity (WS)

| Step | Action | Expected |
|------|--------|----------|
| C1 | Картки бірж | Дані з snapshot |
| C2 | Добрати | `opportunity.accumulate` → `opportunity.action_result` |
| C3 | Графік / стакани | Оновлення з WS |

## Phase D — Orders & Settings (WS)

| Step | Action | Expected |
|------|--------|----------|
| D1 | Orders screen | `orders.snapshot` |
| D2 | Sidebar badge | `orders.summary` push |
| D3 | Settings save | `settings.save_exchange` → `settings.action_result` |

## References

- [mock-data.md](./contracts/mock-data.md) — mock mode, endpoints, перевірка
- [ui-backend-catalog.md](./contracts/ui-backend-catalog.md) — елемент макету → JSON path (для backend)
- [ws-messages.md](./contracts/ws-messages.md)
