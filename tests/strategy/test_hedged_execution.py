from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from arbitrator.application.hedged_execution_service import HedgedExecutionService
from arbitrator.config.settings import Settings
from arbitrator.domain.position_leg import PositionLeg

SYMBOL = "DOGE/USDT:USDT"


class FakeGateway:
    """In-memory futures gateway that tracks position state per symbol."""

    def __init__(
        self,
        exchange_id: str,
        side: Literal["long", "short"],
        *,
        contract_size: float = 1.0,
        fill_ratio: float = 1.0,
        reject_open: bool = False,
        reject_close: bool = False,
    ) -> None:
        self._exchange_id = exchange_id
        self._side = side
        self._contract_size = contract_size
        self._fill_ratio = fill_ratio
        self._reject_open = reject_open
        self._reject_close = reject_close
        self._contracts: dict[str, float] = {}
        self.open_orders: list[tuple[str, str, float]] = []

    async def open_market_position(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        amount: float,
        client_order_id: str,
    ) -> str:
        if self._reject_open:
            raise RuntimeError("open rejected")
        filled_contracts = (amount * self._fill_ratio) / self._contract_size
        self._contracts[symbol] = self._contracts.get(symbol, 0.0) + filled_contracts
        self.open_orders.append((symbol, side, amount))
        return client_order_id

    async def close_market_position(self, leg: PositionLeg) -> str:
        if self._reject_close:
            raise RuntimeError("close rejected")
        current = self._contracts.get(leg.symbol, 0.0)
        self._contracts[leg.symbol] = max(0.0, current - leg.contracts)
        return f"close-{leg.symbol}"

    async def fetch_open_positions(self) -> list[PositionLeg]:
        legs: list[PositionLeg] = []
        for symbol, contracts in self._contracts.items():
            if contracts <= 0.0:
                continue
            legs.append(
                PositionLeg(
                    exchange_id=self._exchange_id,
                    display_name=self._exchange_id,
                    symbol=symbol,
                    side=self._side,
                    contracts=contracts,
                    contract_size=self._contract_size,
                    entry_price=10.0,
                    mark_price=10.0,
                    opened_at=datetime.now(UTC),
                    unrealized_pnl=None,
                    accrued_funding=None,
                    opening_fee=None,
                    estimated_close_fee=None,
                    next_funding_at=None,
                    arb_marker_id=None,
                    position_id=None,
                )
            )
        return legs

    def base_position(self, symbol: str) -> float:
        return self._contracts.get(symbol, 0.0) * self._contract_size


def _service(short: FakeGateway, long: FakeGateway, **overrides: object) -> HedgedExecutionService:
    settings = Settings(**overrides)
    return HedgedExecutionService({"a": short, "b": long}, settings)


def test_open_hedged_success() -> None:
    short, long = FakeGateway("a", "short"), FakeGateway("b", "long")
    outcome = asyncio.run(
        _service(short, long).open(
            symbol=SYMBOL, short_exchange_id="a", long_exchange_id="b",
            notional_usdt=Decimal("1000"), price=Decimal("10"),
        )
    )
    assert outcome.status.value == "success"
    assert outcome.short_leg is not None and outcome.short_leg.filled_amount == Decimal("100")
    assert outcome.long_leg is not None and outcome.long_leg.filled_amount == Decimal("100")
    assert outcome.imbalance_pct == Decimal("0")
    assert len(short.open_orders) == 1 and len(long.open_orders) == 1


def test_filled_amount_comes_from_exchange_not_intent() -> None:
    # Short fills 90% (90 tokens). Long must open for exactly those 90 tokens
    # (delta-neutral: long follows short's actual fill, not the original intent).
    short = FakeGateway("a", "short", fill_ratio=0.9)
    long = FakeGateway("b", "long")
    outcome = asyncio.run(
        _service(short, long).open(
            symbol=SYMBOL, short_exchange_id="a", long_exchange_id="b",
            notional_usdt=Decimal("1000"), price=Decimal("10"),
        )
    )
    assert outcome.short_leg is not None
    assert outcome.short_leg.filled_amount == Decimal("90")
    assert outcome.long_leg is not None
    # Long was sent the filled_short amount (90), not the original intent (100).
    assert outcome.long_leg.requested_amount == Decimal("90")
    assert outcome.long_leg.filled_amount == Decimal("90")
    # Both legs filled the same amount -> no imbalance -> success.
    assert outcome.status.value == "success"


def test_partial_close_keeps_imbalance_within_tolerance() -> None:
    short, long = FakeGateway("a", "short"), FakeGateway("b", "long")
    service = _service(short, long)
    asyncio.run(
        service.open(
            symbol=SYMBOL, short_exchange_id="a", long_exchange_id="b",
            notional_usdt=Decimal("1000"), price=Decimal("10"),
        )
    )
    outcome = asyncio.run(
        service.close_partial(
            symbol=SYMBOL, short_exchange_id="a", long_exchange_id="b",
            close_percent=Decimal("25"),
        )
    )
    assert outcome.status.value == "success"
    assert outcome.imbalance_pct is not None
    assert outcome.imbalance_pct <= Decimal("1.0")
    assert short.base_position(SYMBOL) == 75.0
    assert long.base_position(SYMBOL) == 75.0


def test_one_leg_failure_triggers_rollback_no_unhedged_exposure() -> None:
    short = FakeGateway("a", "short")
    long = FakeGateway("b", "long", reject_open=True)
    outcome = asyncio.run(
        _service(short, long).open(
            symbol=SYMBOL, short_exchange_id="a", long_exchange_id="b",
            notional_usdt=Decimal("1000"), price=Decimal("10"),
        )
    )
    assert outcome.status.value == "rolled_back"
    assert outcome.rolled_back is True
    # The filled short leg was compensated -> no residual position anywhere.
    assert short.base_position(SYMBOL) == 0.0
    assert long.base_position(SYMBOL) == 0.0


def test_rollback_disabled_reports_failed_and_leaves_leg() -> None:
    short = FakeGateway("a", "short")
    long = FakeGateway("b", "long", reject_open=True)
    outcome = asyncio.run(
        _service(short, long, execution_rollback_enabled=False).open(
            symbol=SYMBOL, short_exchange_id="a", long_exchange_id="b",
            notional_usdt=Decimal("1000"), price=Decimal("10"),
        )
    )
    assert outcome.status.value == "failed"
    assert outcome.rolled_back is False
    assert short.base_position(SYMBOL) == 100.0


def test_dry_run_places_no_orders() -> None:
    short, long = FakeGateway("a", "short"), FakeGateway("b", "long")
    settings = Settings()
    service = HedgedExecutionService({"a": short, "b": long}, settings, dry_run=True)
    outcome = asyncio.run(
        service.open(
            symbol=SYMBOL, short_exchange_id="a", long_exchange_id="b",
            notional_usdt=Decimal("1000"), price=Decimal("10"),
        )
    )
    assert outcome.status.value == "simulated"
    assert short.open_orders == [] and long.open_orders == []
