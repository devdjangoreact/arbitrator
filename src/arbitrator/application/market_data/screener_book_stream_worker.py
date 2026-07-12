from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable, Mapping
from decimal import Decimal

from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.market_data.screener_stream_worker import ScreenerStreamWorker
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.exchange.exchange_gateway import ExchangeGateway
from arbitrator.domain.market.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.market.ticker import Ticker
from arbitrator.domain.strategy.quote import Quote
from arbitrator.exchanges.factory import Factory


class ScreenerBookStreamWorker:
    """WS ``watch_order_book`` for screener venues that omit bid/ask in ``watch_tickers``.

    Feeds ``MarketDataCacheMemory`` so :class:`ExecutableSpreadResolver` can rank
    screener rows by executable spread (e.g. MEXC futures).
    """

    def __init__(
        self,
        settings: Settings,
        factory: Factory,
        cache: MarketDataCacheMemory,
        screener_worker: ScreenerStreamWorker,
        snapshot_provider: Callable[[], Mapping[tuple[str, str], Ticker]],
    ) -> None:
        self._settings = settings
        self._factory = factory
        self._cache = cache
        self._screener_worker = screener_worker
        self._snapshot_provider = snapshot_provider
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        exchanges = self._target_exchanges()
        if not exchanges:
            logger.info("screener book stream skipped — no target exchanges")
            return
        self._thread = threading.Thread(
            target=self._thread_main,
            name="screener-book-stream",
            daemon=True,
        )
        self._thread.start()
        logger.info("screener book stream started | exchanges={}", exchanges)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        task = self._main_task
        if loop is not None and task is not None and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)

    def set_screener_worker(self, screener_worker: ScreenerStreamWorker) -> None:
        self._screener_worker = screener_worker

    def _target_exchanges(self) -> list[str]:
        enabled = set(self._settings.enabled_exchanges)
        return [
            exchange_id
            for exchange_id in self._settings.screener_book_stream_exchanges
            if exchange_id in enabled
        ]

    def _symbols_for_exchange(self, exchange_id: str) -> list[str]:
        snapshot = self._snapshot_provider()
        symbols = {
            symbol
            for ex, symbol in snapshot
            if ex == exchange_id
        }
        if symbols:
            return sorted(symbols)
        symbols_by_ex = self._screener_worker.read_symbols_by_exchange()
        return sorted(symbols_by_ex.get(exchange_id, []))

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_main())
        except asyncio.CancelledError:
            logger.info("screener book stream stopped")
        except Exception:
            logger.exception("screener book stream failed")

    async def _async_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._main_task = asyncio.current_task()
        gateways: dict[str, ExchangeGateway] = {}
        tasks: list[asyncio.Task[None]] = []
        try:
            for exchange_id in self._target_exchanges():
                gateways[exchange_id] = self._factory.create(exchange_id).gateway
                tasks.append(
                    asyncio.create_task(
                        self._manage_exchange(exchange_id, gateways[exchange_id]),
                        name=f"screener-book:{exchange_id}",
                    )
                )
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for gateway in gateways.values():
                try:
                    await gateway.close()
                except Exception:
                    logger.exception("screener book stream gateway close failed")

    async def _manage_exchange(
        self,
        exchange_id: str,
        gateway: ExchangeGateway,
    ) -> None:
        active: dict[str, asyncio.Task[None]] = {}
        refresh = self._settings.screener_book_stream_symbol_refresh_seconds
        limit = self._settings.opportunity_order_book_depth
        sem = asyncio.Semaphore(self._settings.screener_book_stream_max_concurrent)

        while not self._stop.is_set():
            desired = set(self._symbols_for_exchange(exchange_id))
            for symbol in set(active) - desired:
                task = active.pop(symbol)
                task.cancel()
            for symbol in desired - set(active):
                active[symbol] = asyncio.create_task(
                    self._watch_symbol(
                        gateway,
                        exchange_id,
                        symbol,
                        limit,
                        sem,
                    ),
                    name=f"screener-book:{exchange_id}:{symbol}",
                )
            await asyncio.sleep(refresh)

        for task in active.values():
            task.cancel()
        if active:
            await asyncio.gather(*active.values(), return_exceptions=True)

    async def _watch_symbol(
        self,
        gateway: ExchangeGateway,
        exchange_id: str,
        symbol: str,
        limit: int,
        sem: asyncio.Semaphore,
    ) -> None:
        delay = self._settings.ws_reconnect_delay_seconds
        # stagger initial connections to avoid REST seed flood (rate limit 510)
        await asyncio.sleep(0.5)
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
                    "screener book stream disconnected | exchange={} symbol={} retry_in={}s",
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
        recv_ms = book.timestamp_ms if book.timestamp_ms is not None else int(time.time() * 1000)
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
