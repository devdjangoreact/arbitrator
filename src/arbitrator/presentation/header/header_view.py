from __future__ import annotations

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from arbitrator.presentation.nav_section import NavSection


class HeaderView:
    """Renders the top header: app title, current section and a live status slot."""

    def __init__(self, app_title: str) -> None:
        self._app_title = app_title
        self._status_slot: DeltaGenerator | None = None

    def render(self, section: NavSection) -> None:
        title_col, section_col, status_col = st.columns([3, 3, 2])
        with title_col:
            st.markdown(f"#### {self._app_title}")
        with section_col:
            st.markdown(f"#### {section.value}")
        with status_col:
            self._status_slot = st.empty()
        st.divider()
        self.set_status("—")

    def set_status(self, status: str) -> None:
        if self._status_slot is None:
            return
        self._status_slot.markdown(f"#### Status: {status}")
