from __future__ import annotations

import streamlit as st

from arbitrator.config.settings import Settings


class SettingsView:
    """Read-only view of the current Settings instance."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def render(self) -> None:
        st.subheader("Settings")
        st.caption("Values loaded from .env and defaults. Read-only.")

        for field_name, value in self._settings.model_dump().items():
            st.text_input(
                label=field_name,
                value=str(value),
                disabled=True,
                key=f"settings_{field_name}",
            )
