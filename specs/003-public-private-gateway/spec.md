# Feature Specification: Public / Private Exchange Gateways

**Feature Branch**: `003-public-private-gateway`
**Created**: 2026-07-08
**Status**: Draft — not implemented
**Input**: Розділити підключення до бірж на public і private канали з різною
мережею. Публічні ринкові дані (tickers, order books) — через проксі без API keys.
Приватні операції (positions, balance, orders) — прямий IP з credentials, без проксі
і без стаканів/графіків.

---

## Мета

1. **Public gateway** (без API keys, через проксі):
   - публічні ринкові дані: tickers, order books, funding (якщо публічний endpoint)
   - використовується скрінером, book stream, strategy cache, spread resolver

2. **Private gateway** (з API keys, БЕЗ проксі, прямий IP):
   - тільки приватні операції: positions, balance, orders, leverage, create_order, close
   - **заборонено**: `watch_order_book`, `watch_tickers`, `watch_trades`,
     `fetch_order_book` для графіків/скрінера

3. Стакани (order book) — **завжди через public gateway**, якщо біржа дозволяє
   публічний доступ без ключів.

---

## Поточний стан (baseline)

- `Factory.create()` → один `CcxtBase` на exchange; credentials додаються автоматично
  якщо є в `.env` (`ccxt_base._base_client_config`).
- Окремі gateway-інстанси вже є, але всі з одного IP і часто з ключами навіть для
  публічних стрімів:
  - `ScreenerStreamWorker` → `watch_tickers`
  - `ScreenerBookStreamWorker` → `watch_order_book` (MEXC, ~500+ символів, rate limit 510)
  - `AccountStreamWorker` → `watch_positions`, `watch_balance`
  - `LiveAutoTrader` / `HedgedExecutionService` → orders + `ExecutableSpreadResolver` REST book
- Проксі в коді **не реалізовані**; є лише `aiohttp_trust_env=True`.
- ccxt pro підтримує per-instance: `http_proxy` (REST) + `ws_proxy` (WebSocket) —
  обидва потрібні для book stream.

---

## User Scenarios

### User Story 1 — Скрінер і стакани через public + проксі (Priority: P1)

Оператор запускає live-режим. Скрінер і book stream отримують tickers/order books через
public gateway без API keys, через проксі (інший IP). Rate limit MEXC 510 зменшується
за рахунок розвантаження основного IP.

**Acceptance**:

1. **Given** задано `EXCHANGE_PUBLIC_HTTP_PROXY` і `EXCHANGE_PUBLIC_WS_PROXY`,
   **When** стартує `ScreenerBookStreamWorker`,
   **Then** ccxt client не має `apiKey` і має `http_proxy` + `ws_proxy`.
2. **Given** public gateway активний,
   **When** надходять оновлення стакану,
   **Then** `MarketDataCacheMemory` і `ExecutableSpreadResolver` використовують ці дані.

### User Story 2 — Trading і account через private без проксі (Priority: P1)

Відкриття/закриття ордерів, positions, balance — тільки через private gateway з
credentials, прямий IP, без проксі.

**Acceptance**:

1. **Given** credentials налаштовані,
   **When** `HedgedExecutionService` відкриває позицію,
   **Then** `create_order` йде через private gateway без proxy.
2. **Given** private gateway,
   **When** worker намагається викликати `watch_order_book`,
   **Then** це не використовується (private gateway не передається в book/ticker workers).

### User Story 3 — Spread resolver бере стакани з public (Priority: P1)

`ExecutableSpreadResolver.entry_spread_for_open` REST verify і кеш book — тільки public gateway.

**Acceptance**:

1. **Given** cached spread ≥ `screener_rest_prefilter_spread_pct` і немає bid/ask у кеші,
   **When** resolver робить REST book fetch,
   **Then** запит йде через public gateway (з проксі якщо задано), не через private.

---

## Вимоги до реалізації

### 1. Два режими gateway

Розшир `Factory` (або `CcxtBase`) щоб можна було створювати:

```python
factory.create(exchange_id, mode="public")   # без credentials, з proxy
factory.create(exchange_id, mode="private")  # з credentials, без proxy
```

Або окремі методи: `create_public()`, `create_private()`.

**Public:**

- не передавати `apiKey` / `secret` / `password`
- встановити `http_proxy` + `ws_proxy` з Settings (для REST seed і WS)
- дозволені методи: `watch_tickers`, `watch_order_book`, `fetch_order_book_once`,
  `fetch_funding_rate`, `load_markets`, `list_symbols`

**Private:**

- credentials з `Settings.credentials_for()`
- proxy **не** встановлювати (явно `None` / не задавати)
- дозволені методи: `watch_positions`, `watch_balance`, `create_order`, `set_leverage`,
  `fetch_open_positions`, `fetch_balance`, тощо
- **не викликати** з private gateway: `watch_order_book`, `watch_tickers`, `watch_trades`

### 2. Settings

Додати в `settings.py` + `.env.example`:

```env
# Проксі тільки для public market data (REST + WS)
EXCHANGE_PUBLIC_HTTP_PROXY=http://user:pass@host:port
EXCHANGE_PUBLIC_WS_PROXY=http://user:pass@host:port
# або socks: EXCHANGE_PUBLIC_SOCKS_PROXY=socks5://127.0.0.1:1080

# Опційно per-exchange override (JSON або окремі поля):
# MEXC_PUBLIC_HTTP_PROXY=...
# MEXC_PUBLIC_WS_PROXY=...
```

Поля в `Settings`:

- `exchange_public_http_proxy: str = ""`
- `exchange_public_ws_proxy: str = ""`
- `exchange_public_socks_proxy: str = ""` (опційно)
- `exchange_public_proxy_by_exchange: dict[str, str]` (опційно, override per exchange)

Порожній рядок = без проксі (fallback на прямий IP).

### 3. Перерозподіл gateway по workers

| Worker | Gateway |
|--------|---------|
| `ScreenerStreamWorker` | **public** |
| `ScreenerBookStreamWorker` | **public** |
| `StrategyTableService` / `MarketDataCacheMemory` | дані з public |
| `AccountStreamWorker` | **private** |
| `HedgedExecutionService` (orders) | **private** |
| `LiveAutoTrader` spread resolver | **public** для book/ticker; **private** тільки для execution |
| `LiveLiquidationGuardService` | **private** (positions) |
| `FundingAccrualService` | public funding якщо можливо |

### 4. ExecutableSpreadResolver

- `fetch_order_book_once` / кеш book → тільки через **public** gateway
- `entry_spread_for_open` REST verify → public gateway
- execution (`create_order`, `close`) → private gateway через `HedgedExecutionService`

### 5. Захист від випадкового використання private для публічних даних

Мінімальний варіант (без over-engineering):

- параметр `GatewayMode.PUBLIC | PRIVATE` на `CcxtBase`
- у public-методах (`watch_order_book`, `watch_tickers`) — no-op / log error якщо
  mode=PRIVATE і викликано з private контексту для market data
- або простіше: private gateway просто не експортується в workers, які потребують стаканів

Не створювати зайвих класів/файлів — розширити існуючі `Factory`, `CcxtBase`,
wiring в `app_runtime.py`.

### 6. CcxtBase зміни

У `_ensure_open()` після `_create_client()`:

```python
if self._mode == "public":
    if proxy := self._settings.public_http_proxy_for(self.exchange_id):
        client.http_proxy = proxy
    if proxy := self._settings.public_ws_proxy_for(self.exchange_id):
        client.ws_proxy = proxy
elif self._mode == "private":
    # явно не ставити proxy, навіть якщо trust_env=True
    client.http_proxy = None
    client.ws_proxy = None
```

Переконатися що `aiohttp_trust_env` не перекриває явні налаштування на private gateway.

---

## Обмеження проєкту

- Poetry venv: `.venv\Scripts\python.exe`, не `poetry run`
- `Settings` — єдине джерело конфігурації; додати поля + `.env.example`
- `mypy --strict`, без `Any`
- Мінімальний diff, без зайвих абстракцій (compact-code rule)
- Не створювати нові файли без потреби (окрім цієї spec)
- Після змін: `ruff`, `mypy`, релевантні тести
- **Не робити git commit** без явного запиту

---

## Тести

Додати/оновити unit-тести:

1. `Factory.create_public("mexc")` — gateway без `apiKey` в ccxt config
2. `Factory.create_private("mexc")` — gateway з credentials, без proxy
3. public gateway отримує `http_proxy` / `ws_proxy` з Settings
4. private gateway — proxy = None навіть при `HTTP_PROXY` в env
5. `ScreenerBookStreamWorker` / `app_runtime` wiring використовує public factory

Мокати ccxt client, не робити реальних запитів до біржі.

---

## Критерії готовності

- [ ] Скрінер + book stream MEXC йдуть через public gateway + проксі (якщо задано в Settings)
- [ ] Відкриття/закриття ордерів — private gateway, прямий IP, з ключами
- [ ] Account stream (positions, balance) — private, без стаканів
- [ ] `ExecutableSpreadResolver` бере стакани з public, не з private
- [ ] `mypy --strict` і тести проходять
- [ ] Логи при старті показують `mode=public|private` per gateway

---

## Порядок роботи для агента

1. Прочитати: `factory.py`, `ccxt_base.py`, `app_runtime.py`,
   `screener_book_stream_worker.py`, `account_stream_worker.py`,
   `hedged_execution_service.py`, `executable_spread_resolver.py`
2. Додати Settings + proxy helpers
3. Розширити Factory / CcxtBase (public/private mode)
4. Перевести workers на правильні gateway
5. Тести
6. Короткий звіт: що змінилось, які env-змінні додати

---

## Файли для змін (орієнтовно)

| Файл | Зміна |
|------|-------|
| `src/arbitrator/config/settings.py` | proxy fields, helpers |
| `src/arbitrator/exchanges/factory.py` | `create_public` / `create_private` |
| `src/arbitrator/exchanges/ccxt_base.py` | mode, proxy wiring |
| `src/arbitrator/application/app_runtime.py` | wiring workers |
| `src/arbitrator/application/screener_book_stream_worker.py` | public factory |
| `src/arbitrator/application/screener_stream_worker.py` | public factory |
| `src/arbitrator/application/account_stream_worker.py` | private factory |
| `src/arbitrator/application/hedged_execution_service.py` | private for orders |
| `src/arbitrator/application/executable_spread_resolver.py` | public for books |
| `tests/unit/test_factory_gateway_mode.py` | new tests |
| `.env.example` | new env keys |

---

## Пов'язані налаштування (вже змінені)

- `screener_book_stream_symbol_refresh_seconds` = `3600` (1 год) — зменшує перепідписки
- `screener_book_stream_max_concurrent` — рекомендовано 5–10 для MEXC 510
