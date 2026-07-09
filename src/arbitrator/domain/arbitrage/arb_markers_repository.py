from __future__ import annotations

from abc import ABC, abstractmethod

from arbitrator.domain.arbitrage.arb_marker_record import ArbMarkerRecord


class ArbMarkersRepository(ABC):
    @abstractmethod
    def load(self) -> list[ArbMarkerRecord]:
        raise NotImplementedError

    @abstractmethod
    def save(self, records: list[ArbMarkerRecord]) -> None:
        raise NotImplementedError

    @abstractmethod
    def append(self, record: ArbMarkerRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def find_by_pair_id(self, pair_id: str) -> ArbMarkerRecord | None:
        raise NotImplementedError
