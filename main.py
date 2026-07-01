from __future__ import annotations

import uvicorn

from arbitrator.application.app_runtime import AppRuntime
from arbitrator.config.logger import init_logger, logger
from arbitrator.config.settings import Settings
from arbitrator.presentation.fastapi_app import FastApiApp

_settings = Settings()
init_logger(console_level=_settings.log_level)
logger.info(
    "Arbitrator starting | exchanges={} ui_data_mode={}",
    _settings.enabled_exchanges,
    _settings.ui_data_mode,
)

_runtime = AppRuntime(settings=_settings)
app = FastApiApp(settings=_settings, runtime=_runtime).create()


def _run() -> None:
    uvicorn.run(
        "main:app",
        host=_settings.fastapi_host,
        port=_settings.fastapi_port,
        reload=_settings.fastapi_reload,
    )


if __name__ == "__main__":
    _run()
