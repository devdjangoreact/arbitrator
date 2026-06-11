from __future__ import annotations

import streamlit as st

from arbitrator.application.symbol_universe_service import SymbolUniverseService
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.symbol_exclusions_repository import SymbolExclusionsRepository
from arbitrator.domain.symbol_universe_repository import SymbolUniverseRepository
from arbitrator.exchanges.factory import Factory
from arbitrator.presentation.header.header_view import HeaderView
from arbitrator.presentation.nav_section import NavSection
from arbitrator.presentation.sidebar.closed_orders.closed_orders_view import (
    ClosedOrdersView,
)
from arbitrator.presentation.sidebar.open_orders.open_orders_view import OpenOrdersView
from arbitrator.presentation.sidebar.screener.screener_view import ScreenerView
from arbitrator.presentation.sidebar.settings.exclusions_view import ExclusionsView
from arbitrator.presentation.sidebar.settings.settings_view import SettingsView
from arbitrator.presentation.sidebar.sidebar_nav import SidebarNav


class StreamlitApp:
    def __init__(
        self,
        settings: Settings,
        exclusions_repo: SymbolExclusionsRepository,
        universe_repo: SymbolUniverseRepository,
    ) -> None:
        self._settings = settings
        self._factory = Factory(settings)
        self._sidebar = SidebarNav()
        self._header = HeaderView(app_title=settings.streamlit_page_title)
        self._open_orders = OpenOrdersView()
        self._closed_orders = ClosedOrdersView()
        self._settings_view = SettingsView(settings)
        self._exclusions_view = ExclusionsView(exclusions_repo, universe_repo)
        self._universe_service = SymbolUniverseService(
            repository=universe_repo,
            exclusions=exclusions_repo,
            ttl_hours=settings.universe_ttl_hours,
            min_exchanges=settings.min_exchanges_per_symbol,
        )
        self._screener = ScreenerView(
            settings=settings,
            factory=self._factory,
            universe_service=self._universe_service,
            header=self._header,
        )

    def run(self) -> None:
        st.set_page_config(
            page_title=self._settings.streamlit_page_title,
            layout=self._settings.streamlit_page_layout,  # type: ignore[arg-type]
        )
        self._inject_full_width_css()

        section = self._sidebar.render()
        self._header.render(section)
        body = st.container()

        logger.info("UI run | section={}", section.value)

        if section is NavSection.SCREENER:
            self._screener.render(body)
        elif section is NavSection.OPEN_ORDERS:
            self._header.set_status("Idle")
            with body:
                self._open_orders.render()
        elif section is NavSection.CLOSED_ORDERS:
            self._header.set_status("Idle")
            with body:
                self._closed_orders.render()
        elif section is NavSection.SETTINGS:
            self._header.set_status("Idle")
            with body:
                self._settings_view.render()
                st.divider()
                self._exclusions_view.render()

    @staticmethod
    def _inject_full_width_css() -> None:
        st.markdown(
            """
            <style>
                .block-container {
                    max-width: 100% !important;
                    padding-top: 1.5rem;
                    padding-bottom: 1rem;
                    padding-left: 1.25rem;
                    padding-right: 1.25rem;
                }
                [data-testid="stSidebar"] > div:first-child {
                    padding-top: 1.5rem;
                }
                [data-testid="stHeader"] {
                    background: transparent;
                }
                [data-testid="stDataFrame"], [data-testid="stTable"] {
                    width: 100% !important;
                }
            </style>
            """,
            unsafe_allow_html=True,
        )
