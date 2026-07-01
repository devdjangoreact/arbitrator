from __future__ import annotations

import asyncio
import time

from arbitrator.application.account_stream_worker import AccountStreamWorker
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.exchange_connection_status import ExchangeConnectionStatus
from arbitrator.domain.exchange_factory import ExchangeFactory


class ExchangeAccountService:
    """Checks API credentials and USDT balances for enabled exchanges."""

    def __init__(
        self,
        settings: Settings,
        factory: ExchangeFactory,
        account_worker: AccountStreamWorker | None = None,
    ) -> None:
        self._settings = settings
        self._factory = factory
        self._account_worker = account_worker

    def bind_account_worker(self, worker: AccountStreamWorker) -> None:
        self._account_worker = worker

    async def verify_exchange(self, exchange_id: str) -> ExchangeConnectionStatus:
        if self._account_worker is not None:
            self._account_worker.ensure_running([exchange_id])
            timeout = self._settings.ccxt_request_timeout_ms / 1000.0
            return self._account_worker.wait_for_status(
                exchange_id,
                timeout_seconds=timeout,
            )
        named = self._factory.create(exchange_id)
        try:
            return await named.gateway.verify_connection()
        except Exception:
            logger.exception("verify_exchange failed | exchange={}", exchange_id)
            return ExchangeConnectionStatus(
                exchange_id=exchange_id,
                display_name=named.display_name,
                credentials_configured=self._settings.credentials_for(exchange_id) is not None,
                authenticated=False,
                trading_enabled=False,
                usdt_balance=None,
                message="Connection check failed",
            )

    async def statuses_for_enabled(self) -> list[ExchangeConnectionStatus]:
        exchange_ids = self._settings.enabled_exchanges
        if self._account_worker is not None:
            self._account_worker.ensure_running(exchange_ids)
            timeout = self._settings.ccxt_request_timeout_ms / 1000.0
            configured = [
                exchange_id
                for exchange_id in exchange_ids
                if self._settings.credentials_for(exchange_id) is not None
            ]
            if not configured:
                return self._account_worker.read_statuses(exchange_ids)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                statuses = self._account_worker.read_statuses(exchange_ids)
                if all(
                    status.authenticated and status.message not in (None, "Connecting…")
                    for status in statuses
                    if status.credentials_configured
                ):
                    return statuses
                await asyncio.sleep(0.2)
            return self._account_worker.read_statuses(exchange_ids)
        logger.info("Fetching exchange statuses | count={}", len(exchange_ids))
        results = await asyncio.gather(
            *(self.verify_exchange(exchange_id) for exchange_id in exchange_ids)
        )
        return list(results)

    def verify_exchange_sync(self, exchange_id: str) -> ExchangeConnectionStatus:
        return asyncio.run(self.verify_exchange(exchange_id))

    def statuses_for_enabled_sync(self) -> list[ExchangeConnectionStatus]:
        return asyncio.run(self.statuses_for_enabled())

    def placeholder_statuses_for_enabled(self) -> list[ExchangeConnectionStatus]:
        """Local-only rows (credentials flag) without exchange API calls."""
        return [
            ExchangeConnectionStatus(
                exchange_id=exchange_id,
                display_name=self._factory.display_name(exchange_id),
                credentials_configured=self._settings.credentials_for(exchange_id) is not None,
                authenticated=False,
                trading_enabled=False,
                usdt_balance=None,
                message=None,
            )
            for exchange_id in self._settings.enabled_exchanges
        ]
