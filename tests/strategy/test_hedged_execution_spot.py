"""Tests for HedgedExecutionService with spot long leg.

Scenarios covered:
  - futures_spot_2ex / futures_spot_1ex / funding_fs: normal open (short futures + long spot)
  - Spot long leg: filled amount recorded with market_type="spot"
  - Futures short leg: filled amount recorded with market_type="futures"
  - Spot leg fails → rollback closes the futures short (no unhedged exposure)
  - Rollback disabled → failed status, futures short remains
  - Futures short leg fails → returns short_leg_failed before spot is touched
  - close_all with spot: closes futures short + sells spot tokens
  - close_all: spot sell fails → partial status, futures closed
  - close_partial: closes N% of futures position + N% of spot balance
  - dry_run with spot strategy → simulated status, no real orders placed
  - Unsupported strategy falls through to futures-only path (no spot gateway needed)
  - Missing spot gateway → spot_gateway_missing failure
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pytest

from arbitrator.application.trading.hedged_execution_service import HedgedExecutionService
from arbitrator.config.settings import Settings
from arbitrator.domain.account.position_leg import PositionLeg
from arbitrator.domain.exchange.spot_gateway import SpotGateway
from arbitrator.domain.strategy.execution_outcome import ExecutionStatus
from arbitrator.domain.strategy.fee_schedule import FeeSchedule

SYMBOL = "DOGE/USDT:USDT"
SPOT_SYMBOL = "DOGE/USDT"
SHORT_EX = "bitget"
LONG_EX = "gate"


# ---------------------------------------------------------------------------
# Fake futures gateway
# ---------------------------------------------------------------------------

class FakeFuturesGateway:
    """Minimal futures gateway that tracks state per symbol."""

    def __init__(
        self,
        exchange_id: str,
        *,
        reject_open: bool = False,
        reject_close: bool = False,
        fill_ratio: float = 1.0,
    ) -> None:
        self._exchange_id = exchange_id
        self._reject_open = reject_open
        self._reject_close = reject_close
        self._fill_ratio = fill_ratio
        self._positions: dict[str, float] = {}  # symbol -> token base
        self.open_calls: list[tuple[str, str, float]] = []
        self.close_calls: list[PositionLeg] = []

    async def open_market_position(
        self,
        symbol: str,
        side: Literal["buy", "sell"],
        amount: float,
        client_order_id: str,
    ) -> str:
        if self._reject_open:
            raise RuntimeError("open rejected")
        filled = amount * self._fill_ratio
        self._positions[symbol] = self._positions.get(symbol, 0.0) + filled
        self.open_calls.append((symbol, side, amount))
        return f"fut-{client_order_id}"

    async def close_market_position(self, leg: PositionLeg) -> str:
        if self._reject_close:
            raise RuntimeError("close rejected")
        current = self._positions.get(leg.symbol, 0.0)
        self._positions[leg.symbol] = max(0.0, current - leg.contracts)
        self.close_calls.append(leg)
        return f"close-{leg.symbol}"

    async def fetch_open_positions(self) -> list[PositionLeg]:
        legs: list[PositionLeg] = []
        for symbol, base in self._positions.items():
            if base <= 0.0:
                continue
            legs.append(PositionLeg(
                exchange_id=self._exchange_id,
                display_name=self._exchange_id,
                symbol=symbol,
                side="short",
                contracts=base,
                contract_size=1.0,
                entry_price=1.0,
                mark_price=1.0,
                opened_at=datetime.now(UTC),
                unrealized_pnl=None,
                accrued_funding=None,
                opening_fee=None,
                estimated_close_fee=None,
                next_funding_at=None,
                arb_marker_id=None,
                position_id=None,
            ))
        return legs

    async def set_margin_mode(self, symbol: str, mode: str) -> None:
        pass

    def position_base(self, symbol: str) -> float:
        return self._positions.get(symbol, 0.0)


# ---------------------------------------------------------------------------
# Fake spot gateway
# ---------------------------------------------------------------------------

class FakeSpotGateway(SpotGateway):
    """Minimal spot gateway that tracks token balance."""

    def __init__(
        self,
        exchange_id: str,
        *,
        reject_buy: bool = False,
        reject_sell: bool = False,
        initial_balance: dict[str, Decimal] | None = None,
    ) -> None:
        self._exchange_id = exchange_id
        self._reject_buy = reject_buy
        self._reject_sell = reject_sell
        self._balance: dict[str, Decimal] = initial_balance or {}
        self.buy_calls: list[tuple[str, float]] = []
        self.sell_calls: list[tuple[str, float]] = []

    async def list_spot_symbols(self) -> list[str]:
        return []

    async def watch_spot_tickers(self, symbols):  # type: ignore[override]
        for _ in ():
            yield {}

    async def fetch_spot_fee(self, symbol: str) -> FeeSchedule | None:
        return None

    async def buy_spot_market(self, symbol: str, amount: float, client_order_id: str) -> str:
        if self._reject_buy:
            raise RuntimeError("spot buy rejected")
        asset = symbol.split("/")[0]
        self._balance[asset] = self._balance.get(asset, Decimal("0")) + Decimal(str(amount))
        self.buy_calls.append((symbol, amount))
        return f"spot-buy-{client_order_id}"

    async def sell_spot_market(self, symbol: str, amount: float, client_order_id: str) -> str:
        if self._reject_sell:
            raise RuntimeError("spot sell rejected")
        asset = symbol.split("/")[0]
        self._balance[asset] = max(
            Decimal("0"),
            self._balance.get(asset, Decimal("0")) - Decimal(str(amount)),
        )
        self.sell_calls.append((symbol, amount))
        return f"spot-sell-{client_order_id}"

    async def fetch_balance(self, asset: str) -> Decimal:
        return self._balance.get(asset, Decimal("0"))

    async def close(self) -> None:
        pass

    def token_balance(self, asset: str) -> Decimal:
        return self._balance.get(asset, Decimal("0"))


# ---------------------------------------------------------------------------
# Service factory
# ---------------------------------------------------------------------------

class FakeMarketCache:
    def get_market_info(self, exchange_id: str, symbol: str) -> object:
        from arbitrator.domain.universe.symbol_market_info import SymbolMarketInfo
        return SymbolMarketInfo(
            exchange_id=exchange_id, symbol=symbol, base_asset="DOGE",
            min_order_volume_usdt=5.0, min_amount_contracts=1.0, contract_size=1.0,
            unified_symbol=symbol, native_market_id=symbol, max_order_volume_usdt=100000.0,
        )
    def get_usdt_balance(self, exchange_id: str) -> float | None:
        return 10000.0

def _service(
    short: FakeFuturesGateway,
    spot: FakeSpotGateway | None = None,
    *,
    dry_run: bool = False,
    **overrides: object,
) -> HedgedExecutionService:
    settings = Settings(**overrides)
    spot_gws = {LONG_EX: spot} if spot is not None else {}
    # If the fallback futures path is tested, we also need a futures gateway for LONG_EX.
    # We supply a fake for SHORT_EX and LONG_EX here so standard _enter doesn't fail.
    return HedgedExecutionService(
        {SHORT_EX: short, LONG_EX: FakeFuturesGateway(LONG_EX)},
        settings,
        dry_run=dry_run,
        spot_gateways=spot_gws,
        market_cache=FakeMarketCache(),
    )


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Open: normal path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("strategy", [
    "futures_spot_2ex",
    "futures_spot_1ex",
    "funding_fs",
])
def test_spot_open_normal(strategy: str) -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX)
    outcome = _run(_service(short, spot).open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("100"),
        price=Decimal("1"),
        strategy_kind=strategy,
    ))
    assert outcome.status == ExecutionStatus.success
    assert outcome.short_leg is not None
    assert outcome.long_leg is not None


def test_spot_open_short_leg_market_type_futures() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX)
    outcome = _run(_service(short, spot).open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("100"),
        price=Decimal("1"),
        strategy_kind="futures_spot_2ex",
    ))
    assert outcome.short_leg is not None
    assert outcome.short_leg.market_type == "futures"


def test_spot_open_long_leg_market_type_spot() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX)
    outcome = _run(_service(short, spot).open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("100"),
        price=Decimal("1"),
        strategy_kind="futures_spot_2ex",
    ))
    assert outcome.long_leg is not None
    assert outcome.long_leg.market_type == "spot"


def test_spot_open_places_futures_sell_and_spot_buy() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX)
    _run(_service(short, spot).open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("200"),
        price=Decimal("2"),
        strategy_kind="futures_spot_2ex",
    ))
    # Futures short placed
    assert len(short.open_calls) == 1
    assert short.open_calls[0][1] == "sell"
    # Spot buy placed
    assert len(spot.buy_calls) == 1
    assert spot.buy_calls[0][0] == SPOT_SYMBOL


def test_spot_open_long_symbol_strips_usdt_suffix() -> None:
    """Spot order must use 'DOGE/USDT' not 'DOGE/USDT:USDT'."""
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX)
    _run(_service(short, spot).open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("50"),
        price=Decimal("1"),
        strategy_kind="futures_spot_1ex",
    ))
    bought_symbol = spot.buy_calls[0][0]
    assert ":USDT" not in bought_symbol
    assert bought_symbol == "DOGE/USDT"


def test_spot_open_token_balance_increases() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX)
    _run(_service(short, spot).open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("100"),
        price=Decimal("1"),
        strategy_kind="futures_spot_2ex",
    ))
    assert spot.token_balance("DOGE") == Decimal("100")


# ---------------------------------------------------------------------------
# Open: failure paths
# ---------------------------------------------------------------------------

def test_spot_open_futures_short_fails_returns_short_leg_failed() -> None:
    short = FakeFuturesGateway(SHORT_EX, reject_open=True)
    spot = FakeSpotGateway(LONG_EX)
    outcome = _run(_service(short, spot).open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("100"),
        price=Decimal("1"),
        strategy_kind="futures_spot_2ex",
    ))
    assert outcome.status == ExecutionStatus.failed
    assert outcome.message == "short_leg_failed"
    # Spot buy must NOT have been called
    assert spot.buy_calls == []


def test_spot_open_spot_buy_fails_rollback_closes_futures() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX, reject_buy=True)
    outcome = _run(_service(short, spot).open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("100"),
        price=Decimal("1"),
        strategy_kind="futures_spot_2ex",
    ))
    assert outcome.status == ExecutionStatus.failed
    assert outcome.message == "spot_long_leg_failed"
    # Rollback should have closed the futures short
    assert short.position_base(SYMBOL) == 0.0


def test_spot_open_spot_buy_fails_rollback_disabled_leaves_futures() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX, reject_buy=True)
    outcome = _run(
        _service(short, spot, execution_rollback_enabled=False).open(
            symbol=SYMBOL,
            short_exchange_id=SHORT_EX,
            long_exchange_id=LONG_EX,
            notional_usdt=Decimal("100"),
            price=Decimal("1"),
            strategy_kind="futures_spot_2ex",
        )
    )
    assert outcome.status == ExecutionStatus.failed
    # Futures short was NOT rolled back
    assert short.position_base(SYMBOL) == 100.0


def test_spot_open_missing_spot_gateway_returns_failure() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    # No spot gateway provided
    outcome = _run(_service(short, None).open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("100"),
        price=Decimal("1"),
        strategy_kind="futures_spot_2ex",
    ))
    assert outcome.status == ExecutionStatus.failed
    assert outcome.message == "spot_gateway_missing"


# ---------------------------------------------------------------------------
# Close: normal path
# ---------------------------------------------------------------------------

def test_spot_close_all_closes_futures_and_sells_spot() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX, initial_balance={"DOGE": Decimal("100")})
    # Pre-open to establish futures position
    _run(_service(short, spot).open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("100"),
        price=Decimal("1"),
        strategy_kind="futures_spot_2ex",
    ))
    outcome = _run(_service(short, spot).close_all(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        strategy_kind="futures_spot_2ex",
    ))
    assert outcome.status == ExecutionStatus.success
    assert short.close_calls != []
    assert spot.sell_calls != []


def test_spot_close_all_spot_symbol_stripped() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX, initial_balance={"DOGE": Decimal("50")})
    _run(_service(short, spot).close_all(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        strategy_kind="futures_spot_1ex",
    ))
    assert spot.sell_calls[0][0] == "DOGE/USDT"


def test_spot_close_all_zero_balance_skips_sell() -> None:
    """Zero spot balance → no sell call, still success."""
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX)  # no balance
    outcome = _run(_service(short, spot).close_all(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        strategy_kind="futures_spot_2ex",
    ))
    assert outcome.status == ExecutionStatus.success
    assert spot.sell_calls == []


def test_spot_close_sell_fails_partial_status() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX, reject_sell=True, initial_balance={"DOGE": Decimal("100")})
    # Establish a futures position first
    short._positions[SYMBOL] = 100.0
    outcome = _run(_service(short, spot).close_all(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        strategy_kind="futures_spot_2ex",
    ))
    # Futures closed OK, spot sell failed → partial
    assert outcome.status == ExecutionStatus.partial


def test_spot_close_partial_sells_fraction_of_balance() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX, initial_balance={"DOGE": Decimal("100")})
    short._positions[SYMBOL] = 100.0
    _run(_service(short, spot).close_partial(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        close_percent=Decimal("50"),
        strategy_kind="futures_spot_2ex",
    ))
    # 50% of 100 DOGE sold
    assert spot.sell_calls[0][1] == pytest.approx(50.0)
    # 50 DOGE remaining
    assert spot.token_balance("DOGE") == Decimal("50")


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

def test_spot_dry_run_simulated_no_orders() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX)
    outcome = _run(_service(short, spot, dry_run=True).open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("100"),
        price=Decimal("1"),
        strategy_kind="futures_spot_2ex",
    ))
    assert outcome.status == ExecutionStatus.simulated
    assert short.open_calls == []
    assert spot.buy_calls == []


def test_spot_dry_run_leg_types() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    spot = FakeSpotGateway(LONG_EX)
    outcome = _run(_service(short, spot, dry_run=True).open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("100"),
        price=Decimal("1"),
        strategy_kind="futures_spot_1ex",
    ))
    assert outcome.short_leg is not None and outcome.short_leg.market_type == "futures"
    assert outcome.long_leg is not None and outcome.long_leg.market_type == "spot"


# ---------------------------------------------------------------------------
# Non-spot strategy: falls through to futures path
# ---------------------------------------------------------------------------

def test_futures_futures_strategy_does_not_use_spot_gateway() -> None:
    short = FakeFuturesGateway(SHORT_EX)
    long_fut = FakeFuturesGateway(LONG_EX)
    spot = FakeSpotGateway(LONG_EX)
    svc = HedgedExecutionService(
        {SHORT_EX: short, LONG_EX: long_fut},
        Settings(),
        spot_gateways={LONG_EX: spot},
        market_cache=FakeMarketCache(),
    )
    _run(svc.open(
        symbol=SYMBOL,
        short_exchange_id=SHORT_EX,
        long_exchange_id=LONG_EX,
        notional_usdt=Decimal("100"),
        price=Decimal("1"),
        strategy_kind="futures_futures",
    ))
    # Spot gateway untouched
    assert spot.buy_calls == []
    # Futures long used
    assert len(long_fut.open_calls) == 1
