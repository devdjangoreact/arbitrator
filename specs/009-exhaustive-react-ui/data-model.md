# Data Model: React UI State & Payloads

This document defines the core data structures managed by the React frontend, derived from the specification. These models represent the state received from WebSockets and REST APIs, and the structures sent back.

## 1. UI Formatting Enums (CSS Classes)

```typescript
type PnlClass = 'pos' | 'neg' | 'na';
```

## 2. Settings (REST `GET/PUT /api/config/strategy`, WS `/ws/settings`)

**Exchange API Key Config**
```typescript
interface ExchangeConfig {
  exchange_id: string;
  configured: boolean;
  api_key_masked?: string;
  has_password?: boolean;
}

// Payload for settings.save_exchange
interface SaveExchangePayload {
  exchange_id: string;
  api_key: string;
  api_secret: string;
  api_password?: string;
}
```

**Strategy Configuration**
```typescript
interface StrategyConfig {
  [key: string]: string | number | boolean | Record<string, any>;
  strategy_overrides: Record<string, any>; // Rendered as JSON textarea
  allowed_strategies: string[];            // Rendered as JSON textarea
}
```

## 3. Screener (`/ws/screener`)

```typescript
interface ScreenerRow {
  asset: string;
  short_exchange_id: string;
  long_exchange_id: string;
  max_p: number;
  min_p: number;
  spread_pct: number;
  delta?: number;
  vol_k_usdt: number;
  profits: {
    futures_futures: number;
    futures_spot_2ex: number;
    // ... other strategies
  };
}

// Payload for screener.set_filter
interface SetScreenerFilterPayload {
  min_volume_k_usdt: number;
  min_spread_pct: number;
}
```

## 4. Opportunity (`/ws/opportunity`)

```typescript
interface StrategyCalculation {
  strategy_name: string;
  spread_pct: number;
  delta: number;
  fee_pct: number;
  max_vol: number;
  details: string; // "OK" or error message
}

// Payload for opportunity.action
interface OpportunityActionPayload {
  action: 'accumulate' | 'close_partial' | 'close_all';
  symbol: string;
  strategy?: string; // required for accumulate
}
```

## 5. Orders (`/ws/orders`)

```typescript
interface OrderLeg {
  side: 'Short' | 'Long';
  exchange: string;
  leverage: number;
  volume: number;
  entry_price: number;
  exit_price?: number;
  fees: number;
  funding: number;
  pnl: number;
}

interface OrderGroup {
  id: string;
  asset: string;
  short_exchange: string;
  long_exchange: string;
  status: 'open' | 'closed';
  opened_at: string; // ISO string
  spread_in: number;
  spread_out?: number;
  total_fees: number;
  total_funding: number;
  total_pnl: number;
  legs: OrderLeg[];
}
```

## 6. Monitors & Live Cards (`/ws/historical_screener`)

**Monitor Config (Editable in Live Card)**
```typescript
interface MonitorConfig {
  id: string;
  symbol: string;
  short_exchange: string;
  long_exchange: string;
  side: 'Auto' | 'LONG' | 'SHORT';
  open_spread_pct?: number;
  open_ticks?: number;
  close_spread_pct?: number;
  close_ticks?: number;
  order_size_usdt?: number;
  max_orders?: number;
  force_stop: boolean;
  total_stop: boolean;
  is_active: boolean;
}

// Payload for cmd: "update_config"
interface UpdateConfigPayload {
  cmd: "update_config";
  monitor_id: string;
  config: Partial<MonitorConfig>;
}
```