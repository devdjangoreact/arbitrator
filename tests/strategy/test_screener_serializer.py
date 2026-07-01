from __future__ import annotations

from decimal import Decimal

from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.strategy_inputs_assembler import StrategyInputsAssembler
from arbitrator.application.strategy_table_service import StrategyTableService
from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.strategies.funding_diff_dates_calculator import (
    FundingDiffDatesCalculator,
)
from arbitrator.domain.strategy.strategies.funding_ff_calculator import FundingFfCalculator
from arbitrator.domain.strategy.strategies.funding_fs_calculator import FundingFsCalculator
from arbitrator.domain.strategy.strategies.futures_futures_calculator import (
    FuturesFuturesCalculator,
)
from arbitrator.domain.strategy.strategies.futures_spot_1ex_calculator import (
    FuturesSpot1exCalculator,
)
from arbitrator.domain.strategy.strategies.futures_spot_2ex_calculator import (
    FuturesSpot2exCalculator,
)
from arbitrator.domain.strategy.strategy_engine import StrategyEngine
from arbitrator.domain.strategy.strategy_kind import StrategyKind
from arbitrator.domain.ticker import Ticker

NOW_MS = 1_700_000_000_000


def _ticker(symbol: str, *, last: float, bid: float, ask: float, volume: float) -> Ticker:
    return Ticker(
        symbol=symbol,
        last=last,
        bid=bid,
        ask=ask,
        high_24h=None,
        low_24h=None,
        base_volume_24h=None,
        quote_volume_24h=volume,
        timestamp_ms=NOW_MS,
        funding_rate=None,
    )


def _engine() -> StrategyEngine:
    return StrategyEngine(
        [
            FuturesFuturesCalculator(),
            FuturesSpot2exCalculator(),
            FuturesSpot1exCalculator(),
            FundingFfCalculator(),
            FundingFsCalculator(),
            FundingDiffDatesCalculator(),
        ]
    )


def _service(cache: MarketDataCacheMemory) -> StrategyTableService:
    settings = Settings()
    assembler = StrategyInputsAssembler(cache, settings)
    return StrategyTableService(cache, assembler, _engine(), settings)


def _seed_fees(cache: MarketDataCacheMemory, symbol: str, *exchanges: str) -> None:
    for exchange_id in exchanges:
        cache.put_fees(
            FeeSchedule(
                exchange_id=exchange_id,
                symbol=symbol,
                futures_maker=Decimal("0.0002"),
                futures_taker=Decimal("0.0005"),
                spot_maker=None,
                spot_taker=None,
            )
        )


def test_strategy_table_service_computes_futures_futures_live() -> None:
    symbol = "DOGE/USDT:USDT"
    cache = MarketDataCacheMemory()
    _seed_fees(cache, symbol, "mexc", "bingx")
    service = _service(cache)
    tickers = {
        ("mexc", symbol): _ticker(symbol, last=1.10, bid=1.10, ask=1.11, volume=2_000_000.0),
        ("bingx", symbol): _ticker(symbol, last=1.00, bid=0.99, ask=1.00, volume=1_500_000.0),
    }
    tables = service.refresh(tickers, NOW_MS)

    table = tables[symbol]
    ff = table.results[StrategyKind.futures_futures]
    assert ff.available is True
    # spread 10% on 100 USDT notional, taker fees 0.2 -> net 9.8
    assert ff.net_profit_usdt == Decimal("9.8")


def test_strategy_screener_serializer_maps_na_for_missing_data() -> None:
    from arbitrator.presentation.serializers.screener_serializer import ScreenerSerializer

    symbol = "DOGE/USDT:USDT"
    cache = MarketDataCacheMemory()
    _seed_fees(cache, symbol, "mexc", "bingx")
    service = _service(cache)
    tickers = {
        ("mexc", symbol): _ticker(symbol, last=1.10, bid=1.10, ask=1.11, volume=2_000_000.0),
        ("bingx", symbol): _ticker(symbol, last=1.00, bid=0.99, ask=1.00, volume=1_500_000.0),
    }
    tables = service.refresh(tickers, NOW_MS)
    snapshot = ScreenerSerializer(Settings()).serialize(tickers, tables, "Live", len(tables))

    assert len(snapshot.rows) == 1
    row = snapshot.rows[0]
    assert row.asset == "DOGE/USDT"
    assert row.short_exchange_id == "mexc"
    assert row.long_exchange_id == "bingx"
    # futures_futures has a real number; spot/funding strategies degrade to N/A (None).
    assert row.strategy_profits.futures_futures == 9.8
    assert row.strategy_profits.futures_spot_1ex is None
    assert row.strategy_profits.funding_ff is None
    assert snapshot.default_opportunity.symbol == "DOGE/USDT"


def test_strategy_table_service_recomputes_only_changed_symbols() -> None:
    sym_a = "DOGE/USDT:USDT"
    sym_b = "SOL/USDT:USDT"
    cache = MarketDataCacheMemory()
    _seed_fees(cache, sym_a, "mexc", "bingx")
    _seed_fees(cache, sym_b, "mexc", "bingx")
    service = _service(cache)

    base = {
        ("mexc", sym_a): _ticker(sym_a, last=1.10, bid=1.10, ask=1.11, volume=2_000_000.0),
        ("bingx", sym_a): _ticker(sym_a, last=1.00, bid=0.99, ask=1.00, volume=1_500_000.0),
        ("mexc", sym_b): _ticker(sym_b, last=2.10, bid=2.10, ask=2.11, volume=2_000_000.0),
        ("bingx", sym_b): _ticker(sym_b, last=2.00, bid=1.99, ask=2.00, volume=1_500_000.0),
    }
    first = service.refresh(base, NOW_MS)
    table_a = first[sym_a]

    # Only sym_b price moves; sym_a unchanged -> its table object must be reused.
    moved = dict(base)
    moved[("mexc", sym_b)] = _ticker(sym_b, last=2.20, bid=2.20, ask=2.21, volume=2_000_000.0)
    second = service.refresh(moved, NOW_MS + 1000)

    assert second[sym_a] is table_a
    assert second[sym_b] is not first[sym_b]
