# Документація стратегій

Кожен файл описує повну логіку однієї арбітражної стратегії: формули, умови входу/виходу, ризики, залежності.

**Правило**: при зміні логіки стратегії в коді — оновити відповідний документ (секція "Історія змін").

---

## Стратегії

| ID | Назва | Файл | Статус |
|----|-------|------|--------|
| `futures_futures` | Ф'ючерс–Ф'ючерс (курсовий спред) | [futures-futures.md](futures-futures.md) | **Реалізовано** (live) |
| `futures_spot_1ex` | Ф'ючерс–Спот (1 біржа) | [futures-spot-1ex.md](futures-spot-1ex.md) | Заготовка |
| `futures_spot_2ex` | Ф'ючерс–Спот (2 біржі) | [futures-spot-2ex.md](futures-spot-2ex.md) | Заготовка |
| `funding_ff` | Funding — спред ставок | [funding-ff.md](funding-ff.md) | Заготовка |
| `funding_fs` | Funding + Spot hedge | [funding-fs.md](funding-fs.md) | Заготовка |
| `funding_diff_dates` | Funding — різниця часу | [funding-diff-dates.md](funding-diff-dates.md) | Заготовка |

---

## Спільні елементи

Усі стратегії дотримуються єдиних правил з `strategies-mechanics.uk.md`:

- **Формула**: `прибуток = (спред_входу − спред_виходу) × обʼєм / 100 − комісія − фандінг`
- **Конвенція котирувань** (2 біржі): вхід short=bid, long=ask; вихід short=ask, long=bid
- **Метрика**: `% до депозиту = net_profit / (notional / leverage) × 100`
- **Деградація**: якщо потрібних даних немає — стратегія показує N/A, не рахується на припущеннях

---

## Пріоритет реалізації

1. `futures_futures` — **DONE** (повний live auto-trade + DCA)
2. `funding_ff` — наступний (дані вже є: rates, settlement time)
3. `funding_diff_dates` — після `funding_ff` (та ж інфраструктура)
4. `futures_spot_1ex` / `futures_spot_2ex` / `funding_fs` — потребують spot data path
