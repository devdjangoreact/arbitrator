from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UniverseSnapshot(BaseModel):
    """Per-exchange list of available symbols with the time it was discovered."""

    model_config = ConfigDict(frozen=True)

    updated_at: datetime
    exchanges: dict[str, list[str]]

    def all_symbols(self) -> set[str]:
        result: set[str] = set()
        for symbols in self.exchanges.values():
            result.update(symbols)
        return result

    def symbols_with_min_exchanges(self, min_exchanges: int) -> list[str]:
        counts: dict[str, int] = {}
        for symbols in self.exchanges.values():
            for symbol in set(symbols):
                counts[symbol] = counts.get(symbol, 0) + 1
        return sorted(s for s, n in counts.items() if n >= min_exchanges)
