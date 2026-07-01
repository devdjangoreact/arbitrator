from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.exchange_gateway import ExchangeGateway
from arbitrator.domain.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.ticker import Ticker
from arbitrator.domain.trade_tick import TradeTick
from arbitrator.domain.symbol_normalizer import SymbolNormalizer
from arbitrator.exchanges.factory import Factory


def _book_key(exchange_id: str, market_type: str) -> str:
    return f"{exchange_id}:{market_type}"


@dataclass(frozen=True, slots=True)
class OpportunityStreamState:
    books: dict[str, OrderBookSnapshot]
    tickers: dict[str, Ticker]
    prices: dict[str, float]
    trades: tuple[TradeTick, ...]
    price_ring: tuple[tuple[int, str, float], ...]
    status: str


class OpportunityStreamWorker:
    """One ccxt WebSocket per exchange: order book + ticker for one symbol."""

    def __init__(
        self,
        settings: Settings,
        factory: Factory,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
    ) -> None:
        self._settings = settings
        self._factory = factory
        self.symbol = symbol
        self.short_exchange_id = short_exchange_id
        self.long_exchange_id = long_exchange_id
        self._spot_symbol = SymbolNormalizer.to_display_symbol(symbol)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._books: dict[str, OrderBookSnapshot] = {}
        self._tickers: dict[str, Ticker] = {}
        self._prices: dict[str, float] = {}
        self._trades: list[TradeTick] = []
        self._price_ring: list[tuple[int, str, float]] = []
        self._status = "Connecting…"
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._thread_main,
            name=f"opportunity-stream:{self.symbol}",
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
        its gateways in the background and exits on its own.
        """
        self._stop.set()
        loop = self._loop
        task = self._main_task
        if loop is not None and task is not None and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)

    def read_state(self) -> OpportunityStreamState:
        with self._lock:
            return OpportunityStreamState(
                books=dict(self._books),
                tickers=dict(self._tickers),
                prices=dict(self._prices),
                trades=tuple(self._trades[-200:]),
                price_ring=tuple(self._price_ring),
                status=self._status,
            )

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_main())
        except asyncio.CancelledError:
            logger.info("Opportunity stream worker stopped | symbol={}", self.symbol)
        except Exception:
            logger.exception("Opportunity stream worker failed | symbol={}", self.symbol)
            self._set_status("Error")

    async def _async_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._main_task = asyncio.current_task()
        unique_exchange_ids = list(
            dict.fromkeys((self.short_exchange_id, self.long_exchange_id))
        )
        gateways = {
            exchange_id: self._factory.create(exchange_id).gateway
            for exchange_id in unique_exchange_ids
        }
        limit = self._settings.opportunity_order_book_depth
        tasks: list[asyncio.Task[None]] = []
        for exchange_id in unique_exchange_ids:
            gateway = gateways[exchange_id]
            tasks.extend(
                [
                    asyncio.create_task(
                        self._consume_book(
                            gateway,
                            exchange_id,
                            self.symbol,
                            "futures",
                            limit,
                        ),
                        name=f"opp-book-fut:{exchange_id}",
                    ),
                    asyncio.create_task(
                        self._consume_book(
                            gateway,
                            exchange_id,
                            self._spot_symbol,
                            "spot",
                            limit,
                        ),
                        name=f"opp-book-spot:{exchange_id}",
                    ),
                    asyncio.create_task(
                        self._consume_ticker(gateway, exchange_id),
                        name=f"opp-ticker:{exchange_id}",
                    ),
                ]
            )
        self._set_status("Live")
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            for gateway in gateways.values():
                await gateway.close()
            logger.info("Opportunity streams closed | symbol={}", self.symbol)

    async def _consume_book(
        self,
        gateway: ExchangeGateway,
        exchange_id: str,
        symbol: str,
        market_type: str,
        limit: int,
    ) -> None:
        async for book in gateway.watch_order_book(symbol, limit):
            if self._stop.is_set():
                break
            key = _book_key(exchange_id, market_type)
            with self._lock:
                self._books[key] = book
                if market_type == "futures":
                    mid = self._mid_from_book(book)
                    if mid is not None:
                        self._prices[exchange_id] = mid
                        self._append_price(exchange_id, mid, book.timestamp_ms)

    async def _consume_ticker(self, gateway: ExchangeGateway, exchange_id: str) -> None:
        async for tickers in gateway.watch_tickers([self.symbol]):
            if self._stop.is_set():
                break
            ticker = tickers.get(self.symbol)
            if ticker is None:
                continue
            with self._lock:
                self._tickers[exchange_id] = ticker

    def _append_price(self, exchange_id: str, price: float, timestamp_ms: int | None) -> None:
        ts = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
        self._price_ring.append((ts, exchange_id, price))
        cutoff_ms = int(time.time() * 1000) - self._settings.opportunity_chart_window_seconds * 1000
        while self._price_ring and self._price_ring[0][0] < cutoff_ms:
            self._price_ring.pop(0)

    @staticmethod
    def _mid_from_book(book: OrderBookSnapshot) -> float | None:
        if not book.bids or not book.asks:
            return None
        return (book.bids[0].price + book.asks[0].price) / 2.0

    def _set_status(self, status: str) -> None:
        with self._lock:
            self._status = status
