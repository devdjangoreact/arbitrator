# Стратегія: Funding — різниця часу settlement

**ID**: `funding_diff_dates`
**UI-колонка**: Ф різн.
**Секція механіки**: §5
**Статус**: Не реалізовано

---

## Суть

Earn на **early** біржі (високий |rate|, settlement скоро). Hedge на **late** біржі (її funding ще не нараховується — settlement пізніше). Після 1 period early → close. Late leg не чекаємо — він лише хеджує ціну, а funding на ньому = 0.

Ключова відмінність від §4: тут біржі мають **різний час** settlement. Ми використовуємо цю різницю — заходимо перед early, виходимо після early, але до late.

---

## Формула прибутку

```
прибуток = |rate_early| × обʼєм / 100 − комісія + price_PnL
```

| Змінна | Визначення |
|--------|-----------|
| `|rate_early|` | Funding rate early-біржі за 1 period |
| `обʼєм` | Notional USDT |
| `комісія` | 4 угоди futures |
| `price_PnL` | P&L від руху ціни (хедж неповний — різний рух на біржах) |

---

## Механіка

1. Визначити early-біржу (settlement скоро) та late-біржу (settlement пізніше)
2. Earn leg на early: long/short за знаком rate_early
3. Hedge leg на late: протилежна сторона
4. Settlement early відбувся → отримали funding
5. Close обидві ноги (до settlement late)

**Сторона earn:**
| rate_early | Earn (early) | Hedge (late) |
|------------|-------------|--------------|
| > 0 | Short | Long |
| < 0 | Long | Short |

---

## Умови входу (план)

| # | Умова | Опис |
|---|-------|------|
| 1 | `|rate_early| ≥ 1%` | Мін дохід |
| 2 | Settlement early через 1–5 хв | Entry window |
| 3 | Settlement late > settlement early + buffer | Різниця достатня |
| 4 | `|rate_early| × volume − fees > 0` | Net profitable |
| 5 | Order book depth | Обидві сторони |
| 6 | Спред цін < anomaly | — |

---

## Умови виходу

| # | Умова |
|---|-------|
| 1 | Settlement early відбувся → close |
| 2 | Close **до** settlement late (інакше заплатимо funding на late) |

---

## Ризики

| Ризик | Опис |
|-------|------|
| Price > funding | P&L від руху ціни може перевищити funding дохід |
| Rate early змінюється | До settlement rate може впасти |
| Неповний хедж | Різний рух ціни на двох біржах |
| Late settlement раптово | Якщо late settlement відбудеться раніше — заплатимо |

---

## Дані (потрібні)

| Дані | Джерело |
|------|---------|
| Funding rate обох бірж | `fetch_funding_infos()` |
| `next_settlement_ms` обох бірж | `FundingInfo` |
| Futures bid/ask | `watch_tickers` / book |
| Різниця settlement times | Порівняння `next_settlement_ms` A vs B |

---

## Залежності для реалізації

- [x] Funding rate + settlement time fetching
- [ ] Settlement time comparison logic (early vs late detection)
- [ ] Entry window tied to early settlement
- [ ] Exit trigger: post-early-settlement close
- [ ] Price PnL tracking (non-zero for imperfect hedge)

---

## Налаштування (план)

```env
FUNDING_DIFF_DATES_ENABLED=false
FUNDING_DIFF_DATES_MIN_RATE_PCT=1.0
FUNDING_DIFF_DATES_MIN_TIME_GAP_SECONDS=600
FUNDING_DIFF_DATES_ENTRY_WINDOW_SECONDS=300
```

---

## Історія змін

| Дата | Зміна |
|------|-------|
| 2026-07-04 | Створено заготовку документа |
