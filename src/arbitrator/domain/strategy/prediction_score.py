from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PredictionScore(BaseModel):
    """Advisory-only heuristic score for the active strategy (FR-016).

    ``score`` is in ``[0, 1]`` (higher = more favorable). It is ``None`` when
    prediction is disabled or there is not enough history, so callers can safely
    ignore it without affecting the core calculation. Components (``trend``,
    ``stability``, ``seconds_to_funding``) are exposed for transparency.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool
    score: Decimal | None = None
    trend: Decimal | None = None
    stability: Decimal | None = None
    seconds_to_funding: int | None = None
    sample_size: int = 0
