from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from arbitrator.presentation.dto.opportunity_dto import OrderGroupDto


class OrdersSummaryDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    open_count: int
    closed_count: int


class OrdersSnapshotDto(BaseModel):
    model_config = ConfigDict(frozen=True)

    summary: OrdersSummaryDto
    filter: Literal["all", "open", "closed"]
    groups: list[OrderGroupDto]
