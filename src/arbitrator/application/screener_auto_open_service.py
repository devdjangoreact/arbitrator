from __future__ import annotations

from collections.abc import Sequence

from arbitrator.application.arbitrage_open_service import ArbitrageOpenService
from arbitrator.application.spread_evaluator import SpreadEvaluator
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.named_exchange import NamedExchange
from arbitrator.domain.spread_calculator import SpreadCalculator
from arbitrator.domain.ticker import Ticker


class ScreenerAutoOpenService:
    """Evaluates screener spreads and opens arbitrage legs when thresholds are met."""

    def __init__(
        self,
        settings: Settings,
        open_service: ArbitrageOpenService,
        spread_evaluator: SpreadEvaluator,
    ) -> None:
        self._settings = settings
        self._open_service = open_service
        self._spread_evaluator = spread_evaluator

    def run_pass(
        self,
        snapshot: dict[tuple[str, str], Ticker],
        stream_symbols: Sequence[str],
        exchanges: Sequence[NamedExchange],
        opened_symbols: set[str],
        *,
        trading_ready: bool,
    ) -> set[str]:
        if not self._settings.arb_auto_open_enabled or not trading_ready:
            return opened_symbols
        updated = set(opened_symbols)
        for symbol in stream_symbols:
            prices = self._last_prices(snapshot, exchanges, symbol)
            if len(prices) < 2:
                continue
            spread_snapshot = SpreadCalculator.compute(symbol, prices)
            if not self._spread_evaluator.should_open(spread_snapshot):
                continue
            if symbol in updated:
                continue
            result = self._open_service.open_from_spread_sync(spread_snapshot)
            if result.success:
                updated.add(symbol)
                logger.info(
                    "Auto-open executed | symbol={} pair_id={}",
                    symbol,
                    result.pair_id,
                )
            else:
                logger.warning(
                    "Auto-open skipped | symbol={} message={}",
                    symbol,
                    result.message,
                )
        return updated

    @staticmethod
    def _last_prices(
        snapshot: dict[tuple[str, str], Ticker],
        exchanges: Sequence[NamedExchange],
        symbol: str,
    ) -> dict[str, float]:
        prices: dict[str, float] = {}
        for exchange in exchanges:
            ticker = snapshot.get((exchange.exchange_id, symbol))
            if ticker is not None and ticker.last is not None and ticker.last > 0.0:
                prices[exchange.exchange_id] = ticker.last
        return prices
