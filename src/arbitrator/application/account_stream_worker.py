from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Sequence

import ccxt.pro as ccxtpro

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.exchange_connection_status import ExchangeConnectionStatus
from arbitrator.domain.exchange_gateway import ExchangeGateway
from arbitrator.domain.named_exchange import NamedExchange
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.exchanges.factory import Factory


class AccountStreamWorker:
    """Streams private account data (positions, USDT balance) over WebSocket.

    One background thread keeps gateways open for exchanges with credentials.
    UI layers read thread-safe snapshots instead of issuing REST polls.
    """

    def __init__(self, settings: Settings, factory: Factory) -> None:
        self._settings = settings
        self._factory = factory
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._positions_by_exchange: dict[str, list[PositionLeg]] = {}
        self._balances: dict[str, float | None] = {}
        self._statuses: dict[str, ExchangeConnectionStatus] = {}
        self._stream_status = "Idle"
        self._running_exchange_ids: list[str] = []
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task[None] | None = None

    def ensure_running(self, exchange_ids: Sequence[str]) -> None:
        eligible = [
            exchange_id
            for exchange_id in exchange_ids
            if self._settings.credentials_for(exchange_id) is not None
        ]
        if not eligible:
            return
        if self.is_alive() and sorted(eligible) == sorted(self._running_exchange_ids):
            return
        if self.is_alive():
            self.stop()
        self._running_exchange_ids = list(eligible)
        self._seed_connecting_statuses(eligible)
        self.start()

    def start(self) -> None:
        if self.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._thread_main,
            name="account-stream",
            daemon=True,
        )
        self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        task = self._main_task
        if loop is not None and task is not None and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)

    def read_positions(self, exchange_ids: Sequence[str] | None = None) -> list[PositionLeg]:
        ids = list(exchange_ids) if exchange_ids is not None else list(self._running_exchange_ids)
        with self._lock:
            legs: list[PositionLeg] = []
            for exchange_id in ids:
                legs.extend(self._positions_by_exchange.get(exchange_id, []))
            return legs

    def read_statuses(self, exchange_ids: Sequence[str]) -> list[ExchangeConnectionStatus]:
        with self._lock:
            return [
                self._statuses.get(
                    exchange_id,
                    self._placeholder_status(exchange_id),
                )
                for exchange_id in exchange_ids
            ]

    def wait_for_status(
        self,
        exchange_id: str,
        *,
        timeout_seconds: float,
    ) -> ExchangeConnectionStatus:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            statuses = self.read_statuses([exchange_id])
            status = statuses[0]
            if status.authenticated and status.message not in (None, "Connecting…"):
                return status
            time.sleep(0.2)
        return self.read_statuses([exchange_id])[0]

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_main())
        except asyncio.CancelledError:
            logger.info("Account background stream stopped")
        except Exception:
            logger.exception("Account background stream failed")
            self._set_stream_status("Error")

    async def _async_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._main_task = asyncio.current_task()
        named_exchanges = self._factory.create_many(self._running_exchange_ids)
        self._set_stream_status("Connecting…")
        logger.info(
            "Account stream spawned | exchanges={}",
            self._running_exchange_ids,
        )
        tasks = [
            asyncio.create_task(
                self._stream_exchange(named),
                name=f"account-stream:{named.exchange_id}",
            )
            for named in named_exchanges
        ]
        try:
            await asyncio.gather(*tasks)
        finally:
            await self._close_exchanges(named_exchanges)

    async def _stream_exchange(self, named: NamedExchange) -> None:
        exchange_id = named.exchange_id
        display_name = named.display_name
        gateway = named.gateway
        position_task = asyncio.create_task(
            self._consume_positions(gateway, exchange_id, display_name),
            name=f"account-positions:{exchange_id}",
        )
        balance_task = asyncio.create_task(
            self._consume_balance(gateway, exchange_id, display_name),
            name=f"account-balance:{exchange_id}",
        )
        try:
            await asyncio.gather(position_task, balance_task)
        finally:
            position_task.cancel()
            balance_task.cancel()
            await asyncio.gather(position_task, balance_task, return_exceptions=True)

    async def _consume_positions(
        self,
        gateway: ExchangeGateway,
        exchange_id: str,
        display_name: str,
    ) -> None:
        try:
            async for legs in gateway.watch_open_positions():
                if self._stop.is_set():
                    break
                self._publish_positions(exchange_id, legs)
                self._publish_trading_enabled(exchange_id, display_name, True)
                self._set_stream_status("Live")
        except asyncio.CancelledError:
            raise
        except ccxtpro.PermissionDenied:
            logger.exception("Position stream permission denied | exchange={}", exchange_id)
            self._publish_trading_enabled(exchange_id, display_name, False)
            self._publish_auth_failure(exchange_id, display_name, "API key lacks required permissions")
        except ccxtpro.AuthenticationError:
            logger.exception("Position stream auth failed | exchange={}", exchange_id)
            self._publish_auth_failure(exchange_id, display_name, "Invalid API key or secret")
        except Exception:
            logger.exception("Position stream failed | exchange={}", exchange_id)

    async def _consume_balance(
        self,
        gateway: ExchangeGateway,
        exchange_id: str,
        display_name: str,
    ) -> None:
        try:
            async for balance in gateway.watch_usdt_balance():
                if self._stop.is_set():
                    break
                self._publish_balance(exchange_id, display_name, balance)
                self._set_stream_status("Live")
        except asyncio.CancelledError:
            raise
        except ccxtpro.AccountNotEnabled:
            logger.warning("Futures account not enabled | exchange={}", exchange_id)
            self._publish_balance(exchange_id, display_name, None)
            self._publish_trading_enabled(exchange_id, display_name, False)
            self._upsert_status(
                exchange_id,
                display_name,
                authenticated=True,
                trading_enabled=False,
                usdt_balance=None,
                message=(
                    "API keys valid; activate USDT futures account "
                    "(transfer funds to futures wallet on exchange)"
                ),
            )
        except ccxtpro.PermissionDenied:
            logger.exception("Balance stream permission denied | exchange={}", exchange_id)
            self._publish_auth_failure(exchange_id, display_name, "API key lacks required permissions")
        except ccxtpro.AuthenticationError:
            logger.exception("Balance stream auth failed | exchange={}", exchange_id)
            self._publish_auth_failure(exchange_id, display_name, "Invalid API key or secret")
        except Exception:
            logger.exception("Balance stream failed | exchange={}", exchange_id)

    def _seed_connecting_statuses(self, exchange_ids: Sequence[str]) -> None:
        with self._lock:
            for exchange_id in exchange_ids:
                self._statuses[exchange_id] = self._connecting_status(exchange_id)

    def _connecting_status(self, exchange_id: str) -> ExchangeConnectionStatus:
        return ExchangeConnectionStatus(
            exchange_id=exchange_id,
            display_name=self._factory.display_name(exchange_id),
            credentials_configured=True,
            authenticated=False,
            trading_enabled=False,
            usdt_balance=None,
            message="Connecting…",
        )

    def _placeholder_status(self, exchange_id: str) -> ExchangeConnectionStatus:
        configured = self._settings.credentials_for(exchange_id) is not None
        if not configured:
            return ExchangeConnectionStatus(
                exchange_id=exchange_id,
                display_name=self._factory.display_name(exchange_id),
                credentials_configured=False,
                authenticated=False,
                trading_enabled=False,
                usdt_balance=None,
                message="API key and secret required in .env",
            )
        return self._connecting_status(exchange_id)

    def _publish_positions(self, exchange_id: str, legs: list[PositionLeg]) -> None:
        with self._lock:
            self._positions_by_exchange[exchange_id] = list(legs)

    def _publish_balance(
        self,
        exchange_id: str,
        display_name: str,
        balance: float | None,
    ) -> None:
        with self._lock:
            self._balances[exchange_id] = balance
            current = self._statuses.get(exchange_id)
            trading_enabled = current.trading_enabled if current is not None else False
            message = current.message if current is not None else "Connected"
            if message == "Connecting…":
                message = "Connected"
            self._statuses[exchange_id] = ExchangeConnectionStatus(
                exchange_id=exchange_id,
                display_name=display_name,
                credentials_configured=True,
                authenticated=True,
                trading_enabled=trading_enabled,
                usdt_balance=balance,
                message=message,
            )

    def _publish_trading_enabled(
        self,
        exchange_id: str,
        display_name: str,
        trading_enabled: bool,
    ) -> None:
        with self._lock:
            current = self._statuses.get(exchange_id)
            balance = self._balances.get(exchange_id)
            if current is not None and current.usdt_balance is not None:
                balance = current.usdt_balance
            authenticated = True
            message = "Connected"
            if not trading_enabled:
                message = "Connected (trading access disabled)"
            if current is not None and current.message not in (None, "Connecting…"):
                current_message = current.message
                if (
                    not trading_enabled
                    and current_message is not None
                    and "trading" in current_message.lower()
                ):
                    message = current_message
                elif current.authenticated:
                    authenticated = current.authenticated
            self._statuses[exchange_id] = ExchangeConnectionStatus(
                exchange_id=exchange_id,
                display_name=display_name,
                credentials_configured=True,
                authenticated=authenticated,
                trading_enabled=trading_enabled,
                usdt_balance=balance,
                message=message,
            )

    def _publish_auth_failure(
        self,
        exchange_id: str,
        display_name: str,
        message: str,
    ) -> None:
        self._upsert_status(
            exchange_id,
            display_name,
            authenticated=False,
            trading_enabled=False,
            usdt_balance=None,
            message=message,
        )

    def _upsert_status(
        self,
        exchange_id: str,
        display_name: str,
        *,
        authenticated: bool,
        trading_enabled: bool,
        usdt_balance: float | None,
        message: str,
    ) -> None:
        with self._lock:
            self._statuses[exchange_id] = ExchangeConnectionStatus(
                exchange_id=exchange_id,
                display_name=display_name,
                credentials_configured=True,
                authenticated=authenticated,
                trading_enabled=trading_enabled,
                usdt_balance=usdt_balance,
                message=message,
            )

    def _set_stream_status(self, status: str) -> None:
        with self._lock:
            self._stream_status = status

    @staticmethod
    async def _close_exchanges(exchanges: Sequence[NamedExchange]) -> None:
        for exchange in exchanges:
            try:
                await exchange.gateway.close()
            except Exception:
                logger.exception(
                    "Failed to close gateway | exchange={}",
                    exchange.exchange_id,
                )
