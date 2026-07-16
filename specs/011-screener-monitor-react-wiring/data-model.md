# Data Model: Screener History React UI Parity

**Feature**: 011-screener-monitor-react-wiring
**Date**: 2026-07-16

---

## Backend entities (Python dataclasses)

### `HistoricalOpportunity` (extended)

File: `src/arbitrator/application/market_data/historical_screener_worker.py`

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | Token name (e.g. `BP`) |
| `short_ex` | `str` | Short-side exchange id |
| `long_ex` | `str` | Long-side exchange id |
| `current_spread_pct` | `float` | Current spread % (Δ in table) |
| `max_historical_spread_pct` | `float` | Max spread % over analysis period (exit value) |
| `short_funding_rate` | `float` | Short-side funding rate |
| `long_funding_rate` | `float` | Long-side funding rate |
| `short_next_funding` | `str` | Short-side next funding time string |
| `long_next_funding` | `str` | Long-side next funding time string |
| `short_price` | `float` | Short-side last price |
| `long_price` | `float` | Long-side last price |
| `short_volume_24h` | `float` | Short-side 24h volume USDT |
| `long_volume_24h` | `float` | Long-side 24h volume USDT |
| `detected_at` | `float` | Unix timestamp of first detection |
| `lookback_seconds` | `int` | Analysis period used |
| `signal_time_seconds` | `int` | **NEW** — seconds since max spread was recorded |
| `max_spread_detected_at` | `float` | **NEW** — Unix timestamp when max spread was last updated |

---

### `MonitorConfig` (extended)

File: `src/arbitrator/config/monitor_config_store.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `symbol` | `str` | — | Token name |
| `short_exchange` | `str` | — | **RENAMED** from `short_ex` |
| `long_exchange` | `str` | — | **RENAMED** from `long_ex` |
| `id` | `str` | `""` | **NEW** — computed: `f"{symbol}:{short_exchange}:{long_exchange}"` |
| `side` | `Literal["auto","long","short"]` | `"auto"` | Position direction mode |
| `open_spread_pct` | `float` | — | Open position spread threshold |
| `close_spread_pct` | `float` | — | Close position spread threshold |
| `order_size_usdt` | `float` | — | Single order size in USDT |
| `max_orders` | `int` | `0` | Max grid orders (0 = unlimited) |
| `open_ticks` | `int` | `2` | Consecutive ticks to confirm open |
| `close_ticks` | `int` | `2` | Consecutive ticks to confirm close |
| `allowed_size_usdt` | `float` | `4000.0` | Max allowed accumulated size USDT |
| `allowed_size_current_usdt` | `float` | `0.0` | **NEW** — current accumulated size USDT |
| `force_stop` | `bool` | `False` | Force-close all positions immediately |
| `total_stop` | `bool` | `False` | Stop all operations including new signals |
| `is_active` | `bool` | `False` | Monitor active flag |
| `adjustment_mode` | `Literal["notify_only","adjust"]` | `"notify_only"` | **NEW** — leverage adjustment behavior |
| `detected_at` | `float` | — | Unix timestamp of creation |
| `max_historical_spread_pct` | `float` | `0.0` | Max spread at time of creation (from screener) |

**Migration note**: JSON files with old keys `short_ex`/`long_ex` handled via `__post_init__` fallback.

---

### `LiveState` per monitor (dict in `HistoricalAutoTrader._live_state`)

Key: `f"{symbol}:{short_exchange}:{long_exchange}"`

| Field | Type | Source |
|-------|------|--------|
| `short_funding_rate` | `float` | market_cache |
| `long_funding_rate` | `float` | market_cache |
| `short_next_funding` | `str` | market_cache |
| `long_next_funding` | `str` | market_cache |
| `short_ask` | `float` | market_cache orderbook |
| `long_ask` | `float` | market_cache orderbook |
| `short_bid` | `float` | market_cache orderbook |
| `long_bid` | `float` | market_cache orderbook |
| `short_size` | `float` | market_cache orderbook top size |
| `long_size` | `float` | market_cache orderbook top size |
| `leverage` | `float` | config or exchange |
| `max_size_short` | `float` | exchange position limits |
| `max_size_long` | `float` | exchange position limits |
| `short_price` | `float` | market_cache last price |
| `long_price` | `float` | market_cache last price |
| `short_pnl` | `float \| None` | paper/live position |
| `long_pnl` | `float \| None` | paper/live position |
| `short_realized_pnl` | `float` | paper/live position |
| `long_realized_pnl` | `float` | paper/live position |
| `enter_spread_short` | `float \| None` | stored at open time |
| `enter_spread_long` | `float \| None` | stored at open time |
| `short_orders` | `int` | paper/live position |
| `long_orders` | `int` | paper/live position |
| `open_spread_current` | `float` | ExecutableSpreadResolver |
| `open_spread_min` | `float` | rolling min over session |
| `open_spread_max` | `float` | rolling max over session |
| `close_spread_current` | `float` | ExecutableSpreadResolver |
| `close_spread_min` | `float` | rolling min over session |
| `close_spread_max` | `float` | rolling max over session |

---

## Frontend types (TypeScript interfaces)

File: `src/arbitrator/presentation/react-ui/src/types/index.ts`

### `OpportunityRow` (new)

```typescript
interface OpportunityRow {
  symbol: string;
  short_exchange: string;
  long_exchange: string;
  current_spread_pct: number;
  max_historical_spread_pct: number;
  signal_time_seconds: number;
  short_funding_rate: number;
  long_funding_rate: number;
  short_next_funding: string;
  long_next_funding: string;
  funding_spread: number;          // computed: short_funding_rate - long_funding_rate
  short_price: number;
  long_price: number;
  short_volume_24h: number;
  long_volume_24h: number;
  detected_at: number;
  lookback_seconds: number;
}
```

### `MonitorConfig` (extended)

```typescript
interface MonitorConfig {
  id: string;                      // composite: "symbol:short_exchange:long_exchange"
  symbol: string;
  short_exchange: string;
  long_exchange: string;
  side: "Auto" | "LONG" | "SHORT";
  open_spread_pct: number;
  open_ticks: number;
  close_spread_pct: number;
  close_ticks: number;
  order_size_usdt: number;
  max_orders: number;
  allowed_size_usdt: number;
  allowed_size_current_usdt: number;  // NEW
  force_stop: boolean;
  total_stop: boolean;
  is_active: boolean;
  is_pinned?: boolean;                // NEW — UI-only, not persisted to backend
  adjustment_mode: "notify_only" | "adjust";  // NEW
}
```

### `LiveState` (new)

```typescript
interface LiveStateEntry {
  short_funding_rate: number | null;
  long_funding_rate: number | null;
  short_next_funding: string | null;
  long_next_funding: string | null;
  short_ask: number | null;
  long_ask: number | null;
  short_bid: number | null;
  long_bid: number | null;
  short_size: number | null;
  long_size: number | null;
  leverage: number | null;
  max_size_short: number | null;
  max_size_long: number | null;
  short_price: number | null;
  long_price: number | null;
  short_pnl: number | null;
  long_pnl: number | null;
  short_realized_pnl: number | null;
  long_realized_pnl: number | null;
  enter_spread_short: number | null;
  enter_spread_long: number | null;
  short_orders: number | null;
  long_orders: number | null;
  open_spread_current: number | null;
  open_spread_min: number | null;
  open_spread_max: number | null;
  close_spread_current: number | null;
  close_spread_min: number | null;
  close_spread_max: number | null;
}

type LiveState = Record<string, LiveStateEntry>;  // key: "symbol:short_exchange:long_exchange"
```

### `SpreadChartPoint` (new)

```typescript
interface SpreadChartPoint {
  time: string;
  open_spread: number | null;
  close_spread: number | null;
}
```

### `HistoricalScreenerUpdate` (WS payload shape)

```typescript
interface HistoricalScreenerUpdate {
  status: "Running" | "Idle" | "Stopping";
  opportunities: OpportunityRow[];
  monitors: MonitorConfig[];
  live_state: LiveState;
  supports_analysis_volume_filter: boolean;  // NEW
}
```

---

## StrategyUIConfig — нові поля (per §17)

File: `src/arbitrator/config/ui_config.py`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `historical_screener_push_interval_seconds` | `int` | `5` | Інтервал пушу WS в секундах |
| `historical_screener_candle_interval_seconds` | `int` | `5` | Таймфрейм свічок: 5 / 15 / 30 / 60 |

---

## Screener worker filter params (розширення `update_filters`)

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `lookback_seconds` | `int` | `1800` | Вікно аналізу в секундах |
| `min_spread_pct` | `float` | `0.0` | Мінімальний спред % |
| `min_volume_usdt` | `float` | `0.0` | Мінімальний 24h обсяг |
| `min_analysis_volume_usdt` | `float` | `0.0` | Мінімальний обсяг за вікно (деферовано) |
| `push_interval_seconds` | `int` | `5` | Інтервал пушу |
| `candle_interval_seconds` | `int` | `5` | Таймфрейм свічок (FR-022) |
| `price_deviation_filter_pct` | `float` | `0.0` | Фільтр відхилення ціни, 0=вимкнено (FR-023) |
