# Стратегія: Ф'ючерс–Ф'ючерс (курсовий спред)

**ID**: `futures_futures`
**UI-колонка**: Ф-Ф
**Секція механіки**: §3
**Статус**: Реалізовано (live auto-trade)

---

## Суть

Long де дешевше, short де дорожче — на двох різних біржах. Прибуток від **зближення** ціни між біржами (convergence курсового спреду).

---

## Формула прибутку

```
прибуток = (спред_входу − спред_виходу) × обʼєм / 100 − комісія − фандінг
```

| Змінна | Визначення |
|--------|-----------|
| `спред_входу` | `(short_bid − long_ask) / long_ask × 100%` |
| `спред_виходу` | `(short_ask − long_bid) / long_bid × 100%` |
| `обʼєм` | Notional USDT (short leg) |
| `комісія` | 4 угоди × taker_fee × notional |
| `фандінг` | Нетто витрати: `max(заплатили − отримали, 0)` |

---

## Умови входу (auto-trade)

| # | Умова | Налаштування | Значення за замовч. |
|---|-------|-------------|-------------------|
| 1 | Спред ≥ поріг | `SCREENER_AUTO_TRADE_OPEN_SPREAD_PCT` | 3.0% |
| 2 | Спред < аномалія | `ANOMALY_MAX_SPREAD_PCT` | 20.0% |
| 3 | Order book depth ≥ notional × 2 в межах 0.4% | Хардкод | 2× / 0.4% |
| 4 | Estimated fill spread ≥ поріг | Розраховується з ордер буку | = open_spread |
| 5 | Token identity match | `TokenIdentityService` | Немає конфлікту |
| 6 | Base asset однаковий | `SymbolMarketInfo.base_asset` | — |
| 7 | Market info кеш наявний | Обидві біржі | — |
| 8 | Min notional задоволено | `max(exchange_min_A, exchange_min_B, floor)` | — |
| 9 | Cooldown після фейлу | `OPEN_FAIL_COOLDOWN_SEC` | 120 с |
| 10 | Максимум позицій не вичерпано | `SCREENER_AUTO_TRADE_MAX_POSITIONS` | 3 |
| 11 | Ticker inner spread не занадто широкий | `TICKER_MAX_INNER_SPREAD_PCT` | 1.0% |

---

## Pre-trade slippage estimation

Перед відкриттям система проходить по ордер буку для обсягу notional:
- Short leg: VWAP з bids (продаємо в біди)
- Long leg: VWAP з asks (купуємо по асках)

Якщо `estimated_fill_spread < open_spread_pct` → вхід блокується.

---

## Post-fill guard

Одразу після заповнення обох ніг:
1. Запит реальних entry price з позицій обох бірж
2. Розрахунок `actual_spread = (short_entry - long_entry) / long_entry × 100`
3. Якщо `actual_spread < LIVE_AUTO_TRADE_POST_FILL_MIN_SPREAD_PCT` (0.5%) → **закриваємо негайно**

---

## Умови виходу

| # | Умова | Налаштування |
|---|-------|-------------|
| 1 | Exit spread ≤ close threshold | `SCREENER_AUTO_TRADE_CLOSE_SPREAD_PCT` = 0.05% |

Exit spread = `(short_ask − long_bid) / long_bid × 100%`

Якщо тікер відсутній у скрінері — система запитує order book REST.

---

## DCA (донабір позиції)

Якщо позиція вже відкрита і спред виріс — можна донабрати:

| # | Умова | Налаштування | Значення |
|---|-------|-------------|----------|
| 1 | Поточний спред ≥ entry_spread + step | `LIVE_AUTO_TRADE_DCA_SPREAD_STEP_PCT` | 1.0% |
| 2 | Шарів DCA < максимуму | `LIVE_AUTO_TRADE_DCA_MAX_LAYERS` | 1 |
| 3 | Ліквідність в буку достатня для 2× обсягу | Depth check | 2× notional |
| 4 | Estimated fill spread OK | Pre-trade estimation | ≥ open_spread |
| 5 | Відстань до ліквідації > порогу | `LIVE_AUTO_TRADE_DCA_MIN_LIQ_DISTANCE_PCT` | 10% |
| 6 | Фандінг не через 30 хв | `LIVE_AUTO_TRADE_DCA_FUNDING_SKIP_SECONDS` | 1800 с |
| 7 | Funding rate не критичний | `|rate| < 1%` | — |

**Обсяг DCA** = 2× базовий notional. Кількість токенів ідентична на обох біржах (harmonize).

**Визначення вже зроблених DCA** (стійке до рестарту): при старті порівнюється реальний розмір позиції з базовим notional. Якщо `position_usdt > 1.5 × base_notional` → вважається що DCA вже зроблено.

---

## Гарантія ідентичності обсягу (harmonize)

Обидві ноги відкриваються з **однаковою кількістю токенів**:
1. Розрахунок цільових tokens = notional / price
2. Конвертація в контракти кожної біржі (з урахуванням contract_size)
3. Floor до amount_step (precision.amount) кожної біржі
4. Мінімум з двох → фінальний обсяг
5. Long leg виводиться з фактичного fill short leg (delta-neutral)

---

## Rollback при провалі другої ноги

Якщо long leg не відкрився після успішного short:
- `EXECUTION_ROLLBACK_ENABLED=true` → закриваємо short (компенсація)
- Pair не додається в open_pairs
- Cooldown `OPEN_FAIL_COOLDOWN_SEC` блокує повторний вхід

---

## Liquidation guard

Окремий фоновий сервіс `LiveLiquidationGuardService`:
- Кожні 5 с перевіряє всі відкриті позиції
- Апроксимація ліквідаційної ціни: `entry × (1 ± 1/leverage × (1 − 0.5%))`
- Якщо margin consumed ≥ 80% → close_all пари

---

## Потік даних

```
Screener WS stream (watch_tickers) 
  → LiveAutoTrader._tick() кожні CHECK_SECONDS
    → candidates: sort by spread desc
    → close pass: exit_spread ≤ threshold → close_all
    → DCA pass: spread widened → accumulate
    → open pass: spread ≥ threshold → validation → execute
      → HedgedExecutionService.open()
        → short first → long derived from short fill
        → post_fill_guard()
```

---

## Налаштування (.env)

```env
SCREENER_AUTO_TRADE_OPEN_SPREAD_PCT=3.0
SCREENER_AUTO_TRADE_CLOSE_SPREAD_PCT=0.05
SCREENER_AUTO_TRADE_MAX_POSITIONS=3
SCREENER_AUTO_TRADE_NOTIONAL_USDT=100.0
SCREENER_AUTO_TRADE_CHECK_SECONDS=2.0
SCREENER_AUTO_TRADE_UNHEDGED_TIMEOUT_SECONDS=10.0
LIVE_AUTO_TRADE_POST_FILL_MIN_SPREAD_PCT=0.5
LIVE_AUTO_TRADE_DCA_SPREAD_STEP_PCT=1.0
LIVE_AUTO_TRADE_DCA_MAX_LAYERS=1
LIVE_AUTO_TRADE_DCA_MIN_LIQ_DISTANCE_PCT=10.0
LIVE_AUTO_TRADE_DCA_FUNDING_SKIP_SECONDS=1800.0
ANOMALY_MAX_SPREAD_PCT=20.0
SLIPPAGE_MAX_PCT=0.5
EXECUTION_ROLLBACK_ENABLED=true
LEG_IMBALANCE_TOLERANCE_PCT=1.0
OPEN_FAIL_COOLDOWN_SEC=120.0
```

---

## Файли реалізації

| Файл | Роль |
|------|------|
| `application/live_auto_trader.py` | Головний тік: open/close/DCA логіка |
| `application/hedged_execution_service.py` | Виконання ордерів, harmonize, rollback |
| `application/screener_auto_trader.py` | Paper-режим аналог |
| `application/live_liquidation_guard_service.py` | Захист від ліквідації |
| `config/settings.py` | Всі параметри |
| `domain/symbol_market_info.py` | Market info + amount_step |

---

## Історія змін

| Дата | Зміна |
|------|-------|
| 2026-07-03 | Додано harmonize amounts (виправлення імбалансу ніг) |
| 2026-07-03 | Gate/Bitget position mapper fix (closed positions) |
| 2026-07-04 | Pre-trade slippage estimation |
| 2026-07-04 | Post-fill guard (close if spread < 0.5%) |
| 2026-07-04 | DCA logic (accumulate at +1% spread) |
| 2026-07-04 | Depth threshold tightened to 0.4% |
