from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from decimal import Decimal

from fastapi import WebSocket, WebSocketDisconnect

from arbitrator.application.app_runtime import AppRuntime
from arbitrator.application.fee_snapshot_service import FeeSnapshotService
from arbitrator.application.hedged_execution_service import HedgedExecutionService
from arbitrator.application.opportunity_bootstrap_service import OpportunityBootstrapService
from arbitrator.application.opportunity_session_state import OpportunitySessionState
from arbitrator.application.opportunity_stream_worker import OpportunityStreamWorker
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.execution_outcome import ExecutionOutcome, ExecutionStatus
from arbitrator.domain.symbol_normalizer import SymbolNormalizer
from arbitrator.exchanges.factory import Factory
from arbitrator.presentation.dto.trading_dto import ActionResultDto
from arbitrator.presentation.mock.mock_data_provider import MockDataProvider
from arbitrator.presentation.serializers.opportunity_serializer import OpportunitySerializer
from arbitrator.presentation.ws.ws_envelope import WsEnvelope


class OpportunityWsHandler:
    """WebSocket handler for /ws/opportunity?symbol=&short=&long=."""

    def __init__(
        self,
        settings: Settings,
        mock_provider: MockDataProvider | None,
        runtime: AppRuntime,
    ) -> None:
        self._settings = settings
        self._mock_provider = mock_provider
        self._runtime = runtime

    async def handle(self, websocket: WebSocket, symbol: str, short_ex: str, long_ex: str) -> None:
        await websocket.accept()
        swap_symbol = SymbolNormalizer.to_swap_symbol(symbol)
        display_symbol = SymbolNormalizer.to_display_symbol(swap_symbol)
        logger.info(
            "ws connected | endpoint=/ws/opportunity symbol={} short={} long={}",
            display_symbol,
            short_ex,
            long_ex,
        )
        push_interval = self._settings.screener_ws_push_seconds
        try:
            if not short_ex or not long_ex or not display_symbol:
                await WsEnvelope.send_dict(
                    websocket,
                    "opportunity.error",
                    {"message": "symbol, short and long query params are required"},
                )
                return
            if self._settings.ui_data_mode == "mock_data":
                await self._mock_loop(websocket, display_symbol, short_ex, long_ex, push_interval)
            else:
                await self._live_loop(
                    websocket,
                    swap_symbol,
                    display_symbol,
                    short_ex,
                    long_ex,
                    push_interval,
                )
        except WebSocketDisconnect:
            logger.info("ws disconnected | endpoint=/ws/opportunity symbol={}", display_symbol)
        except Exception:
            logger.exception("ws disconnected | endpoint=/ws/opportunity symbol={}", display_symbol)
        finally:
            await WsEnvelope.safe_close(websocket)

    async def _mock_loop(
        self,
        websocket: WebSocket,
        symbol: str,
        short_ex: str,
        long_ex: str,
        push_interval: float,
    ) -> None:
        if self._mock_provider is None:
            await WsEnvelope.send_dict(
                websocket,
                "opportunity.error",
                {"message": "mock provider not configured"},
            )
            return
        provider = self._mock_provider
        receiver = asyncio.create_task(
            self._receive_commands(websocket, provider, symbol, short_ex, long_ex)
        )
        try:
            while True:
                provider.tick()
                snap = provider.opportunity_snapshot(symbol, short_ex, long_ex)
                await WsEnvelope.send(websocket, "opportunity.snapshot", snap)
                chart_delta = [
                    {
                        "key": s.key,
                        "point": {"t": s.points[-1].t, "price": s.points[-1].price},
                        "last_price": s.last_price,
                    }
                    for s in provider._chart_series
                    if s.exchange_id in {short_ex, long_ex} and s.points
                ]
                await WsEnvelope.send_dict(
                    websocket,
                    "opportunity.delta",
                    {
                        "chart_series": chart_delta,
                        "books": [book.model_dump() for book in snap.books],
                    },
                )
                await asyncio.sleep(push_interval)
        finally:
            receiver.cancel()
            await WsEnvelope.await_receiver(receiver)

    async def _live_loop(
        self,
        websocket: WebSocket,
        swap_symbol: str,
        display_symbol: str,
        short_ex: str,
        long_ex: str,
        push_interval: float,
    ) -> None:
        screener_worker = self._runtime.screener_worker
        table_service = self._runtime.strategy_table_service
        if screener_worker is None or table_service is None:
            await WsEnvelope.send_dict(
                websocket,
                "opportunity.error",
                {"message": "live workers not running"},
            )
            return

        factory = Factory(settings=self._settings)
        stream_worker = OpportunityStreamWorker(
            settings=self._settings,
            factory=factory,
            symbol=swap_symbol,
            short_exchange_id=short_ex,
            long_exchange_id=long_ex,
        )
        stream_worker.start()
        session = OpportunitySessionState(self._settings)
        serializer = OpportunitySerializer(self._settings)
        strategy_service = table_service.create_opportunity_service()
        cache = self._runtime.market_cache
        if cache is not None:
            bootstrap = OpportunityBootstrapService(factory)
            fee_service = FeeSnapshotService(cache)
            await bootstrap.bootstrap(
                swap_symbol=swap_symbol,
                display_symbol=display_symbol,
                short_exchange_id=short_ex,
                long_exchange_id=long_ex,
                session=session,
                cache=cache,
                fee_service=fee_service,
            )
        receiver = asyncio.create_task(
            self._receive_live_commands(
                websocket, session, stream_worker, swap_symbol, short_ex, long_ex
            )
        )
        prev_ring_len = 0
        try:
            while True:
                tickers, _symbols, _updates, _status, _threshold = screener_worker.read_state()
                now_ms = int(time.time() * 1000)
                table_service.refresh(tickers, now_ms)
                stream_state = stream_worker.read_state()
                snapshot = serializer.serialize(
                    display_symbol=display_symbol,
                    swap_symbol=swap_symbol,
                    short_exchange_id=short_ex,
                    long_exchange_id=long_ex,
                    session=session,
                    stream_state=stream_state,
                    strategy_service=strategy_service,
                    cache=cache,
                    account_worker=self._runtime.account_worker,
                    now_ms=now_ms,
                )
                await WsEnvelope.send(websocket, "opportunity.snapshot", snapshot)
                new_ring = stream_state.price_ring[prev_ring_len:]
                chart_delta = self._chart_delta_from_ring(new_ring, short_ex, long_ex) if new_ring else []
                await WsEnvelope.send_dict(
                    websocket,
                    "opportunity.delta",
                    {
                        "chart_series": chart_delta,
                        "books": [book.model_dump() for book in snapshot.books],
                    },
                )
                if new_ring:
                    prev_ring_len = len(stream_state.price_ring)
                await asyncio.sleep(push_interval)
        finally:
            receiver.cancel()
            stream_worker.stop()
            await WsEnvelope.await_receiver(receiver)

    async def _receive_live_commands(
        self,
        websocket: WebSocket,
        session: OpportunitySessionState,
        stream_worker: OpportunityStreamWorker,
        swap_symbol: str,
        short_ex: str,
        long_ex: str,
    ) -> None:
        while True:
            raw = await websocket.receive_text()
            await self._dispatch_live_command(
                websocket, session, stream_worker, swap_symbol, short_ex, long_ex, raw
            )

    async def _dispatch_live_command(
        self,
        websocket: WebSocket,
        session: OpportunitySessionState,
        stream_worker: OpportunityStreamWorker,
        swap_symbol: str,
        short_ex: str,
        long_ex: str,
        raw: str,
    ) -> None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(message, dict):
            return
        msg_type = message.get("type")
        payload = message.get("payload")
        if not isinstance(payload, Mapping):
            payload = {}

        action_result: ActionResultDto | None = None
        if msg_type == "opportunity.set_params":
            session.apply_params(payload)
            action_result = ActionResultDto(
                success=True, message="params updated", action="set_params"
            )
        elif msg_type == "opportunity.set_leverage":
            session.set_leverage(
                str(payload.get("exchange_id", "")),
                int(payload.get("leverage", self._settings.opp_default_leverage)),
            )
            action_result = ActionResultDto(
                success=True, message="leverage updated", action="set_leverage"
            )
        elif msg_type == "opportunity.set_focus":
            action_result = ActionResultDto(
                success=True,
                message="focus updated — reconnect with new query params",
                action="set_focus",
            )
        elif msg_type in {
            "opportunity.accumulate",
            "opportunity.close_partial",
            "opportunity.close_all",
        }:
            action = str(msg_type).removeprefix("opportunity.")
            action_result = await self._execute_trade(
                session, stream_worker, swap_symbol, short_ex, long_ex, action, payload
            )

        if action_result is not None:
            await WsEnvelope.send(websocket, "opportunity.action_result", action_result)

    async def _execute_trade(
        self,
        session: OpportunitySessionState,
        stream_worker: OpportunityStreamWorker,
        swap_symbol: str,
        short_ex: str,
        long_ex: str,
        action: str,
        payload: Mapping[str, object],
    ) -> ActionResultDto:
        factory = Factory(settings=self._settings)
        short_named = factory.create(short_ex)
        long_named = factory.create(long_ex)
        gateways = {short_ex: short_named.gateway, long_ex: long_named.gateway}
        service = HedgedExecutionService(gateways, self._settings)
        try:
            outcome = await self._run_trade(
                service, stream_worker, swap_symbol, short_ex, long_ex, action, payload
            )
        except Exception:
            logger.exception(
                "trade command failed | action={} symbol={} short={} long={}",
                action, swap_symbol, short_ex, long_ex,
            )
            return ActionResultDto(success=False, message="execution error", action=action)
        finally:
            await short_named.gateway.close()
            await long_named.gateway.close()
        success = outcome.status in {ExecutionStatus.success, ExecutionStatus.simulated}
        return ActionResultDto(
            success=success,
            message=self._outcome_message(outcome),
            action=action,
        )

    async def _run_trade(
        self,
        service: HedgedExecutionService,
        stream_worker: OpportunityStreamWorker,
        swap_symbol: str,
        short_ex: str,
        long_ex: str,
        action: str,
        payload: Mapping[str, object],
    ) -> ExecutionOutcome:
        if action == "close_all":
            return await service.close_all(
                symbol=swap_symbol, short_exchange_id=short_ex, long_exchange_id=long_ex
            )
        if action == "close_partial":
            pct = self._decimal_from(payload, "volume_pct", session_default=None)
            close_percent = pct if pct is not None else Decimal("100")
            return await service.close_partial(
                symbol=swap_symbol, short_exchange_id=short_ex, long_exchange_id=long_ex,
                close_percent=close_percent,
            )
        volume = self._decimal_from(payload, "volume_usdt", session_default=None)
        notional = volume if volume is not None else Decimal(str(self._settings.opp_accumulate_step_usdt))
        price = self._long_entry_price(stream_worker, long_ex)
        if price is None or price <= Decimal("0"):
            return ExecutionOutcome(
                action=action, status=ExecutionStatus.failed, symbol=swap_symbol,
                message="no_price_for_sizing",
            )
        return await service.accumulate(
            symbol=swap_symbol, short_exchange_id=short_ex, long_exchange_id=long_ex,
            notional_usdt=notional, price=price,
        )

    @staticmethod
    def _decimal_from(
        payload: Mapping[str, object],
        key: str,
        session_default: Decimal | None,
    ) -> Decimal | None:
        value = payload.get(key)
        if isinstance(value, (int, float, str)):
            try:
                return Decimal(str(value))
            except (ValueError, ArithmeticError):
                return session_default
        return session_default

    @staticmethod
    def _long_entry_price(stream_worker: OpportunityStreamWorker, long_ex: str) -> Decimal | None:
        ticker = stream_worker.read_state().tickers.get(long_ex)
        if ticker is None:
            return None
        raw = ticker.ask if ticker.ask is not None else ticker.last
        if raw is None:
            return None
        return Decimal(str(raw))

    @staticmethod
    def _outcome_message(outcome: ExecutionOutcome) -> str:
        parts = [outcome.status.value]
        if outcome.message is not None:
            parts.append(outcome.message)
        if outcome.imbalance_pct is not None:
            parts.append(f"imbalance={outcome.imbalance_pct:.2f}%")
        if outcome.rolled_back:
            parts.append("rolled_back")
        return " | ".join(parts)

    @staticmethod
    def _chart_delta_from_ring(
        ring: tuple[tuple[int, str, float], ...],
        short_ex: str,
        long_ex: str,
    ) -> list[dict[str, object]]:
        by_key: dict[str, dict[str, object]] = {}
        for ts, exchange_id, price in ring:
            if exchange_id not in {short_ex, long_ex}:
                continue
            key = f"{exchange_id}Fut"
            by_key[key] = {
                "key": key,
                "point": {"t": ts, "price": price},
                "last_price": price,
            }
        return list(by_key.values())

    async def _receive_commands(
        self,
        websocket: WebSocket,
        provider: MockDataProvider,
        symbol: str,
        short_ex: str,
        long_ex: str,
    ) -> None:
        while True:
            raw = await websocket.receive_text()
            await self._dispatch_command(websocket, provider, symbol, short_ex, long_ex, raw)

    async def _dispatch_command(
        self,
        websocket: WebSocket,
        provider: MockDataProvider,
        symbol: str,
        short_ex: str,
        long_ex: str,
        raw: str,
    ) -> None:
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            return
        if not isinstance(message, dict):
            return
        msg_type = message.get("type")
        payload = message.get("payload")
        if not isinstance(payload, Mapping):
            payload = {}

        action_result: ActionResultDto | None = None
        if msg_type == "opportunity.set_params":
            provider.apply_opportunity_params(
                str(payload.get("active_strategy_id", "futures_futures")),
                float(payload.get("target_volume_usdt", 500.0)),
                float(payload.get("open_spread_threshold_pct", 0.7)),
                float(payload.get("close_spread_threshold_pct", 0.05)),
                float(payload.get("accumulate_volume_usdt", 50.0)),
                float(payload.get("accumulate_volume_pct", 10.0)),
                float(payload.get("close_volume_usdt", 50.0)),
                float(payload.get("close_volume_pct", 10.0)),
                bool(payload.get("auto_accumulate_enabled", True)),
                bool(payload.get("auto_close_enabled", False)),
            )
            action_result = ActionResultDto(
                success=True, message="params updated", action="set_params"
            )
        elif msg_type == "opportunity.set_leverage":
            provider.set_leverage(str(payload.get("exchange_id", "")), int(payload.get("leverage", 10)))
            action_result = ActionResultDto(
                success=True, message="leverage updated", action="set_leverage"
            )
        elif msg_type == "opportunity.set_focus":
            action_result = ActionResultDto(
                success=True,
                message="focus updated — reconnect with new query params",
                action="set_focus",
            )
        elif msg_type == "opportunity.accumulate":
            provider.accumulate(float(payload.get("volume_usdt", 0.0)))
            action_result = ActionResultDto(success=True, message="submitted", action="accumulate")
        elif msg_type == "opportunity.close_partial":
            provider.close_partial(float(payload.get("volume_usdt", 0.0)))
            action_result = ActionResultDto(success=True, message="submitted", action="close_partial")
        elif msg_type == "opportunity.close_all":
            provider.close_all()
            action_result = ActionResultDto(success=True, message="submitted", action="close_all")

        if action_result is not None:
            await WsEnvelope.send(websocket, "opportunity.action_result", action_result)
            await WsEnvelope.send(
                websocket,
                "opportunity.snapshot",
                provider.opportunity_snapshot(symbol, short_ex, long_ex),
            )
