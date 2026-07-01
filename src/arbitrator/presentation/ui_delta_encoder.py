from __future__ import annotations

from arbitrator.presentation.dto.opportunity_dto import (
    ChartPointDto,
    ChartSnapshotDto,
    OpportunitySnapshotDto,
    OrderBookPanelDto,
)
from arbitrator.presentation.dto.screener_dto import ScreenerRowDto, ScreenerSnapshotDto
from arbitrator.presentation.dto.ui_delta_dto import (
    ChartSeriesDeltaDto,
    OpportunityDeltaDto,
    ScreenerDeltaDto,
)


class UiDeltaEncoder:
    """Build incremental WS payloads from consecutive snapshots."""

    @staticmethod
    def screener_delta(
        previous: ScreenerSnapshotDto | None,
        current: ScreenerSnapshotDto,
    ) -> ScreenerDeltaDto:
        prev_by_asset: dict[str, ScreenerRowDto] = {}
        if previous is not None:
            prev_by_asset = {row.asset: row for row in previous.rows}

        curr_assets = {row.asset for row in current.rows}
        rows_changed: list[ScreenerRowDto] = []
        for row in current.rows:
            prev = prev_by_asset.get(row.asset)
            if prev is None or prev.model_dump() != row.model_dump():
                rows_changed.append(row)

        rows_removed = [asset for asset in prev_by_asset if asset not in curr_assets]

        status = current.status if previous is None or previous.status != current.status else None
        symbol_count = (
            current.symbol_count
            if previous is None or previous.symbol_count != current.symbol_count
            else None
        )
        exchanges = (
            current.exchanges
            if previous is None or previous.exchanges != current.exchanges
            else None
        )
        filters = (
            current.filters
            if previous is None or previous.filters != current.filters
            else None
        )

        return ScreenerDeltaDto(
            status=status,
            symbol_count=symbol_count,
            exchanges=exchanges,
            filters=filters,
            rows_changed=rows_changed,
            rows_removed=rows_removed,
        )

    @staticmethod
    def opportunity_delta(
        previous: OpportunitySnapshotDto | None,
        current: OpportunitySnapshotDto,
    ) -> OpportunityDeltaDto:
        chart_series: list[ChartSeriesDeltaDto] = []
        if current.chart is not None:
            chart_series = UiDeltaEncoder._chart_series_delta(previous, current.chart)

        books: list[OrderBookPanelDto] = []
        if previous is None:
            books = list(current.books)
        else:
            prev_books = {
                f"{book.exchange_id}:{book.market_type}": book for book in previous.books
            }
            for book in current.books:
                key = f"{book.exchange_id}:{book.market_type}"
                prev = prev_books.get(key)
                if prev is None or prev.model_dump() != book.model_dump():
                    books.append(book)

        exchange_cards = None
        funding_countdown_sec = None
        if previous is None or previous.exchange_cards != current.exchange_cards:
            exchange_cards = list(current.exchange_cards)
        elif current.exchange_cards and previous.exchange_cards:
            new_cd = current.exchange_cards[0].funding_countdown_sec
            old_cd = previous.exchange_cards[0].funding_countdown_sec
            if new_cd != old_cd:
                funding_countdown_sec = new_cd

        return OpportunityDeltaDto(
            symbol=current.symbol if previous is None else None,
            short_exchange_id=current.short_exchange_id if previous is None else None,
            long_exchange_id=current.long_exchange_id if previous is None else None,
            chart_series=chart_series,
            books=books,
            exchange_cards=exchange_cards,
            funding_countdown_sec=funding_countdown_sec,
        )

    @staticmethod
    def _chart_series_delta(
        previous: OpportunitySnapshotDto | None,
        current_chart: ChartSnapshotDto,
    ) -> list[ChartSeriesDeltaDto]:
        prev_series: dict[str, ChartPointDto | None] = {}
        if previous is not None and previous.chart is not None:
            for series in previous.chart.series:
                last_point = series.points[-1] if series.points else None
                prev_series[series.key] = last_point

        deltas: list[ChartSeriesDeltaDto] = []
        for series in current_chart.series:
            point = series.points[-1] if series.points else None
            if point is None:
                continue
            prev_point = prev_series.get(series.key)
            if prev_point is None or prev_point.t != point.t or prev_point.price != point.price:
                deltas.append(
                    ChartSeriesDeltaDto(
                        key=series.key,
                        last_price=series.last_price,
                        point=point,
                    )
                )
        return deltas
