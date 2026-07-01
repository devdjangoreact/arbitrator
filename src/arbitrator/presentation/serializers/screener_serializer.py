from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.strategy_kind import StrategyKind
from arbitrator.domain.strategy.strategy_table import StrategyTable
from arbitrator.domain.ticker import Ticker
from arbitrator.presentation.dto.opportunity_dto import OpportunityFocusDto
from arbitrator.presentation.dto.screener_dto import (
    ExchangePricesDto,
    ScreenerFiltersDto,
    ScreenerRowDto,
    ScreenerSnapshotDto,
    StrategyProfitsDto,
)


class ScreenerSerializer:
    """Builds the live ``ScreenerSnapshotDto`` from worker tickers + StrategyTables.

    Unavailable strategies map to ``None`` (``N/A`` on the UI, never a fake ``0``);
    spreads/nets are rounded only here, at the edge (FR-005/T063).
    """

    def __init__(self, settings: Settings) -> None:
        self._exchanges = list(settings.enabled_exchanges)
        self._filters = ScreenerFiltersDto(
            min_volume_k_usdt=settings.default_min_quote_volume_kusdt,
            stream_min_volume_usdt=settings.stream_min_quote_volume_usdt,
            min_spread_pct=settings.default_min_spread_pct,
        )
        self._prev_spread: dict[str, float] = {}

    def set_stream_min_volume_usdt(self, stream_min_volume_usdt: float) -> None:
        self._filters = ScreenerFiltersDto(
            min_volume_k_usdt=self._filters.min_volume_k_usdt,
            stream_min_volume_usdt=stream_min_volume_usdt,
            min_spread_pct=self._filters.min_spread_pct,
        )

    def set_filters(
        self,
        min_volume_k_usdt: float,
        stream_min_volume_usdt: float,
        min_spread_pct: float,
    ) -> None:
        self._filters = ScreenerFiltersDto(
            min_volume_k_usdt=min_volume_k_usdt,
            stream_min_volume_usdt=stream_min_volume_usdt,
            min_spread_pct=min_spread_pct,
        )

    def serialize(
        self,
        tickers: Mapping[tuple[str, str], Ticker],
        tables: Mapping[str, StrategyTable],
        status: str,
        symbol_count: int,
    ) -> ScreenerSnapshotDto:
        by_symbol: dict[str, dict[str, Ticker]] = {}
        for (exchange_id, symbol), ticker in tickers.items():
            by_symbol.setdefault(symbol, {})[exchange_id] = ticker

        rows: list[ScreenerRowDto] = []
        for symbol, per_exchange in by_symbol.items():
            row = self._build_row(symbol, per_exchange, tables.get(symbol))
            if row is None:
                continue
            rows.append(row)

        rows.sort(key=lambda r: r.spread_pct, reverse=True)
        default_focus = self._default_focus(rows)
        return ScreenerSnapshotDto(
            status=status,
            symbol_count=symbol_count,
            exchanges=self._exchanges,
            filters=self._filters,
            updated_at=datetime.now(tz=UTC),
            rows=rows,
            default_opportunity=default_focus,
        )

    def _build_row(
        self,
        symbol: str,
        per_exchange: Mapping[str, Ticker],
        table: StrategyTable | None,
    ) -> ScreenerRowDto | None:
        priced = {
            exchange_id: ticker.last
            for exchange_id, ticker in per_exchange.items()
            if ticker.last is not None and ticker.last > 0.0
        }
        if len(priced) < 2:
            return None
        short_exchange_id = max(priced, key=lambda ex: priced[ex])
        long_exchange_id = min(priced, key=lambda ex: priced[ex])
        max_price = priced[short_exchange_id]
        min_price = priced[long_exchange_id]
        spread_pct = (max_price - min_price) / min_price * 100.0 if min_price > 0 else 0.0
        spread_delta = spread_pct - self._prev_spread.get(symbol, spread_pct)
        self._prev_spread[symbol] = spread_pct

        any_ticker = next(iter(per_exchange.values()))
        asset = f"{any_ticker.base_asset}/{any_ticker.quote_asset}"
        volume_k = self._volume_k(per_exchange)

        return ScreenerRowDto(
            asset=asset,
            prices={
                exchange_id: ExchangePricesDto(futures=ticker.last, spot=None)
                for exchange_id, ticker in per_exchange.items()
            },
            max_price=max_price,
            min_price=min_price,
            spread_pct=round(spread_pct, 2),
            spread_delta=round(spread_delta, 2),
            volume_k_usdt=round(volume_k, 2),
            strategy_profits=self._profits(table),
            short_exchange_id=short_exchange_id,
            long_exchange_id=long_exchange_id,
        )

    @staticmethod
    def _volume_k(per_exchange: Mapping[str, Ticker]) -> float:
        volumes = [
            ticker.quote_volume_24h
            for ticker in per_exchange.values()
            if ticker.quote_volume_24h is not None
        ]
        return max(volumes) / 1000.0 if volumes else 0.0

    @staticmethod
    def _profits(table: StrategyTable | None) -> StrategyProfitsDto:
        def net(kind: StrategyKind) -> float | None:
            if table is None:
                return None
            result = table.results.get(kind)
            if result is None or not result.available or result.net_profit_usdt is None:
                return None
            return round(float(result.net_profit_usdt), 2)

        return StrategyProfitsDto(
            futures_futures=net(StrategyKind.futures_futures),
            futures_spot_2ex=net(StrategyKind.futures_spot_2ex),
            futures_spot_1ex=net(StrategyKind.futures_spot_1ex),
            funding_ff=net(StrategyKind.funding_ff),
            funding_fs=net(StrategyKind.funding_fs),
            funding_diff_dates=net(StrategyKind.funding_diff_dates),
        )

    @staticmethod
    def _default_focus(rows: list[ScreenerRowDto]) -> OpportunityFocusDto:
        if not rows:
            return OpportunityFocusDto(symbol="", short_exchange_id="", long_exchange_id="")
        top = rows[0]
        return OpportunityFocusDto(
            symbol=top.asset,
            short_exchange_id=top.short_exchange_id,
            long_exchange_id=top.long_exchange_id,
        )
