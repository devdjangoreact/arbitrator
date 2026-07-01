from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arbitrator.presentation.dto.opportunity_dto import (
    ChartPointDto,
    ExchangeInfoCardDto,
    OrderBookPanelDto,
)
from arbitrator.presentation.dto.screener_dto import ScreenerFiltersDto, ScreenerRowDto


class ScreenerDeltaDto(BaseModel):
    """Incremental screener update — only changed rows and optional meta."""

    model_config = ConfigDict(frozen=True)

    status: str | None = None
    symbol_count: int | None = None
    exchanges: list[str] | None = None
    filters: ScreenerFiltersDto | None = None
    rows_changed: list[ScreenerRowDto] = []
    rows_removed: list[str] = []


class ChartSeriesDeltaDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    last_price: float
    point: ChartPointDto


class OpportunityDeltaDto(BaseModel):
    """Incremental opportunity update — chart ticks, books, optional cards."""

    model_config = ConfigDict(frozen=True)

    symbol: str | None = None
    short_exchange_id: str | None = None
    long_exchange_id: str | None = None
    chart_series: list[ChartSeriesDeltaDto] = []
    books: list[OrderBookPanelDto] = []
    exchange_cards: list[ExchangeInfoCardDto] | None = None
    funding_countdown_sec: int | None = None
