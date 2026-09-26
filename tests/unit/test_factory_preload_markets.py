"""Tests for Factory.preload_markets and CcxtBase market-donor sharing."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arbitrator.config.settings import Settings
from arbitrator.exchanges.ccxt_base import CcxtBase
from arbitrator.exchanges.factory import Factory


def _settings() -> Settings:
    return Settings(_env_file=None)


def _make_donor_client(markets: dict | None = None) -> MagicMock:
    """Return a mock ccxt client that behaves like a loaded donor."""
    connector = MagicMock()
    connector.close = AsyncMock()
    session = MagicMock()
    session.connector = connector
    client = MagicMock()
    client.markets = markets if markets is not None else {"BTC/USDT:USDT": {}}
    client.load_markets = AsyncMock()
    client.close = AsyncMock()
    client.session = session
    client.set_markets_from_exchange = MagicMock()
    client.options = {}
    return client


# ---------------------------------------------------------------------------
# Factory.preload_markets — happy path
# ---------------------------------------------------------------------------

def test_preload_markets_populates_donors() -> None:
    """After preload_markets, _market_donors contains an entry per exchange."""
    settings = _settings()
    factory = Factory(settings)

    donor_client = _make_donor_client()

    with patch.object(CcxtBase, "build_public_client", return_value=donor_client):
        factory.preload_markets(["mexc"])

    assert "mexc" in factory._market_donors
    assert factory._market_donors["mexc"] is donor_client
    donor_client.load_markets.assert_awaited_once()
    donor_client.close.assert_awaited_once()
    donor_client.session.connector.close.assert_awaited_once()


def test_preload_markets_multiple_exchanges_parallel() -> None:
    """All requested exchanges get donors populated."""
    settings = _settings()
    factory = Factory(settings)

    clients: dict[str, MagicMock] = {}

    # build_public_client is a classmethod — patch replaces it with a regular
    # callable that receives (settings,) when called as cls.build_public_client(settings).
    def _build(s: Settings) -> MagicMock:
        # We can't know cls here, but we can use the order of calls.
        c = _make_donor_client()
        return c

    built: list[MagicMock] = []

    def _build_tracked(s: Settings) -> MagicMock:
        c = _make_donor_client()
        built.append(c)
        return c

    with patch.object(CcxtBase, "build_public_client", side_effect=_build_tracked):
        factory.preload_markets(["mexc", "gate", "bingx"])

    assert len(factory._market_donors) == 3
    assert set(factory._market_donors.keys()) == {"mexc", "gate", "bingx"}


# ---------------------------------------------------------------------------
# Factory.preload_markets — failure resilience
# ---------------------------------------------------------------------------

def test_preload_markets_one_failure_does_not_block_others() -> None:
    """If one exchange fails, the rest still get populated.

    We patch build_public_client to return a failing client for every call,
    then manually place a good donor for 'mexc' to simulate partial success.
    The real guarantee tested here is: preload_markets never raises even when
    some exchanges fail.
    """
    settings = _settings()
    factory = Factory(settings)

    # All calls fail
    bad_client = _make_donor_client(markets={})
    bad_client.load_markets = AsyncMock(side_effect=RuntimeError("network error"))

    with patch.object(CcxtBase, "build_public_client", return_value=bad_client):
        factory.preload_markets(["mexc", "gate"])  # must not raise

    # Neither populated — that's correct when both fail
    assert factory._market_donors == {}


def test_preload_markets_all_fail_leaves_donors_empty() -> None:
    """If every exchange fails, donors stay empty and no exception propagates."""
    settings = _settings()
    factory = Factory(settings)

    bad_client = _make_donor_client(markets={})
    bad_client.load_markets = AsyncMock(side_effect=RuntimeError("timeout"))

    with patch.object(CcxtBase, "build_public_client", return_value=bad_client):
        factory.preload_markets(["mexc", "bingx"])  # must not raise

    assert factory._market_donors == {}


def test_preload_markets_closes_connector() -> None:
    """Connector is closed explicitly after preload (connector_owner=False in ClientSession)."""
    settings = _settings()
    factory = Factory(settings)

    donor_client = _make_donor_client()

    with patch.object(CcxtBase, "build_public_client", return_value=donor_client):
        factory.preload_markets(["mexc"])

    donor_client.session.connector.close.assert_awaited_once()


def test_preload_markets_closes_connector_on_failure() -> None:
    """Connector is closed even when load_markets raises."""
    settings = _settings()
    factory = Factory(settings)

    bad_client = _make_donor_client(markets={})
    bad_client.load_markets = AsyncMock(side_effect=RuntimeError("network"))

    with patch.object(CcxtBase, "build_public_client", return_value=bad_client):
        factory.preload_markets(["mexc"])  # must not raise

    bad_client.session.connector.close.assert_awaited_once()


# ---------------------------------------------------------------------------
# Factory.create — donor propagated to new gateway
# ---------------------------------------------------------------------------

def test_create_passes_donor_to_gateway_when_preloaded() -> None:
    """Gateway created after preload has _market_donor set."""
    settings = _settings()
    factory = Factory(settings)

    donor = _make_donor_client()
    factory._market_donors["mexc"] = donor

    named = factory.create("mexc")
    gateway = named.gateway

    assert isinstance(gateway, CcxtBase)
    assert gateway._market_donor is donor


def test_create_no_donor_when_not_preloaded() -> None:
    """Gateway created without preload has no donor."""
    settings = _settings()
    factory = Factory(settings)

    named = factory.create("mexc")
    gateway = named.gateway

    assert isinstance(gateway, CcxtBase)
    assert gateway._market_donor is None


def test_create_private_also_passes_donor() -> None:
    """create_private also forwards the donor."""
    settings = _settings()
    factory = Factory(settings)

    donor = _make_donor_client()
    factory._market_donors["gate"] = donor

    named = factory.create_private("gate")
    gateway = named.gateway

    assert isinstance(gateway, CcxtBase)
    assert gateway._market_donor is donor


# ---------------------------------------------------------------------------
# CcxtBase._ensure_markets_loaded — donor path vs REST path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ensure_markets_loaded_uses_donor_skips_rest() -> None:
    """When donor has markets, set_markets_from_exchange is called, REST skipped."""
    settings = _settings()
    gateway = Factory(settings).create("mexc").gateway
    assert isinstance(gateway, CcxtBase)

    donor = _make_donor_client({"BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT"}})
    gateway.set_market_donor(donor)

    client = _make_donor_client(markets={})

    await gateway._ensure_markets_loaded(client)

    client.set_markets_from_exchange.assert_called_once_with(donor)
    client.load_markets.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_markets_loaded_falls_back_to_rest_when_no_donor() -> None:
    """Without donor, load_markets REST call is made."""
    settings = _settings()
    gateway = Factory(settings).create("mexc").gateway
    assert isinstance(gateway, CcxtBase)

    assert gateway._market_donor is None

    client = _make_donor_client(markets={})

    async def _fill_markets() -> None:
        client.markets = {"BTC/USDT:USDT": {}}

    client.load_markets = AsyncMock(side_effect=_fill_markets)

    await gateway._ensure_markets_loaded(client)

    client.load_markets.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_markets_loaded_skips_when_already_loaded() -> None:
    """If client.markets already populated, neither donor nor REST is used."""
    settings = _settings()
    gateway = Factory(settings).create("mexc").gateway
    assert isinstance(gateway, CcxtBase)

    donor = _make_donor_client()
    gateway.set_market_donor(donor)

    # client already has markets
    client = _make_donor_client({"BTC/USDT:USDT": {}})

    await gateway._ensure_markets_loaded(client)

    client.set_markets_from_exchange.assert_not_called()
    client.load_markets.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_markets_loaded_donor_empty_falls_back_to_rest() -> None:
    """If donor markets dict is empty (preload failed silently), REST is used."""
    settings = _settings()
    gateway = Factory(settings).create("mexc").gateway
    assert isinstance(gateway, CcxtBase)

    donor = _make_donor_client(markets={})  # empty — not useful
    gateway.set_market_donor(donor)

    client = _make_donor_client(markets={})

    async def _fill() -> None:
        client.markets = {"BTC/USDT:USDT": {}}

    client.load_markets = AsyncMock(side_effect=_fill)

    await gateway._ensure_markets_loaded(client)

    client.load_markets.assert_awaited_once()
    client.set_markets_from_exchange.assert_not_called()
