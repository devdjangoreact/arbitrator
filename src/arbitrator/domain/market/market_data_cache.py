from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.funding_info import FundingInfo
from arbitrator.domain.strategy.quote import Quote


@runtime_checkable
class MarketDataCache(Protocol):
    """Read abstraction over the in-process L1 cache of latest exchange snapshots.

    Implementations are concrete adapters (memory now, possibly Redis later).
    Lookups are by ``(exchange_id, symbol)`` and, for quotes, ``market_type``.
    Returns ``None`` when nothing fresh is cached (callers degrade to ``N/A``).
    """

    def get_quote(
        self,
        exchange_id: str,
        symbol: str,
        market_type: Literal["futures", "spot"],
    ) -> Quote | None: ...

    def get_funding(self, exchange_id: str, symbol: str) -> FundingInfo | None: ...

    def get_fees(self, exchange_id: str, symbol: str) -> FeeSchedule | None: ...
