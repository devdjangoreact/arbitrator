from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping

from fastapi import WebSocket, WebSocketDisconnect

from arbitrator.application.app_runtime import AppRuntime
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.presentation.dto.trading_dto import ActionResultDto
from arbitrator.presentation.mock.mock_data_provider import MockDataProvider
from arbitrator.presentation.serializers.screener_serializer import ScreenerSerializer
from arbitrator.presentation.ui_delta_encoder import UiDeltaEncoder
from arbitrator.presentation.ws.ws_envelope import WsEnvelope


class ScreenerWsHandler:
    """WebSocket handler for /ws/screener."""

    def __init__(
        self,
        settings: Settings,
        mock_provider: MockDataProvider | None,
        runtime: AppRuntime,
    ) -> None:
        self._settings = settings
        self._mock_provider = mock_provider
        self._runtime = runtime

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("ws connected | endpoint=/ws/screener")
        push_interval = self._settings.screener_ws_push_seconds
        try:
            if self._settings.ui_data_mode == "mock_data":
                await self._mock_loop(websocket, push_interval)
            else:
                await self._live_loop(websocket, push_interval)
        except WebSocketDisconnect:
            logger.info("ws disconnected | endpoint=/ws/screener")
        except Exception:
            logger.exception("ws error | endpoint=/ws/screener")
        finally:
            await WsEnvelope.safe_close(websocket)

    async def _mock_loop(self, websocket: WebSocket, push_interval: float) -> None:
        if self._mock_provider is None:
            await WsEnvelope.send_dict(
                websocket,
                "screener.error",
                {"message": "mock provider not configured"},
            )
            return
        receiver = asyncio.create_task(self._receive_commands(websocket, self._mock_provider))
        previous = None
        try:
            while True:
                self._mock_provider.tick()
                current = self._mock_provider.screener_snapshot()
                if previous is None:
                    await WsEnvelope.send(websocket, "screener.snapshot", current)
                else:
                    delta = UiDeltaEncoder.screener_delta(previous, current)
                    await WsEnvelope.send(websocket, "screener.delta", delta)
                previous = current
                await asyncio.sleep(push_interval)
        finally:
            receiver.cancel()
            await WsEnvelope.await_receiver(receiver)

    async def _live_loop(self, websocket: WebSocket, push_interval: float) -> None:
        worker = self._runtime.screener_worker
        service = self._runtime.strategy_table_service
        if worker is None or service is None:
            await WsEnvelope.send_dict(
                websocket,
                "screener.error",
                {"message": "worker not running"},
            )
            await asyncio.sleep(push_interval)
            return
        serializer = ScreenerSerializer(self._settings)
        receiver = asyncio.create_task(self._receive_live_commands(websocket, serializer))
        previous = None
        try:
            while True:
                snapshot, _stream_symbols, _updates, status, _threshold = worker.read_state()
                now_ms = int(time.time() * 1000)
                tables = service.refresh(snapshot, now_ms)
                symbol_count = len({symbol for _exchange_id, symbol in snapshot})
                current = serializer.serialize(snapshot, tables, status, symbol_count)
                if previous is None:
                    await WsEnvelope.send(websocket, "screener.snapshot", current)
                else:
                    delta = UiDeltaEncoder.screener_delta(previous, current)
                    await WsEnvelope.send(websocket, "screener.delta", delta)
                previous = current
                await asyncio.sleep(push_interval)
        finally:
            receiver.cancel()
            await WsEnvelope.await_receiver(receiver)

    async def _receive_live_commands(
        self,
        websocket: WebSocket,
        serializer: ScreenerSerializer,
    ) -> None:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            msg_type = message.get("type")
            payload = message.get("payload")
            if not isinstance(payload, Mapping):
                payload = {}
            if msg_type == "screener.reconnect":
                stream_min = float(
                    payload.get(
                        "stream_min_volume_usdt",
                        serializer._filters.stream_min_volume_usdt,
                    )
                )
                serializer.set_stream_min_volume_usdt(stream_min)
                self._runtime.reconnect_screener(stream_min)
                await WsEnvelope.send(
                    websocket,
                    "screener.action_result",
                    ActionResultDto(success=True, message="reconnect requested"),
                )

    async def _receive_commands(self, websocket: WebSocket, provider: MockDataProvider) -> None:
        while True:
            raw = await websocket.receive_text()
            await self._dispatch_command(websocket, provider, raw)

    async def _dispatch_command(
        self,
        websocket: WebSocket,
        provider: MockDataProvider,
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
        if msg_type == "ping":
            return
        if not isinstance(payload, Mapping):
            payload = {}

        if msg_type == "screener.reconnect":
            stream_min = float(
                payload.get(
                    "stream_min_volume_usdt",
                    provider._filters.stream_min_volume_usdt,
                )
            )
            provider.screener_reconnect(stream_min)
            await WsEnvelope.send(
                websocket,
                "screener.action_result",
                ActionResultDto(success=True, message="reconnect requested"),
            )
            await WsEnvelope.send(
                websocket,
                "screener.snapshot",
                provider.screener_snapshot(),
            )
