from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

from pydantic import ValidationError

from arbitrator.config.logger import logger
from arbitrator.domain.universe.symbol_universe_repository import SymbolUniverseRepository
from arbitrator.domain.universe.universe_snapshot import UniverseSnapshot


class JsonSymbolUniverseRepository(SymbolUniverseRepository):
    """Caches per-exchange symbol universe in a JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = Lock()

    def load(self) -> UniverseSnapshot | None:
        with self._lock:
            if not self._path.exists():
                return None
            try:
                raw = self._path.read_text(encoding="utf-8")
                if not raw.strip():
                    return None
                return UniverseSnapshot.model_validate_json(raw)
            except ValidationError:
                logger.exception("Universe cache schema mismatch | path={}", self._path)
                return None
            except Exception:
                logger.exception("Failed to read universe cache | path={}", self._path)
                return None

    def save(self, snapshot: UniverseSnapshot) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            try:
                tmp.write_text(
                    snapshot.model_dump_json(indent=2),
                    encoding="utf-8",
                )
                os.replace(tmp, self._path)
                logger.info(
                    "Universe cache saved | path={} exchanges={} total={}",
                    self._path,
                    list(snapshot.exchanges.keys()),
                    sum(len(v) for v in snapshot.exchanges.values()),
                )
            except Exception:
                logger.exception("Failed to write universe cache | path={}", self._path)
                raise
