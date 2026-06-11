from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock

from arbitrator.config.logger import logger
from arbitrator.domain.symbol_exclusions_repository import SymbolExclusionsRepository


class JsonSymbolExclusionsRepository(SymbolExclusionsRepository):
    """Stores excluded symbols as a JSON file: {"symbols": [...]}."""

    _SCHEMA_KEY = "symbols"

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = Lock()

    def load(self) -> set[str]:
        with self._lock:
            return self._read()

    def add(self, symbol: str) -> None:
        symbol = symbol.strip()
        if not symbol:
            return
        with self._lock:
            current = self._read()
            if symbol in current:
                return
            current.add(symbol)
            self._write(current)
            logger.info("Exclusion added | symbol={}", symbol)

    def remove(self, symbol: str) -> None:
        symbol = symbol.strip()
        if not symbol:
            return
        with self._lock:
            current = self._read()
            if symbol not in current:
                return
            current.discard(symbol)
            self._write(current)
            logger.info("Exclusion removed | symbol={}", symbol)

    def _read(self) -> set[str]:
        if not self._path.exists():
            return set()
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw) if raw.strip() else {}
        except Exception:
            logger.exception("Failed to read exclusions | path={}", self._path)
            return set()
        symbols = data.get(self._SCHEMA_KEY, []) if isinstance(data, dict) else []
        if not isinstance(symbols, list):
            return set()
        return {str(s) for s in symbols if isinstance(s, str)}

    def _write(self, symbols: set[str]) -> None:
        payload = {self._SCHEMA_KEY: sorted(symbols)}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self._path)
        except Exception:
            logger.exception("Failed to write exclusions | path={}", self._path)
            raise
