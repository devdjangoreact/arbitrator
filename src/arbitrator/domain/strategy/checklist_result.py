from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ChecklistResult(BaseModel):
    """Pre-entry mini-checklist outcome (FR-009).

    Each field is a single gate that must hold before an ``open`` signal is
    allowed. ``passed`` is true only when every gate holds; ``failures`` names
    the gates that failed so callers can log a precise block reason.
    """

    model_config = ConfigDict(frozen=True)

    same_asset: bool
    quotes_side_ok: bool
    fees_loaded: bool
    funding_ts_valid: bool

    @property
    def passed(self) -> bool:
        return (
            self.same_asset
            and self.quotes_side_ok
            and self.fees_loaded
            and self.funding_ts_valid
        )

    @property
    def failures(self) -> tuple[str, ...]:
        failed: list[str] = []
        if not self.same_asset:
            failed.append("same_asset")
        if not self.quotes_side_ok:
            failed.append("quotes_side_ok")
        if not self.fees_loaded:
            failed.append("fees_loaded")
        if not self.funding_ts_valid:
            failed.append("funding_ts_valid")
        return tuple(failed)
