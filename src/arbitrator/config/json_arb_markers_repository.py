from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

from pydantic import TypeAdapter

from arbitrator.config.logger import logger
from arbitrator.domain.arb_marker_record import ArbMarkerRecord
from arbitrator.domain.arb_markers_repository import ArbMarkersRepository

_MARKER_ADAPTER: TypeAdapter[list[ArbMarkerRecord]] = TypeAdapter(list[ArbMarkerRecord])


class JsonArbMarkersRepository(ArbMarkersRepository):
    """Persists arbitrage pair markers as a JSON array."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = Lock()

    def load(self) -> list[ArbMarkerRecord]:
        with self._lock:
            return self._read()

    def save(self, records: list[ArbMarkerRecord]) -> None:
        with self._lock:
            self._write(records)

    def append(self, record: ArbMarkerRecord) -> None:
        with self._lock:
            current = self._read()
            if any(item.pair_id == record.pair_id for item in current):
                return
            current.append(record)
            self._write(current)
            logger.info(
                "Arb marker appended | pair_id={} symbol={}",
                record.pair_id,
                record.symbol,
            )

    def find_by_pair_id(self, pair_id: str) -> ArbMarkerRecord | None:
        for record in self.load():
            if record.pair_id == pair_id:
                return record
        return None

    def _read(self) -> list[ArbMarkerRecord]:
        if not self._path.exists():
            return []
        try:
            raw = self._path.read_text(encoding="utf-8")
            payload = json.loads(raw) if raw.strip() else []
        except Exception:
            logger.exception("Failed to read arb markers | path={}", self._path)
            return []
        if not isinstance(payload, list):
            return []
        try:
            return _MARKER_ADAPTER.validate_python(payload)
        except Exception:
            logger.exception("Invalid arb markers schema | path={}", self._path)
            return []

    def _write(self, records: list[ArbMarkerRecord]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            payload = _MARKER_ADAPTER.dump_python(records, mode="json")
            tmp.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(tmp, self._path)
        except Exception:
            logger.exception("Failed to write arb markers | path={}", self._path)
            raise
