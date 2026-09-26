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
  max_price: number;
  min_price: number;
  spread_pct: number;
  spread_delta?: number;
  volume_k_usdt: number;
  prices: Record<string, { futures: number | null; spot: number | null }>;
  strategy_profits: {
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
  side: "auto" | "long" | "short";
  open_spread_pct: number;
  open_ticks: number;
  close_spread_pct: number;
  close_ticks: number;
  order_size_usdt: number;
  max_orders: number;
  allowed_size_usdt: number;
  allowed_size_current_usdt: number;
  force_stop: boolean;
  total_stop: boolean;
  is_active: boolean;
  adjustment_mode: "notify_only" | "adjust";
  short_leverage: number;
  long_leverage: number;
  max_historical_spread_pct: number;
}

export interface UpdateConfigPayload {
  cmd: "update_config";
  monitor_id: string;
  config: Partial<MonitorConfig>;
}

export interface HistoricalOpportunity {
  symbol: string;
  short_exchange: string;
  long_exchange: string;
  current_spread_pct: number;
  max_historical_spread_pct: number;
  signal_time_seconds: number;
  short_funding_rate: number;
  long_funding_rate: number;
  short_next_funding: number;
  long_next_funding: number;
  short_price: number;
  long_price: number;
  short_volume_24h: number;
  long_volume_24h: number;
  detected_at: number;
  lookback_seconds: number;
}

export interface MonitorLiveState {
  active_short: string | null;
  active_long: string | null;
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
  short_leverage: number | null;
  long_leverage: number | null;
  max_size_short: number | null;
  max_size_long: number | null;
  min_size_short: number | null;
  min_size_long: number | null;
  allowed_short: number | null;
  allowed_long: number | null;
  short_price: number | null;
  long_price: number | null;
  short_entry_price: number | null;
  long_entry_price: number | null;
  short_liq_price: number | null;
  long_liq_price: number | null;
  short_pnl: number | null;
  long_pnl: number | null;
  short_realized_pnl: number;
  long_realized_pnl: number;
  enter_spread: number | null;
  short_accrued_funding: number | null;
  long_accrued_funding: number | null;
  short_open_fee: number | null;
  long_open_fee: number | null;
  short_close_fee_est: number | null;
  long_close_fee_est: number | null;
  short_orders: number;
  long_orders: number;
  open_spread_current: number;
  open_spread_min: number;
  open_spread_max: number;
  close_spread_current: number;
  close_spread_min: number;
  close_spread_max: number;
  vwap_short_bid: number | null;
  vwap_long_ask: number | null;
  vwap_short_ask: number | null;
  vwap_long_bid: number | null;
}

export type LiveStateMap = Record<string, MonitorLiveState>;
