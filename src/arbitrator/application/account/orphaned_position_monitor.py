from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import TYPE_CHECKING

from arbitrator.config.logger import logger
from arbitrator.config.telegram_notifier import TelegramNotifier

if TYPE_CHECKING:
    from arbitrator.domain.exchange.exchange_gateway import ExchangeGateway

class OrphanedPositionMonitor:
    """Monitors for single-leg futures positions that lack a corresponding hedge."""

    def __init__(
        self,
        gateways: Mapping[str, ExchangeGateway],
        notifier: TelegramNotifier | None = None,
        check_interval_seconds: float = 600.0,
    ) -> None:
        self._gateways = gateways
        self._notifier = notifier
        self._interval = check_interval_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop(), name="orphaned-position-monitor")

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()

    async def _run_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval)
                await self._check_orphans()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Orphaned position monitor encountered an error")

    async def _check_orphans(self) -> None:
        positions_by_symbol = {}

        for ex_id, gateway in self._gateways.items():
            try:
                legs = await gateway.fetch_open_positions()
                for leg in legs:
                    positions_by_symbol.setdefault(leg.symbol, []).append((ex_id, leg))
            except Exception:
                logger.warning("Orphan monitor could not fetch positions for {}", ex_id)

        for symbol, entries in positions_by_symbol.items():
            # Simplistic check: If there's only one leg for a symbol across all exchanges, it's orphaned.
            # A more robust check might consider spot positions or different strategies,
            # but for pure futures-futures, 1 leg = orphan.
            if len(entries) == 1:
                ex_id, leg = entries[0]
                logger.error(
                    "ORPHANED POSITION DETECTED | sym={} ex={} side={} contracts={}",
                    symbol, ex_id, leg.side, leg.contracts
                )
                if self._notifier:
                    self._notifier.notify(
                        f"⚠️ <b>ORPHANED POSITION</b>\n"
                        f"Symbol: <code>{symbol}</code>\n"
                        f"Exchange: {ex_id}\n"
                        f"Side: {leg.side}\n"
                        f"Contracts: {leg.contracts}\n"
                        f"Action required: Close manually or hedge."
                    )
