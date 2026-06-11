from __future__ import annotations

from abc import ABC, abstractmethod


class SymbolExclusionsRepository(ABC):
    """Persistent set of symbols that must be excluded from the screener."""

    @abstractmethod
    def load(self) -> set[str]:
        raise NotImplementedError

    @abstractmethod
    def add(self, symbol: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def remove(self, symbol: str) -> None:
        raise NotImplementedError
