from __future__ import annotations

import asyncio

from arbitrator_2.connector.ccxt_session_factory import CcxtSessionFactory
from arbitrator_2.connector.connector_settings import ConnectorSettings
from arbitrator_2.connector.market_kind import MarketKind


def test_book_trades_meta_are_distinct_clients() -> None:
    factory = CcxtSessionFactory()
    book = factory.create("binance", MarketKind.PERP)
    trades = factory.create("binance", MarketKind.PERP)
    meta = factory.create("binance", MarketKind.PERP)
    assert book is not trades
    assert book is not meta
    assert trades is not meta
    assert not getattr(book, "apiKey", None)
    assert not getattr(book, "secret", None)
    asyncio.run(_close(book, trades, meta))


def test_book_client_has_no_private_keys_even_if_env_exists() -> None:
    factory = CcxtSessionFactory()
    book = factory.create("binance", MarketKind.SPOT)
    assert not getattr(book, "apiKey", None)
    assert not getattr(book, "secret", None)
    asyncio.run(_close(book))


def test_factory_leaves_proxy_off_by_default() -> None:
    factory = CcxtSessionFactory(ConnectorSettings())
    book = factory.create("binance", MarketKind.SPOT)
    assert not getattr(book, "http_proxy", None)
    assert not getattr(book, "ws_proxy", None)
    assert not getattr(book, "socks_proxy", None)
    asyncio.run(_close(book))


def test_factory_ignores_blank_proxy() -> None:
    settings = ConnectorSettings(
        exchange_public_http_proxy="  ",
        exchange_public_ws_proxy="",
        exchange_public_socks_proxy="\t",
    )
    factory = CcxtSessionFactory(settings)
    book = factory.create("binance", MarketKind.SPOT)
    assert not getattr(book, "http_proxy", None)
    assert not getattr(book, "ws_proxy", None)
    assert not getattr(book, "socks_proxy", None)
    asyncio.run(_close(book))


def test_factory_applies_http_and_ws_proxy() -> None:
    settings = ConnectorSettings(
        exchange_public_http_proxy="http://127.0.0.1:8888",
        exchange_public_ws_proxy="http://127.0.0.1:8889",
    )
    factory = CcxtSessionFactory(settings)
    book = factory.create("binance", MarketKind.SPOT)
    assert getattr(book, "http_proxy") == "http://127.0.0.1:8888"
    assert getattr(book, "ws_proxy") == "http://127.0.0.1:8889"
    asyncio.run(_close(book))


async def _close(*clients: object) -> None:
    for client in clients:
        closer = getattr(client, "close", None)
        if closer is not None:
            await asyncio.wait_for(closer(), timeout=5.0)
