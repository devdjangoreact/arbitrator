from __future__ import annotations

import asyncio
import threading
from collections.abc import Mapping, Sequence

from arbitrator.application.multi_exchange_watcher import MultiExchangeWatcher
from arbitrator.application.symbol_universe_service import SymbolUniverseService
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.named_exchange import NamedExchange
from arbitrator.domain.ticker import Ticker
from arbitrator.exchanges.factory import Factory


class ScreenerStreamWorker:
    """Runs the screener WebSocket loop on a background thread.

    Phase 1 (*discovery*) streams the full universe to collect 24h volumes.
    Phase 2 (*filtered*) streams only symbols where at least one exchange
    reports volume above the configured threshold.
    """

    def __init__(
        self,
        settings: Settings,
        factory: Factory,
        universe_service: SymbolUniverseService,
        reconnect_nonce: int,
        volume_threshold_usdt: float,
    ) -> None:
        self._settings = settings
        self._factory = factory
        self._universe_service = universe_service
        self.reconnect_nonce = reconnect_nonce
        self._volume_threshold_usdt = volume_threshold_usdt
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._snapshot: dict[tuple[str, str], Ticker] = {}
        self._stream_symbols: list[str] = []
        self._updates = 0
        self._status = "Connecting…"
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._thread_main,
            name=f"screener-stream:{self.reconnect_nonce}",
            daemon=True,
        )
        self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        """Signal teardown without blocking the caller.

        The UI must never wait for the background
        stream to wind down. We set the stop flag and request cancellation of
        the async task from inside its own loop; the daemon thread then closes
        its watcher and gateways in the background and exits on its own.
        """
        self._stop.set()
        loop = self._loop
        task = self._main_task
        if loop is not None and task is not None and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)

    def read_state(
        self,
    ) -> tuple[dict[tuple[str, str], Ticker], list[str], int, str, float]:
        with self._lock:
            return (
                dict(self._snapshot),
                list(self._stream_symbols),
                self._updates,
                self._status,
                self._volume_threshold_usdt,
            )

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_main())
        except asyncio.CancelledError:
            logger.info("Screener background stream stopped | nonce={}", self.reconnect_nonce)
        except Exception:
            logger.exception("Screener background stream failed")
            self._set_status("Error")

    async def _async_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._main_task = asyncio.current_task()
        named_exchanges = self._factory.create_many(self._settings.enabled_exchanges)
        try:
            try:
                symbols, symbols_by_exchange, _universe = await self._universe_service.resolve(
                    named_exchanges
                )
            except Exception:
                logger.exception("Failed to resolve universe")
                self._set_status("Error")
                return

            if not symbols:
                self._set_status("Idle")
                return

            self._set_stream_symbols(symbols)
            await self._stream_loop(named_exchanges, symbols_by_exchange)
        finally:
            await self._close_exchanges(named_exchanges)

    async def _stream_loop(
        self,
        named_exchanges: Sequence[NamedExchange],
        symbols_by_exchange: Mapping[str, Sequence[str]],
    ) -> None:
        watcher = MultiExchangeWatcher(named_exchanges)
        try:
            async for snapshot in watcher.updates(symbols_by_exchange):
                if self._stop.is_set():
                    break
                self._publish_snapshot(snapshot)
                self._set_status("Live")
        finally:
            logger.info("Closing screener watcher")
            await watcher.close()

    def _publish_snapshot(self, snapshot: Mapping[tuple[str, str], Ticker]) -> None:
        with self._lock:
            self._snapshot = dict(snapshot)
            self._updates += 1

    def _set_stream_symbols(self, symbols: Sequence[str]) -> None:
        with self._lock:
            self._stream_symbols = list(symbols)

    def _set_status(self, status: str) -> None:
        with self._lock:
            self._status = status

    @staticmethod
    async def _close_exchanges(exchanges: Sequence[NamedExchange]) -> None:
        for exchange in exchanges:
            try:
                await exchange.gateway.close()
            except Exception:
                logger.exception(
                    "Failed to close gateway | exchange={}",
                    exchange.exchange_id,
                )
