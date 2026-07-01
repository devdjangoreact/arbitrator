from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ChartPointDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    t: int
    price: float


class ChartSeriesDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    label: str
    exchange_id: str
    market_type: Literal["futures", "spot"]
    color: str
    dashed: bool
    last_price: float
    points: list[ChartPointDto]


class ChartSnapshotDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    window_seconds: int
    series: list[ChartSeriesDto]


class OrderBookLevelDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: float
    amount: float
    total: float
    fill_pct: float
    amount_fill_pct: float


class OrderBookPanelDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    exchange_id: str
    market_type: Literal["futures", "spot"]
    side_role: Literal["short", "long"]
    volume_24h_label: str
    range_label: str
    spread_pct: float
    mid_price: float
    asks: list[OrderBookLevelDto]
    bids: list[OrderBookLevelDto]


class ExchangeInfoCardDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    exchange_id: str
    side: Literal["short", "long"]
    base_asset: str
    market_symbol: str
    native_market_id: str | None
    min_order_volume_usdt: float | None
    max_order_volume_usdt: float | None
    spot_min_order_volume_usdt: float | None = None
    spot_max_order_volume_usdt: float | None = None
    balance_usdt: float | None
    funding_rate_pct: float | None
    funding_countdown_sec: int | None
    leverage: int
    futures_fee: str
    spot_fee: str
    open_orders_count: int
    closed_orders_count: int


class StrategyCalculationRowDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    strategy_label: str
    spread_pct: float
    prices_label: str
    fees_usdt: float
    funding_usdt: float
    volume_usdt: float
    leverage: int
    gross_profit_usdt: float | None
    costs_usdt: float
    costs_breakdown: str
    net_profit_usdt: float | None
    percent_to_deposit: float | None
    unavailable_reason: str | None = None


class OpportunityParamsDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    active_strategy_id: str
    accumulated_volume_usdt: float
    target_volume_usdt: float
    open_spread_threshold_pct: float
    close_spread_threshold_pct: float
    accumulate_volume_usdt: float
    accumulate_volume_pct: float
    close_volume_usdt: float
    close_volume_pct: float
    auto_accumulate_enabled: bool
    auto_close_enabled: bool
    volume_pct_presets: list[float] = Field(default_factory=list)


class OrderLegDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    exchange_id: str
    side: Literal["short", "long"]
    leverage: int
    volume_usdt: float
    entry_price: float
    exit_price: float | None
    fees_usdt: float
    funding_usdt: float
    pnl_usdt: float


class OrderGroupDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    group_id: str
    asset: str
    strategy_code: str
    short_exchange_id: str
    long_exchange_id: str
    opened_at: str
    closed_at: str | None
    leverage: int
    volume_usdt: float
    entry_price: float | None
    exit_price: float | None
    fees_usdt: float
    funding_usdt: float
    pnl_usdt: float
    status: Literal["open", "closed"]
    legs: list[OrderLegDto]


class OpportunityFocusDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    short_exchange_id: str
    long_exchange_id: str


class OpportunitySnapshotDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    short_exchange_id: str
    long_exchange_id: str
    exchange_cards: list[ExchangeInfoCardDto]
    strategy_rows: list[StrategyCalculationRowDto]
    books: list[OrderBookPanelDto]
    chart: ChartSnapshotDto
    params: OpportunityParamsDto
    orders: list[OrderGroupDto]
    status: str
