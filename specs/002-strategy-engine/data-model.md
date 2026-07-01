# Data Model: Strategy Engine (002-strategy-engine)

Усі моделі — `pydantic.BaseModel` `frozen=True` (або `@dataclass(frozen=True, slots=True)` для
суто внутрішніх), `Decimal` для грошей/цін у домені. Поля округлюються до 2 знаків **лише** в
serializer на виході. DTO з `001` розширюються **additive**: net-поля стають `float | None`
(None → `N/A` на UI, не 0), у рядок Opportunity додаються `percent_to_deposit` і
`unavailable_reason`. Mock-режим сумісний (заповнює ті самі поля числами).

## Канон стратегій

`StrategyKind` (Literal/Enum): `futures_futures`, `futures_spot_2ex`, `futures_spot_1ex`,
`funding_ff`, `funding_fs`, `funding_diff_dates`.

## Value objects (входи)

### Quote
| Поле | Тип | Опис |
|------|-----|------|
| exchange_id | str | біржа |
| symbol | str | `BASE/USDT:USDT` (futures) або `BASE/USDT` (spot) |
| market_type | Literal["futures","spot"] | ринок |
| bid | Decimal \| None | найкраща ціна купівлі |
| ask | Decimal \| None | найкраща ціна продажу |
| last | Decimal \| None | остання |
| recv_time_ms | int | час отримання (freshness) |

> Розрив у коді: `Ticker` зараз без bid/ask → додати поля (additive, default None) у `_to_ticker`.

### FundingInfo
| Поле | Тип | Опис |
|------|-----|------|
| exchange_id, symbol | str | — |
| rate | Decimal \| None | поточна ставка period |
| next_rate | Decimal \| None | `nextFundingRate` |
| next_settlement_ms | int \| None | `fundingTimestamp`/`fundingDatetime` |
| recv_time_ms | int | freshness |

### FeeSchedule
| Поле | Тип | Опис |
|------|-----|------|
| exchange_id, symbol | str | — |
| futures_maker / futures_taker | Decimal \| None | частки (напр. 0.0002) |
| spot_maker / spot_taker | Decimal \| None | — |

### StrategyInputs
Нормалізований знімок для символу та конкретної пари бірж (short/long), зібраний
`StrategyInputsAssembler` з кешу з перевіркою свіжості.
| Поле | Тип |
|------|-----|
| symbol | str |
| short_exchange_id / long_exchange_id | str |
| futures_quotes | map[exchange_id] Quote |
| spot_quotes | map[exchange_id] Quote |
| funding | map[exchange_id] FundingInfo |
| fees | map[exchange_id] FeeSchedule |
| target_volume_usdt | Decimal |
| leverage | map[exchange_id] int |
| deposit_usdt | Decimal \| None |
| now_ms | int |

## Результати

### StrategyResult
| Поле | Тип | Опис |
|------|-----|------|
| strategy_id | StrategyKind | — |
| available | bool | чи порахована |
| unavailable_reason | str \| None | напр. `no_spot`, `funding_ts_stale`, `no_fees` |
| spread_pct | Decimal \| None | спред входу |
| price_short / price_long | Decimal \| None | ціни ніг (за конвенцією bid/ask) |
| fees_usdt | Decimal \| None | комісія за 4 угоди |
| funding_usdt | Decimal \| None | net funding (дохід +, витрата −) |
| volume_usdt | Decimal \| None | notional |
| leverage | int \| None | використане |
| gross_profit_usdt | Decimal \| None | від спреду/funding |
| costs_usdt | Decimal \| None | сума витрат |
| costs_breakdown | str \| None | розбивка |
| net_profit_usdt | Decimal \| None | підсумок |
| percent_to_deposit | Decimal \| None | `net / deposit × 100` (головна метрика) |

### StrategyTable
| Поле | Тип |
|------|-----|
| symbol | str |
| results | map[StrategyKind] StrategyResult |
| best_strategy_id | StrategyKind \| None |
| updated_at_ms | int |

> Serializer → `StrategyProfitsDto` (6 net `float | None` для Screener) і `StrategyCalculationRowDto`
> (повні рядки Opportunity + `percent_to_deposit`, `unavailable_reason`). Недоступні стратегії:
> net = `None` → `N/A` на UI (не 0); причина показується у тултіпі/підказці.

## Сигнали / валідація

### ChecklistResult
| Поле | Тип | Опис |
|------|-----|------|
| same_asset | bool | один `BASE` на обох ногах |
| quotes_side_ok | bool | bid/ask за конвенцією присутні/свіжі |
| fees_loaded | bool | комісії доступні |
| funding_ts_valid | bool | next settlement у майбутньому/свіжий |
| passed | bool | усі True |
| reason | str \| None | перший провалений пункт |

### TradeSignal
| Поле | Тип |
|------|-----|
| symbol | str |
| strategy_id | StrategyKind |
| kind | Literal["open","close","accumulate"] |
| short_exchange_id / long_exchange_id | str |
| volume_usdt | Decimal |
| spread_pct | Decimal \| None |
| checklist | ChecklistResult |
| blocked_reason | str \| None |

### PredictionScore
| Поле | Тип | Опис |
|------|-----|------|
| symbol | str | — |
| score | Decimal | advisory 0..1 (чи інша шкала) |
| trend | Literal["widening","narrowing","flat"] | напрям Δ |
| stability | Decimal | стабільність вікна |
| seconds_to_funding | int \| None | час до фандінгу |
| enabled | bool | чи активний прогноз |

## Виконання

### ExecutionOutcome
| Поле | Тип | Опис |
|------|-----|------|
| symbol | str | — |
| strategy_id | StrategyKind | — |
| action | Literal["open","accumulate","close_partial","close_all"] | — |
| status | Literal["success","partial","failed","rolled_back"] | підсумок |
| short_fill_usdt / long_fill_usdt | Decimal | фактичні fills з біржі |
| imbalance_pct | Decimal | залишковий дисбаланс ніг |
| rollback_action | str \| None | що зроблено при збої |
| message | str \| None | для `action_result` |

## Абстракції (domain Protocols)

- `MarketDataCache`: читання `Quote/FundingInfo/FeeSchedule` за (exchange_id, symbol, market_type).
- `StrategyCalculator`: `compute(StrategyInputs) -> StrategyResult`.
- `SpotGateway`: спотові ціни/fees/ордери (реалізація — ccxt `defaultType=spot`).

## State transitions (виконання, спрощено)

```
IDLE ──signal/manual──▶ VALIDATING ──checklist+anomaly ok──▶ EXECUTING
VALIDATING ──fail──▶ BLOCKED(reason)
EXECUTING ──both legs ok──▶ DONE(success)
EXECUTING ──one leg fail──▶ ROLLBACK ──▶ DONE(rolled_back) | ALERT(partial)
```
