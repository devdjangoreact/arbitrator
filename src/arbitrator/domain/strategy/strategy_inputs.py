from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.funding_info import FundingInfo
from arbitrator.domain.strategy.quote import Quote


class StrategyInputs(BaseModel):
    """Immutable, freshness-gated snapshot for one symbol and one exchange pair.

    Built once by ``StrategyInputsAssembler`` from a single locked cache read
    (C5/FR-025): the engine computes every strategy off this frozen slice only.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    short_exchange_id: str
    long_exchange_id: str
    futures_quotes: dict[str, Quote]
    spot_quotes: dict[str, Quote]
    funding: dict[str, FundingInfo]
    fees: dict[str, FeeSchedule]
    target_volume_usdt: Decimal
    leverage: dict[str, int]
    deposit_usdt: Decimal | None
    now_ms: int
