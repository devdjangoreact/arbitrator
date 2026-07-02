from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from arbitrator.config.logger import logger
from arbitrator.domain.symbol_market_info import SymbolMarketInfo
from arbitrator.domain.symbol_normalizer import SymbolNormalizer
from arbitrator.presentation.dto.opportunity_dto import (
    ChartPointDto,
    ChartSeriesDto,
    ChartSnapshotDto,
    ExchangeInfoCardDto,
    OpportunityParamsDto,
    OpportunitySnapshotDto,
    OrderBookLevelDto,
    OrderBookPanelDto,
    OrderGroupDto,
    StrategyCalculationRowDto,
)
from arbitrator.presentation.dto.opportunity_dto import OpportunityFocusDto
from arbitrator.presentation.dto.orders_dto import OrdersSnapshotDto, OrdersSummaryDto
from arbitrator.presentation.dto.screener_dto import (
    ExchangePricesDto,
    ScreenerFiltersDto,
    ScreenerRowDto,
    ScreenerSnapshotDto,
    StrategyProfitsDto,
)
from arbitrator.presentation.dto.settings_dto import SettingsExchangeDto, SettingsSnapshotDto
from arbitrator.presentation.mock.mock_strategy_calculator import (
    MockExchangePrices,
    MockScreenerStrategyCalibration,
    MockStrategyCalculator,
)

_MOCK_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "mock_data.json"


def _load_seed_data() -> dict[str, object]:
    try:
        raw = _MOCK_DATA_PATH.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except Exception:
        logger.exception("Failed to load mock seed data | path={}", _MOCK_DATA_PATH)
        raise
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid mock seed data schema: {_MOCK_DATA_PATH}")
    return payload


_SEED_DATA = _load_seed_data()


class _MutablePrices(BaseModel):
    model_config = ConfigDict(frozen=False)

    futures: float
    spot: float


class _MutableScreenerRow(BaseModel):
    model_config = ConfigDict(frozen=False)

    asset: str
    prices: dict[str, _MutablePrices]
    volume_k_usdt: float
    short_exchange_id: str
    long_exchange_id: str
    prev_spread_pct: float = 0.0


class _MutableBookLevel(BaseModel):
    model_config = ConfigDict(frozen=False)

    price: float
    amount: float


class _MutableBook(BaseModel):
    model_config = ConfigDict(frozen=False)

    exchange_id: str
    market_type: Literal["futures", "spot"]
    side_role: Literal["short", "long"]
    volume_24h_label: str
    range_label: str
    asks: list[_MutableBookLevel]
    bids: list[_MutableBookLevel]


class _MutableChartSeries(BaseModel):
    model_config = ConfigDict(frozen=False)

    key: str
    label: str
    exchange_id: str
    market_type: Literal["futures", "spot"]
    color: str
    dashed: bool
    last_price: float
    points: list[ChartPointDto]


_MASKED_KEY = "••••••••••••"


def _screener_seed_rows() -> list[_MutableScreenerRow]:
    seed_raw = _SEED_DATA.get("screener_rows", [])
    if not isinstance(seed_raw, list):
        raise ValueError("Invalid mock seed: screener_rows must be list")
    rows: list[_MutableScreenerRow] = []
    for row_data in seed_raw:
        if not isinstance(row_data, dict):
            continue
        prices_data = row_data.get("prices", {})
        if not isinstance(prices_data, dict):
            continue
        price_map = {
            ex: _MutablePrices(
                futures=float(price_values.get("futures", 0.0)),
                spot=float(price_values.get("spot", 0.0)),
            )
            for ex, price_values in prices_data.items()
            if isinstance(ex, str) and isinstance(price_values, dict)
        }
        fut_prices = [p.futures for p in price_map.values()]
        spread = (max(fut_prices) - min(fut_prices)) / min(fut_prices) * 100.0 if fut_prices else 0.0
        rows.append(
            _MutableScreenerRow(
                asset=str(row_data.get("asset", "")),
                prices=price_map,
                volume_k_usdt=float(row_data.get("volume_k_usdt", 0.0)),
                short_exchange_id=str(row_data.get("short_exchange_id", "")),
                long_exchange_id=str(row_data.get("long_exchange_id", "")),
                prev_spread_pct=spread,
            )
        )
    return rows


class MockDataProvider:
    """In-memory mock snapshots and command handlers for UI_DATA_MODE=mock_data."""

    def __init__(self, enabled_exchanges: list[str]) -> None:
        self._exchanges = list(enabled_exchanges)
        self._screener_rows = _screener_seed_rows()
        self._screener_status = str(_SEED_DATA.get("screener_status", "filtered"))
        self._reconnect_pending = False
        self._filters = ScreenerFiltersDto.model_validate(_SEED_DATA.get("screener_filters", {}))
        self._orders_filter: Literal["all", "open", "closed"] = str(
            _SEED_DATA.get("orders_filter_default", "all")
        )  # type: ignore[assignment]
        self._order_groups = self._build_order_groups()
        settings_masked_key = str(_SEED_DATA.get("settings_masked_key", _MASKED_KEY))
        settings_seed = _SEED_DATA.get("settings_exchanges", [])
        if not isinstance(settings_seed, list):
            settings_seed = []
        self._settings_exchanges = [
            SettingsExchangeDto(
                exchange_id=str(ex.get("exchange_id", "")),
                api_key_masked=settings_masked_key,
                configured=bool(ex.get("configured", False)),
                has_secret=bool(ex.get("has_secret", False)),
                has_password=bool(ex.get("has_password", False)),
            )
            for ex in settings_seed
            if isinstance(ex, dict)
        ]
        self._opportunity_params = OpportunityParamsDto.model_validate(
            _SEED_DATA.get("opportunity_params", {})
        )
        leverage_seed = _SEED_DATA.get("leverage", {})
        self._leverage: dict[str, int] = {
            str(exchange_id): int(value)
            for exchange_id, value in leverage_seed.items()
        } if isinstance(leverage_seed, dict) else {}
        _fcd = _SEED_DATA.get("funding_countdown_sec", 0)
        self._funding_countdown_sec = int(_fcd) if isinstance(_fcd, (int, float)) else 0
        _frs = _SEED_DATA.get("funding_reset_seconds", 8 * 3600)
        self._funding_reset_seconds = int(_frs) if isinstance(_frs, (int, float)) else 8 * 3600
        _cws = _SEED_DATA.get("chart_window_seconds", 120)
        self._chart_window_seconds = int(_cws) if isinstance(_cws, (int, float)) else 120
        _cmp = _SEED_DATA.get("chart_max_points", 61)
        self._chart_max_points = int(_cmp) if isinstance(_cmp, (int, float)) else 61
        tick_seed = _SEED_DATA.get("tick_settings", {})
        if not isinstance(tick_seed, dict):
            tick_seed = {}
        self._price_delta_min_pct = float(tick_seed.get("price_delta_min_pct", 0.0005))
        self._price_delta_max_pct = float(tick_seed.get("price_delta_max_pct", 0.0015))
        self._chart_delta_min_pct = float(tick_seed.get("chart_delta_min_pct", 0.0003))
        self._chart_delta_max_pct = float(tick_seed.get("chart_delta_max_pct", 0.0007))
        self._book_price_tick_ratio = float(tick_seed.get("book_price_tick_ratio", 0.0001))
        cards_seed = _SEED_DATA.get("opportunity_exchange_cards", {})
        self._opportunity_exchange_cards = cards_seed if isinstance(cards_seed, dict) else {}
        strategy_seed = _SEED_DATA.get("strategy_rows", [])
        strategy_seed_list = strategy_seed if isinstance(strategy_seed, list) else []
        self._opportunity_row_templates = MockStrategyCalculator.build_opportunity_templates(
            [row for row in strategy_seed_list if isinstance(row, dict)]
        )
        _opp_params = _SEED_DATA.get("opportunity_params")
        _opp_vol = _opp_params.get("accumulated_volume_usdt", 320.0) if isinstance(_opp_params, dict) else 320.0
        self._opportunity_reference_volume_usdt = float(_opp_vol) if isinstance(_opp_vol, (int, float)) else 320.0
        self._screener_strategy_calibrations = self._build_screener_strategy_calibrations()
        self._chart_series = self._build_chart_series()
        self._books = self._build_books()
        self._tick_counter = 0
        focus_seed = _SEED_DATA.get("default_opportunity_focus", {})
        if isinstance(focus_seed, dict):
            self._default_opportunity = OpportunityFocusDto(
                symbol=str(focus_seed.get("symbol", "")),
                short_exchange_id=str(focus_seed.get("short_exchange_id", "")),
                long_exchange_id=str(focus_seed.get("long_exchange_id", "")),
            )
        else:
            self._default_opportunity = OpportunityFocusDto(
                symbol="",
                short_exchange_id="",
                long_exchange_id="",
            )

    def _build_screener_strategy_calibrations(self) -> dict[str, MockScreenerStrategyCalibration]:
        seed_raw = _SEED_DATA.get("screener_rows", [])
        if not isinstance(seed_raw, list):
            return {}
        calibrations: dict[str, MockScreenerStrategyCalibration] = {}
        for row_data in seed_raw:
            if not isinstance(row_data, dict):
                continue
            asset = str(row_data.get("asset", ""))
            if not asset:
                continue
            base_profits = StrategyProfitsDto.model_validate(row_data.get("strategy_profits", {}))
            prices_data = row_data.get("prices", {})
            if not isinstance(prices_data, dict):
                continue
            prices = self._mock_prices_from_seed(prices_data)
            short_ex = str(row_data.get("short_exchange_id", ""))
            long_ex = str(row_data.get("long_exchange_id", ""))
            calibrations[asset] = MockStrategyCalculator.build_screener_calibration(
                prices,
                short_ex,
                long_ex,
                base_profits,
            )
        return calibrations

    @staticmethod
    def _mock_prices_from_seed(prices_data: dict[str, object]) -> dict[str, MockExchangePrices]:
        prices: dict[str, MockExchangePrices] = {}
        for exchange_id, price_values in prices_data.items():
            if not isinstance(exchange_id, str) or not isinstance(price_values, dict):
                continue
            prices[exchange_id] = MockExchangePrices(
                futures=float(price_values.get("futures", 0.0)),
                spot=float(price_values.get("spot", 0.0)),
            )
        return prices

    @staticmethod
    def _mutable_prices_to_mock(
        prices: dict[str, _MutablePrices],
    ) -> dict[str, MockExchangePrices]:
        return {
            exchange_id: MockExchangePrices(futures=p.futures, spot=p.spot)
            for exchange_id, p in prices.items()
        }

    def _prices_for_asset(self, symbol: str) -> dict[str, MockExchangePrices] | None:
        for row in self._screener_rows:
            if row.asset == symbol:
                return self._mutable_prices_to_mock(row.prices)
        return None

    def _build_order_groups(self) -> list[OrderGroupDto]:
        groups_seed = _SEED_DATA.get("order_groups", [])
        if not isinstance(groups_seed, list):
            return []
        return [
            OrderGroupDto.model_validate(group_data)
            for group_data in groups_seed
            if isinstance(group_data, dict)
        ]

    def _build_chart_series(self) -> list[_MutableChartSeries]:
        now_ms = 0
        bases_seed = _SEED_DATA.get("chart_series", [])
        if not isinstance(bases_seed, list):
            return []
        series: list[_MutableChartSeries] = []
        for series_seed in bases_seed:
            if not isinstance(series_seed, dict):
                continue
            base = float(series_seed.get("last_price", 0.0))
            points = [
                ChartPointDto(t=now_ms - (self._chart_max_points - i), price=base)
                for i in range(self._chart_max_points)
            ]
            series.append(
                _MutableChartSeries(
                    key=str(series_seed.get("key", "")),
                    label=str(series_seed.get("label", "")),
                    exchange_id=str(series_seed.get("exchange_id", "")),
                    market_type=str(series_seed.get("market_type", "futures")),  # type: ignore[arg-type]
                    color=str(series_seed.get("color", "#000000")),
                    dashed=bool(series_seed.get("dashed", False)),
                    last_price=base,
                    points=points,
                )
            )
        return series

    def _build_books(self) -> list[_MutableBook]:
        books_seed = _SEED_DATA.get("books", [])
        if not isinstance(books_seed, list):
            return []
        books: list[_MutableBook] = []
        for book_seed in books_seed:
            if not isinstance(book_seed, dict):
                continue
            asks_seed = book_seed.get("asks", [])
            bids_seed = book_seed.get("bids", [])
            if not isinstance(asks_seed, list) or not isinstance(bids_seed, list):
                continue
            asks = [
                _MutableBookLevel(price=float(level.get("price", 0.0)), amount=float(level.get("amount", 0.0)))
                for level in asks_seed
                if isinstance(level, dict)
            ]
            bids = [
                _MutableBookLevel(price=float(level.get("price", 0.0)), amount=float(level.get("amount", 0.0)))
                for level in bids_seed
                if isinstance(level, dict)
            ]
            books.append(
                _MutableBook(
                    exchange_id=str(book_seed.get("exchange_id", "")),
                    market_type=str(book_seed.get("market_type", "futures")),  # type: ignore[arg-type]
                    side_role=str(book_seed.get("side_role", "short")),  # type: ignore[arg-type]
                    volume_24h_label=str(book_seed.get("volume_24h_label", "")),
                    range_label=str(book_seed.get("range_label", "")),
                    asks=asks,
                    bids=bids,
                )
            )
        return books

    def tick(self) -> None:
        self._tick_counter += 1
        if self._reconnect_pending and self._tick_counter % 2 == 0:
            self._screener_status = "filtered"
            self._reconnect_pending = False

        for row in self._screener_rows:
            for prices in row.prices.values():
                for field in ("futures", "spot"):
                    current = getattr(prices, field)
                    delta = current * random.uniform(self._price_delta_min_pct, self._price_delta_max_pct) * random.choice([-1.0, 1.0])
                    setattr(prices, field, max(current + delta, 0.0001))

        for series in self._chart_series:
            delta = series.last_price * random.uniform(self._chart_delta_min_pct, self._chart_delta_max_pct) * random.choice([-1.0, 1.0])
            series.last_price = max(series.last_price + delta, 0.0001)
            next_t = series.points[-1].t + 1 if series.points else self._tick_counter
            series.points.append(ChartPointDto(t=next_t, price=series.last_price))
            if len(series.points) > self._chart_max_points:
                series.points = series.points[-self._chart_max_points:]

        for book in self._books:
            tick = book.asks[0].price * self._book_price_tick_ratio
            for level in book.asks:
                level.price += tick * random.choice([-1.0, 1.0])
                level.amount = max(level.amount * random.uniform(0.92, 1.08), 1.0)
            for level in book.bids:
                level.price += tick * random.choice([-1.0, 1.0])
                level.amount = max(level.amount * random.uniform(0.92, 1.08), 1.0)

        if self._funding_countdown_sec > 0:
            self._funding_countdown_sec -= 1
        else:
            self._funding_countdown_sec = self._funding_reset_seconds

    def apply_screener_filters(
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

    def screener_reconnect(self, stream_min_volume_usdt: float) -> None:
        self._filters = ScreenerFiltersDto(
            min_volume_k_usdt=self._filters.min_volume_k_usdt,
            stream_min_volume_usdt=stream_min_volume_usdt,
            min_spread_pct=self._filters.min_spread_pct,
        )
        self._screener_status = "connecting"
        self._reconnect_pending = True

    def apply_opportunity_params(
        self,
        active_strategy_id: str,
        target_volume_usdt: float,
        open_spread_threshold_pct: float,
        close_spread_threshold_pct: float,
        accumulate_volume_usdt: float,
        accumulate_volume_pct: float,
        close_volume_usdt: float,
        close_volume_pct: float,
        auto_accumulate_enabled: bool,
        auto_close_enabled: bool,
    ) -> None:
        self._opportunity_params = OpportunityParamsDto(
            active_strategy_id=active_strategy_id,
            accumulated_volume_usdt=self._opportunity_params.accumulated_volume_usdt,
            target_volume_usdt=target_volume_usdt,
            open_spread_threshold_pct=open_spread_threshold_pct,
            close_spread_threshold_pct=close_spread_threshold_pct,
            accumulate_volume_usdt=accumulate_volume_usdt,
            accumulate_volume_pct=accumulate_volume_pct,
            close_volume_usdt=close_volume_usdt,
            close_volume_pct=close_volume_pct,
            auto_accumulate_enabled=auto_accumulate_enabled,
            auto_close_enabled=auto_close_enabled,
            volume_pct_presets=list(self._opportunity_params.volume_pct_presets),
        )

    def set_leverage(self, exchange_id: str, leverage: int) -> None:
        self._leverage[exchange_id] = leverage

    def accumulate(self, volume_usdt: float) -> None:
        self._opportunity_params = OpportunityParamsDto(
            active_strategy_id=self._opportunity_params.active_strategy_id,
            accumulated_volume_usdt=self._opportunity_params.accumulated_volume_usdt + volume_usdt,
            target_volume_usdt=self._opportunity_params.target_volume_usdt,
            open_spread_threshold_pct=self._opportunity_params.open_spread_threshold_pct,
            close_spread_threshold_pct=self._opportunity_params.close_spread_threshold_pct,
            accumulate_volume_usdt=self._opportunity_params.accumulate_volume_usdt,
            accumulate_volume_pct=self._opportunity_params.accumulate_volume_pct,
            close_volume_usdt=self._opportunity_params.close_volume_usdt,
            close_volume_pct=self._opportunity_params.close_volume_pct,
            auto_accumulate_enabled=self._opportunity_params.auto_accumulate_enabled,
            auto_close_enabled=self._opportunity_params.auto_close_enabled,
            volume_pct_presets=list(self._opportunity_params.volume_pct_presets),
        )

    def close_partial(self, volume_usdt: float) -> None:
        new_vol = max(0.0, self._opportunity_params.accumulated_volume_usdt - volume_usdt)
        self._opportunity_params = OpportunityParamsDto(
            active_strategy_id=self._opportunity_params.active_strategy_id,
            accumulated_volume_usdt=new_vol,
            target_volume_usdt=self._opportunity_params.target_volume_usdt,
            open_spread_threshold_pct=self._opportunity_params.open_spread_threshold_pct,
            close_spread_threshold_pct=self._opportunity_params.close_spread_threshold_pct,
            accumulate_volume_usdt=self._opportunity_params.accumulate_volume_usdt,
            accumulate_volume_pct=self._opportunity_params.accumulate_volume_pct,
            close_volume_usdt=self._opportunity_params.close_volume_usdt,
            close_volume_pct=self._opportunity_params.close_volume_pct,
            auto_accumulate_enabled=self._opportunity_params.auto_accumulate_enabled,
            auto_close_enabled=self._opportunity_params.auto_close_enabled,
            volume_pct_presets=list(self._opportunity_params.volume_pct_presets),
        )

    def close_all(self) -> None:
        self._opportunity_params = OpportunityParamsDto(
            active_strategy_id=self._opportunity_params.active_strategy_id,
            accumulated_volume_usdt=0.0,
            target_volume_usdt=self._opportunity_params.target_volume_usdt,
            open_spread_threshold_pct=self._opportunity_params.open_spread_threshold_pct,
            close_spread_threshold_pct=self._opportunity_params.close_spread_threshold_pct,
            accumulate_volume_usdt=self._opportunity_params.accumulate_volume_usdt,
            accumulate_volume_pct=self._opportunity_params.accumulate_volume_pct,
            close_volume_usdt=self._opportunity_params.close_volume_usdt,
            close_volume_pct=self._opportunity_params.close_volume_pct,
            auto_accumulate_enabled=self._opportunity_params.auto_accumulate_enabled,
            auto_close_enabled=self._opportunity_params.auto_close_enabled,
            volume_pct_presets=list(self._opportunity_params.volume_pct_presets),
        )

    def set_orders_filter(self, filter_value: Literal["all", "open", "closed"]) -> None:
        self._orders_filter = filter_value

    def save_exchange(
        self,
        exchange_id: str,
        api_key: str,
        api_secret: str,
        api_password: str,
    ) -> None:
        masked = api_key[:4] + "••••" if len(api_key) > 4 else _MASKED_KEY
        updated: list[SettingsExchangeDto] = []
        for ex in self._settings_exchanges:
            if ex.exchange_id == exchange_id:
                updated.append(
                    SettingsExchangeDto(
                        exchange_id=exchange_id,
                        api_key_masked=masked,
                        configured=True,
                        has_secret=bool(api_secret),
                        has_password=bool(api_password),
                    )
                )
            else:
                updated.append(ex)
        self._settings_exchanges = updated

    def screener_snapshot(self) -> ScreenerSnapshotDto:
        from datetime import UTC, datetime

        rows: list[ScreenerRowDto] = []
        stream_min_usdt = self._filters.stream_min_volume_usdt
        for row in self._screener_rows:
            if self._screener_status != "connecting" and row.volume_k_usdt * 1000.0 < stream_min_usdt:
                continue
            fut_prices = [p.futures for p in row.prices.values()]
            max_price = max(fut_prices)
            min_price = min(fut_prices)
            spread_pct = (max_price - min_price) / min_price * 100.0 if min_price > 0 else 0.0
            spread_delta = spread_pct - row.prev_spread_pct
            row.prev_spread_pct = spread_pct
            if self._screener_status == "connecting":
                continue
            mock_prices = self._mutable_prices_to_mock(row.prices)
            calibration = self._screener_strategy_calibrations.get(row.asset)
            if calibration is None:
                strategy_profits = StrategyProfitsDto(
                    futures_futures=None,
                    futures_spot_2ex=None,
                    futures_spot_1ex=None,
                    funding_ff=None,
                    funding_fs=None,
                    funding_diff_dates=None,
                )
            else:
                strategy_profits = MockStrategyCalculator.screener_profits(
                    mock_prices,
                    row.short_exchange_id,
                    row.long_exchange_id,
                    calibration,
                )
            rows.append(
                ScreenerRowDto(
                    asset=row.asset,
                    prices={
                        ex: ExchangePricesDto(futures=p.futures, spot=p.spot)
                        for ex, p in row.prices.items()
                    },
                    max_price=max_price,
                    min_price=min_price,
                    spread_pct=round(spread_pct, 2),
                    spread_delta=round(spread_delta, 2),
                    volume_k_usdt=row.volume_k_usdt,
                    strategy_profits=strategy_profits,
                    short_exchange_id=row.short_exchange_id,
                    long_exchange_id=row.long_exchange_id,
                )
            )
        default_opportunity = self._default_opportunity
        if rows:
            top = rows[0]
            default_opportunity = OpportunityFocusDto(
                symbol=top.asset,
                short_exchange_id=top.short_exchange_id,
                long_exchange_id=top.long_exchange_id,
            )
        return ScreenerSnapshotDto(
            status=self._screener_status,
            symbol_count=len(self._screener_rows),
            exchanges=self._exchanges,
            filters=self._filters,
            updated_at=datetime.now(tz=UTC),
            rows=rows,
            default_opportunity=default_opportunity,
        )

    def opportunity_snapshot(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
    ) -> OpportunitySnapshotDto:
        short_seed = self._opportunity_exchange_cards.get(short_ex, {})
        long_seed = self._opportunity_exchange_cards.get(long_ex, {})
        if not isinstance(short_seed, dict):
            short_seed = {}
        if not isinstance(long_seed, dict):
            long_seed = {}
        cards = [
            self._exchange_card(short_ex, "short", symbol, short_seed),
            self._exchange_card(long_ex, "long", symbol, long_seed),
        ]
        strategy_rows = self._strategy_rows(symbol=symbol, short_ex=short_ex, long_ex=long_ex)
        books = self._books_for_pair(short_ex, long_ex)
        chart = ChartSnapshotDto(
            window_seconds=self._chart_window_seconds,
            series=[
                ChartSeriesDto(
                    key=s.key,
                    label=s.label,
                    exchange_id=s.exchange_id,
                    market_type=s.market_type,
                    color=s.color,
                    dashed=s.dashed,
                    last_price=s.last_price,
                    points=list(s.points),
                )
                for s in self._chart_series
                if s.exchange_id in {short_ex, long_ex}
            ],
        )
        symbol_orders = [g for g in self._order_groups if g.asset == symbol]
        return OpportunitySnapshotDto(
            symbol=symbol,
            short_exchange_id=short_ex,
            long_exchange_id=long_ex,
            exchange_cards=cards,
            strategy_rows=strategy_rows,
            books=books,
            chart=chart,
            params=self._opportunity_params,
            orders=symbol_orders,
            status="streaming",
        )

    def _books_for_pair(self, short_ex: str, long_ex: str) -> list[OrderBookPanelDto]:
        specs: list[tuple[str, Literal["futures", "spot"], Literal["short", "long"]]] = [
            (short_ex, "futures", "short"),
            (short_ex, "spot", "short"),
            (long_ex, "futures", "long"),
            (long_ex, "spot", "long"),
        ]
        panels: list[OrderBookPanelDto] = []
        for exchange_id, market_type, side_role in specs:
            book = next(
                (
                    candidate
                    for candidate in self._books
                    if candidate.exchange_id == exchange_id and candidate.market_type == market_type
                ),
                None,
            )
            if book is None:
                panels.append(
                    OrderBookPanelDto(
                        exchange_id=exchange_id,
                        market_type=market_type,
                        side_role=side_role,
                        volume_24h_label="—",
                        range_label="—",
                        spread_pct=0.0,
                        mid_price=0.0,
                        asks=[],
                        bids=[],
                    )
                )
            else:
                dto = self._book_to_dto(book)
                panels.append(
                    OrderBookPanelDto(
                        exchange_id=dto.exchange_id,
                        market_type=dto.market_type,
                        side_role=side_role,
                        volume_24h_label=dto.volume_24h_label,
                        range_label=dto.range_label,
                        spread_pct=dto.spread_pct,
                        mid_price=dto.mid_price,
                        asks=dto.asks,
                        bids=dto.bids,
                    )
                )
        return panels

    def _exchange_card(
        self,
        exchange_id: str,
        side: Literal["short", "long"],
        symbol: str,
        seed: dict[str, object],
    ) -> ExchangeInfoCardDto:
        market_info = self._mock_market_info(symbol, seed)
        return ExchangeInfoCardDto(
            exchange_id=exchange_id,
            side=side,
            base_asset=market_info.base_asset,
            market_symbol=market_info.unified_symbol,
            native_market_id=market_info.native_market_id,
            min_order_volume_usdt=market_info.min_order_volume_usdt,
            max_order_volume_usdt=market_info.max_order_volume_usdt,
            spot_min_order_volume_usdt=self._spot_volume(seed, "min"),
            spot_max_order_volume_usdt=self._spot_volume(seed, "max"),
            balance_usdt=float(bal) if isinstance(bal := seed.get("balance_usdt", 0.0), (int, float)) else 0.0,
            funding_rate_pct=float(fr) if isinstance(fr := seed.get("funding_rate_pct", 0.0), (int, float)) else 0.0,
            funding_countdown_sec=self._funding_countdown_sec,
            leverage=self._leverage.get(exchange_id, 10),
            futures_fee=str(seed.get("futures_fee", "")),
            spot_fee=str(seed.get("spot_fee", "")),
            open_orders_count=int(oo) if isinstance(oo := seed.get("open_orders_count", 0), (int, float)) else 0,
            closed_orders_count=int(co) if isinstance(co := seed.get("closed_orders_count", 0), (int, float)) else 0,
        )

    @staticmethod
    def _spot_volume(seed: dict[str, object], side: str) -> float | None:
        key = f"spot_{side}_order_volume_usdt"
        raw = seed.get(key)
        if isinstance(raw, (int, float)):
            return float(raw)
        return None

    @staticmethod
    def _mock_market_info(
        symbol: str,
        seed: dict[str, object],
    ) -> SymbolMarketInfo:
        swap_symbol = SymbolNormalizer.to_swap_symbol(symbol)
        base_asset = SymbolNormalizer.base_asset(symbol)
        native_ids = seed.get("native_market_ids")
        native_id: str | None = None
        if isinstance(native_ids, dict):
            raw = native_ids.get(base_asset)
            if isinstance(raw, str) and raw:
                native_id = raw
        if native_id is None:
            fallback = seed.get("native_market_id")
            if isinstance(fallback, str) and fallback:
                native_id = fallback
        min_raw = seed.get("min_order_volume_usdt")
        max_raw = seed.get("max_order_volume_usdt")
        min_vol = float(min_raw) if isinstance(min_raw, (int, float)) else None
        max_vol = float(max_raw) if isinstance(max_raw, (int, float)) else None
        return SymbolMarketInfo(
            unified_symbol=swap_symbol,
            base_asset=base_asset,
            native_market_id=native_id,
            min_order_volume_usdt=min_vol,
            max_order_volume_usdt=max_vol,
        )

    def _strategy_rows(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
    ) -> list[StrategyCalculationRowDto]:
        volume = self._opportunity_params.accumulated_volume_usdt
        leverage = min(self._leverage.get(short_ex, 10), self._leverage.get(long_ex, 10))
        prices = self._prices_for_asset(symbol)
        if prices is None:
            prices = self._prices_from_chart(short_ex, long_ex)
        if not prices:
            return []
        return MockStrategyCalculator.opportunity_rows(
            prices,
            short_ex,
            long_ex,
            volume,
            leverage,
            self._opportunity_reference_volume_usdt,
            self._opportunity_row_templates,
        )

    def _prices_from_chart(
        self,
        short_ex: str,
        long_ex: str,
    ) -> dict[str, MockExchangePrices]:
        prices: dict[str, MockExchangePrices] = {}
        for series in self._chart_series:
            existing = prices.get(series.exchange_id)
            if series.market_type == "futures":
                if existing is None:
                    prices[series.exchange_id] = MockExchangePrices(
                        futures=series.last_price,
                        spot=series.last_price,
                    )
                else:
                    prices[series.exchange_id] = MockExchangePrices(
                        futures=series.last_price,
                        spot=existing.spot,
                    )
            elif existing is None:
                prices[series.exchange_id] = MockExchangePrices(
                    futures=series.last_price,
                    spot=series.last_price,
                )
            else:
                prices[series.exchange_id] = MockExchangePrices(
                    futures=existing.futures,
                    spot=series.last_price,
                )
        return {
            exchange_id: price
            for exchange_id, price in prices.items()
            if exchange_id in {short_ex, long_ex}
        }

    @staticmethod
    def _book_to_dto(book: _MutableBook) -> OrderBookPanelDto:
        def levels_to_dto(
            levels: list[_MutableBookLevel],
            side: Literal["ask", "bid"],
        ) -> list[OrderBookLevelDto]:
            if not levels:
                return []
            if side == "ask":
                touch_first = sorted(levels, key=lambda level: level.price)
            else:
                touch_first = sorted(levels, key=lambda level: level.price, reverse=True)
            staged: list[tuple[_MutableBookLevel, float]] = []
            running = 0.0
            for level in touch_first:
                running += level.amount
                staged.append((level, running))
            max_total = max((total for _, total in staged), default=1.0)
            if max_total <= 0.0:
                max_total = 1.0
            rows = [
                OrderBookLevelDto(
                    price=round(level.price, 6),
                    amount=level.amount,
                    total=round(total, 2),
                    fill_pct=round(100.0 * total / max_total, 1),
                    amount_fill_pct=round(100.0 * level.amount / max_total, 1),
                )
                for level, total in staged
            ]
            return sorted(rows, key=lambda row: row.price, reverse=True)

        best_ask = min((level.price for level in book.asks), default=0.0)
        best_bid = max((level.price for level in book.bids), default=0.0)
        mid = (best_ask + best_bid) / 2.0 if best_ask and best_bid else 0.0
        spread_pct = (best_ask - best_bid) / mid * 100.0 if mid > 0 else 0.0
        return OrderBookPanelDto(
            exchange_id=book.exchange_id,
            market_type=book.market_type,
            side_role=book.side_role,
            volume_24h_label=book.volume_24h_label,
            range_label=book.range_label,
            spread_pct=round(spread_pct, 3),
            mid_price=round(mid, 6),
            asks=levels_to_dto(book.asks, "ask"),
            bids=levels_to_dto(book.bids, "bid"),
        )

    def orders_summary(self) -> OrdersSummaryDto:
        open_count = sum(1 for g in self._order_groups if g.status == "open")
        closed_count = sum(1 for g in self._order_groups if g.status == "closed")
        return OrdersSummaryDto(open_count=open_count, closed_count=closed_count)

    def orders_snapshot(self) -> OrdersSnapshotDto:
        summary = self.orders_summary()
        groups = self._order_groups
        if self._orders_filter == "open":
            groups = [g for g in groups if g.status == "open"]
        elif self._orders_filter == "closed":
            groups = [g for g in groups if g.status == "closed"]
        return OrdersSnapshotDto(summary=summary, filter=self._orders_filter, groups=groups)

    def settings_snapshot(self) -> SettingsSnapshotDto:
        return SettingsSnapshotDto(exchanges=list(self._settings_exchanges))
