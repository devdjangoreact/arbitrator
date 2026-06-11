from __future__ import annotations

from enum import StrEnum


class NavSection(StrEnum):
    """Identifies a top-level section selectable from the sidebar."""

    SCREENER = "Screener"
    OPEN_ORDERS = "Open orders"
    CLOSED_ORDERS = "Closed orders"
    SETTINGS = "Settings"
