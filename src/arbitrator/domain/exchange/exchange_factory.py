from __future__ import annotations

from typing import Protocol

from arbitrator.domain.exchange.named_exchange import NamedExchange


class ExchangeFactory(Protocol):
    """Creates exchange gateways by canonical id."""

    def display_name(self, exchange_id: str) -> str:
        ...

    def create(self, exchange_id: str) -> NamedExchange:
        ...
