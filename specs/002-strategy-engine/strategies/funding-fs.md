# Стратегія: Funding + Spot hedge

**ID**: `funding_fs`
**UI-колонка**: Ф Ф-С
**Секція механіки**: §6 (одна біржа) / §7 (дві біржі)
**Статус**: Не реалізовано (потребує spot execution path)

---

## Суть

**Futures** — заробляюча нога (отримує funding). **Spot** — хедж від руху ціни. Прибуток від **funding payment** на futures. Spot не заробляє — він компенсує price PnL. 1 period → close.

Має два варіанти:
- **§6**: обидві ноги на одній біржі
- **§7**: spot на X, futures на Y (де |rate| вищий)

---

## Формула прибутку

```
прибуток = |rate| × обʼєм / 100 − комісія − basis_drift
```

| Змінна | Визначення |
|--------|-----------|
| `|rate|` | Funding rate futures leg |
| `обʼєм` | Notional USDT |
| `комісія` | 4 угоди: spot open/close + futures open/close |
| `basis_drift` | `(basis_виходу − basis_входу) × обʼєм / 100` |

Basis (§6): `(futures − spot) / spot × 100%` на одній біржі.
Cross-basis (§7): `(futures_Y − spot_X) / spot_X × 100%`.

---

## Механіка

**Rate > 0 (типовий кейс):**
1. Spot buy (USDT) — хедж
2. Futures short (`Q`) — earn (отримує від лонгів)
3. 1 settlement
4. Close: futures buy → spot sell

**Rate < 0:**
1. Spot sell (`Q` — потрібен баланс монет) — хедж
2. Futures long (`Q`) — earn (отримує від шортів)
3. 1 settlement
4. Close: futures sell → spot buy

---

## Умови входу (план)

| # | Умова | Опис |
|---|-------|------|
| 1 | `|rate| ≥ 1%` | Мін funding дохід |
| 2 | Settlement через 1–5 хв | Entry window |
| 3 | `|rate| × volume − fees − estimated_basis_drift > 0` | Net profitable |
| 4 | Spot market наявний | На тій самій (§6) або іншій (§7) біржі |
| 5 | Basis/cross-basis < порогу | Не переплачуємо за premium |
| 6 | Order book depth | Spot + futures |
| 7 | Для rate < 0: баланс монет достатній | Spot sell потребує баланс |

---

## Умови виходу

| # | Умова |
|---|-------|
| 1 | Settlement відбувся → close обидві |
| 2 | Basis drift > funding income → early exit (guard) |

---

## Відмінності §6 vs §7

| Аспект | §6 (одна біржа) | §7 (дві біржі) |
|--------|-----------------|----------------|
| Basis | Local basis (futures − spot на 1 біржі) | Cross-basis (futures Y − spot X) |
| Контрагент | Один | Два (додатковий ризик) |
| API lag | Немає | Є (між ногами на різних біржах) |
| Spot fees | Fees однієї біржі | Fees spot X + futures Y |
| Rate вибір | Rate даної біржі | Max |rate| серед усіх бірж |

---

## Ризики

| Ризик | Опис |
|-------|------|
| Basis проти | Premium зростає — з'їдає funding profit |
| Rate змінюється | До settlement rate може впасти |
| Spot sell (rate < 0) | Потрібен spot-баланс монет |
| Комісії spot | 4 угоди з spot fee — значна частка при малому rate |
| API lag (§7) | Фактичний basis гірший за сигнал |

---

## Дані (потрібні)

| Дані | Джерело |
|------|---------|
| Funding rate futures | `fetch_funding_infos()` / ticker |
| Next settlement time | `FundingInfo.next_settlement_ms` |
| Spot bid/ask | Spot `watch_ticker` (нового data path) |
| Futures bid/ask | `watch_tickers` |
| Spot fees | Spot `load_markets()` |
| Spot balance (для rate < 0) | `fetch_balance` |

---

## Залежності для реалізації

- [x] Funding rate fetching
- [x] Settlement time available
- [ ] Spot data path (watch_ticker spot)
- [ ] Spot execution gateway
- [ ] Spot fees loading
- [ ] Basis / cross-basis calculation
- [ ] Rate sign → side selection logic
- [ ] Entry window + settlement trigger
- [ ] Basis drift monitoring (early exit guard)

---

## Налаштування (план)

```env
SPOT_ENABLED=true
FUNDING_FS_ENABLED=false
FUNDING_FS_MIN_RATE_PCT=1.0
FUNDING_FS_ENTRY_WINDOW_SECONDS=300
FUNDING_FS_SKIP_WITHIN_SECONDS=60
FUNDING_FS_MAX_BASIS_DRIFT_PCT=0.5
```

---

## Історія змін

| Дата | Зміна |
|------|-------|
| 2026-07-04 | Створено заготовку документа |
