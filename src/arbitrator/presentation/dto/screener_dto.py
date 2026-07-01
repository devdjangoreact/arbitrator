from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from arbitrator.presentation.dto.opportunity_dto import OpportunityFocusDto


class ExchangePricesDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    futures: float | None
    spot: float | None


class StrategyProfitsDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    futures_futures: float | None
    futures_spot_2ex: float | None
    futures_spot_1ex: float | None
    funding_ff: float | None
    funding_fs: float | None
    funding_diff_dates: float | None


class ScreenerRowDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset: str
    prices: dict[str, ExchangePricesDto]
    max_price: float
    min_price: float
    spread_pct: float
    spread_delta: float
    volume_k_usdt: float
    strategy_profits: StrategyProfitsDto
    short_exchange_id: str
    long_exchange_id: str


class ScreenerFiltersDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    min_volume_k_usdt: float
    stream_min_volume_usdt: float
    min_spread_pct: float


class ScreenerSnapshotDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    symbol_count: int
    exchanges: list[str]
    filters: ScreenerFiltersDto
    updated_at: datetime
    rows: list[ScreenerRowDto]
    default_opportunity: OpportunityFocusDto
