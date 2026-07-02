from __future__ import annotations

from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.logger import logger
from arbitrator.domain.exchange_factory import ExchangeFactory
from arbitrator.domain.symbol_market_info import SymbolMarketInfo


class SymbolMarketInfoService:
    """Loads per-exchange swap market identity and order volume limits.

    Checks ``MarketDataCacheMemory`` first (populated by ``FundingRateWorker``
    on every refresh cycle). Falls back to a live REST fetch only when the cache
    is empty (e.g. first request before the first funding cycle completes).
    """

    def __init__(self, factory: ExchangeFactory, cache: MarketDataCacheMemory) -> None:
        self._factory = factory
        self._cache = cache

    async def fetch_for_exchange(
        self,
        exchange_id: str,
        symbol: str,
    ) -> SymbolMarketInfo | None:
        cached = self._cache.get_market_info(exchange_id, symbol)
        if cached is not None:
            return cached
        named = self._factory.create(exchange_id)
        try:
            info = await named.gateway.fetch_symbol_market_info(symbol)
        except Exception:
            logger.exception(
                "fetch_symbol_market_info failed | exchange={} symbol={}",
                exchange_id,
                symbol,
            )
            return None
        finally:
            await named.gateway.close()
        if info is not None:
            self._cache.put_market_info(info, exchange_id)
        return info
