from __future__ import annotations

from statistics import quantiles


class LatencyMetrics:
    def __init__(self) -> None:
        self._lags_ms: list[float] = []
        self._first_bbo_ms: dict[str, float] = {}
        self._subscribe_ns: dict[str, int] = {}
        self.updates: int = 0

    def mark_subscribe(self, key: str, ts_ns: int) -> None:
        self._subscribe_ns[key] = ts_ns

    def record_apply(self, key: str, recv_ts_ns: int, apply_ts_ns: int) -> None:
        self.updates += 1
        self._lags_ms.append((apply_ts_ns - recv_ts_ns) / 1_000_000.0)
        if len(self._lags_ms) > 10_000:
            self._lags_ms = self._lags_ms[-5_000:]
        if key not in self._first_bbo_ms and key in self._subscribe_ns:
            self._first_bbo_ms[key] = (apply_ts_ns - self._subscribe_ns[key]) / 1_000_000.0

    def snapshot(self) -> dict[str, float]:
        lags = self._lags_ms
        p50 = 0.0
        p95 = 0.0
        if len(lags) >= 2:
            qs = quantiles(lags, n=20)
            p50 = qs[9]
            p95 = qs[18]
        elif lags:
            p50 = p95 = lags[0]
        first = min(self._first_bbo_ms.values()) if self._first_bbo_ms else 0.0
        return {
            "apply_lag_p50_ms": p50,
            "apply_lag_p95_ms": p95,
            "first_bbo_ms": first,
            "updates": float(self.updates),
        }
