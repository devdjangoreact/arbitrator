from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence

from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.logger import logger
from arbitrator.domain.exchange.named_exchange import NamedExchange


class FeeSnapshotService:
    """Populates the cache with per-symbol maker/taker fee schedules.

    Fees come from ccxt ``markets`` (loaded once per exchange), so the cost is a
    cheap in-memory read per symbol after the first ``load_markets``. Strategies
    are ``N/A`` until fees are present (FR: fee-completeness gate).
    """

    def __init__(self, cache: MarketDataCacheMemory) -> None:
        self._cache = cache

    async def snapshot(
        self,
        named_exchanges: Sequence[NamedExchange],
        symbols_by_exchange: Mapping[str, Sequence[str]],
    ) -> int:
        async def _fetch(exchange: NamedExchange, symbol: str) -> int:
            try:
                fees = await exchange.gateway.fetch_fee_schedule(symbol)
            except Exception:
                logger.exception(
                    "fetch_fee_schedule failed | exchange={} symbol={}",
                    exchange.exchange_id,
                    symbol,
                )
                return 0
            if fees is not None:
                self._cache.put_fees(fees)
                return 1
            return 0

        tasks = [
            _fetch(exchange, symbol)
            for exchange in named_exchanges
            for symbol in symbols_by_exchange.get(exchange.exchange_id, ())
        ]
        results = await asyncio.gather(*tasks)
        loaded = sum(results)
        pair_count = sum(
            len(symbols_by_exchange.get(ex.exchange_id, ())) for ex in named_exchanges
        )
        logger.info(
            "fee snapshot complete | exchanges={} pairs={} loaded={}",
            len(named_exchanges),
            pair_count,
            loaded,
        )
        return loaded
