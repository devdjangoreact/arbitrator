from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Literal

from fastapi import WebSocket, WebSocketDisconnect

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.presentation.mock.mock_data_provider import MockDataProvider
from arbitrator.presentation.ws.ws_envelope import WsEnvelope


class OrdersWsHandler:
    """WebSocket handler for /ws/orders."""

    def __init__(self, settings: Settings, mock_provider: MockDataProvider | None) -> None:
        self._settings = settings
        self._mock_provider = mock_provider
        self._last_summary: tuple[int, int] | None = None

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("ws connected | endpoint=/ws/orders")
        push_interval = self._settings.screener_ws_push_seconds
        try:
            if self._settings.ui_data_mode == "mock_data":
                await self._mock_loop(websocket, push_interval)
            else:
                await self._live_loop(websocket, push_interval)
        except WebSocketDisconnect:
            logger.info("ws disconnected | endpoint=/ws/orders")
        except Exception:
            logger.exception("ws error | endpoint=/ws/orders")
        finally:
            await WsEnvelope.safe_close(websocket)

    async def _live_loop(self, websocket: WebSocket, push_interval: float) -> None:
        snapshot: dict[str, object] = {
            "summary": {"open_count": 0, "closed_count": 0},
            "filter": "all",
            "groups": [],
        }
        await WsEnvelope.send_dict(websocket, "orders.snapshot", snapshot)
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("type") == "orders.set_filter":
                payload = message.get("payload")
                if isinstance(payload, dict):
                    snapshot["filter"] = payload.get("filter", "all")
                await WsEnvelope.send_dict(websocket, "orders.snapshot", snapshot)

    async def _mock_loop(self, websocket: WebSocket, push_interval: float) -> None:
        if self._mock_provider is None:
            return
        provider = self._mock_provider
        receiver = asyncio.create_task(self._receive_commands(websocket, provider))
        try:
            while True:
                provider.tick()
                snapshot = provider.orders_snapshot()
                await WsEnvelope.send(websocket, "orders.snapshot", snapshot)
                summary = (snapshot.summary.open_count, snapshot.summary.closed_count)
                if summary != self._last_summary:
                    self._last_summary = summary
                    await WsEnvelope.send(websocket, "orders.summary", snapshot.summary)
                await asyncio.sleep(push_interval)
        finally:
            receiver.cancel()
            await WsEnvelope.await_receiver(receiver)

    async def _receive_commands(self, websocket: WebSocket, provider: MockDataProvider) -> None:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("type") != "orders.set_filter":
                continue
            payload = message.get("payload")
            if not isinstance(payload, Mapping):
                continue
            filter_value = str(payload.get("filter", "all"))
            if filter_value in {"all", "open", "closed"}:
                typed_filter: Literal["all", "open", "closed"] = filter_value  # type: ignore[assignment]
                provider.set_orders_filter(typed_filter)
                await WsEnvelope.send(
                    websocket,
                    "orders.snapshot",
                    provider.orders_snapshot(),
                )
