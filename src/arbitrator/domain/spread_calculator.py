from __future__ import annotations

from datetime import UTC, datetime

from arbitrator.domain.spread_snapshot import SpreadSnapshot


class SpreadCalculator:
    """Shared cross-exchange spread formula for screener and arbitrage."""

    @staticmethod
    def compute(symbol: str, prices_by_exchange: dict[str, float]) -> SpreadSnapshot:
        positive = {ex: price for ex, price in prices_by_exchange.items() if price > 0.0}
        updated_at = datetime.now(UTC)
        if len(positive) < 2:
            return SpreadSnapshot(
                symbol=symbol,
                prices_by_exchange=dict(positive),
                spread_pct=None,
                high_exchange_id=None,
                low_exchange_id=None,
                updated_at=updated_at,
            )
        high_ex = max(positive, key=lambda ex: positive[ex])
        low_ex = min(positive, key=lambda ex: positive[ex])
        max_price = positive[high_ex]
        min_price = positive[low_ex]
        spread_pct: float | None = None
        if min_price != 0.0:
            spread_pct = (max_price - min_price) / min_price * 100.0
        return SpreadSnapshot(
            symbol=symbol,
            prices_by_exchange=dict(positive),
            spread_pct=spread_pct,
            high_exchange_id=high_ex,
            low_exchange_id=low_ex,
            updated_at=updated_at,
        )

    @staticmethod
    def from_last_prices(
        symbol: str,
        exchange_ids: list[str],
        last_prices: list[float],
    ) -> SpreadSnapshot:
        prices: dict[str, float] = {}
        for exchange_id, price in zip(exchange_ids, last_prices, strict=False):
            if price > 0.0:
                prices[exchange_id] = price
        return SpreadCalculator.compute(symbol, prices)
