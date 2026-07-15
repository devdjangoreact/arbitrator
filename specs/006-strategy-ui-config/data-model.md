# Data Model: Strategy UI Configuration

## Entities

### `StrategyUIConfig`

Represents the mutable, persistent configuration managed via the UI.

**Fields (grouped by category):**

#### Auto Trade (Live)
- `live_auto_trade_enabled`: boolean
- `live_auto_trade_post_fill_min_spread_pct`: float
- `live_auto_trade_dca_spread_step_pct`: float
- `live_auto_trade_dca_max_layers`: int
- `live_auto_trade_dca_min_liq_distance_pct`: float
- `live_auto_trade_dca_funding_skip_seconds`: float

#### Auto Trade (Paper/Screener)
- `screener_auto_trade_enabled`: boolean
- `screener_auto_trade_max_positions`: int
- `screener_auto_trade_notional_usdt`: float
- `screener_auto_trade_open_spread_pct`: float
- `screener_auto_trade_close_spread_pct`: float
- `screener_auto_trade_check_seconds`: float
- `screener_auto_trade_unhedged_timeout_seconds`: float

#### Strategy Engine Parameters
- `spot_enabled`: boolean
- `quote_max_age_seconds`: float
- `book_max_age_seconds`: float
- `funding_refresh_seconds`: float
- `funding_entry_window_seconds`: float
- `anomaly_max_spread_pct`: float
- `slippage_max_pct`: float
- `ticker_max_inner_spread_pct`: float
- `execution_rollback_enabled`: boolean
- `leg_imbalance_tolerance_pct`: float
- `open_fail_cooldown_sec`: float
- `allowed_strategies`: list[str]
- `strategy_overrides`: dict[str, dict[str, float]]

#### Protections (Live)
- `live_liq_guard_enabled`: boolean
- `live_liq_guard_check_interval_seconds`: float
- `live_liq_guard_warning_pct_to_liq`: float
- `live_funding_protect_enabled`: boolean
- `live_funding_protect_check_interval_seconds`: float
- `live_funding_protect_act_window_seconds`: float
- `live_funding_protect_skip_within_seconds`: float
- `live_funding_protect_min_reopen_spread_pct`: float

#### Protections (Paper)
- `liq_guard_enabled`: boolean
- `liq_guard_check_interval_seconds`: float
- `liq_guard_warning_pct_to_liq`: float
- `funding_reentry_enabled`: boolean
- `funding_reentry_check_interval_seconds`: float
- `funding_reentry_act_window_seconds`: float
- `funding_reentry_skip_within_seconds`: float
- `funding_reentry_min_spread_pct`: float

#### Historical / Monitor
- `historical_screener_enabled`: boolean
- `historical_screener_lookback_minutes`: int
- `historical_screener_spread_threshold_pct`: float
- `historical_screener_scan_interval_seconds`: float
- `historical_monitor_open_spread_pct`: float
- `historical_monitor_close_spread_pct`: float
- `historical_monitor_max_positions`: int
- `historical_monitor_notional_usdt`: float

#### Opportunities
- `opp_default_accumulate_spread_pct`: float
- `opp_default_max_notional_usdt`: float
- `opp_default_leverage`: int
- `opp_position_imbalance_tolerance_pct`: float
- `opp_accumulate_step_usdt`: float
