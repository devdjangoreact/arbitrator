from __future__ import annotations

import asyncio

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.account.exchange_account_snapshot import ExchangeAccountSnapshot
from arbitrator.domain.account.open_order_leg import OpenOrderLeg
from arbitrator.domain.account.position_leg import PositionLeg
from arbitrator.domain.exchange.exchange_connection_status import ExchangeConnectionStatus
from arbitrator.domain.market.order_book_snapshot import OrderBookSnapshot
from arbitrator.domain.market.ticker import Ticker
from arbitrator.exchanges.ccxt_base import CcxtBase
from arbitrator.exchanges.factory import Factory


class ReadOnlyExchangeInspector:
    """Read-only exchange probing for agents and ops.

    This class exposes only market/account **read** operations. It never places,
    amends, or cancels orders and never changes leverage or transfers funds.
    """

    def __init__(self, settings: Settings, factory: Factory) -> None:
        self._settings = settings
        self._factory = factory

    def supported_exchange_ids(self) -> tuple[str, ...]:
        return self._factory.supported_ids()

    def enabled_exchange_ids(self) -> tuple[str, ...]:
        return tuple(self._settings.enabled_exchanges)

    async def verify_exchange(self, exchange_id: str) -> ExchangeConnectionStatus:
        gateway = self._open_gateway(exchange_id, mode="private")
        try:
            return await gateway.verify_connection()
        finally:
            await gateway.close()

    async def verify_enabled(self) -> list[ExchangeConnectionStatus]:
        tasks = [self.verify_exchange(exchange_id) for exchange_id in self.enabled_exchange_ids()]
        return list(await asyncio.gather(*tasks))

    async def account_snapshot(
        self,
        exchange_id: str,
        *,
        include_symbol_count: bool = False,
    ) -> ExchangeAccountSnapshot:
        gateway = self._open_gateway(exchange_id, mode="private")
        try:
            connection = await gateway.probe_connection()
            positions: tuple[PositionLeg, ...] = ()
            open_orders: tuple[OpenOrderLeg, ...] = ()
            swap_symbols_count: int | None = None
            if connection.credentials_configured and connection.authenticated:
                positions = tuple(await gateway.fetch_open_positions())
                open_orders = tuple(await gateway.fetch_open_orders())
                if include_symbol_count:
                    swap_symbols_count = len(await gateway.list_symbols())
            return ExchangeAccountSnapshot(
                exchange_id=gateway.exchange_id,
                display_name=gateway.display_name,
                connection=connection,
                positions=positions,
                open_orders=open_orders,
                swap_symbols_count=swap_symbols_count,
            )
        finally:
            await gateway.close()

    async def account_snapshots_for_enabled(
        self,
        *,
        include_symbol_count: bool = False,
    ) -> list[ExchangeAccountSnapshot]:
        tasks = [
            self.account_snapshot(exchange_id, include_symbol_count=include_symbol_count)
            for exchange_id in self.enabled_exchange_ids()
        ]
        return list(await asyncio.gather(*tasks))

    async def fetch_ticker(self, exchange_id: str, symbol: str) -> Ticker | None:
        gateway = self._open_gateway(exchange_id, mode="public")
        try:
            return await gateway.fetch_ticker_once(symbol)
        finally:
            await gateway.close()

    async def fetch_order_book(
        self,
        exchange_id: str,
        symbol: str,
        limit: int,
    ) -> OrderBookSnapshot:
        gateway = self._open_gateway(exchange_id, mode="public")
        try:
            return await gateway.fetch_order_book_once(symbol, limit)
        finally:
            await gateway.close()

    async def list_swap_symbols(self, exchange_id: str) -> list[str]:
        gateway = self._open_gateway(exchange_id, mode="public")
        try:
            return await gateway.list_symbols()
        finally:
            await gateway.close()

    def _open_gateway(self, exchange_id: str, mode: str = "public") -> CcxtBase:
        named = self._factory.create(exchange_id, mode=mode)
        gateway = named.gateway
        if not isinstance(gateway, CcxtBase):
            logger.error("Gateway is not CcxtBase | exchange={}", exchange_id)
            raise TypeError(f"unsupported gateway for exchange {exchange_id}")
        return gateway
