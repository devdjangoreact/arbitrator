import json
import logging
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from arbitrator.config.ui_config import StrategyUIConfig
# To do the migration, we temporarily read Settings, but only once on startup.
# We will import settings locally inside the migrate function to avoid circular imports.

logger = logging.getLogger(__name__)

class UIConfigManager:
    """
    Singleton manager for reading and writing StrategyUIConfig.
    """
    _instance = None
    _config: StrategyUIConfig | None = None
    _config_path: Path | None = None

    @classmethod
    def initialize(cls, config_path: Path | str) -> None:
        """
        Initializes the manager, loads the JSON, and performs one-time migration if needed.
        Must be called on app startup.
        """
        if cls._instance is None:
            cls._instance = UIConfigManager()
        
        cls._config_path = Path(config_path)
        cls._config_path.parent.mkdir(parents=True, exist_ok=True)
        
        if cls._config_path.exists():
            cls._instance._load_from_disk()
        else:
            cls._instance._migrate_from_env()

    @classmethod
    def get_config(cls) -> StrategyUIConfig:
        if cls._instance is None or cls._config is None:
            raise RuntimeError("UIConfigManager has not been initialized.")
        return cls._config

    @classmethod
    def update_config(cls, updates: dict[str, Any]) -> StrategyUIConfig:
        if cls._instance is None or cls._config is None:
            raise RuntimeError("UIConfigManager has not been initialized.")
        
        # Merge updates
        current_data = cls._config.model_dump()
        for k, v in updates.items():
            if k in current_data:
                current_data[k] = v
                
        # Validate the new config before saving
        try:
            new_config = StrategyUIConfig(**current_data)
        except ValidationError as e:
            logger.error(f"Invalid configuration update: {e}")
            raise ValueError(f"Invalid configuration update: {e}")
            
        cls._config = new_config
        cls._instance._save_to_disk()
        logger.info("Strategy UI configuration updated successfully.")
        return cls._config

    def _load_from_disk(self) -> None:
        """Loads configuration from JSON file. Halts on corruption."""
        if self._config_path is None:
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            UIConfigManager._config = StrategyUIConfig(**data)
            logger.info("Strategy UI configuration loaded successfully.")
        except json.JSONDecodeError as e:
            logger.critical(f"FATAL: Failed to parse ui_config.json. File is corrupted. Details: {e}")
            sys.exit(1)
        except ValidationError as e:
            logger.critical(f"FATAL: ui_config.json contains invalid data matching StrategyUIConfig schema. Details: {e}")
            sys.exit(1)
        except Exception as e:
            logger.critical(f"FATAL: Unexpected error reading ui_config.json: {e}")
            sys.exit(1)

    def _save_to_disk(self) -> None:
        """Saves current configuration to JSON file."""
        if UIConfigManager._config is None or self._config_path is None:
            return
        
        # Atomic write pattern: write to tmp, then rename
        tmp_path = self._config_path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(UIConfigManager._config.model_dump(), f, indent=2)
        tmp_path.replace(self._config_path)

    def _migrate_from_env(self) -> None:
        """Performs one-time migration from current .env settings to the new JSON config."""
        logger.info("ui_config.json not found. Performing one-time migration from .env settings...")
        from arbitrator.config.settings import Settings
        settings = Settings()
        
        # We instantiate a default StrategyUIConfig to know what fields exist
        # Then we copy matching values from `settings`
        default_config = StrategyUIConfig()
        migration_data = {}
        
        for field_name in default_config.model_fields.keys():
            if hasattr(settings, field_name):
                migration_data[field_name] = getattr(settings, field_name)
            else:
                migration_data[field_name] = getattr(default_config, field_name)
        
        UIConfigManager._config = StrategyUIConfig(**migration_data)
        self._save_to_disk()
        logger.info("One-time migration completed and ui_config.json created.")

