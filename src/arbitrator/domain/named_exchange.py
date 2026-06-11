from __future__ import annotations

from dataclasses import dataclass

from arbitrator.domain.exchange_gateway import ExchangeGateway


@dataclass(frozen=True, slots=True)
class NamedExchange:
    """Pairs a canonical exchange id and human-readable name with its gateway."""

    exchange_id: str
    display_name: str
    gateway: ExchangeGateway
