from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from arbitrator.domain.exchange.exchange_credentials import ExchangeCredentials

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

    historical_trader_tick_seconds: float = 2.0  # Interval for auto-trader check


    fastapi_host: str = "127.0.0.1"
    fastapi_port: int = 8000
    fastapi_reload: bool = False
    app_title: str = "Arbitrator"

    use_react_frontend: bool = False

    ui_data_mode: Literal["mock_data", "live", "paper"] = "mock_data"
    mock_tick_seconds: float = 1.0
    screener_ws_push_seconds: float = 1.0

    paper_orders_path: Path = _DATA_DIR / "paper_orders.json"
    monitor_configs_path: Path = _DATA_DIR / "monitor_configs.json"

    log_level: str = "INFO"

    exclusions_path: Path = _DATA_DIR / "exclusions.json"
    symbols_universe_path: Path = _DATA_DIR / "symbols_universe.json"
    universe_ttl_hours: int = 24
    min_exchanges_per_symbol: int = 2

    default_min_quote_volume_kusdt: float = 500.0
    default_min_spread_pct: float = 1.0
    stream_min_quote_volume_usdt: float = 1_000_000.0
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
    # Live auto-trader (live mode only — places real orders)
    # Post-fill guard: close pair immediately if actual spread < this after fill
    # DCA: accumulate when current spread >= entry_spread + this value
    # DCA: max times to accumulate one pair
    # DCA: min distance to liquidation (%) required to add
    # DCA: skip if next funding is within this many seconds

    # Historical Screener & Monitor


    # Liquidation guard (paper mode)

    # --- PUBLIC GATEWAY PROXIES (Spec 003) ---
    exchange_public_http_proxy: str | None = None
    exchange_public_ws_proxy: str | None = None
    exchange_public_socks_proxy: str | None = None

    # Funding reentry (paper mode)

    # Live liquidation guard (live mode)

    # Live funding protection (live mode)

    opportunity_order_book_depth: int = 20
    screener_book_stream_exchanges: list[str] = ["mexc"]
    screener_book_stream_max_concurrent: int = 20
    screener_book_stream_symbol_refresh_seconds: float = 3600.0
    opportunity_chart_window_seconds: int = 120
    opportunity_poll_seconds: int = 1

    # --- Strategy selection & per-strategy overrides ---
    # Which strategies the auto-trader is allowed to open.
    # Empty list = all strategies allowed. Non-empty = whitelist.
    # Per-strategy parameter overrides (JSON dict in .env).
    # Keys = strategy_id, values = dict of overridable params.
    # Overridable: open_spread_pct, close_spread_pct, notional_usdt, max_positions
    # Example: {"futures_futures": {"open_spread_pct": 1.5, "close_spread_pct": 0.02}}

    # --- Strategy engine (002-strategy-engine) ---
    spot_default_type: str = "spot"
    strategy_decimal_places: int = 2
    deposit_basis: Literal["position_margin", "account_balance"] = "position_margin"

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

    def public_http_proxy_for(self, exchange_id: str) -> str | None:
        """Return public HTTP proxy for the given exchange."""
        return self.exchange_public_http_proxy

    def public_ws_proxy_for(self, exchange_id: str) -> str | None:
        """Return public WS proxy for the given exchange."""
        return self.exchange_public_ws_proxy

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
