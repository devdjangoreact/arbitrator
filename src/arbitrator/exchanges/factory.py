from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
from typing import ClassVar

import ccxt.pro as ccxtpro

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.exchange.named_exchange import NamedExchange
from arbitrator.exchanges.binance import Binance
from arbitrator.exchanges.bingx import Bingx
from arbitrator.exchanges.bitget import Bitget
from arbitrator.exchanges.ccxt_base import CcxtBase
from arbitrator.exchanges.gate import Gate
from arbitrator.exchanges.mexc import Mexc


class Factory:
    """Builds ExchangeGateway implementations by canonical exchange id."""

    _registry: ClassVar[dict[str, type[CcxtBase]]] = {
        Binance.exchange_id: Binance,
        Mexc.exchange_id: Mexc,
        Bitget.exchange_id: Bitget,
        Gate.exchange_id: Gate,
        Bingx.exchange_id: Bingx,
    }

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # Donor ccxt clients with pre-loaded markets, keyed by exchange_id.
        # Populated by preload_markets(); shared to new CcxtBase instances via
        # set_markets_from_exchange so they skip the REST load_markets call.
        self._market_donors: dict[str, ccxtpro.Exchange] = {}

    def supported_ids(self) -> tuple[str, ...]:
        return tuple(self._registry.keys())

    def display_name(self, exchange_id: str) -> str:
        return self._lookup(exchange_id).display_name

    def create(self, exchange_id: str, mode: str = "public") -> NamedExchange:
        cls = self._lookup(exchange_id)
        gateway = cls(self._settings, mode=mode)
        donor = self._market_donors.get(exchange_id)
        if donor is not None:
            gateway.set_market_donor(donor)
        return NamedExchange(
            exchange_id=cls.exchange_id,
            display_name=cls.display_name,
            gateway=gateway,
        )

    def create_public(self, exchange_id: str) -> NamedExchange:
        return self.create(exchange_id, mode="public")

    def create_private(self, exchange_id: str) -> NamedExchange:
        return self.create(exchange_id, mode="private")

    def create_many(self, exchange_ids: list[str], mode: str = "public") -> list[NamedExchange]:
        return [self.create(eid, mode=mode) for eid in exchange_ids]

    def preload_markets(self, exchange_ids: list[str]) -> None:
        """Parallel REST load_markets for all exchanges before workers start.

        After this call every gateway created via Factory.create() receives
        markets instantly via set_markets_from_exchange — no per-instance REST.
        Runs in a dedicated thread so it works both inside and outside a running
        event loop (uvicorn lifespan calls this from within asyncio).
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, self._preload_async(exchange_ids))
            future.result()

    async def _preload_async(self, exchange_ids: list[str]) -> None:
        async def _load_one(exchange_id: str) -> None:
            cls = self._lookup(exchange_id)
            client = cls.build_public_client(self._settings)
            # Grab connector reference before close — ClientSession(connector=...)
            # sets connector_owner=False, so session.close() won't close it.
            session = getattr(client, "session", None)
            connector = getattr(session, "connector", None) if session is not None else None
            try:
                await client.load_markets()
                self._market_donors[exchange_id] = client
                logger.info(
                    "markets preloaded | exchange={} count={}",
                    exchange_id,
                    len(client.markets),
                )
            except Exception:
                logger.exception("markets preload failed | exchange={} — will load on demand", exchange_id)
            finally:
                with contextlib.suppress(Exception):
                    await client.close()
                if connector is not None:
                    with contextlib.suppress(Exception):
                        await connector.close()

        await asyncio.gather(*[_load_one(ex) for ex in exchange_ids])

    @classmethod
    def _lookup(cls, exchange_id: str) -> type[CcxtBase]:
        try:
            return cls._registry[exchange_id]
        except KeyError as exc:
            logger.error(
                "Unknown exchange id | requested={} supported={}",
                exchange_id,
                list(cls._registry.keys()),
            )
            raise ValueError("unknown exchange id") from exc
