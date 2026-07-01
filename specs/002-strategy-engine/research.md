# Research: Strategy Engine (002-strategy-engine)

Формат: Decision · Rationale · Alternatives.

## R1. Кеш гарячого шляху — in-process L1 (не Redis)

- **Decision**: тримати останні біржові знімки (futures/spot quotes, funding, fees) у
  in-process `MarketDataCacheMemory` (dict + lock, immutable pydantic). Redis — лише опційний
  адаптер за `MarketDataCache` Protocol на майбутнє.
- **Rationale**: застосунок single-process, single-user (див. `001` spec). In-process читання —
  без серіалізації/мережі, найнижча латентність; узгоджено з наявними воркерами (threading + lock).
- **Alternatives**: Redis/Dragonfly/KeyDB — дають міжпроцесний доступ і replay, але додають
  мережу+серіалізацію на гарячий шлях і нову залежність; виправдані лише при мультипроцесі.

## R2. Спотові дані — окремий ccxt-клієнт `defaultType=spot`

- **Decision**: ввести спотовий канал окремим ccxt-клієнтом (повторно використати
  `CcxtBase._base_client_config` зі `spot_default_type`), абстракція `SpotGateway`; futures-клієнти
  лишаються `swap`.
- **Rationale**: один клієнт не може одночасно бути `swap` і `spot`; basis-стратегії (§1,§2,§6,§7)
  вимагають реальних спотових bid/ask і spot fees + спот-ордери для хеджа.
- **Alternatives**: змішувати типи в одному клієнті (ламає `defaultType`); рахувати basis від
  `last` без споту (заборонено — fabrication/неточність).

## R3. Funding rate + next time — `fetch_funding_rate(s)` (REST), ticker як швидкий fallback

- **Decision**: `FundingRateWorker` періодично (`funding_refresh_seconds`) тягне
  `fetch_funding_rates([symbols])` → `fundingRate`, `fundingTimestamp/fundingDatetime`,
  `nextFundingRate`. `Ticker.funding_rate` лишається швидким наближенням між оновленнями.
- **Rationale**: ticker не несе час наступного settlement (потрібен для §5 і вікон входу); ccxt
  funding rate structure має ці поля (звірено через Context7).
- **Alternatives**: лише ticker (немає next time → §5 неможлива); `watch*` funding — не всі біржі
  підтримують (буде як апгрейд per-exchange).

## R4. Точність — Decimal у домені, округлення лише на виході

- **Decision**: усі грошові/цінові розрахунки в калькуляторах — `Decimal`; serializer округляє до
  `strategy_decimal_places` (=2) у `float` для DTO.
- **Rationale**: уникнути накопичення похибки на ланцюгах множень; узгоджено з правилом 2 знаки
  «лише на виході» з `strategies-mechanics`.
- **Alternatives**: float скрізь (наявні DTO float) — простіше, але втрата точності при малих спредах.

## R5. Калькулятор-патерн — один клас на стратегію за спільним Protocol

- **Decision**: `StrategyCalculator` Protocol `compute(StrategyInputs) -> StrategyResult`; 6
  реалізацій; `StrategyEngine` інжектує список калькуляторів (Open/Closed, DIP).
- **Rationale**: нова стратегія = новий клас без зміни наявних (SOLID); легко юніт-тестувати на
  числових прикладах з `strategies-mechanics`.
- **Alternatives**: один великий сервіс з гілками if/elif (порушує SRP/OCP).

## R6. `N/A`-контракт і freshness gate в assembler

- **Decision**: `StrategyInputsAssembler` перевіряє наявність і вік даних (`*_max_age_seconds`);
  калькулятор отримує лише валідні входи, інакше повертає `StrategyResult(availability=N/A, reason)`.
- **Rationale**: no-fabrication (FR-002/003); єдине місце рішення «свіжо/доступно».
- **Alternatives**: перевірки всередині кожного калькулятора (дублювання, розсинхрон).

## R7. Хеджоване виконання з rollback

- **Decision**: `HedgedExecutionService` відкриває/закриває обидві ноги; при збої другої ноги —
  компенсація (re-hedge) або закриття першої; набраний обсяг/ціни — зі стану біржі (fills/positions).
- **Rationale**: наявний `ArbitrageOpenService` відкриває short→long **без відкату** при збої long
  (ризик неприхованої ноги) — закриває розрив (FR-013).
- **Alternatives**: лишити best-effort без відкату (неприйнятний ризик).

## R8. Прогноз — легкі евристики

- **Decision**: `PredictionService` рахує advisory-скор із короткого вікна історії спреду
  (`prediction_window_seconds`): напрям/нахил Δ, стабільність, час до фандінгу; вимикабельний.
- **Rationale**: дешево, інтерпретовано, не блокує основний розрахунок; ML — окремий напрям.
- **Alternatives**: ML-модель — поза scope цієї фічі.

## R9. Інтеграція без зламу mock

- **Decision**: нові воркери/сервіси активні лише при `ui_data_mode=live`; `mock_data` лишається
  на `MockDataProvider`. DTO (`StrategyProfitsDto`, `StrategyCalculationRowDto`) змінюються **лише
  additive**: net → `float | None` (для `N/A`), додаються `percent_to_deposit` і
  `unavailable_reason`. Live і mock серіалізатори заповнюють той самий розширений контракт.
- **Rationale**: зберегти робочий UI-режим і WS-контракти з `001`, але дати можливість показати
  `N/A` (FR-003) і `% до депозиту` (FR-004) — без цього користувач не перевірить фічу з браузера.
- **Alternatives**: лишити DTO `float`-only (неможливо показати `N/A` → фальшиві нулі, порушує
  no-fabrication); ламати контракт неаддитивно (зламає mock і наявний фронт).
