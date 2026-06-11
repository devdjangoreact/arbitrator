from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        case_sensitive=False,
    )

    enabled_exchanges: list[str] = ["binance", "mexc", "bitget", "gate", "bingx"]
    default_type: str = "swap"

    use_threaded_dns_resolver: bool = True
    aiohttp_trust_env: bool = True
    enable_rate_limit: bool = True

    streamlit_page_title: str = "Arbitrator"
    streamlit_page_layout: str = "wide"

    log_level: str = "INFO"

    exclusions_path: Path = _DATA_DIR / "exclusions.json"
    symbols_universe_path: Path = _DATA_DIR / "symbols_universe.json"
    universe_ttl_hours: int = 24
    min_exchanges_per_symbol: int = 2

    default_min_quote_volume_kusdt: float = 0.0
    default_min_spread_pct: float = 0.0
