from __future__ import annotations

from dataclasses import dataclass

from arbitrator.domain.symbol_market_info import SymbolMarketInfo


@dataclass(frozen=True, slots=True)
class ExchangeMarketInfoPair:
    """Futures and optional spot market metadata for one exchange leg."""

    futures: SymbolMarketInfo | None
    spot: SymbolMarketInfo | None
