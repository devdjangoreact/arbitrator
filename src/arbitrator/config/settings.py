from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from arbitrator.domain.exchange_credentials import ExchangeCredentials

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_PASSWORD_EXCHANGES: frozenset[str] = frozenset({"bitget"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    enabled_exchanges: list[str] = [
        "binance",
        "mexc",
        "bitget",
        "gate",
        "bingx",
    ]
    default_type: str = "swap"

    use_threaded_dns_resolver: bool = True
    aiohttp_trust_env: bool = True
    enable_rate_limit: bool = True
    watch_tickers_chunk_size: int = 50
    watch_tickers_max_concurrent_chunks: int = 8
    ws_reconnect_delay_seconds: float = 5.0
    ccxt_request_timeout_ms: int = 60_000

    fastapi_host: str = "127.0.0.1"
    fastapi_port: int = 8000
    fastapi_reload: bool = False
    app_title: str = "Arbitrator"

    ui_data_mode: Literal["mock_data", "live", "paper"] = "mock_data"
    mock_tick_seconds: float = 1.0
    screener_ws_push_seconds: float = 1.0

    paper_orders_path: Path = _DATA_DIR / "paper_orders.json"

    log_level: str = "INFO"

    exclusions_path: Path = _DATA_DIR / "exclusions.json"
    symbols_universe_path: Path = _DATA_DIR / "symbols_universe.json"
    universe_ttl_hours: int = 24
    min_exchanges_per_symbol: int = 2

    default_min_quote_volume_kusdt: float = 500.0
    default_min_spread_pct: float = 0.0
    stream_min_quote_volume_usdt: float = 500_000.0
    screener_volume_discovery_seconds: float = 60.0

    screener_table_height_px: int = 800

    arb_open_spread_threshold_pct: float = 4.0
    arb_close_spread_threshold_pct: float = 0.1
    arb_auto_open_enabled: bool = False
    arb_auto_open_check_seconds: int = 30
    arb_auto_close_enabled: bool = False
    arb_default_notional_usdt: float = 100.0
    arb_pairing_window_seconds: int = 300
    arb_closed_history_days: int = 30
    arb_positions_poll_seconds: int = 5
    arb_markers_path: Path = _DATA_DIR / "arb_markers.json"

    # Screener auto-trader (paper mode only)
    screener_auto_trade_enabled: bool = False
    # Live auto-trader (live mode only — places real orders)
    live_auto_trade_enabled: bool = False
    screener_auto_trade_max_positions: int = 3
    screener_auto_trade_notional_usdt: float = 100.0
    screener_auto_trade_open_spread_pct: float = 3.0
    screener_auto_trade_close_spread_pct: float = 0.05
    screener_auto_trade_check_seconds: float = 2.0
    screener_auto_trade_unhedged_timeout_seconds: float = 10.0
    # Post-fill guard: close pair immediately if actual spread < this after fill
    live_auto_trade_post_fill_min_spread_pct: float = 0.5
    # DCA: accumulate when current spread >= entry_spread + this value
    live_auto_trade_dca_spread_step_pct: float = 1.0
    # DCA: max times to accumulate one pair
    live_auto_trade_dca_max_layers: int = 1
    # DCA: min distance to liquidation (%) required to add
    live_auto_trade_dca_min_liq_distance_pct: float = 10.0
    # DCA: skip if next funding is within this many seconds
    live_auto_trade_dca_funding_skip_seconds: float = 1800.0

    # Liquidation guard (paper mode)
    liq_guard_enabled: bool = True
    liq_guard_check_interval_seconds: float = 5.0
    liq_guard_warning_pct_to_liq: float = 80.0  # close when 80% of margin consumed

    # Funding reentry (paper mode)
    funding_reentry_enabled: bool = False
    funding_reentry_check_interval_seconds: float = 30.0
    funding_reentry_act_window_seconds: float = 300.0  # check when funding is within 5 min
    funding_reentry_skip_within_seconds: float = 60.0  # do not act in last 60s before funding
    funding_reentry_min_spread_pct: float = 0.1        # minimum spread to reopen

    # Live liquidation guard (live mode)
    live_liq_guard_enabled: bool = True
    live_liq_guard_check_interval_seconds: float = 5.0
    live_liq_guard_warning_pct_to_liq: float = 80.0

    # Live funding protection (live mode)
    live_funding_protect_enabled: bool = False
    live_funding_protect_check_interval_seconds: float = 30.0
    live_funding_protect_act_window_seconds: float = 300.0
    live_funding_protect_skip_within_seconds: float = 60.0
    live_funding_protect_min_reopen_spread_pct: float = 0.1

    opportunity_order_book_depth: int = 20
    opportunity_chart_window_seconds: int = 120
    opportunity_poll_seconds: int = 1
    opp_default_accumulate_spread_pct: float = 4.0
    opp_default_max_notional_usdt: float = 500.0
    opp_default_leverage: int = 10
    opp_position_imbalance_tolerance_pct: float = 1.0
    opp_accumulate_step_usdt: float = 100.0

    # --- Strategy selection & per-strategy overrides ---
    # Which strategies the auto-trader is allowed to open.
    # Empty list = all strategies allowed. Non-empty = whitelist.
    allowed_strategies: list[str] = []
    # Per-strategy parameter overrides (JSON dict in .env).
    # Keys = strategy_id, values = dict of overridable params.
    # Overridable: open_spread_pct, close_spread_pct, notional_usdt, max_positions
    # Example: {"futures_futures": {"open_spread_pct": 1.5, "close_spread_pct": 0.02}}
    strategy_overrides: dict[str, dict[str, float]] = {}

    # --- Strategy engine (002-strategy-engine) ---
    spot_enabled: bool = False
    spot_default_type: str = "spot"
    quote_max_age_seconds: float = 5.0
    book_max_age_seconds: float = 2.0
    funding_refresh_seconds: float = 60.0
    funding_entry_window_seconds: float = 300.0
    strategy_decimal_places: int = 2
    anomaly_max_spread_pct: float = 20.0
    slippage_max_pct: float = 0.5
    ticker_max_inner_spread_pct: float = 1.0
    prediction_enabled: bool = False
    prediction_window_seconds: float = 120.0
    deposit_basis: Literal["position_margin", "account_balance"] = "position_margin"
    execution_rollback_enabled: bool = True
    leg_imbalance_tolerance_pct: float = 1.0
    open_fail_cooldown_sec: float = 120.0

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    binance_api_key: str = ""
    binance_api_secret: str = ""
    mexc_api_key: str = ""
    mexc_api_secret: str = ""
    bitget_api_key: str = ""
    bitget_api_secret: str = ""
    bitget_api_password: str = ""
    gate_api_key: str = ""
    gate_api_secret: str = ""
    bingx_api_key: str = ""
    bingx_api_secret: str = ""

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

    def credentials_for(self, exchange_id: str) -> ExchangeCredentials | None:
        mapping: dict[str, ExchangeCredentials] = {
            "binance": ExchangeCredentials(
                api_key=self.binance_api_key,
                api_secret=self.binance_api_secret,
            ),
            "mexc": ExchangeCredentials(
                api_key=self.mexc_api_key,
                api_secret=self.mexc_api_secret,
            ),
            "bitget": ExchangeCredentials(
                api_key=self.bitget_api_key,
                api_secret=self.bitget_api_secret,
                password=self.bitget_api_password,
            ),
            "gate": ExchangeCredentials(
                api_key=self.gate_api_key,
                api_secret=self.gate_api_secret,
            ),
            "bingx": ExchangeCredentials(
                api_key=self.bingx_api_key,
                api_secret=self.bingx_api_secret,
            ),
        }
        creds = mapping.get(exchange_id)
        if creds is None:
            return None
        requires_password = exchange_id in _PASSWORD_EXCHANGES
        if not creds.is_complete(requires_password=requires_password):
            return None
        return creds
