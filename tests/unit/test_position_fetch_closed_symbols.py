from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from arbitrator.application.position_fetch_service import PositionFetchService
from arbitrator.config.settings import Settings
from arbitrator.domain.closed_position_leg import ClosedPositionLeg
from arbitrator.domain.named_exchange import NamedExchange


def _closed_leg() -> ClosedPositionLeg:
    return ClosedPositionLeg(
        exchange_id="mexc",
        display_name="MEXC",
        symbol="BTC/USDT:USDT",
        side="short",
        realized_pnl=1.0,
        commission=0.1,
        funding=0.0,
        opened_at=None,
        closed_at=datetime.now(UTC),
        arb_marker_id=None,
        position_id="1",
    )


def test_fetch_closed_queries_each_exchange_without_local_symbols() -> None:
    settings = Settings(mexc_api_key="key", mexc_api_secret="secret")
    gateway = MagicMock()
    gateway.fetch_closed_positions = AsyncMock(return_value=[_closed_leg()])
    gateway.close = AsyncMock()
    named = NamedExchange(exchange_id="mexc", display_name="MEXC", gateway=gateway)
    factory = MagicMock()
    factory.create.return_value = named
    service = PositionFetchService(settings, factory)
    legs = asyncio.run(service.fetch_closed(["mexc"], history_days=7))
    assert len(legs) == 1
    gateway.fetch_closed_positions.assert_awaited_once()
    since_ms = gateway.fetch_closed_positions.await_args.args[0]
    symbols = gateway.fetch_closed_positions.await_args.args[1]
    assert isinstance(since_ms, int)
    assert symbols == []


def test_fetch_closed_for_symbols_queries_each_exchange() -> None:
    settings = Settings(mexc_api_key="key", mexc_api_secret="secret")
    gateway = MagicMock()
    gateway.fetch_closed_positions = AsyncMock(return_value=[_closed_leg()])
    gateway.close = AsyncMock()
    named = NamedExchange(exchange_id="mexc", display_name="MEXC", gateway=gateway)
    factory = MagicMock()
    factory.create.return_value = named
    service = PositionFetchService(settings, factory)
    legs = asyncio.run(
        service.fetch_closed_for_symbols(
            ["mexc"],
            ["BTC/USDT:USDT"],
            history_days=7,
        )
    )
    assert len(legs) == 1
    gateway.fetch_closed_positions.assert_awaited_once()

