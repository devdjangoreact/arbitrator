from __future__ import annotations

from arbitrator.config.json_symbol_exclusions_repository import (
    JsonSymbolExclusionsRepository,
)
from arbitrator.config.json_symbol_universe_repository import (
    JsonSymbolUniverseRepository,
)
from arbitrator.config.logger import init_logger, logger
from arbitrator.config.settings import Settings
from arbitrator.presentation.streamlit_app import StreamlitApp

_settings = Settings()
init_logger(console_level=_settings.log_level)
logger.info("Arbitrator starting | exchanges={}", _settings.enabled_exchanges)

_exclusions_repo = JsonSymbolExclusionsRepository(_settings.exclusions_path)
_universe_repo = JsonSymbolUniverseRepository(_settings.symbols_universe_path)

StreamlitApp(
    settings=_settings,
    exclusions_repo=_exclusions_repo,
    universe_repo=_universe_repo,
).run()
