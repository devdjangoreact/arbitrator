from pydantic import BaseModel, Field
from typing import Literal

class StrategyUIConfig(BaseModel):
    """
    Mutable, persistent strategy configuration managed via the UI.
    """
    # Auto Trade (Live)
    live_auto_trade_enabled: bool = False
    live_auto_trade_post_fill_min_spread_pct: float = 0.5
    live_auto_trade_dca_spread_step_pct: float = 1.0
    live_auto_trade_dca_max_layers: int = 1
    live_auto_trade_dca_min_liq_distance_pct: float = 10.0
    live_auto_trade_dca_funding_skip_seconds: float = 1800.0

    # Auto Trade (Paper/Screener)
    screener_auto_trade_enabled: bool = False
    screener_auto_trade_max_positions: int = 3
    screener_auto_trade_notional_usdt: float = 100.0
    screener_auto_trade_open_spread_pct: float = 3.0
    screener_auto_trade_close_spread_pct: float = 0.05
    screener_auto_trade_check_seconds: float = 2.0
    screener_auto_trade_unhedged_timeout_seconds: float = 10.0

    # Strategy Engine Parameters
    spot_enabled: bool = False
    quote_max_age_seconds: float = 5.0
    book_max_age_seconds: float = 2.0
    funding_refresh_seconds: float = 60.0
    funding_entry_window_seconds: float = 300.0
    anomaly_max_spread_pct: float = 20.0
    slippage_max_pct: float = 0.5
    ticker_max_inner_spread_pct: float = 1.0
    execution_rollback_enabled: bool = True
    leg_imbalance_tolerance_pct: float = 1.0
    open_fail_cooldown_sec: float = 120.0
    allowed_strategies: list[str] = Field(default_factory=list)
    strategy_overrides: dict[str, dict[str, float]] = Field(default_factory=dict)

    # Protections (Live)
    live_liq_guard_enabled: bool = True
    live_liq_guard_check_interval_seconds: float = 5.0
    live_liq_guard_warning_pct_to_liq: float = 80.0
    live_funding_protect_enabled: bool = True
    live_funding_protect_check_interval_seconds: float = 30.0
    live_funding_protect_act_window_seconds: float = 300.0
    live_funding_protect_skip_within_seconds: float = 60.0
    live_funding_protect_min_reopen_spread_pct: float = 0.1

    # Protections (Paper)
    liq_guard_enabled: bool = True
    liq_guard_check_interval_seconds: float = 5.0
    liq_guard_warning_pct_to_liq: float = 80.0
    funding_reentry_enabled: bool = False
    funding_reentry_check_interval_seconds: float = 30.0
    funding_reentry_act_window_seconds: float = 300.0
    funding_reentry_skip_within_seconds: float = 60.0
    funding_reentry_min_spread_pct: float = 0.1

    # Historical / Monitor
    historical_screener_enabled: bool = False
    historical_screener_lookback_minutes: int = 60
    historical_screener_spread_threshold_pct: float = 1.0
    historical_screener_scan_interval_seconds: float = 5.0
    historical_monitor_open_spread_pct: float = 1.0
    historical_monitor_close_spread_pct: float = 0.1
    historical_monitor_max_positions: int = 3
    historical_monitor_notional_usdt: float = 100.0

    # Opportunities
    opp_default_accumulate_spread_pct: float = 4.0
    opp_default_max_notional_usdt: float = 500.0
    opp_default_leverage: int = 10
    opp_position_imbalance_tolerance_pct: float = 1.0
    opp_accumulate_step_usdt: float = 100.0

    def is_strategy_allowed(self, strategy_kind: str) -> bool:
        """Check if strategy is in the whitelist (empty list = all allowed)."""
        if not self.allowed_strategies:
            return True
        return strategy_kind in self.allowed_strategies

    def strategy_open_spread_pct(self, strategy_kind: str) -> float:
        """Return open spread threshold for a strategy (override or default)."""
        overrides = self.strategy_overrides.get(strategy_kind)
        if overrides and "open_spread_pct" in overrides:
            return overrides["open_spread_pct"]
        return self.screener_auto_trade_open_spread_pct

    def strategy_close_spread_pct(self, strategy_kind: str) -> float:
        """Return close spread threshold for a strategy (override or default)."""
        overrides = self.strategy_overrides.get(strategy_kind)
        if overrides and "close_spread_pct" in overrides:
            return overrides["close_spread_pct"]
        return self.screener_auto_trade_close_spread_pct

    def strategy_notional_usdt(self, strategy_kind: str) -> float:
        """Return notional for a strategy (override or default)."""
        overrides = self.strategy_overrides.get(strategy_kind)
        if overrides and "notional_usdt" in overrides:
            return overrides["notional_usdt"]
        return self.screener_auto_trade_notional_usdt

    def strategy_max_positions(self, strategy_kind: str) -> int:
        """Return max positions for a strategy (override or default global max)."""
        overrides = self.strategy_overrides.get(strategy_kind)
        if overrides and "max_positions" in overrides:
            return int(overrides["max_positions"])
        return self.screener_auto_trade_max_positions
