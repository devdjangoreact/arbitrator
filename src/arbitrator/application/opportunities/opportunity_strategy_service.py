from __future__ import annotations
from arbitrator.config.ui_config_manager import UIConfigManager

from decimal import Decimal

from arbitrator.application.strategies.strategy_inputs_assembler import StrategyInputsAssembler
from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.strategy_engine import StrategyEngine
from arbitrator.domain.strategy.strategy_table import StrategyTable


class OpportunityStrategyService:
    """Full strategy table for one explicit short/long pair on Opportunity."""

    def __init__(
        self,
        assembler: StrategyInputsAssembler,
        engine: StrategyEngine,
        settings: Settings,
    ) -> None:
        self._assembler = assembler
        self._engine = engine
        self._settings = settings

    def compute(
        self,
        *,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        target_volume_usdt: float,
        leverage_by_exchange: dict[str, int],
        now_ms: int,
    ) -> StrategyTable:
        exchange_ids = {short_exchange_id, long_exchange_id}
        leverage = {
            exchange_id: leverage_by_exchange.get(exchange_id, UIConfigManager.get_config().opp_default_leverage)
            for exchange_id in exchange_ids
        }
        inputs = self._assembler.assemble(
            symbol=symbol,
            short_exchange_id=short_exchange_id,
            long_exchange_id=long_exchange_id,
            target_volume_usdt=Decimal(str(target_volume_usdt)),
            leverage=leverage,
            now_ms=now_ms,
        )
        return self._engine.compute(inputs)
