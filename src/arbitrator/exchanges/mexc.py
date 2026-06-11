from __future__ import annotations

from typing import ClassVar

import aiohttp
import ccxt.pro as ccxtpro

from arbitrator.exchanges.ccxt_base import CcxtBase


class Mexc(CcxtBase):
    exchange_id: ClassVar[str] = "mexc"
    display_name: ClassVar[str] = "MEXC"

    def _create_client(self, session: aiohttp.ClientSession) -> ccxtpro.Exchange:
        return ccxtpro.mexc(
            {
                "session": session,
                "enableRateLimit": self._settings.enable_rate_limit,
                "options": {"defaultType": self._settings.default_type},
            }
        )
