from __future__ import annotations

from typing import ClassVar

import aiohttp
import ccxt.pro as ccxtpro

from arbitrator.exchanges.ccxt_base import CcxtBase


class Binance(CcxtBase):
    exchange_id: ClassVar[str] = "binance"
    display_name: ClassVar[str] = "Binance"

    def _create_client(self, session: aiohttp.ClientSession) -> ccxtpro.Exchange:
        return ccxtpro.binance(self._base_client_config(session))
