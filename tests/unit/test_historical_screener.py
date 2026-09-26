from unittest.mock import MagicMock

from arbitrator.application.market_data.historical_screener_worker import (
    HistoricalScreenerWorker,
)
from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.settings import Settings
from arbitrator.domain.market.ticker import Ticker


def test_historical_screener_scan_from_screener_tickers() -> None:
    settings = Settings(
        historical_screener_enabled=True,
        historical_screener_lookback_minutes=60,
        historical_screener_spread_threshold_pct=1.0,
        enabled_exchanges=["mexc", "bitget"],
    )
    cache = MarketDataCacheMemory()
    store = MagicMock()

    t_mexc = Ticker(
        symbol="BTC/USDT:USDT",
        last=1.05,
        bid=1.05,
        ask=1.06,
        high_24h=None,
        low_24h=None,
        base_volume_24h=None,
        quote_volume_24h=1_000_000.0,
        timestamp_ms=1000,
        funding_rate=0.0001,
    )
    t_bitget = Ticker(
        symbol="BTC/USDT:USDT",
        last=0.90,
        bid=0.89,
        ask=0.90,
        high_24h=None,
        low_24h=None,
        base_volume_24h=None,
        quote_volume_24h=2_000_000.0,
        timestamp_ms=1000,
        funding_rate=-0.0002,
    )
    screener_worker = MagicMock()
    screener_worker.read_state.return_value = (
        {("mexc", "BTC/USDT:USDT"): t_mexc, ("bitget", "BTC/USDT:USDT"): t_bitget},
        [],
        0,
        "Idle",
        0.0,
    )

    worker = HistoricalScreenerWorker(settings, cache, screener_worker, store)
    worker._scan()

    _, opps = worker.read_opportunities()
    assert len(opps) == 1
    assert opps[0].symbol == "BTC/USDT:USDT"
    assert opps[0].max_historical_spread_pct > 15.0
    assert opps[0].short_ex == "mexc"
    assert opps[0].long_ex == "bitget"
    assert opps[0].short_volume_24h == 1_000_000.0


def test_price_deviation_filter_excludes_similar_prices() -> None:
    """T039: price_deviation_filter_pct > 0 should exclude pairs where (max-min)/min*100 < threshold."""
    settings = Settings(
        historical_screener_enabled=True,
        historical_screener_lookback_minutes=60,
        historical_screener_spread_threshold_pct=1.0,
        enabled_exchanges=["mexc", "bitget"],
    )
    cache = MarketDataCacheMemory()
    store = MagicMock()

    # Prices very close — deviation ~0.5%
    t_mexc = Ticker(
        symbol="ETH/USDT:USDT",
        last=1.000,
        bid=1.000,
        ask=1.001,
        high_24h=None,
        low_24h=None,
        base_volume_24h=None,
        quote_volume_24h=1_000_000.0,
        timestamp_ms=1000,
        funding_rate=0.0,
    )
    t_bitget = Ticker(
        symbol="ETH/USDT:USDT",
        last=0.995,
        bid=0.994,
        ask=0.995,
        high_24h=None,
        low_24h=None,
        base_volume_24h=None,
        quote_volume_24h=1_000_000.0,
        timestamp_ms=1000,
        funding_rate=0.0,
    )
    screener_worker = MagicMock()
    screener_worker.read_state.return_value = (
        {("mexc", "ETH/USDT:USDT"): t_mexc, ("bitget", "ETH/USDT:USDT"): t_bitget},
        [],
        0,
        "Idle",
        0.0,
    )

    worker = HistoricalScreenerWorker(settings, cache, screener_worker, store)
    # Set 2% price deviation filter — 0.5% deviation should NOT pass
    worker.update_filters(price_deviation_filter_pct=2.0)
    worker._scan()

    _, opps = worker.read_opportunities()
    assert len(opps) == 0, "Should be filtered out by price deviation threshold"


def test_price_deviation_filter_allows_large_deviation() -> None:
    """T039: price_deviation_filter_pct = 0 disables filter; large deviation should pass."""
    settings = Settings(
        historical_screener_enabled=True,
        historical_screener_lookback_minutes=60,
        historical_screener_spread_threshold_pct=1.0,
        enabled_exchanges=["mexc", "bitget"],
    )
    cache = MarketDataCacheMemory()
    store = MagicMock()

    # Prices far apart — deviation ~16%
    t_mexc = Ticker(
        symbol="BTC/USDT:USDT",
        last=1.05,
        bid=1.05,
        ask=1.06,
        high_24h=None,
        low_24h=None,
        base_volume_24h=None,
        quote_volume_24h=1_000_000.0,
        timestamp_ms=1000,
        funding_rate=0.0,
    )
    t_bitget = Ticker(
        symbol="BTC/USDT:USDT",
        last=0.90,
        bid=0.89,
        ask=0.90,
        high_24h=None,
        low_24h=None,
        base_volume_24h=None,
        quote_volume_24h=1_000_000.0,
        timestamp_ms=1000,
        funding_rate=0.0,
    )
    screener_worker = MagicMock()
    screener_worker.read_state.return_value = (
        {("mexc", "BTC/USDT:USDT"): t_mexc, ("bitget", "BTC/USDT:USDT"): t_bitget},
        [],
        0,
        "Idle",
        0.0,
    )

    worker = HistoricalScreenerWorker(settings, cache, screener_worker, store)
    # 2% threshold — 16% deviation should pass
    worker.update_filters(price_deviation_filter_pct=2.0)
    worker._scan()

    _, opps = worker.read_opportunities()
    assert len(opps) == 1, "Large deviation should pass filter"
