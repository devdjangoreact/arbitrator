from __future__ import annotations

from arbitrator.config.logger import logger
from arbitrator.domain.exchange_factory import ExchangeFactory
from arbitrator.domain.symbol_market_info import SymbolMarketInfo


class SymbolMarketInfoService:
    """Loads per-exchange swap market identity and order volume limits."""

    def __init__(self, factory: ExchangeFactory) -> None:
        self._factory = factory

    async def fetch_for_exchange(
        self,
        exchange_id: str,
        symbol: str,
    ) -> SymbolMarketInfo | None:
        named = self._factory.create(exchange_id)
        try:
            return await named.gateway.fetch_symbol_market_info(symbol)
        except Exception:
            logger.exception(
                "fetch_symbol_market_info failed | exchange={} symbol={}",
                exchange_id,
                symbol,
            )
            return None
        finally:
            await named.gateway.close()
