from __future__ import annotations

from arbitrator.domain.universe.symbol_market_info import SymbolMarketInfoParser
from arbitrator.domain.universe.symbol_normalizer import SymbolNormalizer


def test_to_swap_symbol_from_display() -> None:
    assert SymbolNormalizer.to_swap_symbol("DOGE/USDT") == "DOGE/USDT:USDT"


def test_to_swap_symbol_idempotent() -> None:
    assert SymbolNormalizer.to_swap_symbol("DOGE/USDT:USDT") == "DOGE/USDT:USDT"


def test_base_asset_from_display() -> None:
    assert SymbolNormalizer.base_asset("DOGE/USDT") == "DOGE"


def test_market_info_from_cost_limits() -> None:
    market: dict[str, object] = {
        "symbol": "DOGE/USDT:USDT",
        "base": "DOGE",
        "id": "DOGE_USDT",
        "contractSize": 1.0,
        "limits": {
            "cost": {"min": 5.0, "max": 100000.0},
            "amount": {"min": 1.0, "max": 50000.0},
        },
    }
    info = SymbolMarketInfoParser.from_ccxt_market(market, mark_price=0.2)
    assert info is not None
    assert info.unified_symbol == "DOGE/USDT:USDT"
    assert info.base_asset == "DOGE"
    assert info.native_market_id == "DOGE_USDT"
    assert info.min_order_volume_usdt == 5.0
    assert info.max_order_volume_usdt == 100000.0


def test_market_info_amount_fallback() -> None:
    market: dict[str, object] = {
        "symbol": "DOGE/USDT:USDT",
        "base": "DOGE",
        "id": "DOGE-USDT",
        "contractSize": 1.0,
        "limits": {
            "amount": {"min": 10.0, "max": 1000.0},
        },
    }
    info = SymbolMarketInfoParser.from_ccxt_market(market, mark_price=0.25)
    assert info is not None
    assert info.min_order_volume_usdt == 2.5
    assert info.max_order_volume_usdt == 250.0
