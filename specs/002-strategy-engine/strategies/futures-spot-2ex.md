# Стратегія: Ф'ючерс–Спот (дві біржі)

**ID**: `futures_spot_2ex`
**UI-колонка**: Ф-С 2б
**Секція механіки**: §2
**Статус**: Не реалізовано (потребує spot execution path)

---

## Суть

Spot long на біржі **X**, futures short на біржі **Y**. Прибуток від зменшення cross-basis (premium futures Y над spot X). Як §1, але ноги розподілені по біржах.

---

## Формула прибутку

```
прибуток = (cross_basis_входу − cross_basis_виходу) × обʼєм / 100 − комісія − фандінг
```

| Змінна | Визначення |
|--------|-----------|
| `cross_basis` | `(futures_Y − spot_X) / spot_X × 100%` |
| `обʼєм` | Notional USDT (spot buy X) |
| `комісія` | 4 угоди на двох біржах (spot X + futures Y) |
| `фандінг` | Futures Y short: rate × notional × periods |

---

## Механіка

1. Spot buy на X (USDT)
2. Futures short на Y (`Q` монет)
3. Чекаємо звуження cross-basis
4. Close: futures Y buy-to-cover → spot X sell

---

## Умови входу (план)

| # | Умова | Опис |
|---|-------|------|
| 1 | Cross-basis ≥ поріг | `futures_Y_bid − spot_X_ask > threshold` |
| 2 | Spot на X + futures на Y наявні | Market info для обох |
| 3 | Token identity match | Один і той самий токен |
| 4 | Order book depth достатня | Обидві сторони |
| 5 | Funding rate на Y допустимий | — |
| 6 | API lag мінімальний | Різниця timestamp < порогу |

---

## Умови виходу

| # | Умова |
|---|-------|
| 1 | Cross-basis ≤ close threshold |
| 2 | Або: basis виріс надто (stop-loss) |

---

## Ризики

| Ризик | Опис |
|-------|------|
| Усе з §1 | — |
| API lag | Різниця fill vs сигнал (ноги на різних біржах) |
| Два контрагенти | Подвоєний execution risk |
| Spot withdraw disabled | Не можна арбітражити переказом |

---

## Залежності для реалізації

- [ ] Spot data path (watch_ticker spot на X)
- [ ] Spot execution gateway (X)
- [ ] Futures execution gateway (Y) — вже є
- [ ] Cross-basis calculation
- [ ] Token identity check (spot ↔ futures different exchanges)

---

## Налаштування (план)

```env
SPOT_ENABLED=true
FUTURES_SPOT_2EX_MIN_CROSS_BASIS_PCT=3.0
FUTURES_SPOT_2EX_CLOSE_BASIS_PCT=0.2
```

---

## Історія змін

| Дата | Зміна |
|------|-------|
| 2026-07-04 | Створено заготовку документа |
