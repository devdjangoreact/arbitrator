from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping

from fastapi import WebSocket, WebSocketDisconnect

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.presentation.dto.trading_dto import ActionResultDto
from arbitrator.presentation.mock.mock_data_provider import MockDataProvider
from arbitrator.presentation.ws.ws_envelope import WsEnvelope


class SettingsWsHandler:
    """WebSocket handler for /ws/settings."""

    def __init__(self, settings: Settings, mock_provider: MockDataProvider | None) -> None:
        self._settings = settings
        self._mock_provider = mock_provider

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("ws connected | endpoint=/ws/settings")
        push_interval = self._settings.screener_ws_push_seconds
        try:
            if self._settings.ui_data_mode == "mock_data":
                await self._mock_loop(websocket, push_interval)
            else:
                await self._live_loop(websocket, push_interval)
        except WebSocketDisconnect:
            logger.info("ws disconnected | endpoint=/ws/settings")
        except Exception:
            logger.exception("ws error | endpoint=/ws/settings")
        finally:
            await WsEnvelope.safe_close(websocket)

    async def _live_loop(self, websocket: WebSocket, push_interval: float) -> None:
        exchanges = []
        for ex_id in self._settings.enabled_exchanges:
            creds = self._settings.credentials_for(ex_id)
            configured = creds is not None and bool(creds.api_key)
            exchanges.append(
                {
                    "exchange_id": ex_id,
                    "api_key_masked": "***" if configured else "",
                    "configured": configured,
                    "has_secret": configured and bool(creds.api_secret) if creds else False,
                    "has_password": configured and bool(creds.password) if creds else False,
                }
            )
        await WsEnvelope.send_dict(
            websocket,
            "settings.snapshot",
            {"exchanges": exchanges},
        )
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("type") == "settings.save_exchange":
                await WsEnvelope.send_dict(
                    websocket,
                    "settings.action_result",
                    {"success": False, "message": "Cannot save in live mode", "exchange_id": ""}
                )

    async def _mock_loop(self, websocket: WebSocket, push_interval: float) -> None:
        if self._mock_provider is None:
            return
        provider = self._mock_provider
        receiver = asyncio.create_task(self._receive_commands(websocket, provider))
        try:
            while True:
                await WsEnvelope.send(websocket, "settings.snapshot", provider.settings_snapshot())
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
            if message.get("type") != "settings.save_exchange":
                continue
            payload = message.get("payload")
            if not isinstance(payload, Mapping):
                continue
            exchange_id = str(payload.get("exchange_id", ""))
            provider.save_exchange(
                exchange_id,
                str(payload.get("api_key", "")),
                str(payload.get("api_secret", "")),
                str(payload.get("api_password", "")),
            )
            await WsEnvelope.send(
                websocket,
                "settings.action_result",
                ActionResultDto(success=True, message="saved", exchange_id=exchange_id),
            )
            await WsEnvelope.send(websocket, "settings.snapshot", provider.settings_snapshot())
