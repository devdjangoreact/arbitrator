from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from arbitrator.application.app_runtime import AppRuntime
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.presentation.ws.opportunity_ws_handler import OpportunityWsHandler
from arbitrator.presentation.ws.orders_ws_handler import OrdersWsHandler
from arbitrator.presentation.ws.paper_trades_ws_handler import PaperTradesWsHandler
from arbitrator.presentation.ws.screener_ws_handler import ScreenerWsHandler
from arbitrator.presentation.ws.settings_ws_handler import SettingsWsHandler

_WS_ENDPOINTS: list[str] = [
    "/ws/screener",
    "/ws/opportunity?symbol=&short=&long=",
    "/ws/orders",
    "/ws/paper_trades",
    "/ws/settings",
]


class FastApiApp:
    """FastAPI app: static UI, health check, WebSocket routes."""

    def __init__(self, settings: Settings, runtime: AppRuntime) -> None:
        self._settings = settings
        self._runtime = runtime
        self._static_dir = Path(__file__).resolve().parent / "static"

    def create(self) -> FastAPI:
        @asynccontextmanager
        async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
            self._runtime.start()
            logger.info(
                "app lifespan started | ui_data_mode={}",
                self._settings.ui_data_mode,
            )
            yield
            self._runtime.stop()
            logger.info("app lifespan stopped")

        app = FastAPI(title=self._settings.app_title, lifespan=lifespan)

        @app.get("/health")
        async def health() -> dict[str, object]:
            return {
                "status": "ok",
                "ui_data_mode": self._settings.ui_data_mode,
                "ws_endpoints": list(_WS_ENDPOINTS),
            }

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(self._static_dir / "index.html")

        app.mount("/static", StaticFiles(directory=self._static_dir), name="static")

        screener_handler = ScreenerWsHandler(
            settings=self._settings,
            mock_provider=self._runtime.mock_provider,
            runtime=self._runtime,
        )
        opportunity_handler = OpportunityWsHandler(
            settings=self._settings,
            mock_provider=self._runtime.mock_provider,
            runtime=self._runtime,
        )
        orders_handler = OrdersWsHandler(
            settings=self._settings,
            mock_provider=self._runtime.mock_provider,
            paper_store=self._runtime.paper_store,
            runtime=self._runtime,
        )
        settings_handler = SettingsWsHandler(
            settings=self._settings,
            mock_provider=self._runtime.mock_provider,
        )
        paper_trades_handler = PaperTradesWsHandler(
            settings=self._settings,
            paper_store=self._runtime.paper_store,
            runtime=self._runtime,
        )

        @app.websocket("/ws/screener")
        async def screener_ws(websocket: WebSocket) -> None:
            await screener_handler.handle(websocket)

        @app.websocket("/ws/opportunity")
        async def opportunity_ws(
            websocket: WebSocket,
            symbol: str = "",
            short: str = "",
            long: str = "",
        ) -> None:
            await opportunity_handler.handle(websocket, symbol, short, long)

        @app.websocket("/ws/orders")
        async def orders_ws(websocket: WebSocket) -> None:
            await orders_handler.handle(websocket)

        @app.websocket("/ws/paper_trades")
        async def paper_trades_ws(websocket: WebSocket) -> None:
            await paper_trades_handler.handle(websocket)

        @app.websocket("/ws/settings")
        async def settings_ws(websocket: WebSocket) -> None:
            await settings_handler.handle(websocket)

        logger.info(
            "FastAPI app created | title={} host={} port={} ui_data_mode={}",
            self._settings.app_title,
            self._settings.fastapi_host,
            self._settings.fastapi_port,
            self._settings.ui_data_mode,
        )
        return app
