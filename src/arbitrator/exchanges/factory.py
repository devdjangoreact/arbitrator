from __future__ import annotations

from typing import ClassVar

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.named_exchange import NamedExchange
from arbitrator.exchanges.binance import Binance
from arbitrator.exchanges.bingx import Bingx
from arbitrator.exchanges.bitget import Bitget
from arbitrator.exchanges.ccxt_base import CcxtBase
from arbitrator.exchanges.gate import Gate
from arbitrator.exchanges.mexc import Mexc


class Factory:
    """Builds ExchangeGateway implementations by canonical exchange id."""

    _registry: ClassVar[dict[str, type[CcxtBase]]] = {
        Binance.exchange_id: Binance,
        Mexc.exchange_id: Mexc,
        Bitget.exchange_id: Bitget,
        Gate.exchange_id: Gate,
        Bingx.exchange_id: Bingx,
    }

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def supported_ids(self) -> tuple[str, ...]:
        return tuple(self._registry.keys())

    def display_name(self, exchange_id: str) -> str:
        return self._lookup(exchange_id).display_name

    def create(self, exchange_id: str) -> NamedExchange:
        cls = self._lookup(exchange_id)
        return NamedExchange(
            exchange_id=cls.exchange_id,
            display_name=cls.display_name,
            gateway=cls(self._settings),
        )

    def create_many(self, exchange_ids: list[str]) -> list[NamedExchange]:
        return [self.create(eid) for eid in exchange_ids]

    @classmethod
    def _lookup(cls, exchange_id: str) -> type[CcxtBase]:
        try:
            return cls._registry[exchange_id]
        except KeyError as exc:
            logger.error(
                "Unknown exchange id | requested={} supported={}",
                exchange_id,
                list(cls._registry.keys()),
            )
            raise ValueError("unknown exchange id") from exc
