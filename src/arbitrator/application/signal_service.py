from __future__ import annotations

from decimal import Decimal

from arbitrator.application.anomaly_guard import AnomalyGuard
from arbitrator.application.checklist_evaluator import ChecklistEvaluator
from arbitrator.config.logger import logger
from arbitrator.domain.strategy.checklist_result import ChecklistResult
from arbitrator.domain.strategy.strategy_inputs import StrategyInputs
from arbitrator.domain.strategy.strategy_kind import StrategyKind
from arbitrator.domain.strategy.strategy_result import StrategyResult
from arbitrator.domain.strategy.strategy_table import StrategyTable
from arbitrator.domain.strategy.trade_signal import SignalAction, TradeSignal


class SignalService:
    """Emits open/close signals for the active strategy by spread thresholds.

    Open signals are gated by the pre-entry checklist (FR-009) and the anomaly
    guard (FR-015); close signals fire on the close threshold and are not gated
    (closing only reduces exposure). Every decision is logged (FR-017).
    """

    def __init__(self, checklist: ChecklistEvaluator, anomaly: AnomalyGuard) -> None:
        self._checklist = checklist
        self._anomaly = anomaly

    def evaluate(
        self,
        *,
        inputs: StrategyInputs,
        table: StrategyTable,
        active_strategy_id: StrategyKind,
        open_threshold_pct: Decimal,
        close_threshold_pct: Decimal,
        volume_usdt: Decimal,
    ) -> TradeSignal:
        result = table.results.get(active_strategy_id)
        if result is None or not result.available:
            reason = result.unavailable_reason if result is not None else "strategy_missing"
            return self._blocked_none(
                inputs, active_strategy_id, open_threshold_pct, close_threshold_pct,
                volume_usdt, spread_pct=None, checklist=None, reason=reason or "unavailable",
            )

        spread = result.spread_pct
        checklist = self._checklist.evaluate(inputs, active_strategy_id)

        if spread is not None and spread >= open_threshold_pct:
            return self._open_decision(
                inputs, result, active_strategy_id, open_threshold_pct,
                close_threshold_pct, volume_usdt, spread, checklist,
            )
        if spread is not None and spread <= close_threshold_pct:
            logger.info(
                "signal | action=close symbol={} strategy={} spread={} close_thr={}",
                inputs.symbol, active_strategy_id.value, spread, close_threshold_pct,
            )
            return self._signal(
                inputs, active_strategy_id, SignalAction.close, open_threshold_pct,
                close_threshold_pct, volume_usdt, spread, checklist,
            )
        return self._signal(
            inputs, active_strategy_id, SignalAction.none, open_threshold_pct,
            close_threshold_pct, volume_usdt, spread, checklist,
        )

    def _open_decision(
        self,
        inputs: StrategyInputs,
        result: StrategyResult,
        strategy_id: StrategyKind,
        open_threshold_pct: Decimal,
        close_threshold_pct: Decimal,
        volume_usdt: Decimal,
        spread: Decimal,
        checklist: ChecklistResult,
    ) -> TradeSignal:
        anomaly_reason = self._anomaly.evaluate(inputs, spread)
        if anomaly_reason is not None:
            logger.warning(
                "signal blocked | reason={} symbol={} strategy={} spread={}",
                anomaly_reason, inputs.symbol, strategy_id.value, spread,
            )
            return self._blocked_none(
                inputs, strategy_id, open_threshold_pct, close_threshold_pct,
                volume_usdt, spread_pct=spread, checklist=checklist, reason=anomaly_reason,
            )
        if not checklist.passed:
            reason = "checklist:" + ",".join(checklist.failures)
            logger.warning(
                "signal blocked | reason={} symbol={} strategy={} spread={}",
                reason, inputs.symbol, strategy_id.value, spread,
            )
            return self._blocked_none(
                inputs, strategy_id, open_threshold_pct, close_threshold_pct,
                volume_usdt, spread_pct=spread, checklist=checklist, reason=reason,
            )
        logger.info(
            "signal | action=open symbol={} strategy={} spread={} open_thr={} pct_to_deposit={}",
            inputs.symbol, strategy_id.value, spread, open_threshold_pct,
            result.percent_to_deposit,
        )
        return self._signal(
            inputs, strategy_id, SignalAction.open, open_threshold_pct,
            close_threshold_pct, volume_usdt, spread, checklist,
        )

    @staticmethod
    def _signal(
        inputs: StrategyInputs,
        strategy_id: StrategyKind,
        action: SignalAction,
        open_threshold_pct: Decimal,
        close_threshold_pct: Decimal,
        volume_usdt: Decimal,
        spread_pct: Decimal | None,
        checklist: ChecklistResult | None,
    ) -> TradeSignal:
        return TradeSignal(
            symbol=inputs.symbol,
            strategy_id=strategy_id,
            action=action,
            short_exchange_id=inputs.short_exchange_id,
            long_exchange_id=inputs.long_exchange_id,
            spread_pct=spread_pct,
            open_threshold_pct=open_threshold_pct,
            close_threshold_pct=close_threshold_pct,
            volume_usdt=volume_usdt,
            checklist=checklist,
        )

    @staticmethod
    def _blocked_none(
        inputs: StrategyInputs,
        strategy_id: StrategyKind,
        open_threshold_pct: Decimal,
        close_threshold_pct: Decimal,
        volume_usdt: Decimal,
        *,
        spread_pct: Decimal | None,
        checklist: ChecklistResult | None,
        reason: str,
    ) -> TradeSignal:
        return TradeSignal(
            symbol=inputs.symbol,
            strategy_id=strategy_id,
            action=SignalAction.none,
            short_exchange_id=inputs.short_exchange_id,
            long_exchange_id=inputs.long_exchange_id,
            spread_pct=spread_pct,
            open_threshold_pct=open_threshold_pct,
            close_threshold_pct=close_threshold_pct,
            volume_usdt=volume_usdt,
            checklist=checklist,
            blocked=True,
            block_reason=reason,
        )
