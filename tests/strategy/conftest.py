from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Literal

import pytest

from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.funding_info import FundingInfo
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.strategy.strategy_inputs import StrategyInputs

NOW_MS = 1_700_000_000_000

Number = str | int | float | Decimal


def _dec(value: Number | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


@pytest.fixture
def now_ms() -> int:
    return NOW_MS


@pytest.fixture
def make_quote() -> Callable[..., Quote]:
    def _make(
        exchange_id: str,
        *,
        market_type: Literal["futures", "spot"] = "futures",
        bid: Number | None = None,
        ask: Number | None = None,
        last: Number | None = None,
        symbol: str = "DOGE/USDT:USDT",
        recv_time_ms: int = NOW_MS,
    ) -> Quote:
        return Quote(
            exchange_id=exchange_id,
            symbol=symbol,
            market_type=market_type,
            bid=_dec(bid),
            ask=_dec(ask),
            last=_dec(last),
            recv_time_ms=recv_time_ms,
        )

    return _make


@pytest.fixture
def make_funding() -> Callable[..., FundingInfo]:
    def _make(
        exchange_id: str,
        *,
        rate: Number | None = None,
        next_rate: Number | None = None,
        next_settlement_ms: int | None = NOW_MS + 60_000,
        symbol: str = "DOGE/USDT:USDT",
        recv_time_ms: int = NOW_MS,
    ) -> FundingInfo:
        return FundingInfo(
            exchange_id=exchange_id,
            symbol=symbol,
            rate=_dec(rate),
            next_rate=_dec(next_rate),
            next_settlement_ms=next_settlement_ms,
            recv_time_ms=recv_time_ms,
        )

    return _make


@pytest.fixture
def make_fee() -> Callable[..., FeeSchedule]:
    def _make(
        exchange_id: str,
        *,
        futures_taker: Number | None = "0.0005",
        futures_maker: Number | None = "0.0002",
        spot_taker: Number | None = "0.0005",
        spot_maker: Number | None = "0.0002",
        symbol: str = "DOGE/USDT:USDT",
    ) -> FeeSchedule:
        return FeeSchedule(
            exchange_id=exchange_id,
            symbol=symbol,
            futures_maker=_dec(futures_maker),
            futures_taker=_dec(futures_taker),
            spot_maker=_dec(spot_maker),
            spot_taker=_dec(spot_taker),
        )

    return _make


@pytest.fixture
def make_inputs() -> Callable[..., StrategyInputs]:
    def _make(
        *,
        short_exchange_id: str = "a",
        long_exchange_id: str = "b",
        futures_quotes: Mapping[str, Quote] | None = None,
        spot_quotes: Mapping[str, Quote] | None = None,
        funding: Mapping[str, FundingInfo] | None = None,
        fees: Mapping[str, FeeSchedule] | None = None,
        target_volume_usdt: Number = "1000",
        leverage: Mapping[str, int] | None = None,
        deposit_usdt: Number | None = None,
        symbol: str = "DOGE/USDT:USDT",
        now: int = NOW_MS,
    ) -> StrategyInputs:
        return StrategyInputs(
            symbol=symbol,
            short_exchange_id=short_exchange_id,
            long_exchange_id=long_exchange_id,
            futures_quotes=dict(futures_quotes or {}),
            spot_quotes=dict(spot_quotes or {}),
            funding=dict(funding or {}),
            fees=dict(fees or {}),
            target_volume_usdt=Decimal(str(target_volume_usdt)),
            leverage=dict(leverage or {}),
            deposit_usdt=_dec(deposit_usdt),
            now_ms=now,
        )

    return _make
