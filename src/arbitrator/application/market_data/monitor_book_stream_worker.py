from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from decimal import Decimal

from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.logger import logger
from arbitrator.config.monitor_config_store import MonitorConfigStore
from arbitrator.config.settings import Settings
from arbitrator.domain.exchange.exchange_gateway import ExchangeGateway
from arbitrator.domain.market.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.strategy.quote import Quote
from arbitrator.exchanges.factory import Factory


class MonitorBookStreamWorker:
    """WS ``watch_order_book`` for every ``(exchange, symbol)`` pair in ``MonitorConfigStore``.

    Fills ``MarketDataCacheMemory`` with live order-book data so that
    ``ExecutableSpreadResolver.entry_spread_sync`` / ``exit_spread_sync`` return
    fresh quotes for exchanges NOT covered by ``ScreenerBookStreamWorker``
    (e.g. Gate, Bitget).

    Pairs already served by ``screener_book_stream_exchanges`` are skipped to
    avoid duplicate WebSocket connections.  Pairs whose symbol is absent from
    the cached universe for the given exchange are also skipped — the symbol
    is not traded on that exchange.  The symbol list is refreshed every
    ``_REFRESH_SECONDS`` so newly added monitors are picked up automatically.
    """

    _REFRESH_SECONDS = 5.0

    def __init__(
        self,
        settings: Settings,
        factory: Factory,
        cache: MarketDataCacheMemory,
        store: MonitorConfigStore,
        universe: dict[str, set[str]] | None = None,
        screener_symbols_provider: Callable[[], dict[str, list[str]]] | None = None,
    ) -> None:
        self._settings = settings
        self._factory = factory
        self._cache = cache
        self._store = store
        self._universe = universe
        self._screener_symbols_provider = screener_symbols_provider
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._thread_main,
            name="monitor-book-stream",
            daemon=True,
        )
        self._thread.start()
        logger.info("monitor book stream worker started")

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        task = self._main_task
        if loop is not None and task is not None and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _screener_covered(self) -> dict[str, set[str]]:
        """Returns {exchange_id: set(symbols)} that ScreenerBookStreamWorker actually streams."""
        enabled = set(self._settings.enabled_exchanges)
        screener_exchanges = {
            ex for ex in self._settings.screener_book_stream_exchanges if ex in enabled
        }
        if not screener_exchanges or self._screener_symbols_provider is None:
            return {}
        by_ex = self._screener_symbols_provider()
        return {ex: set(syms) for ex, syms in by_ex.items() if ex in screener_exchanges}

    def _desired_pairs(self) -> set[tuple[str, str]]:
        screener_covered = self._screener_covered()
        pairs: set[tuple[str, str]] = set()
        for cfg in self._store.get_all():
            for ex in (cfg.short_exchange, cfg.long_exchange):
                # Skip only if screener actively streams this pair AND the cache
                # already has a book for it. If the screener nominally covers the
                # exchange but has not yet delivered a book, subscribe here so the
                # monitor card gets data as fast as possible.
                if cfg.symbol in screener_covered.get(ex, set()):
                    ob = self._cache.get_order_book(ex, cfg.symbol)
                    if ob and ob.bids and ob.asks:
                        continue
                if self._universe is not None and cfg.symbol not in self._universe.get(ex, set()):
                    logger.warning(
                        "monitor book stream skip | exchange={} symbol={} reason=not_in_universe",
                        ex,
                        cfg.symbol,
                    )
                    continue
                pairs.add((ex, cfg.symbol))
        return pairs

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_main())
        except asyncio.CancelledError:
            logger.info("monitor book stream stopped")
        except Exception:
            logger.exception("monitor book stream failed")

    async def _async_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._main_task = asyncio.current_task()
        gateways: dict[str, ExchangeGateway] = {}
        active: dict[tuple[str, str], asyncio.Task[None]] = {}
        limit = self._settings.opportunity_order_book_depth
        sem = asyncio.Semaphore(self._settings.screener_book_stream_max_concurrent)

        try:
            while not self._stop.is_set():
                desired = self._desired_pairs()

                for pair in set(active) - desired:
                    active.pop(pair).cancel()
                    logger.debug(
                        "monitor book stream unsubscribed | exchange={} symbol={}",
                        pair[0],
                        pair[1],
                    )

                for pair in desired - set(active):
                    ex_id, symbol = pair
                    if ex_id not in gateways:
                        gateways[ex_id] = self._factory.create(ex_id).gateway
                    active[pair] = asyncio.create_task(
                        self._watch_symbol(gateways[ex_id], ex_id, symbol, limit, sem),
                        name=f"monitor-book:{ex_id}:{symbol}",
                    )
                    logger.info(
                        "monitor book stream subscribed | exchange={} symbol={}",
                        ex_id,
                        symbol,
                    )

                await asyncio.sleep(self._REFRESH_SECONDS)

        except asyncio.CancelledError:
            pass
        finally:
            for task in active.values():
                task.cancel()
            if active:
                await asyncio.gather(*active.values(), return_exceptions=True)
            for gateway in gateways.values():
                try:
                    await gateway.close()
                except Exception:
                    logger.exception("monitor book stream gateway close failed")

    async def _watch_symbol(
        self,
        gateway: ExchangeGateway,
        exchange_id: str,
        symbol: str,
        limit: int,
        sem: asyncio.Semaphore,
    ) -> None:
        delay = self._settings.ws_reconnect_delay_seconds
        await asyncio.sleep(0.3)
        while not self._stop.is_set():
            try:
                async with sem:
                    async for book in gateway.watch_order_book(symbol, limit):
                        if self._stop.is_set():
                            return
                        self._publish_book(book)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "monitor book stream disconnected | exchange={} symbol={} retry_in={}s",
                    exchange_id,
                    symbol,
                    delay,
                )
                await asyncio.sleep(delay)

    def _publish_book(self, book: OrderBookSnapshot) -> None:
        self._cache.put_order_book(book)
        if not book.bids or not book.asks:
            return
        bid = book.bids[0].price
        ask = book.asks[0].price
        if bid <= 0.0 or ask <= 0.0:
            return
        recv_ms = (
            book.timestamp_ms if book.timestamp_ms is not None else int(time.time() * 1000)
        )
        self._cache.put_quote(
            Quote(
                exchange_id=book.exchange_id,
                symbol=book.symbol,
                market_type="futures",
                bid=Decimal(str(bid)),
                ask=Decimal(str(ask)),
                last=None,
                recv_time_ms=recv_ms,
            )
        )
