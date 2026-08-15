from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ConnectorSettings(BaseSettings):
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
    book_depth: int = 1
    exchange_public_http_proxy: str | None = None
    exchange_public_ws_proxy: str | None = None
    exchange_public_socks_proxy: str | None = None
    ccxt_request_timeout_ms: int = 60_000
