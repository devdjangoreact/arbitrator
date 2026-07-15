from __future__ import annotations

from collections.abc import Sequence

from arbitrator.application.market_data.fee_snapshot_service import FeeSnapshotService
from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.opportunities.opportunity_session_state import OpportunitySessionState
from arbitrator.config.logger import logger
from arbitrator.domain.exchange.named_exchange import NamedExchange
from arbitrator.domain.universe.symbol_market_info import SymbolMarketInfo
from arbitrator.domain.universe.symbol_normalizer import SymbolNormalizer
from arbitrator.exchanges.factory import Factory


class OpportunityBootstrapService:
    """One-shot REST bootstrap for a focused opportunity pair (fees, funding, limits)."""

    def __init__(self, factory: Factory) -> None:
        self._factory = factory

    async def bootstrap(
        self,
        *,
        swap_symbol: str,
        display_symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        session: OpportunitySessionState,
        cache: MarketDataCacheMemory,
        fee_service: FeeSnapshotService,
    ) -> None:
        exchange_ids = list(dict.fromkeys((short_exchange_id, long_exchange_id)))
        named_exchanges = self._factory.create_many(exchange_ids)
        try:
            await fee_service.snapshot(
                named_exchanges,
                {ex.exchange_id: [swap_symbol] for ex in named_exchanges},
            )
            for exchange in named_exchanges:
                await self._refresh_funding(exchange, swap_symbol, cache)
                futures_info = await self._fetch_market_info(exchange, swap_symbol, cache)
                spot_info = await self._fetch_market_info(exchange, display_symbol, cache)
                session.set_market_info(
                    exchange.exchange_id,
                    futures=futures_info,
                    spot=spot_info,
                )
        finally:
            await self._close_exchanges(named_exchanges)

    async def _refresh_funding(
        self,
        exchange: NamedExchange,
        swap_symbol: str,
        cache: MarketDataCacheMemory,
    ) -> None:
        try:
            infos = await exchange.gateway.fetch_funding_infos([swap_symbol])
        except Exception:
            logger.exception(
                "opportunity funding bootstrap failed | exchange={} symbol={}",
                exchange.exchange_id,
                swap_symbol,
            )
            return
        for info in infos:
            cache.put_funding(info)

    async def _fetch_market_info(
        self,
        exchange: NamedExchange,
        symbol: str,
        cache: MarketDataCacheMemory,
    ) -> SymbolMarketInfo | None:
        cached = cache.get_market_info(exchange.exchange_id, symbol)
        if cached is not None:
            return cached
        try:
            info = await exchange.gateway.fetch_symbol_market_info(symbol)
        except Exception:
            logger.exception(
                "opportunity market info failed | exchange={} symbol={}",
                exchange.exchange_id,
                symbol,
            )
            return None
        if info is not None:
            cache.put_market_info(info, exchange.exchange_id)
        return info

    @staticmethod
    async def _close_exchanges(named_exchanges: Sequence[NamedExchange]) -> None:
        for exchange in named_exchanges:
            try:
                await exchange.gateway.close()
            except Exception:
                logger.exception(
                    "Failed to close bootstrap gateway | exchange={}",
                    exchange.exchange_id,
                )

    @staticmethod
    def display_symbol_for(swap_symbol: str) -> str:
        return SymbolNormalizer.to_display_symbol(swap_symbol)
