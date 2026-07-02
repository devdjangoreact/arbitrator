from __future__ import annotations

import threading
import time

from arbitrator.application.screener_stream_worker import ScreenerStreamWorker
from arbitrator.application.strategy_table_service import StrategyTableService
from arbitrator.config.logger import logger


class StrategyRefreshWorker:
    """Background thread: keeps StrategyTableService up-to-date from screener tickers.

    The WS screener handler calls refresh() only while a browser is connected.
    This worker runs the same refresh loop independently so the auto-trader and
    any other consumers always have current tables — no browser required.
    """

    def __init__(
        self,
        screener_worker: ScreenerStreamWorker,
        table_service: StrategyTableService,
        interval_seconds: float = 1.0,
    ) -> None:
        self._screener = screener_worker
        self._table_service = table_service
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="strategy-refresh-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("strategy refresh worker started | interval={}s", self._interval)

    def stop(self) -> None:
        self._stop.set()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                snapshot, _symbols, _updates, _status, _threshold = self._screener.read_state()
                if snapshot:
                    now_ms = int(time.time() * 1000)
                    self._table_service.refresh(snapshot, now_ms)
            except Exception:
                logger.exception("strategy refresh worker tick failed")
            self._stop.wait(timeout=self._interval)
