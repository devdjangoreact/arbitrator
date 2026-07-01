# Data Model: 001-mockup-ui

Pydantic DTO для WebSocket payloads.  
**Повний каталог елемент UI → поле JSON**: [contracts/ui-backend-catalog.md](./contracts/ui-backend-catalog.md).  
**WS протокол UI**: [contracts/ws-ui-protocol.md](./contracts/ws-ui-protocol.md).

## NavigationState (client-only)

| Field | Type | Notes |
|-------|------|-------|
| active_page | enum: screener, opportunity, orders, settings | |
| focus_opportunity | OpportunityFocusDto \| null | Після Open Opportunity |

## OpportunityFocusDto

| Field | Type | Source |
|-------|------|--------|
| symbol | string | Screener row / Orders button |
| short_exchange_id | string | SpreadCalculator high leg |
| long_exchange_id | string | SpreadCalculator low leg |

Maps to domain `OpportunityView`.

---

## ScreenerSnapshotDto (WS payload)

| Field | Type | Source |
|-------|------|--------|
| status | string | `ScreenerStreamWorker.read_state()` |
| symbol_count | int | len(stream_symbols) |
| exchanges | list[string] | `Settings.enabled_exchanges` |
| filters | ScreenerFiltersDto | runtime + Settings |
| rows | list[ScreenerRowDto] | `ScreenerTableService` |
| updated_at | ISO datetime | server clock |

Деталі полів і форматування UI: [ws-ui-protocol.md](./contracts/ws-ui-protocol.md).

### ScreenerFiltersDto

| Field | Type | Default (Settings) |
|-------|------|------------------|
| min_volume_k_usdt | float | `default_min_quote_volume_kusdt` |
| stream_min_volume_usdt | float | `stream_min_quote_volume_usdt` |
| min_spread_pct | float | `default_min_spread_pct` |

### ScreenerRowDto

| Field | Type | Validation |
|-------|------|------------|
| asset | string | `BASE/USDT` display form |
| prices | dict[exchange_id, ExchangePricesDto] | fut + spot optional |
| max_price | float | > 0 |
| min_price | float | > 0 |
| spread_pct | float | |
| spread_delta | float | optional, vs previous tick |
| volume_k_usdt | float | ≥ 0 |
| strategy_profits | StrategyProfitsDto | 6 keys |
| short_exchange_id | string | |
| long_exchange_id | string | |

### ExchangePricesDto

| Field | Type |
|-------|------|
| futures | float \| null |
| spot | float \| null |

### StrategyProfitsDto

| Field | Type | Maps to spec column |
|-------|------|---------------------|
| futures_futures | float \| null | Ф-Ф |
| futures_spot_2ex | float \| null | Ф-С 2б |
| futures_spot_1ex | float \| null | Ф-С 1б |
| funding_ff | float \| null | Ф Ф-Ф |
| funding_fs | float \| null | Ф Ф-С |
| funding_diff_dates | float \| null | Ф різн. |

`null` ⇒ UI shows `N/A` (not `0`).

---

## OpportunitySnapshotDto (WS payload)

| Field | Type |
|-------|------|
| symbol | string |
| short_exchange_id | string |
| long_exchange_id | string |
| exchange_cards | list[ExchangeInfoCardDto] |
| strategy_rows | list[StrategyCalculationRowDto] |
| books | list[OrderBookPanelDto] |
| chart | ChartSnapshotDto |
| params | OpportunityParamsDto |
| orders | list[OrderGroupDto] |
| status | string |

Деталі Opportunity UI: [ws-ui-protocol.md](./contracts/ws-ui-protocol.md).

### ExchangeInfoCardDto

| Field | Type |
|-------|------|
| exchange_id | string |
| side | short \| long |
| base_asset | string |
| market_symbol | string |
| native_market_id | string \| null |
| min_order_volume_usdt | float \| null |
| max_order_volume_usdt | float \| null |
| balance_usdt | float \| null |
| funding_rate_pct | float \| null |
| funding_countdown_sec | int \| null |
| leverage | int |
| futures_fee | string |
| spot_fee | string |
| open_orders_count | int |
| closed_orders_count | int |

### StrategyCalculationRowDto

| Field | Type |
|-------|------|
| strategy_id | string |
| strategy_label | string |
| spread_pct | float |
| prices_label | string |
| fees_usdt | float |
| funding_usdt | float |
| volume_usdt | float |
| leverage | int |
| gross_profit_usdt | float \| null |
| costs_usdt | float |
| costs_breakdown | string |
| net_profit_usdt | float \| null |
| percent_to_deposit | float \| null |
| unavailable_reason | string \| null |

`null` net/gross/`percent_to_deposit` ⇒ `N/A` on UI; `unavailable_reason` shown in tooltip.

### OrderBookPanelDto

| Field | Type |
|-------|------|
| exchange_id | string |
| market_type | futures \| spot |
| side_role | short \| long |
| volume_24h_label | string |
| range_label | string |
| spread_pct | float |
| mid_price | float |
| asks | list[OrderBookLevelDto] |
| bids | list[OrderBookLevelDto] |

### OrderBookLevelDto

| Field | Type | Обчислення |
|-------|------|------------|
| price | float | з біржі |
| amount | float | `size` з `OrderBookLevel` (об’єм на рівні) |
| total | float | кумулятивний `amount` від best price |
| fill_pct | float | `100 * total / max(total на стороні)` — ширина світлої смуги |
| amount_fill_pct | float | `100 * amount / max(total на стороні)` — ширина темної смуги (рівень) |

Рівні в `asks` і `bids`: сортування **за ціною спадання** (найвища зверху, найнижча знизу біля mid).

Maps from domain `OrderBookLevel`.

### ChartSnapshotDto

| Field | Type |
|-------|------|
| window_seconds | int |
| series | list[ChartSeriesDto] |

### ChartSeriesDto

| Field | Type |
|-------|------|
| key | string |
| label | string |
| exchange_id | string |
| market_type | futures \| spot |
| color | string |
| dashed | bool |
| last_price | float |
| points | list[{t: int, price: float}] |

`last_price` дублює останню точку `points` для легенди (§2.5.2).

### OpportunityParamsDto

| Field | Type | Source |
|-------|------|--------|
| active_strategy_id | string | user selection |
| accumulated_volume_usdt | float | open positions |
| target_volume_usdt | float | `opp_default_max_notional_usdt` / user |
| open_spread_threshold_pct | float | controls / Settings |
| close_spread_threshold_pct | float | controls / Settings |
| accumulate_volume_usdt | float | default volume for accumulate form |
| accumulate_volume_pct | float | default percentage for accumulate form |
| close_volume_usdt | float | default volume for partial close form |
| close_volume_pct | float | default percentage for partial close form |
| auto_accumulate_enabled | bool | |
| auto_close_enabled | bool | |

Maps to domain `OpportunityControls` (partial).

---

## OrderGroupDto

| Field | Type |
|-------|------|
| group_id | string |
| asset | string |
| strategy_code | string | UI short code: `Ф-Ф`, `Ф-С 2б`, … |
| short_exchange_id | string |
| long_exchange_id | string |
| opened_at | string (display) |
| closed_at | string \| null |
| leverage | int |
| volume_usdt | float |
| entry_price | float \| null |
| exit_price | float \| null |
| fees_usdt | float |
| funding_usdt | float |
| pnl_usdt | float |
| status | open \| closed |
| legs | list[OrderLegDto] |

### OrderLegDto

| Field | Type |
|-------|------|
| exchange_id | string |
| side | short \| long |
| leverage | int |
| volume_usdt | float |
| entry_price | float |
| exit_price | float \| null |
| fees_usdt | float |
| funding_usdt | float |
| pnl_usdt | float |

**Sources**: open legs from `PositionLeg` / account stream; closed from `ClosedArbitrageGroup`; PnL from `ArbitragePnlService`.

Деталі списку ордерів: [ws-ui-protocol.md](./contracts/ws-ui-protocol.md).

---

## OrdersSnapshotDto (WS payload)

| Field | Type |
|-------|------|
| summary | OrdersSummaryDto |
| filter | all \| open \| closed |
| groups | list[OrderGroupDto] |

---

## OrdersSummaryDto

| Field | Type |
|-------|------|
| open_count | int |
| closed_count | int |

---

## SettingsSnapshotDto (WS payload)

| Field | Type |
|-------|------|
| exchanges | list[SettingsExchangeDto] |

Деталі Settings UI: [ws-ui-protocol.md](./contracts/ws-ui-protocol.md).

---

## SettingsExchangeDto

| Field | Type |
|-------|------|
| exchange_id | string |
| api_key_masked | string |
| configured | bool |
| has_secret | bool |
| has_password | bool |

## SettingsExchangeUpdateDto (request)

| Field | Type |
|-------|------|
| exchange_id | string |
| api_key | string |
| api_secret | string optional |
| api_password | string optional |

---

## TradingActionRequest DTOs

### AccumulateRequest

| Field | Type |
|-------|------|
| symbol | string |
| short_exchange_id | string |
| long_exchange_id | string |
| volume_usdt | float |
| volume_pct | float optional |

### PartialCloseRequest

Same shape as AccumulateRequest.

### CloseAllRequest

| Field | Type |
|-------|------|
| symbol | string |
| short_exchange_id | string |
| long_exchange_id | string |

### TradingActionResult

| Field | Type |
|-------|------|
| success | bool |
| message | string |
| error_code | string optional |

---

## State Transitions

### OrderGroup.status

```text
(open) --partial close--> (open, reduced volume)
(open) --full close--> (closed)
(closed) --terminal--> (closed)
```

### ScreenerStreamWorker (application)

```text
Connecting → discovery → filtered → (reconnect) → Connecting
```

UI відображає `status` у stream-note; Reconnect bump `reconnect_nonce`.
