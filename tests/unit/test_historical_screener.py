from decimal import Decimal
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

    status, opps = worker.read_opportunities()
    assert status == "Running"
    assert len(opps) == 1
    assert opps[0].symbol == "BTC/USDT:USDT"
    assert opps[0].max_historical_spread_pct > 15.0
    assert opps[0].short_ex == "mexc"
    assert opps[0].long_ex == "bitget"
    assert opps[0].short_volume_24h == 1_000_000.0
