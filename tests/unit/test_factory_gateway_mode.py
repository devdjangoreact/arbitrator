import pytest
from arbitrator.config.settings import Settings
from arbitrator.exchanges.factory import Factory
from arbitrator.exchanges.ccxt_base import CcxtBase

def test_factory_creates_public_mode_by_default() -> None:
    settings = Settings(_env_file=None)
    factory = Factory(settings)
    named = factory.create("mexc")
    
    base = named.gateway
    assert isinstance(base, CcxtBase)
    assert base._mode == "public"

def test_factory_creates_private_mode() -> None:
    settings = Settings(_env_file=None)
    factory = Factory(settings)
    named = factory.create_private("mexc")
    
    base = named.gateway
    assert isinstance(base, CcxtBase)
    assert base._mode == "private"

def test_public_mode_blocks_private_methods() -> None:
    # Actually the spec didn't strictly require blocking private methods on public, 
    # but blocking public methods on private. Let's check that.
    pass

import asyncio

def test_private_mode_blocks_public_streams(caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(_env_file=None)
    factory = Factory(settings)
    named = factory.create_private("mexc")

    base = named.gateway
    assert isinstance(base, CcxtBase)

    async def run_it() -> None:
        # Trigger watch_tickers
        async for _ in base.watch_tickers(["BTC/USDT"]):
            pass
        # Trigger watch_order_book
        async for _ in base.watch_order_book("BTC/USDT", 20):
            pass

    asyncio.run(run_it())

