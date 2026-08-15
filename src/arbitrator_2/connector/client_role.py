from __future__ import annotations

from enum import StrEnum


class ClientRole(StrEnum):
    BOOK = "book"
    TRADES = "trades"
    META = "meta"
