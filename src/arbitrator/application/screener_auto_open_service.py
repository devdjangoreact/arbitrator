from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from arbitrator.application.arbitrage_open_service import ArbitrageOpenService
from arbitrator.application.executable_spread_resolver import ExecutableSpreadResolver
from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.spread_evaluator import SpreadEvaluator
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.named_exchange import NamedExchange
from arbitrator.domain.spread_calculator import SpreadCalculator
from arbitrator.domain.spread_snapshot import SpreadSnapshot
from arbitrator.domain.ticker import Ticker

if TYPE_CHECKING:
    from arbitrator.domain.exchange_gateway import ExchangeGateway


class ScreenerAutoOpenService:
    """Evaluates screener spreads and opens arbitrage legs when thresholds are met."""

    def __init__(
        self,
        settings: Settings,
        open_service: ArbitrageOpenService,
        spread_evaluator: SpreadEvaluator,
        market_cache: MarketDataCacheMemory | None = None,
        gateways: Mapping[str, ExchangeGateway] | None = None,
    ) -> None:

        self._settings = settings

        self._open_service = open_service

        self._spread_evaluator = spread_evaluator

        self._spread_resolver = (
            ExecutableSpreadResolver(settings, market_cache, gateways)
            if market_cache is not None
            else None
        )

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

            spread_snapshot = self._executable_spread_snapshot(snapshot, exchanges, symbol)

            if spread_snapshot is None or spread_snapshot.spread_pct is None:

                continue

            if not self._spread_evaluator.should_open(spread_snapshot):

                continue

            if symbol in updated:

                continue

            spread_snapshot = self._confirm_spread_snapshot(spread_snapshot, snapshot)
            if spread_snapshot is None:
                continue

            if not self._spread_evaluator.should_open(spread_snapshot):
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

    def _confirm_spread_snapshot(
        self,
        spread_snapshot: SpreadSnapshot,
        snapshot: dict[tuple[str, str], Ticker],
    ) -> SpreadSnapshot | None:
        from datetime import UTC, datetime

        if self._spread_resolver is None or spread_snapshot.spread_pct is None:
            return spread_snapshot

        symbol = spread_snapshot.symbol
        short_ex = spread_snapshot.high_exchange_id
        long_ex = spread_snapshot.low_exchange_id
        confirmed = asyncio.run(
            self._spread_resolver.entry_spread_for_open(
                symbol,
                short_ex,
                long_ex,
                spread_snapshot.spread_pct,
                short_ticker=snapshot.get((short_ex, symbol)),
                long_ticker=snapshot.get((long_ex, symbol)),
            )
        )
        if confirmed is None:
            return None

        short_bid, long_ask, spread_pct = confirmed
        return SpreadSnapshot(
            symbol=symbol,
            prices_by_exchange={short_ex: short_bid, long_ex: long_ask},
            spread_pct=spread_pct,
            high_exchange_id=short_ex,
            low_exchange_id=long_ex,
            updated_at=datetime.now(UTC),
        )

    def _executable_spread_snapshot(
        self,
        snapshot: dict[tuple[str, str], Ticker],
        exchanges: Sequence[NamedExchange],
        symbol: str,
    ) -> SpreadSnapshot | None:

        from datetime import UTC, datetime

        per_exchange: dict[str, Ticker] = {}

        for exchange in exchanges:

            ticker = snapshot.get((exchange.exchange_id, symbol))

            if ticker is not None:

                per_exchange[exchange.exchange_id] = ticker

        if len(per_exchange) < 2:

            return None

        best = (
            self._spread_resolver.best_entry_pair_sync(symbol, per_exchange)
            if self._spread_resolver is not None
            else self._best_pair_from_tickers(per_exchange)
        )

        if best is None:

            return None

        short_ex, long_ex, short_bid, long_ask, spread_pct = best

        return SpreadSnapshot(
            symbol=symbol,
            prices_by_exchange={short_ex: short_bid, long_ex: long_ask},
            spread_pct=spread_pct,
            high_exchange_id=short_ex,
            low_exchange_id=long_ex,
            updated_at=datetime.now(UTC),
        )

    @staticmethod
    def _best_pair_from_tickers(
        per_exchange: dict[str, Ticker],
    ) -> tuple[str, str, float, float, float] | None:

        bid_by_exchange: dict[str, float] = {}

        ask_by_exchange: dict[str, float] = {}

        for exchange_id, ticker in per_exchange.items():

            if ticker.bid is not None and ticker.bid > 0.0:

                bid_by_exchange[exchange_id] = ticker.bid

            if ticker.ask is not None and ticker.ask > 0.0:

                ask_by_exchange[exchange_id] = ticker.ask

        return SpreadCalculator.best_executable_pair(bid_by_exchange, ask_by_exchange)
