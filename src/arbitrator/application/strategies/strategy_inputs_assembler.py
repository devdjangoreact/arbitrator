from __future__ import annotations
from arbitrator.config.ui_config_manager import UIConfigManager

from decimal import Decimal

from arbitrator.config.settings import Settings
from arbitrator.domain.market.market_data_cache import MarketDataCache
from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.funding_info import FundingInfo
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.strategy.strategy_inputs import StrategyInputs


class StrategyInputsAssembler:
    """Builds an immutable ``StrategyInputs`` for one symbol + exchange pair.

    Reads the latest cached quotes/funding/fees, applies the freshness gate
    (``quote_max_age_seconds``) so stale quotes are dropped (calculator -> ``N/A``,
    no fabrication), and converts everything into the frozen snapshot the engine
    computes off (C5/FR-025).
    """

    def __init__(self, cache: MarketDataCache, settings: Settings) -> None:
        self._cache = cache
        self._settings = settings

    def assemble(
        self,
        *,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        target_volume_usdt: Decimal,
        leverage: dict[str, int],
        now_ms: int,
    ) -> StrategyInputs:
        exchange_ids = {short_exchange_id, long_exchange_id}
        max_age_ms = int(UIConfigManager.get_config().quote_max_age_seconds * 1000)
        funding_max_age_ms = int(UIConfigManager.get_config().funding_refresh_seconds * 3 * 1000)

        futures_quotes: dict[str, Quote] = {}
        spot_quotes: dict[str, Quote] = {}
        funding: dict[str, FundingInfo] = {}
        fees: dict[str, FeeSchedule] = {}

        for exchange_id in exchange_ids:
            fut = self._cache.get_quote(exchange_id, symbol, "futures")
            if fut is not None and self._fresh(fut.recv_time_ms, now_ms, max_age_ms):
                futures_quotes[exchange_id] = fut
            spot = self._cache.get_quote(exchange_id, symbol, "spot")
            if spot is not None and self._fresh(spot.recv_time_ms, now_ms, max_age_ms):
                spot_quotes[exchange_id] = spot
            fund = self._cache.get_funding(exchange_id, symbol)
            if fund is not None and self._fresh(fund.recv_time_ms, now_ms, funding_max_age_ms):
                funding[exchange_id] = fund
            fee = self._cache.get_fees(exchange_id, symbol)
            if fee is not None:
                fees[exchange_id] = fee

        return StrategyInputs(
            symbol=symbol,
            short_exchange_id=short_exchange_id,
            long_exchange_id=long_exchange_id,
            futures_quotes=futures_quotes,
            spot_quotes=spot_quotes,
            funding=funding,
            fees=fees,
            target_volume_usdt=target_volume_usdt,
            leverage=leverage,
            deposit_usdt=None,
            now_ms=now_ms,
        )

    @staticmethod
    def _fresh(recv_time_ms: int, now_ms: int, max_age_ms: int) -> bool:
        return now_ms - recv_time_ms <= max_age_ms
