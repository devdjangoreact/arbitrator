from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Literal

from arbitrator.application.account_stream_worker import AccountStreamWorker
from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.opportunity_cache_seeder import OpportunityCacheSeeder
from arbitrator.application.opportunity_session_state import OpportunitySessionState
from arbitrator.application.opportunity_stream_worker import OpportunityStreamState
from arbitrator.application.opportunity_strategy_service import OpportunityStrategyService
from arbitrator.config.settings import Settings
from arbitrator.domain.order_book_level import OrderBookLevel
from arbitrator.domain.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.funding_info import FundingInfo
from arbitrator.domain.strategy.strategy_kind import StrategyKind
from arbitrator.domain.strategy.strategy_result import StrategyResult
from arbitrator.domain.symbol_normalizer import SymbolNormalizer
from arbitrator.domain.ticker import Ticker
from arbitrator.presentation.dto.opportunity_dto import (
    ChartPointDto,
    ChartSeriesDto,
    ChartSnapshotDto,
    ExchangeInfoCardDto,
    OpportunitySnapshotDto,
    OrderBookLevelDto,
    OrderBookPanelDto,
    StrategyCalculationRowDto,
)

_STRATEGY_LABELS: dict[StrategyKind, str] = {
    StrategyKind.futures_futures: "Фючерс-фючерс",
    StrategyKind.futures_spot_2ex: "Фючерс-спот 2 біржі",
    StrategyKind.futures_spot_1ex: "Фючерс-спот 1 біржа",
    StrategyKind.funding_ff: "Фандінг фючерс-фючерс",
    StrategyKind.funding_fs: "Фандінг фючерс-спот",
    StrategyKind.funding_diff_dates: "Фандінг — різні дати списання",
}

_CHART_COLORS: dict[str, str] = {
    "mexc": "#c0392b",
    "bitget": "#8e44ad",
    "gate": "#2980b9",
    "bingx": "#1d9e75",
}


class OpportunitySerializer:
    """Builds ``OpportunitySnapshotDto`` from live workers + strategy service."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._chart_window_seconds = settings.opportunity_chart_window_seconds

    def serialize(
        self,
        *,
        display_symbol: str,
        swap_symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        session: OpportunitySessionState,
        stream_state: OpportunityStreamState,
        strategy_service: OpportunityStrategyService,
        cache: MarketDataCacheMemory | None,
        account_worker: AccountStreamWorker | None,
        now_ms: int,
    ) -> OpportunitySnapshotDto:
        leverage_by_exchange = {
            short_exchange_id: session.leverage_for(short_exchange_id),
            long_exchange_id: session.leverage_for(long_exchange_id),
        }
        if cache is not None:
            OpportunityCacheSeeder.seed(cache, stream_state, swap_symbol, now_ms)
        table = strategy_service.compute(
            symbol=swap_symbol,
            short_exchange_id=short_exchange_id,
            long_exchange_id=long_exchange_id,
            target_volume_usdt=session.target_volume_usdt,
            leverage_by_exchange=leverage_by_exchange,
            now_ms=now_ms,
        )
        accumulated = self._accumulated_volume(
            account_worker,
            swap_symbol,
            {short_exchange_id, long_exchange_id},
        )
        cards = [
            self._exchange_card(
                exchange_id=short_exchange_id,
                side="short",
                display_symbol=display_symbol,
                swap_symbol=swap_symbol,
                session=session,
                cache=cache,
                account_worker=account_worker,
                ticker=stream_state.tickers.get(short_exchange_id),
                now_ms=now_ms,
            ),
            self._exchange_card(
                exchange_id=long_exchange_id,
                side="long",
                display_symbol=display_symbol,
                swap_symbol=swap_symbol,
                session=session,
                cache=cache,
                account_worker=account_worker,
                ticker=stream_state.tickers.get(long_exchange_id),
                now_ms=now_ms,
            ),
        ]
        strategy_rows = [
            self._strategy_row(result, session.target_volume_usdt, leverage_by_exchange)
            for result in table.results.values()
        ]
        books = self._book_panels(
            stream_state=stream_state,
            short_exchange_id=short_exchange_id,
            long_exchange_id=long_exchange_id,
        )
        chart = self._chart(
            stream_state=stream_state,
            short_exchange_id=short_exchange_id,
            long_exchange_id=long_exchange_id,
        )
        return OpportunitySnapshotDto(
            symbol=display_symbol,
            short_exchange_id=short_exchange_id,
            long_exchange_id=long_exchange_id,
            exchange_cards=cards,
            strategy_rows=strategy_rows,
            books=books,
            chart=chart,
            params=session.to_dto(accumulated),
            orders=[],
            status=stream_state.status,
        )

    @staticmethod
    def _accumulated_volume(
        account_worker: AccountStreamWorker | None,
        swap_symbol: str,
        exchange_ids: set[str],
    ) -> float:
        if account_worker is None:
            return 0.0
        total = 0.0
        for leg in account_worker.read_positions(list(exchange_ids)):
            if leg.symbol != swap_symbol:
                continue
            mark = leg.mark_price if leg.mark_price is not None else leg.entry_price
            total += abs(leg.contracts * leg.contract_size * mark)
        return total

    def _exchange_card(
        self,
        *,
        exchange_id: str,
        side: str,
        display_symbol: str,
        swap_symbol: str,
        session: OpportunitySessionState,
        cache: MarketDataCacheMemory | None,
        account_worker: AccountStreamWorker | None,
        ticker: Ticker | None,
        now_ms: int,
    ) -> ExchangeInfoCardDto:
        funding = cache.get_funding(exchange_id, swap_symbol) if cache is not None else None
        fees = cache.get_fees(exchange_id, swap_symbol) if cache is not None else None
        balance = self._balance_usdt(account_worker, exchange_id)
        base_asset = SymbolNormalizer.base_asset(display_symbol)
        market_pair = session.market_info_for(exchange_id)
        futures_info = market_pair.futures if market_pair is not None else None
        spot_info = market_pair.spot if market_pair is not None else None
        return ExchangeInfoCardDto(
            exchange_id=exchange_id,
            side="short" if side == "short" else "long",
            base_asset=base_asset,
            market_symbol=swap_symbol,
            native_market_id=futures_info.native_market_id if futures_info is not None else None,
            min_order_volume_usdt=futures_info.min_order_volume_usdt if futures_info is not None else None,
            max_order_volume_usdt=futures_info.max_order_volume_usdt if futures_info is not None else None,
            spot_min_order_volume_usdt=spot_info.min_order_volume_usdt if spot_info is not None else None,
            spot_max_order_volume_usdt=spot_info.max_order_volume_usdt if spot_info is not None else None,
            balance_usdt=balance,
            funding_rate_pct=self._funding_rate_pct(funding, ticker),
            funding_countdown_sec=self._funding_countdown_sec(funding, now_ms),
            leverage=session.leverage_for(exchange_id),
            futures_fee=self._fee_label(fees, "futures"),
            spot_fee=self._fee_label(fees, "spot"),
            open_orders_count=0,
            closed_orders_count=0,
        )

    @staticmethod
    def _balance_usdt(
        account_worker: AccountStreamWorker | None,
        exchange_id: str,
    ) -> float | None:
        if account_worker is None:
            return None
        statuses = account_worker.read_statuses([exchange_id])
        if not statuses:
            return None
        return statuses[0].usdt_balance

    @staticmethod
    def _funding_rate_pct(
        funding: FundingInfo | None,
        ticker: Ticker | None,
    ) -> float | None:
        if funding is not None and funding.rate is not None:
            return round(float(funding.rate) * 100.0, 3)
        if ticker is not None and ticker.funding_rate is not None:
            return round(float(ticker.funding_rate) * 100.0, 3)
        return None

    @staticmethod
    def _funding_countdown_sec(funding: FundingInfo | None, now_ms: int) -> int | None:
        if funding is None or funding.next_settlement_ms is None:
            return None
        remaining = max(0, funding.next_settlement_ms - now_ms) // 1000
        return int(remaining)

    @staticmethod
    def _fee_label(fees: FeeSchedule | None, market: str) -> str:
        if fees is None:
            return "—"
        if market == "futures":
            maker = fees.futures_maker
            taker = fees.futures_taker
        else:
            maker = fees.spot_maker
            taker = fees.spot_taker
        if maker is None and taker is None:
            return "—"
        maker_pct = f"{float(maker) * 100:.2f}" if maker is not None else "—"
        taker_pct = f"{float(taker) * 100:.2f}" if taker is not None else "—"
        return f"{maker_pct} / {taker_pct}%"

    def _strategy_row(
        self,
        result: StrategyResult,
        target_volume_usdt: float,
        leverage_by_exchange: Mapping[str, int],
    ) -> StrategyCalculationRowDto:
        leverage = min(leverage_by_exchange.values()) if leverage_by_exchange else 1
        if not result.available:
            return StrategyCalculationRowDto(
                strategy_id=result.strategy_id.value,
                strategy_label=_STRATEGY_LABELS[result.strategy_id],
                spread_pct=0.0,
                prices_label="—",
                fees_usdt=0.0,
                funding_usdt=0.0,
                volume_usdt=round(target_volume_usdt, 2),
                leverage=leverage,
                gross_profit_usdt=None,
                costs_usdt=0.0,
                costs_breakdown="—",
                net_profit_usdt=None,
                percent_to_deposit=None,
                unavailable_reason=result.unavailable_reason,
            )
        return StrategyCalculationRowDto(
            strategy_id=result.strategy_id.value,
            strategy_label=_STRATEGY_LABELS[result.strategy_id],
            spread_pct=self._round_float(result.spread_pct),
            prices_label=self._prices_label(result),
            fees_usdt=self._round_float(result.fees_usdt),
            funding_usdt=self._round_float(result.funding_usdt),
            volume_usdt=self._round_float(result.volume_usdt) or round(target_volume_usdt, 2),
            leverage=result.leverage if result.leverage is not None else leverage,
            gross_profit_usdt=self._round_optional(result.gross_profit_usdt),
            costs_usdt=self._round_float(result.costs_usdt),
            costs_breakdown=result.costs_breakdown or "—",
            net_profit_usdt=self._round_optional(result.net_profit_usdt),
            percent_to_deposit=self._round_optional(result.percent_to_deposit),
            unavailable_reason=None,
        )

    @staticmethod
    def _prices_label(result: StrategyResult) -> str:
        if result.price_short is None or result.price_long is None:
            return "—"
        return f"{float(result.price_short):.5f} / {float(result.price_long):.5f}"

    @staticmethod
    def _round_float(value: Decimal | None) -> float:
        if value is None:
            return 0.0
        return round(float(value), 2)

    @staticmethod
    def _round_optional(value: Decimal | None) -> float | None:
        if value is None:
            return None
        return round(float(value), 2)

    def _book_panels(
        self,
        *,
        stream_state: OpportunityStreamState,
        short_exchange_id: str,
        long_exchange_id: str,
    ) -> list[OrderBookPanelDto]:
        specs: list[tuple[str, Literal["futures", "spot"], Literal["short", "long"]]] = [
            (short_exchange_id, "futures", "short"),
            (short_exchange_id, "spot", "short"),
            (long_exchange_id, "futures", "long"),
            (long_exchange_id, "spot", "long"),
        ]
        panels: list[OrderBookPanelDto] = []
        for exchange_id, market_type, side_role in specs:
            book_key = f"{exchange_id}:{market_type}"
            book = stream_state.books.get(book_key)
            ticker = stream_state.tickers.get(exchange_id)
            if book is None:
                panels.append(self._empty_book_panel(exchange_id, market_type, side_role, ticker))
            else:
                panels.append(
                    self._book_panel(
                        book,
                        market_type=market_type,
                        side_role=side_role,
                        ticker=ticker,
                    )
                )
        return panels

    def _empty_book_panel(
        self,
        exchange_id: str,
        market_type: Literal["futures", "spot"],
        side_role: Literal["short", "long"],
        ticker: Ticker | None,
    ) -> OrderBookPanelDto:
        volume_label = "—"
        if ticker is not None and ticker.quote_volume_24h is not None:
            volume_label = f"{int(ticker.quote_volume_24h):,} USDT"
        return OrderBookPanelDto(
            exchange_id=exchange_id,
            market_type=market_type,
            side_role=side_role,
            volume_24h_label=volume_label,
            range_label="—",
            spread_pct=0.0,
            mid_price=0.0,
            asks=[],
            bids=[],
        )

    def _book_panel(
        self,
        book: OrderBookSnapshot,
        *,
        market_type: Literal["futures", "spot"],
        side_role: Literal["short", "long"],
        ticker: Ticker | None,
    ) -> OrderBookPanelDto:
        asks = list(book.asks)
        bids = list(book.bids)
        best_ask = min((level.price for level in asks), default=0.0)
        best_bid = max((level.price for level in bids), default=0.0)
        mid = (best_ask + best_bid) / 2.0 if best_ask and best_bid else 0.0
        spread_pct = (best_ask - best_bid) / mid * 100.0 if mid > 0 else 0.0
        volume_label = "—"
        if ticker is not None and ticker.quote_volume_24h is not None:
            volume_label = f"{int(ticker.quote_volume_24h):,} USDT"
        return OrderBookPanelDto(
            exchange_id=book.exchange_id,
            market_type=market_type,
            side_role=side_role,
            volume_24h_label=volume_label,
            range_label="—",
            spread_pct=round(spread_pct, 3),
            mid_price=round(mid, 6),
            asks=self._levels_to_dto(asks, "ask"),
            bids=self._levels_to_dto(bids, "bid"),
        )

    @staticmethod
    def _levels_to_dto(
        levels: Sequence[OrderBookLevel],
        side: str,
    ) -> list[OrderBookLevelDto]:
        if not levels:
            return []
        if side == "ask":
            touch_first = sorted(levels, key=lambda level: level.price)
        else:
            touch_first = sorted(levels, key=lambda level: level.price, reverse=True)
        staged: list[tuple[OrderBookLevel, float]] = []
        running = 0.0
        for level in touch_first:
            running += level.size
            staged.append((level, running))
        max_total = max((total for _, total in staged), default=1.0)
        if max_total <= 0.0:
            max_total = 1.0
        rows = [
            OrderBookLevelDto(
                price=round(level.price, 6),
                amount=level.size,
                total=round(total, 2),
                fill_pct=round(100.0 * total / max_total, 1),
                amount_fill_pct=round(100.0 * level.size / max_total, 1),
            )
            for level, total in staged
        ]
        return sorted(rows, key=lambda row: row.price, reverse=True)

    def _chart(
        self,
        *,
        stream_state: OpportunityStreamState,
        short_exchange_id: str,
        long_exchange_id: str,
    ) -> ChartSnapshotDto:
        series: list[ChartSeriesDto] = []
        for exchange_id, label_suffix in (
            (short_exchange_id, "S(F)"),
            (long_exchange_id, "L(F)"),
        ):
            points = [
                ChartPointDto(t=ts, price=price)
                for ts, ex, price in stream_state.price_ring
                if ex == exchange_id
            ]
            last_price = stream_state.prices.get(exchange_id, 0.0)
            if not points and last_price > 0.0:
                now_ms = int(time.time() * 1000)
                points = [ChartPointDto(t=now_ms, price=last_price)]
            series.append(
                ChartSeriesDto(
                    key=f"{exchange_id}Fut",
                    label=f"{exchange_id.upper()}({label_suffix})",
                    exchange_id=exchange_id,
                    market_type="futures",
                    color=_CHART_COLORS.get(exchange_id, "#888888"),
                    dashed=False,
                    last_price=last_price,
                    points=points,
                )
            )
        return ChartSnapshotDto(
            window_seconds=self._chart_window_seconds,
            series=series,
        )
