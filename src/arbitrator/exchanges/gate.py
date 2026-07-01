from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import ClassVar

import aiohttp
import ccxt.pro as ccxtpro

from arbitrator.config.logger import logger
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.domain.ticker import Ticker
from arbitrator.exchanges.ccxt_base import CcxtBase


class Gate(CcxtBase):
    exchange_id: ClassVar[str] = "gate"
    display_name: ClassVar[str] = "Gate"

    def _create_client(self, session: aiohttp.ClientSession) -> ccxtpro.Exchange:
        return ccxtpro.gate(self._base_client_config(session))

    async def list_symbols(self) -> list[str]:
        symbols = await super().list_symbols()
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        filtered = [
            symbol
            for symbol in symbols
            if Gate._is_tradable(client.markets.get(symbol))
        ]
        removed = len(symbols) - len(filtered)
        if removed > 0:
            logger.info(
                "list_symbols filtered non-tradable contracts | exchange=gate removed={} remaining={}",
                removed,
                len(filtered),
            )
        return filtered

    async def watch_tickers(
        self,
        symbols: Sequence[str],
    ) -> AsyncIterator[dict[str, Ticker]]:
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        allowed = [
            symbol
            for symbol in symbols
            if Gate._is_tradable(client.markets.get(symbol))
        ]
        skipped = len(symbols) - len(allowed)
        if skipped > 0:
            logger.debug(
                "watch_tickers skipped non-tradable contracts | exchange=gate skipped={}",
                skipped,
            )
        async for update in super().watch_tickers(allowed):
            yield update

    async def watch_open_positions(self) -> AsyncIterator[list[PositionLeg]]:
        """Gate WS private channels require uid; use REST polling to avoid errors."""
        creds = self._settings.credentials_for(self.exchange_id)
        if creds is None:
            return
        client = await self._ensure_open()
        if not client.has.get("fetchPositions"):
            logger.info("fetchPositions unsupported | exchange=gate")
            return
        await self._ensure_markets_loaded(client)
        logger.info("Position stream started | exchange=gate mode=rest_poll")
        while True:
            try:
                raw = await client.fetch_positions()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("position stream error | exchange=gate")
                await asyncio.sleep(self._settings.ws_reconnect_delay_seconds)
                continue
            yield await self._map_raw_positions(client, raw)
            await asyncio.sleep(float(self._settings.arb_positions_poll_seconds))

    async def watch_usdt_balance(self) -> AsyncIterator[float | None]:
        """Gate WS private channels require uid; use REST polling to avoid errors."""
        creds = self._settings.credentials_for(self.exchange_id)
        if creds is None:
            return
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        logger.info("Balance stream started | exchange=gate mode=rest_poll")
        while True:
            try:
                payload = await client.fetch_balance()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("balance stream error | exchange=gate")
                await asyncio.sleep(self._settings.ws_reconnect_delay_seconds)
                continue
            yield self._extract_usdt_balance(payload)
            await asyncio.sleep(float(self._settings.arb_positions_poll_seconds))

    async def _first_usdt_balance(self, client: ccxtpro.Exchange) -> float | None:
        """Gate private WS requires uid; probe via REST only."""
        payload = await client.fetch_balance()
        return self._extract_usdt_balance(payload)

    @staticmethod
    def _is_tradable(market: object) -> bool:
        if not CcxtBase._is_arbitrage_symbol(market):
            return False
        if not isinstance(market, dict):
            return False
        info = market.get("info")
        if not isinstance(info, dict):
            return True
        if info.get("is_pre_market") is True:
            return False
        if info.get("in_delisting") is True:
            return False
        status = info.get("status")
        return not (isinstance(status, str) and status != "trading")
