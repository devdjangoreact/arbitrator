from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence

from arbitrator.config.logger import logger
from arbitrator.domain.named_exchange import NamedExchange
from arbitrator.domain.ticker import Ticker


class MultiExchangeWatcher:
    """Streams ticker updates from every exchange over one bulk
    ``watch_tickers`` subscription per exchange and yields a snapshot of the
    latest tickers whenever any update arrives.

    Symbols are passed per exchange so an exchange never receives a symbol it
    does not list in the universe cache.

    The yielded snapshot is keyed by ``(exchange_id, symbol)``.
    """

    def __init__(self, exchanges: Sequence[NamedExchange]) -> None:
        self._exchanges = list(exchanges)
        self._state: dict[tuple[str, str], Ticker] = {}
        self._signal: asyncio.Queue[None] = asyncio.Queue()
        self._tasks: list[asyncio.Task[None]] = []
        self._closing = False

    async def updates(
        self, symbols_by_exchange: Mapping[str, Sequence[str]]
    ) -> AsyncIterator[dict[tuple[str, str], Ticker]]:
        self._spawn_watchers(symbols_by_exchange)
        try:
            while not self._closing:
                await self._signal.get()
                while not self._signal.empty():
                    self._signal.get_nowait()
                yield dict(self._state)
        except asyncio.CancelledError:
            raise
        finally:
            await self._shutdown_watchers()

    async def close(self) -> None:
        await self._shutdown_watchers()

    async def _shutdown_watchers(self) -> None:
        if self._closing and not self._tasks:
            return
        self._closing = True
        for exch in self._exchanges:
            try:
                await exch.gateway.close()
            except Exception:
                logger.exception("Failed to close gateway | exchange={}", exch.exchange_id)
        await self._cancel_watchers()

    def _spawn_watchers(self, symbols_by_exchange: Mapping[str, Sequence[str]]) -> None:
        logger.info(
            "Spawning watchers | exchanges={} symbols={}",
            [e.exchange_id for e in self._exchanges],
            {
                e.exchange_id: len(symbols_by_exchange.get(e.exchange_id, ()))
                for e in self._exchanges
            },
        )
        for exch in self._exchanges:
            symbol_list = list(symbols_by_exchange.get(exch.exchange_id, ()))
            if not symbol_list:
                logger.warning("Watcher skipped | exchange={} reason=no_symbols", exch.exchange_id)
                continue
            task = asyncio.create_task(
                self._watch(exch, symbol_list),
                name=f"watch_tickers:{exch.exchange_id}",
            )
            self._tasks.append(task)

    async def _watch(self, exch: NamedExchange, symbols: Sequence[str]) -> None:
        logger.debug(
            "Watcher start | exchange={} symbols={}",
            exch.exchange_id,
            len(symbols),
        )
        while not self._closing:
            try:
                async for tickers in exch.gateway.watch_tickers(symbols):
                    if self._closing:
                        return
                    if not tickers:
                        continue
                    for symbol, ticker in tickers.items():
                        self._state[(exch.exchange_id, symbol)] = ticker
                    self._signal.put_nowait(None)
            except asyncio.CancelledError:
                logger.debug("Watcher cancelled | exchange={}", exch.exchange_id)
                return
            except Exception:
                if self._closing:
                    return
                logger.exception("Watcher failed, reconnecting | exchange={}", exch.exchange_id)
                try:
                    await exch.gateway.close()
                except Exception:
                    logger.exception(
                        "Failed to close gateway before reconnect | exchange={}",
                        exch.exchange_id,
                    )

    async def _cancel_watchers(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
