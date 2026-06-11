from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True, slots=True)
class ScreenerFilters:
    min_quote_volume_kusdt: float
    min_spread_pct: float


class ScreenerFiltersView:
    """Renders interactive filters above the screener table."""

    _STATE_VOLUME = "screener_min_volume_kusdt"
    _STATE_SPREAD = "screener_min_spread_pct"

    def __init__(self, default_volume_kusdt: float, default_spread_pct: float) -> None:
        self._default_volume = default_volume_kusdt
        self._default_spread = default_spread_pct

    def render(self) -> ScreenerFilters:
        col_vol, col_spread = st.columns(2)
        with col_vol:
            volume = st.number_input(
                "Min 24h volume (K USDT)",
                min_value=0.0,
                value=float(st.session_state.get(self._STATE_VOLUME, self._default_volume)),
                step=100.0,
                key=self._STATE_VOLUME,
            )
        with col_spread:
            spread = st.number_input(
                "Min spread %",
                min_value=0.0,
                value=float(st.session_state.get(self._STATE_SPREAD, self._default_spread)),
                step=0.05,
                key=self._STATE_SPREAD,
            )
        return ScreenerFilters(
            min_quote_volume_kusdt=float(volume),
            min_spread_pct=float(spread),
        )
