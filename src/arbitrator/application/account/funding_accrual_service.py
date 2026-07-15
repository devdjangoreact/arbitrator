from __future__ import annotations

import threading

from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.logger import logger
from arbitrator.config.paper_order_store import PaperOrderStore


class FundingAccrualService:
    """Periodically charges funding to open paper positions.

    For each open leg, reads the current funding rate from the cache and
    applies ``notional × rate`` (sign-adjusted for long/short) to the order's
    accrued_funding_usdt.  Runs every ``interval_seconds`` (default ~30 min).
    """

    def __init__(
        self,
        store: PaperOrderStore,
        cache: MarketDataCacheMemory,
        interval_seconds: float = 1800.0,
    ) -> None:
        self._store = store
        self._cache = cache
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="funding-accrual-service",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "funding accrual service started | interval={}s", self._interval
        )

    def stop(self) -> None:
        self._stop.set()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(timeout=self._interval)
            if self._stop.is_set():
                break
            try:
                self._tick()
            except Exception:
                logger.exception("funding accrual tick failed")

    def _tick(self) -> None:
        records = self._store.load_all()
        open_legs = [
            r for r in records
            if r.action == "open" and r.status == "filled"
        ]
        if not open_legs:
            return

        # Exchange funding rates are quoted per 8-hour period (28800 s).
        # We tick every `_interval` seconds, so charge only the proportional slice.
        interval_fraction = self._interval / 28800.0

        for leg in open_legs:
            funding_info = self._cache.get_funding(leg.exchange_id, leg.symbol)
            if funding_info is None or funding_info.rate is None:
                continue
            rate = float(funding_info.rate) * interval_fraction
            # long pays positive rate; short receives (negated)
            if leg.side == "buy":
                funding_usdt = leg.notional_usdt * rate
            else:
                funding_usdt = -(leg.notional_usdt * rate)

            if abs(funding_usdt) < 0.000001:
                continue

            self._store.accrue_funding(
                pair_id=leg.pair_id,
                exchange_id=leg.exchange_id,
                funding_usdt=round(funding_usdt, 6),
            )

        logger.debug(
            "funding accrual tick done | open_legs={}", len(open_legs)
        )
