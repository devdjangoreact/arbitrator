from __future__ import annotations

from decimal import Decimal

from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.strategy.strategy_inputs import StrategyInputs

_HUNDRED = Decimal("100")


class AnomalyGuard:
    """Blocks automatic entry in anomalous/unsafe conditions (FR-015).

    Returns a machine-readable block reason string, or ``None`` when the entry
    is allowed. Covered anomalies: excessive cross-price spread (possible
    listing/withdraw event) and stale quotes past the configured max age.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def evaluate(self, inputs: StrategyInputs, spread_pct: Decimal | None) -> str | None:
        if spread_pct is not None:
            max_spread = Decimal(str(self._settings.anomaly_max_spread_pct))
            if abs(spread_pct) > max_spread:
                return "anomalous_spread"
        if self._quotes_stale(inputs):
            return "stale_data"
        return None

    def _quotes_stale(self, inputs: StrategyInputs) -> bool:
        max_age_ms = int(self._settings.quote_max_age_seconds * 1000)
        for exchange_id in (inputs.short_exchange_id, inputs.long_exchange_id):
            quote = inputs.futures_quotes.get(exchange_id)
            if self._quote_stale(quote, inputs.now_ms, max_age_ms):
                return True
        return False

    @staticmethod
    def _quote_stale(quote: Quote | None, now_ms: int, max_age_ms: int) -> bool:
        if quote is None:
            return True
        return (now_ms - quote.recv_time_ms) > max_age_ms
