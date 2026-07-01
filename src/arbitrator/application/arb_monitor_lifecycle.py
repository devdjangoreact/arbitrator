from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from arbitrator.domain.arbitrage_pair import ArbitragePair

if TYPE_CHECKING:
    from arbitrator.application.arbitrage_monitor_worker import ArbitrageMonitorWorker

PairSignature = tuple[tuple[str, str, str, str], ...]


class ArbMonitorLifecycle:
    """Decides when the open-orders spread monitor must be restarted."""

    @staticmethod
    def pair_signature(pairs: Sequence[ArbitragePair]) -> PairSignature:
        return tuple(
            sorted(
                (pair.pair_id, pair.symbol, pair.short_leg.exchange_id, pair.long_leg.exchange_id)
                for pair in pairs
            )
        )

    @staticmethod
    def needs_new_worker(
        worker: ArbitrageMonitorWorker | None,
        pairs: Sequence[ArbitragePair],
    ) -> bool:
        if not pairs:
            return False
        signature = ArbMonitorLifecycle.pair_signature(pairs)
        if worker is None:
            return True
        if not worker.is_alive():
            return True
        return worker.monitored_signature() != signature
