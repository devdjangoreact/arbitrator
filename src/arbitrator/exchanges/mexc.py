from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import ClassVar

import aiohttp
import ccxt.pro as ccxtpro

from arbitrator.config.logger import logger
from arbitrator.domain.ticker import Ticker
from arbitrator.exchanges.ccxt_base import CcxtBase


class Mexc(CcxtBase):
    exchange_id: ClassVar[str] = "mexc"
    display_name: ClassVar[str] = "MEXC"

    def _create_client(self, session: aiohttp.ClientSession) -> ccxtpro.Exchange:
        return ccxtpro.mexc(self._base_client_config(session))

    async def list_symbols(self) -> list[str]:
        symbols = await super().list_symbols()
        client = await self._ensure_open()
        await self._ensure_markets_loaded(client)
        filtered = [
            symbol
            for symbol in symbols
            if Mexc._is_api_tradable(client.markets.get(symbol))
        ]
        removed = len(symbols) - len(filtered)
        if removed > 0:
            logger.info(
                "list_symbols filtered non-api contracts | exchange=mexc removed={} remaining={}",
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
            if Mexc._is_api_tradable(client.markets.get(symbol))
        ]
        skipped = len(symbols) - len(allowed)
        if skipped > 0:
            logger.debug(
                "watch_tickers skipped non-api contracts | exchange=mexc skipped={}",
                skipped,
            )
        async for update in super().watch_tickers(allowed):
            yield update

    @staticmethod
    def _is_api_tradable(market: object) -> bool:
        if not CcxtBase._is_arbitrage_symbol(market):
            return False
        if not isinstance(market, dict):
            return False
        info = market.get("info")
        if not isinstance(info, dict):
            return True
        if info.get("apiAllowed") is False:
            return False
        if info.get("preMarket") is True:
            return False
        if str(info.get("automaticDelivery", "0")) == "1":
            return False
        if info.get("isHidden") is True:
            return False
        if str(info.get("state", "0")) != "0":
            return False
        if str(info.get("type", "1")) == "2":
            return False
        concept_plate = info.get("conceptPlate")
        if isinstance(concept_plate, list):
            for plate in concept_plate:
                if isinstance(plate, str) and "innovation" in plate:
                    return False
        return True
