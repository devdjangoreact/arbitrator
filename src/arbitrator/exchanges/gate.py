from __future__ import annotations

from typing import ClassVar

import aiohttp
import ccxt.pro as ccxtpro

from arbitrator.exchanges.ccxt_base import CcxtBase


class Gate(CcxtBase):
    exchange_id: ClassVar[str] = "gate"
    display_name: ClassVar[str] = "Gate"

    def _create_client(self, session: aiohttp.ClientSession) -> ccxtpro.Exchange:
        return ccxtpro.gate(
            {
                "session": session,
                "enableRateLimit": self._settings.enable_rate_limit,
                "options": {"defaultType": self._settings.default_type},
            }
        )
