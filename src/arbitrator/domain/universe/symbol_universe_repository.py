from __future__ import annotations

from abc import ABC, abstractmethod

from arbitrator.domain.universe.universe_snapshot import UniverseSnapshot


class SymbolUniverseRepository(ABC):
    """Persistent cache of symbols available per exchange."""

    @abstractmethod
    def load(self) -> UniverseSnapshot | None:
        raise NotImplementedError

    @abstractmethod
    def save(self, snapshot: UniverseSnapshot) -> None:
        raise NotImplementedError
