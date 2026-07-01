# Strategy Data Catalog (002-strategy-engine)

**Purpose**: точно зафіксувати, **які дані потрібні кожній стратегії, звідки вони беруться
(біржа/UI), для чого** і **як рухаються** браузер ↔ FastAPI ↔ ядро. Це контракт фази `plan`
(деталі реалізації), а не `spec.md` (WHAT/WHY).

> Правило проєкту: live-режим — **лише біржові дані**, жодних вигаданих значень. Якщо поле
> недоступне з біржі → стратегія, що його потребує, позначається `N/A` (див. `spec.md` FR-002/FR-003).
> ccxt-поля нижче звірені з документацією ccxt (Context7): ticker має `bid/ask/last/quoteVolume`;
> funding rate structure має `fundingRate`, `fundingTimestamp`/`fundingDatetime`, `nextFundingRate`,
> `markPrice`, `indexPrice` (методи `fetch_funding_rate` / `fetch_funding_rates`).

---

## 1. Дві площини даних (не плутати)

| Площина | Учасники | Канал | Зміст |
|---------|----------|-------|-------|
| **UI ↔ сервер** | Браузер ↔ `presentation/` | WebSocket `/ws/*` | Снапшоти стратегій + команди оператора (manual mode) |
| **Сервер ↔ біржа** | `application/` + `exchanges/` | ccxt.pro `watch_*` (пріоритет), ccxt `fetch_*`/orders (fallback) | Сирі ринкові й акаунт-дані, виконання ордерів |

Браузер **ніколи** не ходить на біржу напряму. Manual-команда: браузер → `/ws/opportunity` →
`*_ws_handler` → `application/*_service` → ядро/біржа.

---

## 2. Інвентар сирих біржових входів

Позначення статусу: ✅ вже є в коді · 🔶 є частково · ❌ потрібно додати в цій фічі.

| Вхід (нормалізований) | Джерело ccxt (метод → поле) | Канал | Свіжість | Статус у проєкті |
|----|----|----|----|----|
| Futures `last` | `watch_tickers`/`watch_ticker` → `last` | WS | тік | ✅ `Ticker.last` |
| Futures `bid`/`ask` | `watch_tickers`/`watch_ticker` → `bid`/`ask` | WS | тік | ❌ `Ticker` не зберігає bid/ask — **додати** |
| Futures 24h `quoteVolume` | ticker → `quoteVolume` | WS | тік | ✅ `Ticker.quote_volume_24h` |
| Spot `bid`/`ask`/`last` | spot-клієнт `watch_ticker` (defaultType=spot) → `bid`/`ask`/`last` | WS | тік | ❌ споту немає — **додати spot data path** |
| Funding `rate` (поточний period) | ticker → `fundingRate` **або** `fetch_funding_rate` → `fundingRate` | WS/REST | тік / періодично | 🔶 `Ticker.funding_rate` є; точність/повнота через REST |
| Funding `next settlement time` | `fetch_funding_rate(s)` → `fundingTimestamp`/`fundingDatetime` (+ `nextFundingRate`) | REST | періодично | ❌ **додати** (потрібно для countdown + §5) |
| Futures fees maker/taker | `load_markets()` → `markets[symbol].maker/.taker` (за потреби `fetch_trading_fee`) | REST (1×, оновлення рідко) | при старті/рідко | 🔶 markets вантажаться; fee-снапшот **додати** |
| Spot fees maker/taker | spot `load_markets()` → `markets[symbol].maker/.taker` | REST | при старті/рідко | ❌ **додати** |
| Order book (глибина) | `watch_order_book(symbol, limit)` → `bids`/`asks` | WS | тік | ✅ `OrderBookSnapshot` |
| USDT balance | `watch_balance`/`fetch_balance` → `USDT.total` | WS/REST | тік/поллінг | ✅ `watch_usdt_balance` |
| Open positions / fills | `watch_positions`/`fetch_positions`; `fetch_my_trades` | WS/REST | тік/поллінг | ✅ `watch_open_positions`, мапер |
| Realized funding (історія) | `fetch_funding_history` → `amount` | REST | по запиту | ✅ `fetch_funding_since` |
| Виконання ордера | `create_order(market, reduceOnly?)` + `clientOrderId` | REST | по дії | ✅ `open_market_position`/`close_market_position` (тільки futures) |
| Spot-ордери (для §1,§2,§6,§7 хеджа) | spot-клієнт `create_order` | REST | по дії | ❌ **додати** spot execution |

**Похідні (рахуються в ядрі, не з біржі):** basis, cross-basis, курсовий спред, funding-spread,
notional, gross, costs, net, `% до депозиту`, advisory-скор. Це формули над сирими входами вище.

---

## 3. Матриця «стратегія → потрібні дані → для чого»

Конвенція котирувань (двобіржові): вхід short=`bid`, long=`ask`; вихід short=`ask`, long=`bid`.
«✔ обов'язково» — без цього стратегія `N/A`. «◦ опц.» — покращує точність (глибина/сліпедж).

| Дані \\ Стратегія | `futures_futures` (Ф-Ф §3) | `futures_spot_2ex` (Ф-С 2б §2) | `futures_spot_1ex` (Ф-С 1б §1) | `funding_ff` (Ф Ф-Ф §4) | `funding_fs` (Ф Ф-С §6/§7) | `funding_diff_dates` (Ф різн. §5) |
|----|----|----|----|----|----|----|
| Futures bid/ask (2 біржі) | ✔ спред цін | ✔ нога Y | — | ✔ хедж-ноги | ✔ earn-нога | ✔ earn+hedge |
| Futures bid/ask (1 біржа) | — | — | ✔ нога futures | — | ✔ (варіант 1 біржа) | — |
| Spot bid/ask | — | ✔ нога X (basis) | ✔ нога spot (basis) | — | ✔ spot-хедж | — |
| Funding rate (поточний) | — | — | — | ✔ funding-spread | ✔ дохід earn-ноги | ✔ |rate_early| |
| Funding next time | — | — | — | ✔ вікно входу | ✔ вікно входу | ✔ **різниця часів** (ядро стратегії) |
| Futures fees maker/taker | ✔ commission | ✔ | ✔ | ✔ | ✔ | ✔ |
| Spot fees | — | ✔ | ✔ | — | ✔ | — |
| Order book depth | ◦ сліпедж | ◦ | ◦ | ◦ | ◦ | ◦ |
| Balance/margin | ✔ `% до депозиту`/розмір | ✔ | ✔ | ✔ | ✔ | ✔ |

**Для чого служить кожен клас даних:**
- **bid/ask** — точний спред/basis саме на тих цінах, за якими реально виконаємось (не `last`).
- **spot** — друга нога basis-стратегій; без споту §1/§2/§6/§7 не існують → `N/A`.
- **funding rate** — джерело доходу/витрати funding-стратегій; знак визначає сторону earn-ноги.
- **funding next time** — коли відкривати (вікно 1–5 хв) і коли закривати (після 1 settlement);
  для §5 — сама різниця часів між біржами є джерелом стратегії.
- **fees** — реальні комісії за 4 угоди; впливають на поріг прибутковості при малому спреді.
- **order book** — перевірка, що цільовий обсяг влазить у глибину (сліпедж/блокування авто-входу).
- **balance/margin** — знаменник `% до депозиту` і ліміт на розмір позиції.

---

## 4. Дані з фронту для manual-режиму (рішення оператора)

Усе нижче вводиться у браузері й **передається через FastAPI WebSocket у ядро** як команда
(payload). Жодних обчислень у браузері — лише введення/відображення.

| UI-елемент (Opportunity) | Команда WS (`type`) | Поле payload → параметр ядра | Для чого ядру |
|----|----|----|----|
| Select «Стратегія» | `opportunity.set_params` | `active_strategy_id` | Яку стратегію рахувати/торгувати, синхронізує таблицю |
| «Обʼєм до добору» | `opportunity.set_params` | `target_volume_usdt` | Notional цілі; база для % і розміру ордера |
| «Спред відкриття, %» | `opportunity.set_params` | `open_spread_threshold_pct` | Поріг сигналу open / авто-добору |
| «Спред закриття, %» | `opportunity.set_params` | `close_spread_threshold_pct` | Поріг сигналу close / авто-скидання |
| Select «Плече» | `opportunity.set_leverage` | `leverage` (+ `exchange_id`) | Розрахунок маржі/розміру; `set_leverage` на біржі |
| «Добір»: сума/відсоток + кнопки 10/25/50% | `opportunity.accumulate` | `amount_usdt` **або** `percent` | Обсяг реального добору на обох ногах |
| «Закриття»: сума/відсоток | `opportunity.close_partial` | `amount_usdt` **або** `percent` | Обсяг часткового закриття обох ніг |
| «Закрити всі позиції» | `opportunity.close_all` | — | Повне хеджоване закриття по символу |
| «Авто добір» (checkbox) | `opportunity.set_params` | `auto_accumulate_enabled` | Дозвіл авто-входу за сигналом+чеклістом |
| «Авто скидання» (checkbox) | `opportunity.set_params` | `auto_close_enabled` | Дозвіл авто-виходу за сигналом |
| Вибір short/long біржі (з Screener/бейджі) | параметр відкриття `/ws/opportunity/{symbol}?short=&long=` | `short_exchange_id`, `long_exchange_id` | Які біржі утворюють пару ніг |

Screener-команди (контекст вибору): `screener.set_filters` (`min_volume_k_usdt`,
`stream_min_volume_usdt`, `min_spread_pct`), `screener.reconnect`. Формат повідомлень — спільний
з `001-mockup-ui/contracts/ws-messages.md` (`{type, payload}`).

**Валідація вводу з фронту в ядрі (обов'язково):** сума/відсоток у межах допустимого; обсяг ≤
доступна маржа; обсяг ≤ глибина книги (інакше попередження/блок); `active_strategy_id` валідний;
біржі різні там, де стратегія цього вимагає. Невалідний ввід → `action_result(success=false, reason)`.

---

## 5. Потоки даних

### 5.1 Інгест (біржа → кеш)
```
exchanges/ ccxt.pro watch_*  ──>  application/*StreamWorker (фоновий потік)
        │                               │  нормалізація у domain-моделі (Ticker/Book/Funding/Fees)
        ▼                               ▼
   біржові події            in-process L1 кеш останніх снапшотів (dict + immutable моделі)
```

### 5.2 Розрахунок + пуш (кеш → браузер)
```
L1 кеш ──> StrategyEngine (stateless калькулятори, Decimal)
              │  рахує лише зачеплені символи (інкрементально)
              ▼
        StrategyResult/Table ──> serializer ──> DTO (StrategyProfitsDto / StrategyCalculationRowDto)
              ▼
        WS push: screener.snapshot|delta, opportunity.snapshot (UiDeltaEncoder для дельт)
```

### 5.3 Manual-команда (браузер → виконання)
```
Браузер (ввід) ──WS──> *_ws_handler ──> application/*_service
        │ перевірка чекліста + валідація вводу
        ▼
   ExecutionService ──> exchanges/ create_order (futures + spot), clientOrderId (ідемпотентність)
        ▼
   стан позиції з біржових fills/positions (не з наміру) ──> кеш ──> WS push (оновлення)
   при збої однієї ноги ──> компенсація/відкат + action_result(reason)
```

---

## 6. Модель кешу та свіжості

- **L1 in-process** на гарячому шляху (без серіалізації/мережі) — найшвидший варіант для single-process.
- Кожен запис кешу несе `recv_time`/`timestamp_ms`; **max age** (нове поле `Settings`) визначає
  «несвіжість». Несвіжі дані не йдуть у розрахунок/торгівлю → відповідна стратегія `N/A`.
- Орієнтовні політики (фінал — у `plan`/`Settings`): ticker — секунди; order book top — ~1–2 с;
  funding rate — до наступного settlement; fees — оновлення рідко (хвилини/години).
- **Redis/зовнішній кеш** — лише опційний адаптер за інтерфейсом у `domain/` на майбутнє
  (мультипроцес), **не** залежність цієї фічі.

---

## 7. Розриви відносно поточного коду (для `plan`)

1. `Ticker` не має `bid/ask` → додати поля (джерело ccxt ticker `bid`/`ask`).
2. Немає спот-каналу → окремий ccxt-клієнт/гейтвей `defaultType=spot` (ціни + fees + ордери).
3. Немає funding next time → `fetch_funding_rate(s)` (поля `fundingTimestamp`/`fundingDatetime`,
   `nextFundingRate`); за можливості `watch*`, інакше періодичний REST.
4. Немає fee-снапшоту → структура комісій з `markets[symbol].maker/.taker` (futures+spot).
5. Live screener serializer віддає «not implemented» → реалізувати серіалізацію `StrategyProfitsDto`.
6. Виконання лише futures → додати spot-ордери та хеджовану логіку open/accumulate/close + відкат.
7. Усі нові пороги/вік/політики → поля `Settings` (без магічних констант).

---

## 8. Контракт «no fabrication» по кожному полю

- Якщо `bid/ask` відсутні (немає тікера/несвіжий) → стратегії, що їх потребують, `N/A`.
- Якщо споту немає для символу/біржі → §1/§2/§6/§7 `N/A` (рахуємо лише `futures_futures`, `funding_ff`).
- Якщо `fundingTimestamp` прострочений/відсутній → funding-стратегії `N/A`, вхід блокується.
- Якщо fee недоступні з біржі → не підставляти константу; стратегія `N/A` (комісія обов'язкова в net).
- Набраний обсяг/ціни входу — завжди з біржових fills/positions, ніколи з очікувань.
