# Quickstart / Validation: Strategy Engine (002-strategy-engine)

Перевірки, що доводять роботу фічі end-to-end. Деталі моделей/джерел — у
[data-model.md](./data-model.md) і [contracts/strategy-data-catalog.md](./contracts/strategy-data-catalog.md).

## Prerequisites

- Python 3.11+, залежності встановлені (`poetry install`).
- Для live: валідні API-ключі у `.env` (`Settings.credentials_for`), `UI_DATA_MODE=live`.
- Для домену/юніт-тестів біржі не потрібні.

## A. Юніт: формули стратегій (без бірж)

- Команда: `pytest tests/ -k strategy`
- Очікувано: для кожної з 6 стратегій тест на числовому прикладі з `strategies-mechanics`
  дає очікуваний `net_profit_usdt` і `percent_to_deposit` (Decimal, 2 знаки на виході).

## B. Ризик/edge юніт-кейси

- Очікувано (кожен — окремий тест):
  - немає споту → `futures_spot_*` і `funding_fs` `available=False, reason=no_spot`;
    `futures_futures`/`funding_ff` рахуються.
  - прострочений `next_settlement_ms` → funding-стратегії `N/A`, сигнал open блокується.
  - спред > `anomaly_max_spread_pct` → `AnomalyGuard` блокує авто-вхід.
  - обсяг > глибина книги → попередження/блок (slippage).
  - несвіжі котирування (старші за `quote_max_age_seconds`) → `N/A`.

## C. Screener live (з біржами)

- Запуск: `UI_DATA_MODE=live python -m uvicorn main:app` (або `python main.py`).
- Відкрити `/ws/screener`.
- Очікувано: колонки Ф-Ф … Ф різн. заповнені реальними числами; символи без потрібних даних —
  `N/A` у відповідних колонках; жодних mock-значень.
- Перевірка інкрементальності: у логах — перерахунок лише змінених символів на тік.

## D. Opportunity live

- Відкрити `/ws/opportunity/{symbol}?short=&long=`.
- Очікувано: таблиця «Розрахунок по стратегіях» має всі поля (спред, ціни short/long, комісії,
  фандінг, обʼєм, плече, заробіток, витрати, чистий, `% до депозиту`), порахована з біржових даних.
- Зміна `set_params`/`set_leverage` → перерахунок залежних полів.

## E. Сигнали + чекліст

- Підняти спред вище порогу відкриття → з'являється сигнал `open` (чекліст `passed=true`).
- Зробити будь-який пункт чекліста невалідним (напр. зупинити funding-оновлення) → сигнал входу
  не формується; причина в логах.

## F. Реальне виконання (мали обсяги!)

- На малому `target_volume_usdt`: команда `opportunity.accumulate` (сума або %).
- Очікувано: реальні fills на **обох** ногах; набраний обсяг береться з біржі (positions/fills),
  не з наміру; `action_result(success=true)`.
- Часткове закриття 25% → обидві ноги ~−25%, `imbalance_pct` ≤ допуск.
- Симуляція збою другої ноги (тестове середовище) → `status=rolled_back`, неприхованої ноги немає.

## Done criteria (мапінг на Success Criteria)

- A,B → SC-001, SC-002, SC-005, SC-008
- C → SC-001, SC-003, SC-004
- D,E → SC-005
- F → SC-006, SC-007
