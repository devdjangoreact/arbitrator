from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from arbitrator.config.logger import logger
from arbitrator.domain.named_exchange import NamedExchange
from arbitrator.domain.symbol_exclusions_repository import SymbolExclusionsRepository
from arbitrator.domain.symbol_universe_repository import SymbolUniverseRepository
from arbitrator.domain.universe_snapshot import UniverseSnapshot


class SymbolUniverseService:
    """Resolves the list of symbols to watch.

    - Loads cached per-exchange symbols from a repository.
    - Refreshes the cache when older than `ttl_hours` (default once per day).
    - Returns symbols available on at least `min_exchanges` enabled exchanges,
      with excluded symbols removed.
    """

    def __init__(
        self,
        repository: SymbolUniverseRepository,
        exclusions: SymbolExclusionsRepository,
        ttl_hours: int,
        min_exchanges: int,
    ) -> None:
        self._repo = repository
        self._exclusions = exclusions
        self._ttl = timedelta(hours=ttl_hours)
        self._min_exchanges = max(1, min_exchanges)

    async def resolve(
        self,
        exchanges: Sequence[NamedExchange],
        force_refresh: bool = False,
    ) -> tuple[list[str], dict[str, list[str]], UniverseSnapshot]:
        cached = self._repo.load()
        snapshot: UniverseSnapshot
        if force_refresh or self._is_stale(cached, exchanges):
            snapshot = await self._refresh(exchanges)
        else:
            assert cached is not None
            snapshot = cached
        symbols = self._filter(snapshot)
        return symbols, self._symbols_by_exchange(snapshot, symbols), snapshot

    def _is_stale(
        self,
        snapshot: UniverseSnapshot | None,
        exchanges: Sequence[NamedExchange],
    ) -> bool:
        if snapshot is None:
            return True
        wanted = {e.exchange_id for e in exchanges}
        cached = set(snapshot.exchanges.keys())
        if not wanted.issubset(cached):
            logger.info(
                "Universe stale | reason=missing_exchanges wanted={} cached={}",
                sorted(wanted),
                sorted(cached),
            )
            return True
        age = datetime.now(UTC) - snapshot.updated_at
        if age > self._ttl:
            logger.info(
                "Universe stale | reason=ttl age_hours={:.1f} ttl_hours={:.1f}",
                age.total_seconds() / 3600.0,
                self._ttl.total_seconds() / 3600.0,
            )
            return True
        return False

    async def _refresh(
        self,
        exchanges: Sequence[NamedExchange],
    ) -> UniverseSnapshot:
        logger.info(
            "Refreshing universe | exchanges={}",
            [e.exchange_id for e in exchanges],
        )
        results = await asyncio.gather(
            *(self._safe_list(e) for e in exchanges),
            return_exceptions=False,
        )
        per_exchange = {
            exchange.exchange_id: symbols
            for exchange, symbols in zip(exchanges, results, strict=True)
        }
        snapshot = UniverseSnapshot(
            updated_at=datetime.now(UTC),
            exchanges=per_exchange,
        )
        self._repo.save(snapshot)
        return snapshot

    @staticmethod
    async def _safe_list(exchange: NamedExchange) -> list[str]:
        try:
            return await exchange.gateway.list_symbols()
        except Exception:
            logger.exception("list_symbols failed | exchange={}", exchange.exchange_id)
            return []

    def _filter(self, snapshot: UniverseSnapshot) -> list[str]:
        excluded = self._exclusions.load()
        candidates = snapshot.symbols_with_min_exchanges(self._min_exchanges)
        result = [s for s in candidates if s not in excluded]
        logger.info(
            "Universe filtered | total={} after_min_exchanges={} after_exclusions={}",
            len(snapshot.all_symbols()),
            len(candidates),
            len(result),
        )
        return result

    @staticmethod
    def _symbols_by_exchange(
        snapshot: UniverseSnapshot,
        symbols: Sequence[str],
    ) -> dict[str, list[str]]:
        allowed = set(symbols)
        return {
            exchange_id: sorted(s for s in set(exchange_symbols) if s in allowed)
            for exchange_id, exchange_symbols in snapshot.exchanges.items()
        }
