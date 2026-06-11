from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
from streamlit.delta_generator import DeltaGenerator

from arbitrator.domain.named_exchange import NamedExchange
from arbitrator.domain.ticker import Ticker
from arbitrator.presentation.sidebar.screener.screener_filters import ScreenerFilters


class PriceTableView:
    """Renders a live cross-exchange price table.

    Each per-exchange cell is a 3-line block::

        last
        high-low
        volume(K USDT)

    Trailing summary columns: Max/Min/Spread%/Δ — computed from the per-exchange
    last prices (not from cell strings).
    """

    _MAX_COLUMN = "Max"
    _MIN_COLUMN = "Min"
    _SPREAD_COLUMN = "Spread %"
    _DELTA_COLUMN = "Δ"
    _VOLUME_COLUMN = "Vol K USDT"
    _EMPTY_CELL = "—"
    _CELL_ROW_HEIGHT_PX = 76

    def __init__(self, exchanges: Sequence[NamedExchange]) -> None:
        self._exchanges = list(exchanges)
        self._exchange_columns: list[str] = [e.display_name for e in self._exchanges]
        self._column_order: list[str] = [
            *self._exchange_columns,
            self._MAX_COLUMN,
            self._MIN_COLUMN,
            self._SPREAD_COLUMN,
            self._DELTA_COLUMN,
            self._VOLUME_COLUMN,
        ]

    def render(
        self,
        container: DeltaGenerator,
        snapshot: dict[tuple[str, str], Ticker],
        symbols: Sequence[str],
        filters: ScreenerFilters,
    ) -> None:
        df = self._build_dataframe(snapshot, symbols, filters)
        container.dataframe(df, width="stretch", row_height=self._CELL_ROW_HEIGHT_PX)

    def _build_dataframe(
        self,
        snapshot: dict[tuple[str, str], Ticker],
        symbols: Sequence[str],
        filters: ScreenerFilters,
    ) -> pd.DataFrame:
        rows: list[dict[str, object]] = []
        index: list[str] = []

        for symbol in symbols:
            row, base, last_prices, spread_pct, max_volume_kusdt = self._build_row(symbol, snapshot)
            if not self._passes(filters, last_prices, spread_pct, max_volume_kusdt):
                continue
            row[self._VOLUME_COLUMN] = max_volume_kusdt
            rows.append(row)
            index.append(base)

        df = pd.DataFrame(rows, index=index, columns=self._column_order)
        df.index.name = "Asset"
        return df

    def _build_row(
        self,
        symbol: str,
        snapshot: dict[tuple[str, str], Ticker],
    ) -> tuple[dict[str, object], str, list[float], float | None, float | None]:
        row: dict[str, object] = {}
        last_prices: list[float] = []
        max_volume_kusdt: float | None = None
        base_label = symbol.split("/")[0]

        for exch in self._exchanges:
            ticker = snapshot.get((exch.exchange_id, symbol))
            row[exch.display_name] = self._format_cell(ticker)
            if ticker is None:
                continue
            if ticker.last is not None:
                last_prices.append(ticker.last)
            if ticker.base_asset:
                base_label = ticker.base_asset
            volume_kusdt = self._volume_kusdt(ticker)
            if volume_kusdt is not None:
                max_volume_kusdt = (
                    volume_kusdt
                    if max_volume_kusdt is None
                    else max(max_volume_kusdt, volume_kusdt)
                )

        max_price = max(last_prices) if last_prices else None
        min_price = min(last_prices) if last_prices else None
        delta: float | None = None
        spread_pct: float | None = None
        if max_price is not None and min_price is not None:
            delta = max_price - min_price
            if min_price != 0.0:
                spread_pct = delta / min_price * 100.0

        row[self._MAX_COLUMN] = max_price
        row[self._MIN_COLUMN] = min_price
        row[self._SPREAD_COLUMN] = spread_pct
        row[self._DELTA_COLUMN] = delta
        return row, base_label, last_prices, spread_pct, max_volume_kusdt

    @classmethod
    def _format_cell(cls, ticker: Ticker | None) -> str:
        if ticker is None:
            return f"{cls._EMPTY_CELL}\n{cls._EMPTY_CELL}\n{cls._EMPTY_CELL}"
        last = cls._fmt_price(ticker.last)
        if ticker.high_24h is not None and ticker.low_24h is not None:
            high_low = f"{cls._fmt_price(ticker.high_24h)}-{cls._fmt_price(ticker.low_24h)}"
        else:
            high_low = cls._EMPTY_CELL
        volume = cls._volume_kusdt(ticker)
        volume_str = f"{volume:,.0f}" if volume is not None else cls._EMPTY_CELL
        return f"{last}\n{high_low}\n{volume_str}"

    @staticmethod
    def _volume_kusdt(ticker: Ticker) -> float | None:
        if ticker.quote_volume_24h is None:
            return None
        return ticker.quote_volume_24h / 1000.0

    @staticmethod
    def _fmt_price(value: float | None) -> str:
        if value is None:
            return PriceTableView._EMPTY_CELL
        if abs(value) >= 1000:
            return f"{value:,.2f}"
        if abs(value) >= 1:
            return f"{value:,.4f}"
        return f"{value:,.6f}"

    @staticmethod
    def _passes(
        filters: ScreenerFilters,
        last_prices: Sequence[float],
        spread_pct: float | None,
        max_volume_kusdt: float | None,
    ) -> bool:
        if not last_prices:
            return False
        if filters.min_spread_pct > 0.0 and (
            spread_pct is None or spread_pct < filters.min_spread_pct
        ):
            return False
        return not (
            filters.min_quote_volume_kusdt > 0.0
            and (max_volume_kusdt is None or max_volume_kusdt < filters.min_quote_volume_kusdt)
        )
