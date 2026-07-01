from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from arbitrator.application.account_stream_worker import AccountStreamWorker
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.closed_position_leg import ClosedPositionLeg
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.exchanges.factory import Factory


class PositionFetchService:
    """Fetches open and closed positions from enabled exchanges with credentials."""

    def __init__(
        self,
        settings: Settings,
        factory: Factory,
        account_worker: AccountStreamWorker | None = None,
    ) -> None:
        self._settings = settings
        self._factory = factory
        self._account_worker = account_worker

    def bind_account_worker(self, worker: AccountStreamWorker) -> None:
        self._account_worker = worker

    async def fetch_open(self, exchange_ids: list[str]) -> list[PositionLeg]:
        if self._account_worker is not None:
            self._account_worker.ensure_running(exchange_ids)
            return self._account_worker.read_positions(exchange_ids)
        eligible = [
            exchange_id
            for exchange_id in exchange_ids
            if self._settings.credentials_for(exchange_id) is not None
        ]
        if not eligible:
            return []
        results = await asyncio.gather(
            *(self._safe_open(exchange_id) for exchange_id in eligible)
        )
        legs: list[PositionLeg] = []
        for batch in results:
            legs.extend(batch)
        return legs

    async def fetch_closed(
        self,
        exchange_ids: list[str],
        history_days: int | None = None,
    ) -> list[ClosedPositionLeg]:
        days = history_days or self._settings.arb_closed_history_days
        since_ms = int(
            (
                datetime.now(UTC)
                - timedelta(days=days)
            ).timestamp()
            * 1000,
        )
        eligible = [
            exchange_id
            for exchange_id in exchange_ids
            if self._settings.credentials_for(exchange_id) is not None
        ]
        if not eligible:
            return []
        results = await asyncio.gather(
            *(self._safe_closed(exchange_id, since_ms, []) for exchange_id in eligible)
        )
        legs: list[ClosedPositionLeg] = []
        for batch in results:
            legs.extend(batch)
        return legs

    def fetch_open_sync(self, exchange_ids: list[str]) -> list[PositionLeg]:
        return asyncio.run(self.fetch_open(exchange_ids))

    def fetch_closed_sync(
        self,
        exchange_ids: list[str],
        history_days: int | None = None,
    ) -> list[ClosedPositionLeg]:
        return asyncio.run(self.fetch_closed(exchange_ids, history_days))

    async def fetch_closed_for_symbols(
        self,
        exchange_ids: list[str],
        symbols: list[str],
        history_days: int | None = None,
    ) -> list[ClosedPositionLeg]:
        if not symbols:
            return []
        days = history_days or self._settings.arb_closed_history_days
        since_ms = int(
            (
                datetime.now(UTC)
                - timedelta(days=days)
            ).timestamp()
            * 1000,
        )
        eligible = [
            exchange_id
            for exchange_id in exchange_ids
            if self._settings.credentials_for(exchange_id) is not None
        ]
        if not eligible:
            return []
        results = await asyncio.gather(
            *(self._safe_closed(exchange_id, since_ms, symbols) for exchange_id in eligible)
        )
        legs: list[ClosedPositionLeg] = []
        for batch in results:
            legs.extend(batch)
        return legs

    def fetch_closed_for_symbols_sync(
        self,
        exchange_ids: list[str],
        symbols: list[str],
        history_days: int | None = None,
    ) -> list[ClosedPositionLeg]:
        return asyncio.run(self.fetch_closed_for_symbols(exchange_ids, symbols, history_days))

    async def _safe_open(self, exchange_id: str) -> list[PositionLeg]:
        named = self._factory.create(exchange_id)
        try:
            return await named.gateway.fetch_open_positions()
        except Exception:
            logger.exception("fetch_open failed | exchange={}", exchange_id)
            return []
        finally:
            await named.gateway.close()

    async def _safe_closed(
        self,
        exchange_id: str,
        since_ms: int,
        symbols: Sequence[str],
    ) -> list[ClosedPositionLeg]:
        named = self._factory.create(exchange_id)
        try:
            return await named.gateway.fetch_closed_positions(since_ms, symbols)
        except Exception:
            logger.exception("fetch_closed failed | exchange={}", exchange_id)
            return []
        finally:
            await named.gateway.close()
