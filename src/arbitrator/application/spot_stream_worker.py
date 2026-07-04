from __future__ import annotations

import asyncio
import threading
from collections.abc import Mapping

from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.spot_gateway import SpotGateway


class SpotStreamWorker:
    """Background thread: watches spot tickers and feeds quotes into MarketDataCache."""

    def __init__(
        self,
        settings: Settings,
        spot_gateways: Mapping[str, SpotGateway],
        cache: MarketDataCacheMemory,
    ) -> None:
        self._settings = settings
        self._gateways = spot_gateways
        self._cache = cache
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self._gateways:
            logger.info("spot stream worker skipped — no spot gateways")
            return
        self._thread = threading.Thread(
            target=self._run,
            name="spot-stream-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "spot stream worker started | exchanges={}",
            list(self._gateways.keys()),
        )

    def stop(self) -> None:
        self._stop.set()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self._async_main())
        except Exception:
            logger.exception("spot stream worker crashed")
        finally:
            loop.close()

    async def _async_main(self) -> None:
        tasks = [
            asyncio.create_task(self._watch_exchange(exchange_id, gw))
            for exchange_id, gw in self._gateways.items()
        ]
        try:
            while not self._stop.is_set():
                await asyncio.sleep(1.0)
        finally:
            for t in tasks:
                t.cancel()
            for gw in self._gateways.values():
                try:
                    await gw.close()
                except Exception:
                    pass

    async def _watch_exchange(self, exchange_id: str, gw: SpotGateway) -> None:
        try:
            symbols = await gw.list_spot_symbols()
        except Exception:
            logger.exception("spot list_symbols failed | exchange={}", exchange_id)
            return
        if not symbols:
            logger.info("spot stream: no USDT spot symbols | exchange={}", exchange_id)
            return
        # Only watch symbols that also exist in futures (intersection with screener)
        # ponytail: watch all — filtering is caller's job
        logger.info(
            "spot stream watching | exchange={} symbols={}",
            exchange_id, len(symbols),
        )
        async for quotes in gw.watch_spot_tickers(symbols):
            if self._stop.is_set():
                break
            for _symbol, quote in quotes.items():
                # Store with futures symbol key so assembler finds it
                # spot "BTC/USDT" -> futures key "BTC/USDT:USDT"
                futures_symbol = quote.symbol + ":USDT" if ":USDT" not in quote.symbol else quote.symbol
                normalized = quote.model_copy(update={"symbol": futures_symbol})
                self._cache.put_quote(normalized)
