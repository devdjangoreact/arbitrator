from __future__ import annotations

import streamlit as st

from arbitrator.presentation.nav_section import NavSection


class SidebarNav:
    """Renders the left sidebar navigation and returns the selected section."""

    _STATE_KEY = "nav_section"

    def render(self) -> NavSection:
        with st.sidebar:
            st.markdown("## Menu")
            options = list(NavSection)
            default_index = 0
            current = st.session_state.get(self._STATE_KEY)
            if isinstance(current, NavSection) and current in options:
                default_index = options.index(current)

            selected = st.radio(
                label="Section",
                options=options,
                format_func=lambda section: section.value,
                index=default_index,
                label_visibility="collapsed",
                key=self._STATE_KEY,
            )

        if not isinstance(selected, NavSection):
            return NavSection.SCREENER
        return selected
