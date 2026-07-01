# Implementation Plan: Strategy Engine (002-strategy-engine)

**Branch**: `002-strategy-engine`
**Spec**: [spec.md](./spec.md)
**Created**: 2026-06-30
**Status**: Plan complete — ready for `/speckit-tasks`

## Summary

Реалізувати доменний **рушій розрахунку всіх 6 стратегій** + сигнали + **реальне хеджоване
виконання**, інтегрований у наявні FastAPI/WS і ccxt.pro-воркери. Дані — **виключно з бірж**
(no fabrication; за відсутності → `N/A`). Швидкість досягається **in-process L1 кешем** +
**stateless-калькуляторами** (Decimal) + **інкрементальним перерахунком** + дельтами в браузер.

Мапінг даних: [contracts/strategy-data-catalog.md](./contracts/strategy-data-catalog.md).

## Technical Context

| Параметр | Значення |
|----------|----------|
| Мова | Python 3.11+, `mypy --strict`, без `Any` |
| Сервер | FastAPI + uvicorn (наявний) |
| UI ↔ сервер | Тільки WebSocket (наявні `/ws/screener`, `/ws/opportunity/{symbol}`) |
| Біржа дані | ccxt.pro `watch_*` (пріоритет); REST `fetch_*` лише як fallback/одноразово |
| Точність | `Decimal` у домені; округлення 2 знаки **лише** у serializer на виході |
| Кеш | In-process L1 (dict + immutable pydantic); Redis — опційний майбутній адаптер |
| Прогноз | Евристики (advisory-скор), вимикабельні |
| Виконання | Реальні ордери (futures + spot), ідемпотентний `clientOrderId`, rollback ноги |
| Mock | `ui_data_mode=mock_data` лишається лише для UI-розробки, не змішується з live |

## Constitution Check (project rules)

| Принцип (`.cursor/rules/architecture.mdc`) | Відповідність |
|---|---|
| OOP, one class per file, snake_case | ✅ кожен калькулятор/сервіс — окремий файл |
| SOLID, DI через `__init__`, абстракції в `domain/` | ✅ калькулятор = Protocol; кеш/гейтвеї = абстракції |
| Шари: inner не імпортує outer | ✅ домен чистий; assembler/services в application |
| Typing strict, no `Any` | ✅ |
| Async, watch_* пріоритет, ресурси в `finally` | ✅ воркери на фонових потоках як наявні |
| USDT-M perp (`BASE/USDT:USDT`) + spot `BASE/USDT` | ✅ spot лише як хедж/ціна для basis |
| Settings — єдине джерело параметрів, без магічних констант | ✅ нові поля у `Settings` (нижче) |
| No browser REST; WS only | ✅ |
| Logging через `arbitrator.config.logger` | ✅ |

**Gate**: PASS (порушень немає).

## Architecture Overview

```text
exchanges/                     application/                         domain/ (pure)
  ccxt_base (futures) ─┐        SpotStreamWorker ─┐
  spot ccxt client ────┼─watch─ ScreenerStreamWorker (futures) ─┐
  fetch_funding_rate ──┘        FundingRateWorker ──────────────┼─▶ MarketDataCache (L1)
                                FeeSnapshotService ─────────────┘        │
                                                                          ▼
                                StrategyInputsAssembler ──▶ StrategyEngine ──▶ 6×Calculator
                                   (freshness/N/A gate)         │  (Decimal, stateless)
                                                                ▼
                                SignalService + ChecklistEvaluator + PredictionService
                                                                ▼
                                HedgedExecutionService (open/accumulate/close + rollback)
                                   │ futures: open/close_market_position (наявне)
                                   │ spot: spot create_order (нове)
                                   ▼
presentation/  ws/screener_ws_handler (live serializer) · ws/opportunity_ws_handler (commands)
               serializers → StrategyProfitsDto / StrategyCalculationRowDto → WS push (+UiDeltaEncoder)
```

### New classes (one per file)

**domain/ (pure, no I/O):**
- `strategy/strategy_kind.py` — канон 6 ідентифікаторів (Literal/Enum).
- `strategy/quote.py` — `Quote` (bid/ask/last + ts) для futures/spot.
- `strategy/funding_info.py` — `FundingInfo` (rate, next_settlement_ts, next_rate).
- `strategy/fee_schedule.py` — `FeeSchedule` (futures maker/taker, spot maker/taker).
- `strategy/strategy_inputs.py` — `StrategyInputs` (нормалізований знімок для символу+пари).
- `strategy/strategy_result.py` — `StrategyResult` (availability/`N/A` + усі поля + net + `% до депозиту`).
- `strategy/strategy_table.py` — `StrategyTable` (набір результатів символу).
- `strategy/checklist_result.py`, `strategy/trade_signal.py`, `strategy/prediction_score.py`,
  `strategy/execution_outcome.py`.
- `strategy/strategy_calculator.py` — `Protocol` `compute(inputs) -> StrategyResult`.
- `strategy/strategies/*.py` — 6 калькуляторів (по файлу):
  `futures_futures_calculator.py`, `futures_spot_2ex_calculator.py`, `futures_spot_1ex_calculator.py`,
  `funding_ff_calculator.py`, `funding_fs_calculator.py`, `funding_diff_dates_calculator.py`.
- `strategy/strategy_engine.py` — оркеструє калькулятори, повертає `StrategyTable`, рахує `% до депозиту`.
- `market_data_cache.py` — **Protocol** (abstraction) для L1-кешу (читання знімків).
- `spot_gateway.py` — **abstraction** для спотових даних/ордерів (ціна, fee, create_order).

**application/ (orchestration, I/O):**
- `market_data_cache_memory.py` — in-process реалізація `MarketDataCache` (dict + lock, recv_time).
- `spot_stream_worker.py` — `watch_ticker` спотового клієнта → кеш (bid/ask/last).
- `funding_rate_worker.py` — періодичний `fetch_funding_rate(s)` → кеш (rate + next time).
- `fee_snapshot_service.py` — `load_markets`/`fetch_trading_fee` → `FeeSchedule` у кеш.
- `strategy_inputs_assembler.py` — збирає `StrategyInputs` з кешу + freshness gate (`N/A`).
- `strategy_table_service.py` — Screener: інкрементальний перерахунок 6 net по змінених символах.
- `opportunity_strategy_service.py` — Opportunity: повні `StrategyCalculationRowDto`.
- `signal_service.py` — open/close сигнали за порогами + `checklist_evaluator.py`.
- `prediction_service.py` — advisory-скор (тренд Δ/стабільність/час до фандінгу) з короткої історії.
- `hedged_execution_service.py` — open/accumulate/close обох ніг + **rollback** при збої ноги;
  обсяг зі stану біржі (fills/positions), spot-ордери для §1/§2/§6/§7.
- `anomaly_guard.py` — блокування входу (аномальний спред, несвіжість, глибина/баланс).

**exchanges/:**
- спотовий ccxt-клієнт: новий адаптерний шар `defaultType=spot` (повторно використовує конфіг
  `CcxtBase._base_client_config`); створення — через розширений `Factory` (market type) або `SpotFactory`.
- розширення `Ticker` (futures) полями `bid`/`ask` (additive, default `None`) у `_to_ticker`.

**presentation/:**
- `screener_ws_handler._live_loop` — реальна серіалізація з `StrategyTableService` (зняти заглушку).
- `opportunity_ws_handler` — команди `set_params/set_leverage/accumulate/close_partial/close_all`
  делегують у `HedgedExecutionService`; снапшот із `OpportunityStrategyService`.
- серіалізатори → `StrategyProfitsDto` / `StrategyCalculationRowDto` з **additive**-змінами для
  `N/A`-контракту: net-поля `float | None` (None → `N/A` на UI, не 0) і нове поле
  `percent_to_deposit` + `unavailable_reason` у рядку Opportunity (головна метрика FR-004 має бути
  видима у браузері — єдиний канал перевірки для користувача). Зміни сумісні з mock (значення лишаються).

### Settings (нові поля, з `.env.example`)

`spot_enabled: bool`, `spot_default_type: str = "spot"`,
`quote_max_age_seconds`, `book_max_age_seconds`, `funding_refresh_seconds`,
`funding_entry_window_seconds`, `strategy_decimal_places: int = 2`,
`anomaly_max_spread_pct`, `slippage_max_pct`,
`prediction_enabled: bool`, `prediction_window_seconds`,
`deposit_basis: Literal["position_margin","account_balance"] = "position_margin"`
(margin = `Σ notional_leg / leverage_leg`, спот 1× — C2),
`execution_rollback_enabled: bool = True`, `leg_imbalance_tolerance_pct` (повтор.
`opp_position_imbalance_tolerance_pct`),
`active_strategy_default: str = "futures_futures"` (C1),
`exchange_proxies: dict[str, str] = {}` / `public_ws_proxy_url: str | None = None` (опційний проксі
для публічних WS, помʼякшення rate limit — C8).

### Decisions з Clarifications (spec C1–C11)

- **C1** — base/active = `futures_futures`; вибір пари = max крос-спред; далі активна = max `% до депозиту`.
- **C2** — `deposit_usdt = Σ(notional_leg / leverage_leg)` (спот 1×); `deposit_basis=position_margin`.
- **C3** — `funding = max(paid − received, 0)`; знак per-leg за стороною та знаком ставки; тест на знак.
- **C4** — немає споту → §1/§2/§6/§7 `N/A` (`reason=no_spot`); доступність у `StrategyResult`.
- **C5** — `StrategyInputsAssembler`: один locked-read → immutable `StrategyInputs` (без торваних читань).
- **C6** — `float→Decimal` через `str`; округлення лише на виході.
- **C7** — реконсиляція: при старті/reconnect визначати відкриті позиції з біржі → активна стратегія + метрики.
- **C8** — батчинг REST + ccxt rateLimit + опційний проксі для публічних WS.
- **C9** — сценарні тести (зокрема funding-timing close/reopen з комісіями для `futures_futures`).
- **C10** — приватна звірка через read-only скіл/скрипт; без ключів `deposit`/виконання → `N/A`.
- **C11** *(підтверджено)* — `funding_fs` = дві гілки за наявністю споту: §6 (спот+futures на одній
  біржі) і §7 (спот на найдешевшій/доступній біржі, хедж futures на іншій). Комісія споту — з біржі
  споту; §7 додає cross-basis (spot X vs futures Y). За наявності обох — кращий `% до депозиту`.

## Phases

### Phase 0 — Research (артефакт)
[research.md](./research.md): рішення по кешу (in-memory vs Redis), споту (окремий ccxt-клієнт),
funding (REST `fetch_funding_rate` vs ticker), Decimal, калькулятор-патерн, rollback, freshness.

### Phase 1 — Domain core (pure, тестопридатне першим)
1. Моделі `Quote/FundingInfo/FeeSchedule/StrategyInputs/StrategyResult/StrategyTable`.
2. `StrategyCalculator` Protocol + 6 калькуляторів з формулами `strategies-mechanics`.
3. `StrategyEngine` + `% до депозиту`; повний `N/A`-контракт.
4. Юніт-тести: числові приклади з `strategies-mechanics` для кожної стратегії + ризик-кейси.

### Phase 2 — Data sourcing (live)
1. `Ticker` bid/ask; `MarketDataCacheMemory`.
2. Spot client + `SpotStreamWorker`; `FundingRateWorker`; `FeeSnapshotService`.
3. `StrategyInputsAssembler` + freshness/`N/A` gate.

### Phase 3 — Screener live
1. `StrategyTableService` (інкрементально) → `StrategyProfitsDto`.
2. `screener_ws_handler._live_loop` серіалізація + дельти.

### Phase 4 — Opportunity live + signals
1. `OpportunityStrategyService` → `StrategyCalculationRowDto`.
2. `SignalService` + `ChecklistEvaluator` + `AnomalyGuard`.
3. `PredictionService` (advisory).

### Phase 5 — Execution (real orders)
1. Spot order path в gateway/adapter.
2. `HedgedExecutionService`: open/accumulate/close_partial/close_all + **rollback**; стан із біржі.
3. `opportunity_ws_handler` команди → service; авто-режими за сигналом+чеклістом.

### Phase 6 — Wiring & polish
1. `AppRuntime` старт нових воркерів лише при `ui_data_mode=live`.
2. `.env.example` + `architecture.mdc` sync (documentation-sync rule).
3. Тести serializer/інтеграції; quickstart-перевірки.

## Risks & Mitigations

| Ризик | Пом'якшення |
|------|-------------|
| Спот недоступний на біржі/символі | стратегії §1/§2/§6/§7 → `N/A`; не блокує `futures_futures`/`funding_ff` |
| Rate limit при REST funding/fees | періодичність у `Settings`, кеш, `watch*` де є |
| Частковий fill / збій ноги | `HedgedExecutionService` rollback + стан із біржі (no fabrication) |
| Дрейф `last` vs bid/ask | рахунок на bid/ask за конвенцією, не на `last` |
| Несвіжі дані | freshness gate → `N/A`/no-trade |
| Перерахунок усієї таблиці | інкрементально по змінених символах |

## Generated Artifacts

- [research.md](./research.md)
- [data-model.md](./data-model.md)
- [contracts/strategy-data-catalog.md](./contracts/strategy-data-catalog.md)
- [quickstart.md](./quickstart.md)

## Next Step

`/speckit-tasks` — згенерувати дрібнозернисті задачі T001+ за фазами вище.
