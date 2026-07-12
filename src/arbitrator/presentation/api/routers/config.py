from arbitrator.config.ui_config_manager import UIConfigManager
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from arbitrator.config.ui_config import StrategyUIConfig

router = APIRouter(prefix="/api/config/strategy", tags=["Configuration"])

class ConfigUpdateResponse(BaseModel):
    status: str
    config: StrategyUIConfig

@router.get("", response_model=StrategyUIConfig)
def get_strategy_config() -> StrategyUIConfig:
    """Retrieves the current active strategy configuration."""
    try:
        return UIConfigManager.get_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("", response_model=ConfigUpdateResponse)
def update_strategy_config(updates: dict[str, Any]) -> ConfigUpdateResponse:
    """
    Updates the strategy configuration. 
    Accepts partial updates and merges them with the existing configuration.
    """
    try:
        updated_config = UIConfigManager.update_config(updates)
        return ConfigUpdateResponse(status="success", config=updated_config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
