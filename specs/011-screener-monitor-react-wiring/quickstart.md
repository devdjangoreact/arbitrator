# Quickstart Validation Guide

**Feature**: 011-screener-monitor-react-wiring
**Date**: 2026-07-16

## Prerequisites

1. Python venv активований: `.venv\Scripts\activate`
2. `.env` містить API ключі хоча б одної біржі (або `MOCK_DATA=true` для паперового режиму)
3. React UI зібраний: `pnpm build` в `src/arbitrator/presentation/react-ui/`

## Запуск

```bash
.venv\Scripts\python.exe scripts/run_app.py
```

Відкрити браузер: `http://localhost:8000` → вкладка **Monitors**.

---

## Сценарій 1: Таблиця History Screener (SC-001, SC-002, SC-003)

1. Встановити Analysis Period = 1800 с, натиснути **Start Monitoring**
2. Очікувати ≤10 с — таблиця має заповнитись рядками
3. Перевірити сортування: колонка "Max Spread %" має бути за спаданням
4. Встановити Min Spread % = 2.0 → кількість рядків має зменшитись або залишитись такою ж (не збільшитись)
5. Встановити Min 24h Volume = 10 000 000 → рядки з меншим об'ємом зникають
6. Спостерігати 60 с — таблиця оновлюється кожні 5 с без ручної дії
7. **Очікуваний результат**: жодних JS-помилок у консолі; колонки відповідають: Symbol, Δ/exit, Signal time, Exchanges (⊘ якщо картка вже є), Funding Rate, Next Funding, Funding Spread, Price, Volume 24h, Actions

---

## Сценарій 2: Створення картки (SC-004, US-2)

1. Клікнути **⚡ Fast Trade** на будь-якому рядку
2. Картка з'являється внизу сторінки зі статусом "Active"
3. Усі поля картки (Funding rate, Ask, Bid, Leverage тощо) показують числові значення, не "—" і не hardcoded
4. Клікнути **Copy to Form** на іншому рядку (інша пара) → картка з'являється зі статусом "Stopped" (не запущена)
5. Спробувати клікнути **Fast Trade** на тому ж рядку що вже активний → має з'явитись попередження "Monitor already exists"
6. Перевірити іконку ⊘ в таблиці: біля бірж активної картки має з'явитись ⊘

---

## Сценарій 3: Реальні дані на картці (SC-004, SC-005)

1. На активній картці спостерігати 30 с
2. Поля мають оновлюватись кожні 5 с: Funding rate, Ask, Bid, Open spread current/min/max, Close spread current/min/max
3. Графік додає нові точки (червона лінія = шорт, зелена = лонг)
4. Open spread current/min/max — min ≤ current ≤ max (логічна перевірка)

---

## Сценарій 4: Редагування параметрів (SC-006)

1. Змінити Open Spread % на картці → клікнути поза полем (blur)
2. Перезавантажити сторінку (F5)
3. **Очікуваний результат**: нове значення зберіглось (не скинулось до попереднього)

---

## Сценарій 5: Restart (US-3, SC-007)

1. На активній картці з відкритими ордерами клікнути **⟳ Restart**
2. Картка коротко переходить в стан "Restarting"
3. Після відновлення — поля P/L, Realized PNL, Enter spread, Orders показують значення що відповідають реальним позиціям
4. **Критерій**: жодних JS-помилок; ордери не дублюються

---

## Сценарій 6: Pin/Star картки

1. Клікнути ★ на другій картці в списку
2. Ця картка переміщується першою в grid
3. Після перезавантаження сторінки порядок зберігається (pin зберігається лише в пам'яті сесії — або в `MonitorConfig` якщо реалізовано персистентність)

---

## Тайпчек та лінт (перед мержем)

```bash
.venv\Scripts\mypy.exe --strict src/arbitrator
.venv\Scripts\ruff.exe check src tests
pnpm --prefix src/arbitrator/presentation/react-ui tsc --noEmit
```

Всі три команди мають завершитись без помилок.

---

## E2E тест (Playwright)

```bash
.venv\Scripts\python.exe -m pytest tests/e2e/test_monitors_page.py -v
```

Тест покриває: старт screener → поява рядків → Fast Trade → поява картки → поля не "—" → зупинка.
