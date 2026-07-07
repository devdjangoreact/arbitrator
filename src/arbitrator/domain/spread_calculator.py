from __future__ import annotations

from datetime import UTC, datetime

from arbitrator.domain.spread_snapshot import SpreadSnapshot


class SpreadCalculator:
    """Shared cross-exchange spread formula for screener and arbitrage.

    Display / screener ranking may use ``last`` via :meth:`compute`.
    Open/close trading decisions must use :meth:`entry_spread_pct` /
    :meth:`exit_spread_pct` with bid/ask (or order-book top), never ``last``.
    """

    @staticmethod
    def entry_spread_pct(short_bid: float, long_ask: float) -> float | None:
        """Entry spread: short sells at bid, long buys at ask."""
        if long_ask <= 0.0:
            return None
        return (short_bid - long_ask) / long_ask * 100.0

    @staticmethod
    def exit_spread_pct(short_ask: float, long_bid: float) -> float | None:
        """Exit spread: buy back short at ask, sell long at bid."""
        if long_bid <= 0.0:
            return None
        return (short_ask - long_bid) / long_bid * 100.0

    @staticmethod
    def best_executable_pair(
        bid_by_exchange: dict[str, float],
        ask_by_exchange: dict[str, float],
    ) -> tuple[str, str, float, float, float] | None:
        """Pick short/long venues by max bid / min ask; return best positive pair.

        Returns ``(short_ex, long_ex, short_bid, long_ask, spread_pct)`` or None
        when fewer than two exchanges or no cross-venue pair exists.
        """
        if len(bid_by_exchange) < 2 or len(ask_by_exchange) < 2:
            return None
        best: tuple[str, str, float, float, float] | None = None
        for short_ex, short_bid in bid_by_exchange.items():
            for long_ex, long_ask in ask_by_exchange.items():
                if short_ex == long_ex:
                    continue
                spread = SpreadCalculator.entry_spread_pct(short_bid, long_ask)
                if spread is None:
                    continue
                if best is None or spread > best[4]:
                    best = (short_ex, long_ex, short_bid, long_ask, spread)
        return best

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
