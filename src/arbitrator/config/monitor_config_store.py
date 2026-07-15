import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from arbitrator.config.logger import logger


@dataclass
class MonitorConfig:
    symbol: str
    short_ex: str
    long_ex: str
    side: Literal["auto", "long", "short"] = "auto"
    open_spread_pct: float = 1.0
    close_spread_pct: float = 0.1
    order_size_usdt: float = 100.0
    max_orders: int = 1
    open_ticks: int = 2
    close_ticks: int = 1
    allowed_size_usdt: float = 300.0
    force_stop: bool = False
    total_stop: bool = False
    is_active: bool = False
    detected_at: float = 0.0
    max_historical_spread_pct: float = 0.0

class MonitorConfigStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._cache: dict[str, MonitorConfig] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                self._cache[k] = MonitorConfig(**v)
        except Exception:
            logger.exception("Failed to load monitor configs from {}", self._path)

    def _save(self) -> None:
        try:
            data = {k: asdict(v) for k, v in self._cache.items()}
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            logger.exception("Failed to save monitor configs to {}", self._path)

    def get_all(self) -> list[MonitorConfig]:
        with self._lock:
            return list(self._cache.values())

    def get(self, symbol: str) -> MonitorConfig | None:
        with self._lock:
            return self._cache.get(symbol)

    def put(self, config: MonitorConfig) -> None:
        with self._lock:
            self._cache[config.symbol] = config
            self._save()

    def delete(self, symbol: str) -> None:
        with self._lock:
            if symbol in self._cache:
                del self._cache[symbol]
                self._save()
