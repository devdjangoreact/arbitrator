"""Unit test fixtures."""
from __future__ import annotations

import pytest
from pathlib import Path

from arbitrator.config.ui_config_manager import UIConfigManager


@pytest.fixture(autouse=True)
def init_ui_config_manager(tmp_path: Path) -> None:
    """Ensure UIConfigManager is initialized for every unit test."""
    UIConfigManager._instance = None
    UIConfigManager._config = None
    UIConfigManager._config_path = None
    UIConfigManager.initialize(tmp_path / "ui_config.json")
