# Стратегія: Ф'ючерс–Спот (одна біржа)

**ID**: `futures_spot_1ex`
**UI-колонка**: Ф-С 1б
**Секція механіки**: §1
**Статус**: Не реалізовано (потребує spot execution path)

---

## Суть

Long **spot** + short **futures** на **одній** біржі. Прибуток від зменшення basis (premium futures над spot). Напрямок ціни монети не важливий — хедж нейтралізує.

---

## Формула прибутку

```
прибуток = (basis_входу − basis_виходу) × обʼєм / 100 − комісія − фандінг
```

| Змінна | Визначення |
|--------|-----------|
| `basis` | `(futures_price − spot_price) / spot_price × 100%` |
| `обʼєм` | Notional USDT (spot buy leg) |
| `комісія` | 4 угоди: spot buy + sell + futures open + close |
| `фандінг` | Futures short leg: rate × notional × periods |

---

## Механіка

1. Spot buy (USDT) — купуємо дешевше
2. Futures short (`Q` монет) — продаємо дорожче
3. Чекаємо звуження basis
4. Close: futures buy-to-cover → spot sell

---

## Умови входу (план)

| # | Умова | Опис |
|---|-------|------|
| 1 | Basis ≥ поріг відкриття | Налаштовується |
| 2 | Spot + futures на одній біржі | Перевірка наявності spot market |
| 3 | Order book depth достатня | Spot asks + futures bids |
| 4 | Funding rate допустимий | Short не платить надто багато |
| 5 | Баланс USDT достатній | Для spot buy + futures margin |

---

## Умови виходу

| # | Умова |
|---|-------|
| 1 | Basis ≤ close threshold |
| 2 | Або: basis виріс надто (stop-loss) |

---

## Ризики

| Ризик | Опис |
|-------|------|
| Basis не сходиться | Premium не зменшується — позиція зависає |
| Funding проти | Short платить при rate > 0 |
| Комісії spot | Spot fee вища за futures — з'їдає малий basis |
| Контрагент | Обидві ноги на одній біржі |

---

## Залежності для реалізації

- [ ] Spot data path (watch_ticker spot)
- [ ] Spot execution gateway (create_order spot)
- [ ] Spot fees (load_markets spot)
- [ ] Spot balance check
- [ ] Basis calculation service

---

## Налаштування (план)

```env
SPOT_ENABLED=true
FUTURES_SPOT_1EX_MIN_BASIS_PCT=2.0
FUTURES_SPOT_1EX_CLOSE_BASIS_PCT=0.2
FUTURES_SPOT_1EX_MAX_FUNDING_COST_PCT=0.5
```

---

## Історія змін

| Дата | Зміна |
|------|-------|
| 2026-07-04 | Створено заготовку документа |
