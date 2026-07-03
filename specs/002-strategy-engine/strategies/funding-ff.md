# Стратегія: Funding — спред ставок (Ф-Ф)

**ID**: `funding_ff`
**UI-колонка**: Ф Ф-Ф
**Секція механіки**: §4
**Статус**: Не реалізовано (розрахунок є в strategy_table_service, execution — ні)

---

## Суть

Дві біржі, **один settlement**. Заробляємо на **різниці funding rates** між біржами. Earn leg на біржі з вищим |rate|, hedge — протилежна позиція на іншій біржі. **1 period → close.**

---

## Формула прибутку

```
прибуток = funding_spread × обʼєм / 100 − комісія − net_funding_cost
```

| Змінна | Визначення |
|--------|-----------|
| `funding_spread` | `|rate_A| − |rate_B|` (A = earn, B = hedge) |
| `спред_виходу` | 0 (закриваємо після 1 period) |
| `обʼєм` | Notional USDT |
| `комісія` | 4 угоди futures (open/close обох ніг) |
| `net_funding_cost` | Скільки заплатили на hedge − скільки отримали на earn |

---

## Механіка

1. За 1–5 хв до settlement: перевірити `funding_spread ≥ 1%`
2. Earn leg: long/short за знаком rate (отримує funding)
3. Hedge leg: протилежна позиція на іншій біржі
4. 1 settlement відбувається
5. Close обидві ноги

**Яка сторона earn:**
| rate_A | Earn leg A | Hedge leg B |
|--------|-----------|-------------|
| > 0 | Short (отримує від лонгів) | Long |
| < 0 | Long (отримує від шортів) | Short |

---

## Умови входу (план)

| # | Умова | Опис |
|---|-------|------|
| 1 | `funding_spread ≥ 1%` | Мін вхід |
| 2 | Час до settlement: 1–5 хв | Entry window |
| 3 | Обидві біржі мають один час settlement | Синхронний funding |
| 4 | `funding_spread × volume − fees > 0` | Net profitable |
| 5 | Order book depth достатня | Обидві сторони |
| 6 | Спред цін між біржами < anomaly | Не аномальний token |

---

## Умови виходу

| # | Умова |
|---|-------|
| 1 | Settlement відбувся → close обидві ноги |
| 2 | Aварійний: price spike перед settlement (guard) |

---

## Ризики

| Ризик | Опис |
|-------|------|
| Rate змінюється | До settlement rate може впасти |
| Price spike | За хвилини до settlement різкий рух ціни |
| Комісії | 4 угоди vs малий gross (funding spread < 2× fees) |
| Timing | Не встигли відкрити до settlement window |

---

## Дані (потрібні)

| Дані | Джерело | Метод |
|------|---------|-------|
| Funding rate обох бірж | `CcxtBase.fetch_funding_infos()` | REST poll |
| Next settlement time | `FundingInfo.next_settlement_ms` | REST |
| Futures bid/ask обох бірж | `watch_tickers` / order book | WS |
| Fees maker/taker | `load_markets()` | REST (при старті) |

---

## Залежності для реалізації

- [x] Funding rate fetching (`fetch_funding_infos`)
- [x] `FundingInfo` model з `next_settlement_ms`
- [x] `MarketDataCacheMemory.get_funding()`
- [ ] Entry window logic (check time to settlement)
- [ ] Earn/hedge side selection by rate sign
- [ ] Auto-close after settlement trigger
- [ ] Rate change monitoring (abort if rate drops)

---

## Налаштування (план)

```env
FUNDING_FF_ENABLED=false
FUNDING_FF_MIN_SPREAD_PCT=1.0
FUNDING_FF_ENTRY_WINDOW_SECONDS=300
FUNDING_FF_SKIP_WITHIN_SECONDS=60
```

---

## Історія змін

| Дата | Зміна |
|------|-------|
| 2026-07-04 | Створено заготовку документа |
