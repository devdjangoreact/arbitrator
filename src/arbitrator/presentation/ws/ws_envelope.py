from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TypeVar

from fastapi import WebSocket
from pydantic import BaseModel

_TPayload = TypeVar("_TPayload", bound=BaseModel)


class WsEnvelope:
    """Serialize typed WS messages as {type, payload}."""

    @staticmethod
    async def safe_close(websocket: WebSocket) -> None:
        with suppress(RuntimeError):
            await websocket.close()

    @staticmethod
    async def await_receiver(task: asyncio.Task[object]) -> None:
        with suppress(asyncio.CancelledError):
            await task
    @staticmethod
    async def send(websocket: WebSocket, message_type: str, payload: BaseModel) -> None:
        await websocket.send_json(
            {
                "type": message_type,
                "payload": payload.model_dump(mode="json"),
            }
        )

    @staticmethod
    async def send_dict(websocket: WebSocket, message_type: str, payload: dict[str, object]) -> None:
        await websocket.send_json({"type": message_type, "payload": payload})
