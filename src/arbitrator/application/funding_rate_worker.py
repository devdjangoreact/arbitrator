from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Sequence

from arbitrator.application.fee_snapshot_service import FeeSnapshotService
from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.named_exchange import NamedExchange
from arbitrator.exchanges.factory import Factory


class FundingRateWorker:
    """Background thread that refreshes funding rates (and fees) into the cache.

    Funding has no ``watch*`` channel, so this is a periodic REST snapshot
    (``funding_refresh_seconds``). It owns its own gateways/event loop (ccxt
    clients are not shared across threads) and pulls the live symbol set from a
    provider so it tracks the screener's filtered universe.
    """

    def __init__(
        self,
        settings: Settings,
        factory: Factory,
        cache: MarketDataCacheMemory,
        fee_service: FeeSnapshotService,
        symbols_provider: Callable[[], Sequence[str]],
    ) -> None:
        self._settings = settings
        self._factory = factory
        self._cache = cache
        self._fee_service = fee_service
        self._symbols_provider = symbols_provider
        self._refresh_seconds = settings.funding_refresh_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._thread_main,
            name="funding-rate-worker",
            daemon=True,
        )
        self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        task = self._main_task
        if loop is not None and task is not None and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_main())
        except asyncio.CancelledError:
            logger.info("funding worker stopped")
        except Exception:
            logger.exception("funding worker failed")

    async def _async_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._main_task = asyncio.current_task()
        named_exchanges = self._factory.create_many(self._settings.enabled_exchanges)
        try:
            while not self._stop.is_set():
                await self._refresh_once(named_exchanges)
                await asyncio.sleep(self._refresh_seconds)
        finally:
            await self._close_exchanges(named_exchanges)

    async def _refresh_once(self, named_exchanges: Sequence[NamedExchange]) -> None:
        symbols = list(self._symbols_provider())
        if not symbols:
            return
        await self._fee_service.snapshot(named_exchanges, symbols)
        for exchange in named_exchanges:
            try:
                infos = await exchange.gateway.fetch_funding_infos(symbols)
            except Exception:
                logger.exception(
                    "funding refresh failed | exchange={}",
                    exchange.exchange_id,
                )
                continue
            for info in infos:
                self._cache.put_funding(info)
            logger.debug(
                "funding refreshed | exchange={} count={}",
                exchange.exchange_id,
                len(infos),
            )

    @staticmethod
    async def _close_exchanges(named_exchanges: Sequence[NamedExchange]) -> None:
        for exchange in named_exchanges:
            try:
                await exchange.gateway.close()
            except Exception:
                logger.exception(
                    "Failed to close funding gateway | exchange={}",
                    exchange.exchange_id,
                )
