from __future__ import annotations

import asyncio
import ssl
from typing import cast

import aiohttp
import ccxt.pro as ccxtpro
import certifi

from arbitrator_2.connector.connector_settings import ConnectorSettings
from arbitrator_2.connector.market_kind import MarketKind

_DEFAULT_TYPE = {MarketKind.SPOT: "spot", MarketKind.PERP: "swap"}


class CcxtSessionFactory:
    def __init__(self, settings: ConnectorSettings | None = None) -> None:
        self._settings = settings if settings is not None else ConnectorSettings()

    def create(self, venue_id: str, market_kind: MarketKind) -> object:
        cls = getattr(ccxtpro, venue_id, None)
        if cls is None:
            raise ValueError(f"unknown venue: {venue_id}")
        options: dict[str, object] = {
            "defaultType": _DEFAULT_TYPE[market_kind],
            "adjustForTimeDifference": True,
        }
        if venue_id == "gate":
            options["watchOrderBook"] = {
                "checksum": False,
                "snapshotDelay": 0,
                "snapshotMaxRetries": 10,
                "maxRetries": 10,
            }
        config: dict[str, object] = {
            "enableRateLimit": True,
            "timeout": self._settings.ccxt_request_timeout_ms,
            "options": options,
        }
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            config["session"] = self._session()
        client = cls(config)
        client.apiKey = ""
        client.secret = ""
        client.password = ""
        client.http_proxy = self._proxy(self._settings.exchange_public_http_proxy)
        client.ws_proxy = self._proxy(self._settings.exchange_public_ws_proxy)
        client.socks_proxy = self._proxy(self._settings.exchange_public_socks_proxy)
        return cast(object, client)

    @staticmethod
    async def close_client(client: object) -> None:
        session = getattr(client, "session", None)
        closer = getattr(client, "close", None)
        if callable(closer):
            result = closer()
            if asyncio.iscoroutine(result):
                try:
                    await asyncio.wait_for(result, timeout=2.0)
                except TimeoutError:
                    pass
        if isinstance(session, aiohttp.ClientSession) and not session.closed:
            await session.close()

    @staticmethod
    def _proxy(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @staticmethod
    def _session() -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(
            ssl=ssl.create_default_context(cafile=certifi.where()),
            resolver=aiohttp.ThreadedResolver(),
            enable_cleanup_closed=True,
        )
        return aiohttp.ClientSession(connector=connector, trust_env=False)
