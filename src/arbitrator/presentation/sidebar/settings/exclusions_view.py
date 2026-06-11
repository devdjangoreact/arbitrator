from __future__ import annotations

import streamlit as st

from arbitrator.domain.symbol_exclusions_repository import SymbolExclusionsRepository
from arbitrator.domain.symbol_universe_repository import SymbolUniverseRepository


class ExclusionsView:
    """UI for managing the persisted set of excluded symbols."""

    _ADD_INPUT_KEY = "exclusions_add_input"
    _PICKER_KEY = "exclusions_picker"

    def __init__(
        self,
        exclusions_repo: SymbolExclusionsRepository,
        universe_repo: SymbolUniverseRepository,
    ) -> None:
        self._exclusions = exclusions_repo
        self._universe = universe_repo

    def render(self) -> None:
        st.subheader("Excluded symbols")
        st.caption("Symbols listed here will be removed from the screener.")

        excluded = sorted(self._exclusions.load())
        self._render_picker(excluded)
        self._render_manual_input()
        self._render_list(excluded)

    def _render_picker(self, excluded: list[str]) -> None:
        snapshot = self._universe.load()
        if snapshot is None:
            st.info("Symbol universe cache is empty. Open the Screener once to populate it.")
            return

        all_symbols = sorted(snapshot.all_symbols())
        candidates = [s for s in all_symbols if s not in excluded]
        if not candidates:
            return

        col_pick, col_btn = st.columns([4, 1])
        with col_pick:
            chosen = st.selectbox(
                label="Pick a symbol to exclude",
                options=candidates,
                index=0,
                key=self._PICKER_KEY,
            )
        with col_btn:
            st.write("")
            if st.button("Exclude", key="exclusions_pick_btn") and isinstance(chosen, str):
                self._exclusions.add(chosen)
                st.rerun()

    def _render_manual_input(self) -> None:
        col_input, col_btn = st.columns([4, 1])
        with col_input:
            value = st.text_input(
                "Or type a symbol (e.g. FOO/USDT:USDT)",
                key=self._ADD_INPUT_KEY,
            )
        with col_btn:
            st.write("")
            if (
                st.button("Add", key="exclusions_add_btn")
                and isinstance(value, str)
                and value.strip()
            ):
                self._exclusions.add(value.strip())
                st.rerun()

    def _render_list(self, excluded: list[str]) -> None:
        if not excluded:
            st.caption("No exclusions yet.")
            return
        st.write(f"Current exclusions ({len(excluded)}):")
        for symbol in excluded:
            col_label, col_btn = st.columns([4, 1])
            with col_label:
                st.code(symbol, language=None)
            with col_btn:
                if st.button("Remove", key=f"exclusions_remove_{symbol}"):
                    self._exclusions.remove(symbol)
                    st.rerun()
