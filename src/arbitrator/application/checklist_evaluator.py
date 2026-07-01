from __future__ import annotations

from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.checklist_result import ChecklistResult
from arbitrator.domain.strategy.funding_info import FundingInfo
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.strategy.strategy_inputs import StrategyInputs
from arbitrator.domain.strategy.strategy_kind import StrategyKind

_FUNDING_STRATEGIES: frozenset[StrategyKind] = frozenset(
    {
        StrategyKind.funding_ff,
        StrategyKind.funding_fs,
        StrategyKind.funding_diff_dates,
    }
)


class ChecklistEvaluator:
    """Evaluates the pre-entry mini-checklist off a frozen ``StrategyInputs``.

    Pure gate logic (no I/O): reflects FR-009 items — same asset on both legs,
    entry-side quotes present (short ``bid`` / long ``ask``), fees loaded, and a
    valid (non-stale) funding settlement timestamp for funding strategies.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def evaluate(
        self,
        inputs: StrategyInputs,
        active_strategy_id: StrategyKind,
    ) -> ChecklistResult:
        short_q = inputs.futures_quotes.get(inputs.short_exchange_id)
        long_q = inputs.futures_quotes.get(inputs.long_exchange_id)
        return ChecklistResult(
            same_asset=self._same_asset(inputs, short_q, long_q),
            quotes_side_ok=self._quotes_side_ok(short_q, long_q),
            fees_loaded=self._fees_loaded(inputs),
            funding_ts_valid=self._funding_ts_valid(inputs, active_strategy_id),
        )

    @staticmethod
    def _same_asset(
        inputs: StrategyInputs,
        short_q: Quote | None,
        long_q: Quote | None,
    ) -> bool:
        if short_q is None or long_q is None:
            return False
        return short_q.symbol == inputs.symbol and long_q.symbol == inputs.symbol

    @staticmethod
    def _quotes_side_ok(short_q: Quote | None, long_q: Quote | None) -> bool:
        if short_q is None or long_q is None:
            return False
        if short_q.bid is None or long_q.ask is None:
            return False
        return short_q.bid > 0 and long_q.ask > 0

    @staticmethod
    def _fees_loaded(inputs: StrategyInputs) -> bool:
        short_fee = inputs.fees.get(inputs.short_exchange_id)
        long_fee = inputs.fees.get(inputs.long_exchange_id)
        if short_fee is None or long_fee is None:
            return False
        return short_fee.futures_taker is not None and long_fee.futures_taker is not None

    def _funding_ts_valid(
        self,
        inputs: StrategyInputs,
        active_strategy_id: StrategyKind,
    ) -> bool:
        if active_strategy_id not in _FUNDING_STRATEGIES:
            return True
        exchange_ids = (inputs.short_exchange_id, inputs.long_exchange_id)
        for exchange_id in exchange_ids:
            funding = inputs.funding.get(exchange_id)
            if not self._funding_leg_valid(funding, inputs.now_ms):
                return False
        return True

    @staticmethod
    def _funding_leg_valid(funding: FundingInfo | None, now_ms: int) -> bool:
        """Valid only when the next settlement timestamp is in the future.

        A missing or past ``next_settlement_ms`` means the funding data is stale
        (edge case in spec): funding strategies must not enter on it.
        """
        if funding is None or funding.next_settlement_ms is None:
            return False
        return funding.next_settlement_ms > now_ms
