export type PnlClass = "pos" | "neg" | "na";

// --- 2. Settings ---

export interface ExchangeConfig {
  exchange_id: string;
  configured: boolean;
  api_key_masked?: string;
  has_password?: boolean;
}

export interface SaveExchangePayload {
  exchange_id: string;
  api_key: string;
  api_secret: string;
  api_password?: string;
}

export interface StrategyConfig {
  [key: string]: string | number | boolean | Record<string, any>;
  strategy_overrides: Record<string, any>;
  allowed_strategies: string[];
}

// --- 3. Screener ---

export interface ScreenerRow {
  asset: string;
  short_exchange_id: string;
  long_exchange_id: string;
  max_p: number;
  min_p: number;
  spread_pct: number;
  delta?: number;
  vol_k_usdt: number;
  profits: {
    futures_futures?: number;
    futures_spot_2ex?: number;
    futures_spot_1ex?: number;
    funding_ff?: number;
    funding_fs?: number;
    funding_diff_dates?: number;
  };
}

export interface SetScreenerFilterPayload {
  min_volume_k_usdt: number;
  min_spread_pct: number;
}

// --- 4. Opportunity ---

export interface StrategyCalculation {
  strategy_name: string;
  spread_pct: number;
  delta: number;
  fee_pct: number;
  max_vol: number;
  details: string;
}

export interface OpportunityActionPayload {
  action: "accumulate" | "close_partial" | "close_all";
  symbol: string;
  strategy?: string;
}

// --- 5. Orders ---

export interface OrderLeg {
  side: "Short" | "Long";
  exchange: string;
  leverage: number;
  volume: number;
  entry_price: number;
  exit_price?: number;
  fees: number;
  funding: number;
  pnl: number;
}

export interface OrderGroup {
  id: string;
  asset: string;
  short_exchange: string;
  long_exchange: string;
  status: "open" | "closed";
  opened_at: string;
  spread_in: number;
  spread_out?: number;
  total_fees: number;
  total_funding: number;
  total_pnl: number;
  legs: OrderLeg[];
}

// --- 6. Monitors ---

export interface MonitorConfig {
  id: string;
  symbol: string;
  short_exchange: string;
  long_exchange: string;
  side: "Auto" | "LONG" | "SHORT";
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

export interface UpdateConfigPayload {
  cmd: "update_config";
  monitor_id: string;
  config: Partial<MonitorConfig>;
}
