import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

from arbitrator.config.logger import logger


@dataclass
class MonitorConfig:
    symbol: str
    short_exchange: str
    long_exchange: str
    side: Literal["auto", "long", "short"] = "auto"
    open_spread_pct: float = 1.0
    close_spread_pct: float = 0.1
    order_size_usdt: float = 100.0
    max_orders: int = 1
    open_ticks: int = 2
    close_ticks: int = 1
    allowed_size_usdt: float = 300.0
    allowed_size_current_usdt: float = 0.0
    force_stop: bool = False
    total_stop: bool = False
    is_active: bool = False
    adjustment_mode: Literal["notify_only", "adjust"] = "notify_only"
    short_leverage: int = 1
    long_leverage: int = 1
    detected_at: float = 0.0
    max_historical_spread_pct: float = 0.0
    id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.id:
            self.id = f"{self.symbol}:{self.short_exchange}:{self.long_exchange}"

    @classmethod
    def from_dict(cls, d: dict) -> "MonitorConfig":
        # Migration: old single `leverage` → both legs
        if "leverage" in d and "short_leverage" not in d:
            lev = int(d.pop("leverage"))
            d["short_leverage"] = lev
            d["long_leverage"] = lev
        known = {f.name for f in __import__("dataclasses").fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


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
                # Migration: old keys short_ex/long_ex → short_exchange/long_exchange
                if "short_ex" in v and "short_exchange" not in v:
                    v["short_exchange"] = v.pop("short_ex")
                if "long_ex" in v and "long_exchange" not in v:
                    v["long_exchange"] = v.pop("long_ex")
                self._cache[k] = MonitorConfig.from_dict(v)
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

    def get(self, monitor_id: str) -> MonitorConfig | None:
        with self._lock:
            return self._cache.get(monitor_id)

    def get_by_symbol(self, symbol: str) -> MonitorConfig | None:
        with self._lock:
            for c in self._cache.values():
                if c.symbol == symbol:
                    return c
            return None

    def put(self, config: MonitorConfig) -> None:
        if not config.id:
            config.id = f"{config.symbol}:{config.short_exchange}:{config.long_exchange}"
        with self._lock:
            self._cache[config.id] = config
            self._save()

    def delete(self, monitor_id: str) -> None:
        with self._lock:
            if monitor_id in self._cache:
                del self._cache[monitor_id]
                self._save()
