# UI ↔ Backend Catalog

**Призначення**: кожен видимий елемент `maket/index.html` → точне поле JSON, яке backend MUST віддати (або прийняти як команду).

**Канал UI↔сервер**: лише WebSocket (див. [ws-messages.md](./ws-messages.md)).  
**Pydantic DTO**: [data-model.md](../data-model.md).  
**WS протокол і partials**: [ws-ui-protocol.md](./ws-ui-protocol.md).
**Біржовий REST**: `.cursor/rules/exchange-data.mdc` (не частина цієї фічі).

### Легенда колонок

| Колонка | Значення |
|---------|----------|
| **WS** | Endpoint + message `type` |
| **JSON path** | Шлях у `payload` (JSON Pointer стиль) |
| **Тип** | Python / JSON тип |
| **Формат UI** | Як показати в браузері |
| **Джерело backend** | Service / worker / domain |
| **Оновлення** | `push` (сервер шле) / `cmd` (клієнт шле) / `static` |

---

## 0. Глобальна оболонка

| # | Елемент макету | Селектор / id | WS | JSON path | Тип | Формат UI | Джерело backend | Оновлення |
|---|----------------|---------------|-----|-----------|-----|-----------|-------------------|-----------|
| G01 | Бренд «Arbitrator» | `.sidebar .brand` | — | — | — | текст | static | static |
| G02 | Nav Screener | `.nav-item[data-page=screener]` | — | — | — | текст | static | static |
| G03 | Nav Opportunity | `.nav-item[data-page=opportunity]` | — | — | — | текст | static | static |
| G04 | Nav Orders · **N** | `.nav-item[data-page=orders]` | `/ws/orders` | `orders.summary.open_count` | int | `Orders · {N}` | `OrdersSerializer` ← open arb groups | push `orders.summary` |
| G05 | Nav Settings | `.nav-item[data-page=settings]` | — | — | — | текст | static | static |
| G06 | Active nav dot | `.nav-item.active .dot` | — | — | — | CSS | client `showPage()` | static |

**Backend для G04**: при зміні open positions надсилати:

```json
{ "type": "orders.summary", "payload": { "open_count": 2, "closed_count": 14 } }
```

Підключення: `/ws/orders` або глобальний `/ws/app` (якщо обʼєднають канали).

---

## 1. Screener (`#page-screener`)

**WS endpoint**: `/ws/screener`  
**Push**: `screener.snapshot` кожні `Settings.screener_ws_push_seconds`

### 1.1 Topbar

| # | Елемент | Селектор | JSON path | Тип | Джерело | Оновлення |
|---|---------|----------|-----------|-----|---------|-----------|
| S01 | Заголовок «Screener» | `.topbar h1` | — | — | static | static |

### 1.2 Фільтри (`screener-params`)

| # | Елемент | Селектор | JSON path (read) | JSON path (write cmd) | Тип | Default | Джерело read | Джерело write | Оновлення |
|---|---------|----------|------------------|----------------------|-----|---------|--------------|---------------|-----------|
| S02 | Min 24h volume K USDT | input[label≈Min 24h] | `filters.min_volume_k_usdt` | `screener.set_filters` → `min_volume_k_usdt` | float | 0.0 | `Settings.default_min_quote_volume_kusdt` + runtime | user cmd | push + cmd |
| S03 | Stream min 24h USDT | input[label≈Stream min] | `filters.stream_min_volume_usdt` | `screener.set_filters` → `stream_min_volume_usdt` | float | 50000 | `Settings.stream_min_quote_volume_usdt` | user cmd → restart worker | push + cmd |
| S04 | Min spread % | input[label≈Min spread] | `filters.min_spread_pct` | `screener.set_filters` → `min_spread_pct` | float | 0.0 | `Settings.default_min_spread_pct` | user cmd | push + cmd |
| S05 | Кнопка Reconnect | `.screener-params .btn` | — | `screener.reconnect` | — | — | — | bump `reconnect_nonce`, restart `ScreenerStreamWorker` | cmd → `screener.action_result` |

**Відповідь на cmd**: `screener.action_result` `{ success, message }`.

### 1.3 Stream note (`.stream-note`)

| # | Частина тексту | JSON path | Тип | Формат | Джерело |
|---|----------------|-----------|-----|--------|---------|
| S06 | «Streaming: **N** symbols» | `symbol_count` | int | decimal | `len(stream_symbols)` з worker |
| S07 | «Exchanges: **a, b, …**» | `exchanges` | list[str] | comma-separated | `Settings.enabled_exchanges` |
| S08 | «Stream min volume: **X** USDT» | `filters.stream_min_volume_usdt` | float | `#,##0` USDT | filters |
| S09 | Статус підключення (не в макеті, рекомендовано) | `status` | str | `Connecting…` / `discovery` / `filtered` | `ScreenerStreamWorker.read_state()` |

Шаблон: `Streaming: {symbol_count} symbols · Exchanges: {exchanges.join(', ')} · Stream min volume: {stream_min_volume_usdt formatted}`

### 1.4 Таблиця — заголовки бірж

| # | Колонка | JSON path (meta) | Примітка |
|---|---------|------------------|----------|
| S10 | MEXC fut/spot | `exchanges` contains `mexc` | Порядок колонок = порядок `exchanges` |
| S11 | Bitget fut/spot | `exchanges` contains `bitget` | |
| S12 | Gate fut/spot | `exchanges` contains `gate` | |
| S13 | BingX fut/spot | `exchanges` contains `bingx` | |

### 1.5 Таблиця — рядок (`rows[i]`)

| # | Колонка UI | JSON path | Тип | Формат | Джерело backend |
|---|------------|-----------|-----|--------|-----------------|
| S14 | Asset | `rows[i].asset` | str | `BASE/USDT` | symbol universe display |
| S15 | {exchange} ф'ючерс | `rows[i].prices.{ex}.futures` | float \| null | 4–5 decimals, `.fut-col` | `Ticker.last` swap symbol |
| S16 | {exchange} спот | `rows[i].prices.{ex}.spot` | float \| null | `.spot-col` | `Ticker.last` spot symbol |
| S17 | Max | `rows[i].max_price` | float | tabular | max усіх non-null prices |
| S18 | Min | `rows[i].min_price` | float | tabular | min усіх non-null prices |
| S19 | Spread % | `rows[i].spread_pct` | float | `0.83`, class `pos` if > 0 | `SpreadCalculator` |
| S20 | Δ | `rows[i].spread_delta` | float | `+0.12` / `−0.03`, pos/neg | diff vs previous snapshot |
| S21 | Vol K USDT | `rows[i].volume_k_usdt` | float | integer-like | `Ticker.quoteVolume/1000` max across exchanges |
| S22 | Ф-Ф | `rows[i].strategy_profits.futures_futures` | float \| null | `+18.40` or `N/A`, pos/neg/na | `StrategyProfitService` |
| S23 | Ф-С 2б | `rows[i].strategy_profits.futures_spot_2ex` | float \| null | | |
| S24 | Ф-С 1б | `rows[i].strategy_profits.futures_spot_1ex` | float \| null | | |
| S25 | Ф Ф-Ф | `rows[i].strategy_profits.funding_ff` | float \| null | | |
| S26 | Ф Ф-С | `rows[i].strategy_profits.funding_fs` | float \| null | | |
| S27 | Ф різн. | `rows[i].strategy_profits.funding_diff_dates` | float \| null | | |
| S28 | Open Opportunity (дані для переходу) | `rows[i].short_exchange_id`, `rows[i].long_exchange_id` | str | — | best pair from spread calc |
| S29 | Кнопка Open Opportunity | — | cmd | client | `showPage('opportunity')` + connect `/ws/opportunity?symbol=&short=&long=` |

**Фільтрація рядків**: backend MAY фільтрувати за `min_volume_k_usdt` / `min_spread_pct` до відправки; або client-side з повного `rows`.

### 1.6 Порожній стан (не в макеті)

| # | Умова | JSON path | Backend |
|---|-------|-----------|---------|
| S30 | Немає рядків | `rows: []` | push порожній масив + `status` |

---

## 2. Opportunity (`#page-opportunity`)

**WS endpoint**: `/ws/opportunity?symbol={pair}&short={id}&long={id}`  
**Push**: `opportunity.snapshot` кожні `Settings.opportunity_poll_seconds`

### 2.1 Topbar

| # | Елемент | JSON path | Тип | Формат | Джерело |
|---|---------|-----------|-----|--------|---------|
| O01 | «Opportunity» | — | static | | |
| O02 | Символ | `symbol` | str | `DOGE/USDT` | URL path + payload |
| O03 | Badge S · {ex} | `short_exchange_id` | str | `badge short` «S · MEXC» | spread high leg |
| O04 | Badge L · {ex} | `long_exchange_id` | str | `badge long` | spread low leg |

### 2.2 Картка біржі (`ex-info-card`) — `exchange_cards[j]`

Два обʼєкти: один `side=short`, один `side=long`.

| # | Поле UI | JSON path | Тип | Формат | Джерело backend |
|---|---------|-----------|-----|--------|-----------------|
| O05 | Назва біржі | `exchange_cards[j].exchange_id` | str | display name | id → `NamedExchange` |
| O06 | Бейдж short/long | `exchange_cards[j].side` | enum | `short`/`long` | opportunity legs |
| O06b | Базовий актив (ідентифікація монети) | `exchange_cards[j].base_asset` | str | `DOGE` | `SymbolMarketInfo` / ccxt `market.base` |
| O06c | Уніфікований символ ccxt | `exchange_cards[j].market_symbol` | str | `DOGE/USDT:USDT` | ccxt unified symbol (однаковий на обох біржах) |
| O06d | Нативний ID біржі | `exchange_cards[j].native_market_id` | str \| null | `DOGE_USDT` / `DOGE-USDT` | ccxt `market.id` — різний per exchange |
| O06e | Обʼєм ордера (мін/макс) | `exchange_cards[j].min_order_volume_usdt`, `max_order_volume_usdt` | float \| null | `5/250000` (одна строка) | ccxt `limits.cost` або `amount × price` |
| O07 | Баланс | `exchange_cards[j].balance_usdt` | float \| null | `842.10 USDT` | `AccountStreamWorker` / `fetch_balance` |
| O08 | Фандінг % | `exchange_cards[j].funding_rate_pct` | float \| null | `−0.012%`, red if < 0 | `fetch_funding_rate` / ticker |
| O09 | Countdown фандінгу | `exchange_cards[j].funding_countdown_sec` | int \| null | `HH:MM:SS` client | next funding timestamp − now |
| O10 | Плече (select) | `exchange_cards[j].leverage` | int | `1x`…`100x` | position / `fetch_leverage`; write: `opportunity.set_leverage` |
| O11 | Комісія ф'ючерс | `exchange_cards[j].futures_fee` | str | `0.02 / 0.04%` | markets maker/taker |
| O12 | Комісія спот | `exchange_cards[j].spot_fee` | str | `0.10 / 0.10%` | markets |
| O13 | Ордери відкр./закр. | `open_orders_count`, `closed_orders_count` | int, int | `1 відкр. / 2 закр.` | arb markers + registry |

### 2.3 Таблиця стратегій (`strategy_rows[k]`)

| # | Колонка UI | JSON path | Тип | Формат |
|---|------------|-----------|-----|--------|
| O14 | Стратегія | `strategy_rows[k].strategy_label` | str | UA назва |
| O15 | id (внутр.) | `strategy_rows[k].strategy_id` | str | `futures_futures`, … |
| O16 | Спред | `strategy_rows[k].spread_pct` | float | `0.83%` |
| O17 | Ціни | `strategy_rows[k].prices_label` | str | `0.2124 / 0.2098` |
| O18 | Комісії | `strategy_rows[k].fees_usdt` | float | USDT |
| O19 | Фандінг | `strategy_rows[k].funding_usdt` | float | pos/neg class |
| O20 | Обʼєм | `strategy_rows[k].volume_usdt` | float | `320.00` |
| O21 | Плече | `strategy_rows[k].leverage` | int | `10x` |
| O22 | Заробіток | `strategy_rows[k].gross_profit_usdt` | float \| null | pos/na; `N/A` if unavailable |
| O23 | Витрати | `strategy_rows[k].costs_usdt` | float | з `costs_breakdown` у дужках |
| O24 | Розбивка витрат | `strategy_rows[k].costs_breakdown` | str | `(0.84 + 0.12 + 1.19)` |
| O25 | Чистий прибуток | `strategy_rows[k].net_profit_usdt` | float \| null | pos/neg/na; tooltip `unavailable_reason` |
| O26 | % до депозиту | `strategy_rows[k].percent_to_deposit` | float \| null | pos/neg/na; sorted desc on render |
| O27 | Причина N/A | `strategy_rows[k].unavailable_reason` | str \| null | tooltip only (`no_spot`, …) |

**Джерело**: `StrategyProfitService` × 6 strategies; volume/leverage з `params` + positions.

**Рядки (фіксований порядок `strategy_id`)**:

1. `futures_futures` — Фючерс-фючерс  
2. `futures_spot_2ex` — Фючерс-спот 2 біржі  
3. `futures_spot_1ex` — Фючерс-спот 1 біржа  
4. `funding_ff` — Фандінг фючерс-фючерс  
5. `funding_fs` — Фандінг фючерс-спот  
6. `funding_diff_dates` — Фандінг — різні дати  

### 2.4 Параметри (`params`)

| # | Поле UI | JSON path (read) | cmd `opportunity.set_params` | Тип | Readonly | Джерело |
|---|---------|------------------|------------------------------|-----|----------|---------|
| O26 | Стратегія (select) | `params.active_strategy_id` | `active_strategy_id` | str | ні | `OpportunityControls` |
| O27 | Набрано обʼєм | `params.accumulated_volume_usdt` | — | float | **так** | sum open position notional |
| O28 | Обʼєм до добору | `params.target_volume_usdt` | `target_volume_usdt` | float | ні | settings / user |
| O29 | Спред відкриття % | `params.open_spread_threshold_pct` | `open_spread_threshold_pct` | float | ні | `Settings.arb_open_spread_threshold_pct` |
| O30 | Спред закриття % | `params.close_spread_threshold_pct` | `close_spread_threshold_pct` | float | ні | `Settings.arb_close_spread_threshold_pct` |
| O31 | Сума добору (поле) | `params.accumulate_volume_usdt` | `accumulate_volume_usdt` | float | ні | controls |
| O32 | % добору (поле) | `params.accumulate_volume_pct` | `accumulate_volume_pct` | float | ні | controls |
| O32b | Сума закриття (поле) | `params.close_volume_usdt` | `close_volume_usdt` | float | ні | controls |
| O32c | % закриття (поле) | `params.close_volume_pct` | `close_volume_pct` | float | ні | controls |
| O31b | Авто добір | `params.auto_accumulate_enabled` | `auto_accumulate_enabled` | bool | ні | `Settings.arb_auto_open_enabled` |
| O32d | Авто скидання | `params.auto_close_enabled` | `auto_close_enabled` | bool | ні | `Settings.arb_auto_close_enabled` |

### 2.5 Добір / Закриття (client form → cmd)

| # | Елемент | cmd type | payload fields | Backend service |
|---|---------|----------|----------------|-----------------|
| O33 | Сума добору USDT | `opportunity.accumulate` | `volume_usdt` | `OpportunityAccumulateService` |
| O34 | % добору | `opportunity.accumulate` | `volume_pct` (optional) | calc from `target_volume_usdt` |
| O35 | Кнопки 10/25/50% | — | client fills % | — |
| O36 | Кнопка «Добрати» | `opportunity.accumulate` | | exchange REST orders |
| O37 | Сума закриття | `opportunity.close_partial` | `volume_usdt` | `ArbitrageCloseService` |
| O38 | % закриття | `opportunity.close_partial` | `volume_pct` | |
| O39 | Кнопка «Закрити» | `opportunity.close_partial` | | |
| O40 | «Закрити всі позиції» | `opportunity.close_all` | `{}` | `ArbitrageCloseService` full |

**Відповідь**: `opportunity.action_result` `{ action, success, message }`.

### 2.6 Ордери по символу (`orders[m]` — той самий `OrderGroupDto`)

Фільтр chips — **client-only** по `orders[m].status`; backend шле всі групи для symbol.

| # | Колонка parent | JSON path | Тип | Формат |
|---|----------------|-----------|-----|--------|
| O41 | Asset | `orders[m].asset` | str | |
| O42 | Стратегія | `orders[m].strategy_code` | str | `Ф-Ф`, `Ф-С 2б` |
| O43 | Біржі | `short_exchange_id`, `long_exchange_id` | str | badges S·/L· |
| O44 | Відкрито | `orders[m].opened_at` | str | `DD.MM HH:MM` |
| O45 | Закрито | `orders[m].closed_at` | str \| null | `—` if null |
| O46 | Плече | `orders[m].leverage` | int | `10x` |
| O47 | Обʼєм | `orders[m].volume_usdt` | float | |
| O48 | Вхід (parent) | `orders[m].entry_price` | float \| null | often `—` |
| O49 | Вихід (parent) | `orders[m].exit_price` | float \| null | |
| O50 | Комісія | `orders[m].fees_usdt` | float | |
| O51 | Фандінг | `orders[m].funding_usdt` | float | neg allowed |
| O52 | PnL | `orders[m].pnl_usdt` | float | pos/neg |
| O53 | Статус | `orders[m].status` | enum | `open`/`closed` → badge |

**Child leg** `orders[m].legs[n]`:

| # | Колонка | JSON path | Тип |
|---|---------|-----------|-----|
| O54 | Біржа+side | `legs[n].exchange_id`, `legs[n].side` | str, enum |
| O55 | Плече | `legs[n].leverage` | int |
| O56 | Обʼєм | `legs[n].volume_usdt` | float |
| O57 | Вхід | `legs[n].entry_price` | float |
| O58 | Вихід | `legs[n].exit_price` | float \| null |
| O59 | Комісія | `legs[n].fees_usdt` | float |
| O60 | Фандінг | `legs[n].funding_usdt` | float |
| O61 | PnL | `legs[n].pnl_usdt` | float |

**Джерело**: `OpportunityRegistryService`, `ArbitragePnlService`, `arb_markers`, account positions.

### 2.7 Графік (`chart`)

| # | Елемент | JSON path | Тип | Формат | Джерело |
|---|---------|-----------|-----|--------|---------|
| O62 | Вікно | `chart.window_seconds` | int | 60 | `Settings.opportunity_chart_window_seconds` |
| O63 | Серія MEXC fut | `chart.series[].key=mexc_fut` | ChartSeriesDto | color `#c0392b` | `OpportunityStreamWorker.price_ring` |
| O64 | MEXC spot | `key=mexc_spot` | | dash `#e67e22` | |
| O65 | BingX fut | `key=bingx_fut` | | `#1d9e75` | |
| O66 | BingX spot | `key=bingx_spot` | | dash `#52be80` | |
| O67 | Last price (legend) | `series[].last_price` | float | `#ch-mexc-fut` ids | last tick |
| O68 | Точки лінії | `series[].points[]` | `{t: int, price: float}` | t = sec ago | ring buffer |
| O69 | Підпис «реальний час» | — | static | | |

**series[] обовʼязкові поля**: `key`, `exchange_id`, `market_type`, `color`, `dashed`, `last_price`, `points`.

### 2.8 Стакани (`books[b]`) — 4 панелі

Порядок у масиві (рекомендовано):

1. short exchange + `futures`  
2. short exchange + `spot`  
3. long exchange + `futures`  
4. long exchange + `spot`  

| # | Елемент UI | JSON path | Тип | Формат | Джерело |
|---|------------|-----------|-----|--------|---------|
| O70 | Заголовок біржі | `books[b].exchange_id` + `side_role` | | `MEXC` + badge | |
| O71 | Тип fut/spot | `books[b].market_type` | enum | badge `фючерс`/`спот` | |
| O72 | 24h vol · range | `volume_24h_label`, `range_label` | str | `908K · 0.2088–0.2506` | ticker 24h |
| O73 | Ask price | `books[b].asks[l].price` | float | red | `OrderBookSnapshot` |
| O74 | Ask amount | `books[b].asks[l].amount` | float | `108K` compact | |
| O75 | Ask total | `books[b].asks[l].total` | float | `23K` | cumulative |
| O76 | Ask fill bar % (cum) | `books[b].asks[l].fill_pct` | float 0–100 | CSS width світла смуга | `total / max(total)` |
| O76b | Ask level bar % | `books[b].asks[l].amount_fill_pct` | float 0–100 | CSS width темна смуга | `amount / max(total)` |
| O77 | Mid price (ask side) | `books[b].mid_price` | float | between sides | best bid/ask |
| O78 | Спред книги | `books[b].spread_pct` | float | `спред · 0.716%` | (ask−bid)/bid |
| O79 | Bid price/amount/total/fill | `books[b].bids[l].*` | | green | |
| O80 | Глибина | len(asks), len(bids) | | 10 levels | `Settings.opportunity_order_book_depth` |

---

## 3. Orders (`#page-orders`)

**WS endpoint**: `/ws/orders`  
**Push**: `orders.snapshot` (on connect + on change), `orders.summary` (counts)

### 3.1 Topbar

| # | Елемент | JSON path | Тип | Формат |
|---|---------|-----------|-----|--------|
| R01 | «N відкритих арбітражі» | `summary.open_count` | int | у заголовку |
| R02 | «2 open · 14 closed» | `summary.open_count`, `summary.closed_count` | int | `.status` |
| R03 | Kebab ⋮ | — | — | out of scope |

### 3.2 Фільтри chips

| # | Chip | cmd | payload |
|---|------|-----|---------|
| R04 | Усі | `orders.set_filter` | `{ "filter": "all" }` |
| R05 | Відкриті | `orders.set_filter` | `{ "filter": "open" }` |
| R06 | Закриті | `orders.set_filter` | `{ "filter": "closed" }` |

Backend MAY echo `filter` у наступному `orders.snapshot` або client фільтрує локально.

### 3.3 Таблиця `groups[g]`

Ті самі поля що **O41–O61**, плюс:

| # | Елемент | JSON path | Умова |
|---|---------|-----------|-------|
| R07 | Кнопка Opportunity | `groups[g].symbol`, `short_exchange_id`, `long_exchange_id` | лише `status=open` |
| R08 | Expand caret | — | client UI |

**Повний snapshot**:

```json
{
  "type": "orders.snapshot",
  "payload": {
    "summary": { "open_count": 2, "closed_count": 14 },
    "filter": "all",
    "groups": [ /* OrderGroupDto[] */ ]
  }
}
```

---

## 4. Settings (`#page-settings`)

**WS endpoint**: `/ws/settings`  
**Push**: `settings.snapshot` on connect  
**Cmd**: `settings.save_exchange`

| # | Поле UI | JSON path (read) | cmd payload | Тип | Формат |
|---|---------|------------------|-------------|-----|--------|
| T01 | MEXC API key | `exchanges[].api_key_masked` where `exchange_id=mexc` | `settings.save_exchange` | str | `••••••••••••` |
| T02 | BingX API key | id=bingx | | | |
| T03 | Bitget API key | id=bitget | | | |
| T04 | Gate API key | id=gate | | | |
| T05 | configured flag | `exchanges[].configured` | — | bool | enable fields |
| T06 | has_secret | `exchanges[].has_secret` | — | bool | UI hint |
| T07 | has_password (bitget) | `exchanges[].has_password` | — | bool | show password field |

**save_exchange payload**:

```json
{
  "exchange_id": "mexc",
  "api_key": "...",
  "api_secret": "...",
  "api_password": ""
}
```

**Відповідь**: `settings.action_result` → новий `settings.snapshot` (masked).

---

## 5. Зведена матриця WS messages → payload root

| Message type | Direction | Payload root object | Екран |
|--------------|-----------|---------------------|-------|
| `screener.snapshot` | S→C | `ScreenerSnapshotDto` | Screener |
| `screener.action_result` | S→C | `{ success, message }` | Screener |
| `screener.set_filters` | C→S | filters object | Screener |
| `screener.reconnect` | C→S | `{}` | Screener |
| `opportunity.snapshot` | S→C | `OpportunitySnapshotDto` | Opportunity |
| `opportunity.action_result` | S→C | `{ action, success, message }` | Opportunity |
| `opportunity.set_params` | C→S | partial `OpportunityParamsDto` | Opportunity |
| `opportunity.accumulate` | C→S | `{ volume_usdt?, volume_pct? }` | Opportunity |
| `opportunity.close_partial` | C→S | same | Opportunity |
| `opportunity.close_all` | C→S | `{}` | Opportunity |
| `opportunity.set_leverage` | C→S | `{ exchange_id, leverage }` | Opportunity |
| `orders.snapshot` | S→C | `{ summary, filter, groups }` | Orders + sidebar |
| `orders.summary` | S→C | `OrdersSummaryDto` | Sidebar G04 |
| `orders.set_filter` | C→S | `{ filter }` | Orders |
| `settings.snapshot` | S→C | `{ exchanges: SettingsExchangeDto[] }` | Settings |
| `settings.save_exchange` | C→S | `SettingsExchangeUpdateDto` | Settings |
| `settings.action_result` | S→C | `{ success, exchange_id }` | Settings |

---

## 6. Backend services checklist (що реалізувати)

| Service | Що віддає в UI |
|---------|----------------|
| `ScreenerStreamWorker` | raw tickers → S14–S16 |
| `ScreenerTableService` | rows S14–S28 |
| `StrategyProfitService` | S22–S27, O14–O25 |
| `SpreadCalculator` | S19, O03–O04 |
| `OpportunityStreamWorker` | O62–O80 (books, chart points) |
| `AccountStreamWorker` | O07, O13, orders legs |
| `ExchangeAccountService` | balance fallback, fees O11–O12 |
| `SymbolMarketInfoService` | O06b–O06f (market identity + order volume limits) |
| `OpportunityRegistryService` | O41–O61, R07 |
| `ArbitragePnlService` | PnL fields |
| `OpportunityAccumulateService` | O33–O36 cmd |
| `ArbitrageCloseService` | O37–O40 cmd |
| `ArbMarkersRepository` | order counts, history |
| Settings runtime | T01–T07 |

---

## 7. Повний приклад `opportunity.snapshot` (скорочено)

```json
{
  "type": "opportunity.snapshot",
  "payload": {
    "symbol": "DOGE/USDT",
    "short_exchange_id": "mexc",
    "long_exchange_id": "bingx",
    "status": "streaming",
    "exchange_cards": [
      {
        "exchange_id": "mexc",
        "side": "short",
        "base_asset": "DOGE",
        "market_symbol": "DOGE/USDT:USDT",
        "native_market_id": "DOGE_USDT",
        "min_order_volume_usdt": 5.0,
        "max_order_volume_usdt": 250000.0,
        "balance_usdt": 842.10,
        "funding_rate_pct": -0.012,
        "funding_countdown_sec": 8075,
        "leverage": 10,
        "futures_fee": "0.02 / 0.04%",
        "spot_fee": "0.10 / 0.10%",
        "open_orders_count": 1,
        "closed_orders_count": 2
      }
    ],
    "strategy_rows": [],
    "params": {
      "active_strategy_id": "futures_futures",
      "accumulated_volume_usdt": 320.0,
      "target_volume_usdt": 500.0,
      "open_spread_threshold_pct": 0.7,
      "close_spread_threshold_pct": 0.05,
      "accumulate_volume_usdt": 50.0,
      "accumulate_volume_pct": 10.0,
      "close_volume_usdt": 50.0,
      "close_volume_pct": 10.0,
      "auto_accumulate_enabled": true,
      "auto_close_enabled": false
    },
    "books": [],
    "chart": { "window_seconds": 60, "series": [] },
    "orders": []
  }
}
```

Цей документ — **єдиний референс для backend**: якщо елемент є в макеті, він має рядок у таблицях вище.
