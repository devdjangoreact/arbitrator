from __future__ import annotations

import asyncio
from collections.abc import Sequence

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from arbitrator.application.multi_exchange_watcher import MultiExchangeWatcher
from arbitrator.application.symbol_universe_service import SymbolUniverseService
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.named_exchange import NamedExchange
from arbitrator.exchanges.factory import Factory
from arbitrator.presentation.header.header_view import HeaderView
from arbitrator.presentation.sidebar.screener.price_table_view import PriceTableView
from arbitrator.presentation.sidebar.screener.screener_filters import (
    ScreenerFilters,
    ScreenerFiltersView,
)


class ScreenerView:
    """Composes the live screener: discovers symbols, applies filters, streams tickers."""

    def __init__(
        self,
        settings: Settings,
        factory: Factory,
        universe_service: SymbolUniverseService,
        header: HeaderView,
    ) -> None:
        self._settings = settings
        self._factory = factory
        self._universe_service = universe_service
        self._header = header
        self._filters_view = ScreenerFiltersView(
            default_volume_kusdt=settings.default_min_quote_volume_kusdt,
            default_spread_pct=settings.default_min_spread_pct,
        )

    def render(self, body: DeltaGenerator) -> None:
        with body:
            filters = self._filters_view.render()
            info_slot = st.empty()
            table = st.empty()
            counter = st.empty()

        self._header.set_status("Connecting…")
        try:
            asyncio.run(self._run(info_slot, table, counter, filters))
        except Exception:
            logger.exception("screener stream failed")
            self._header.set_status("Error")

    async def _run(
        self,
        info_slot: DeltaGenerator,
        table: DeltaGenerator,
        counter: DeltaGenerator,
        filters: ScreenerFilters,
    ) -> None:
        named_exchanges = self._factory.create_many(self._settings.enabled_exchanges)
        try:
            symbols, symbols_by_exchange, _snapshot = await self._universe_service.resolve(
                named_exchanges
            )
        except Exception:
            logger.exception("Failed to resolve universe")
            self._header.set_status("Error")
            await self._close(named_exchanges)
            return

        if not symbols:
            info_slot.warning(
                "No symbols available on at least "
                f"{self._settings.min_exchanges_per_symbol} exchanges. "
                "Check enabled exchanges and exclusions."
            )
            self._header.set_status("Idle")
            await self._close(named_exchanges)
            return

        info_slot.caption(
            f"Symbols: {len(symbols)}  •  Exchanges: " + ", ".join(self._settings.enabled_exchanges)
        )

        view = PriceTableView(exchanges=named_exchanges)
        watcher = MultiExchangeWatcher(named_exchanges)
        updates = 0
        try:
            async for snapshot in watcher.updates(symbols_by_exchange):
                updates += 1
                if updates == 1:
                    self._header.set_status("Live")
                    logger.info("First snapshot received, stream is live")
                view.render(table, snapshot, symbols, filters)
                counter.caption(f"Updates received: {updates}")
        finally:
            logger.info("Closing watcher after {} updates", updates)
            await watcher.close()

    @staticmethod
    async def _close(exchanges: Sequence[NamedExchange]) -> None:
        for exch in exchanges:
            try:
                await exch.gateway.close()
            except Exception:
                logger.exception("Failed to close gateway | exchange={}", exch.exchange_id)
