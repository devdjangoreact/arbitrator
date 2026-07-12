from __future__ import annotations

import sys
import asyncio

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        # Monkey-patch uvicorn to prevent it from forcing SelectorEventLoop in workers
        import uvicorn.loops.asyncio
        def _patched_factory(use_subprocess: bool = False):
            return asyncio.ProactorEventLoop
        uvicorn.loops.asyncio.asyncio_loop_factory = _patched_factory
    except Exception:
        pass

import uvicorn

from arbitrator.application.app_runtime import AppRuntime
from arbitrator.config.logger import init_logger, logger
from arbitrator.config.ui_config_manager import UIConfigManager
from arbitrator.config.settings import Settings
from arbitrator.presentation.fastapi_app import FastApiApp

_settings = Settings()
init_logger(console_level=_settings.log_level)
logger.info(
    "Arbitrator starting | exchanges={} ui_data_mode={}",
    _settings.enabled_exchanges,
    _settings.ui_data_mode,
)

# Initialize persistent UI configuration
ui_config_path = _settings.monitor_configs_path.parent / "ui_config.json"
UIConfigManager.initialize(ui_config_path)

_runtime = AppRuntime(settings=_settings)
app = FastApiApp(settings=_settings, runtime=_runtime).create()


def _run() -> None:
    uvicorn.run(
        "main:app",
        host=_settings.fastapi_host,
        port=_settings.fastapi_port,
        reload=_settings.fastapi_reload,
        loop="asyncio",
    )


if __name__ == "__main__":
    _run()
