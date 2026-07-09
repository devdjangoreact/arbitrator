from __future__ import annotations

from decimal import Decimal

from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.opportunities.opportunity_session_state import OpportunitySessionState
from arbitrator.application.opportunities.opportunity_stream_worker import OpportunityStreamState
from arbitrator.application.opportunities.opportunity_strategy_service import OpportunityStrategyService
from arbitrator.application.strategies.strategy_inputs_assembler import StrategyInputsAssembler
from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.strategies.futures_futures_calculator import (
    FuturesFuturesCalculator,
)
from arbitrator.domain.strategy.strategies.funding_ff_calculator import FundingFfCalculator
from arbitrator.domain.strategy.strategies.funding_fs_calculator import FundingFsCalculator
from arbitrator.domain.strategy.strategies.funding_diff_dates_calculator import (
    FundingDiffDatesCalculator,
)
from arbitrator.domain.strategy.strategies.futures_spot_1ex_calculator import (
    FuturesSpot1exCalculator,
)
from arbitrator.domain.strategy.strategies.futures_spot_2ex_calculator import (
    FuturesSpot2exCalculator,
)
from arbitrator.domain.strategy.strategy_engine import StrategyEngine
from arbitrator.domain.strategy.fee_schedule import FeeSchedule
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.market.ticker import Ticker
from arbitrator.presentation.serializers.opportunity_serializer import OpportunitySerializer

NOW_MS = 1_700_000_000_000


def _service(cache: MarketDataCacheMemory) -> OpportunityStrategyService:
    settings = Settings()
    assembler = StrategyInputsAssembler(cache, settings)
    engine = StrategyEngine(
        [
            FuturesFuturesCalculator(),
            FuturesSpot2exCalculator(),
            FuturesSpot1exCalculator(),
            FundingFfCalculator(),
            FundingFsCalculator(),
            FundingDiffDatesCalculator(),
        ]
    )
    return OpportunityStrategyService(assembler, engine, settings)


def test_opportunity_serializer_builds_snapshot_with_strategy_rows() -> None:
    symbol = "DOGE/USDT:USDT"
    cache = MarketDataCacheMemory()
    cache.put_quote(
        Quote(
            exchange_id="mexc",
            symbol=symbol,
            market_type="futures",
            bid=Decimal("1.10"),
            ask=Decimal("1.11"),
            last=Decimal("1.10"),
            recv_time_ms=NOW_MS,
        )
    )
    cache.put_quote(
        Quote(
            exchange_id="bingx",
            symbol=symbol,
            market_type="futures",
            bid=Decimal("1.00"),
            ask=Decimal("1.01"),
            last=Decimal("1.00"),
            recv_time_ms=NOW_MS,
        )
    )
    cache.put_fees(
        FeeSchedule(
            exchange_id="mexc",
            symbol=symbol,
            futures_maker=Decimal("0.0002"),
            futures_taker=Decimal("0.0005"),
            spot_maker=None,
            spot_taker=None,
        )
    )
    cache.put_fees(
        FeeSchedule(
            exchange_id="bingx",
            symbol=symbol,
            futures_maker=Decimal("0.0002"),
            futures_taker=Decimal("0.0005"),
            spot_maker=None,
            spot_taker=None,
        )
    )
    session = OpportunitySessionState(Settings())
    stream_state = OpportunityStreamState(
        books={},
        tickers={
            "mexc": Ticker(
                symbol=symbol,
                last=1.10,
                bid=1.10,
                ask=1.11,
                high_24h=None,
                low_24h=None,
                base_volume_24h=None,
                quote_volume_24h=1_000_000.0,
                timestamp_ms=NOW_MS,
                funding_rate=None,
            ),
            "bingx": Ticker(
                symbol=symbol,
                last=1.00,
                bid=1.00,
                ask=1.01,
                high_24h=None,
                low_24h=None,
                base_volume_24h=None,
                quote_volume_24h=900_000.0,
                timestamp_ms=NOW_MS,
                funding_rate=None,
            ),
        },
        prices={"mexc": 1.10, "bingx": 1.00},
        trades=(),
        price_ring=((NOW_MS, "mexc", 1.10), (NOW_MS, "bingx", 1.00)),
        status="Live",
    )
    snapshot = OpportunitySerializer(Settings()).serialize(
        display_symbol="DOGE/USDT",
        swap_symbol=symbol,
        short_exchange_id="mexc",
        long_exchange_id="bingx",
        session=session,
        stream_state=stream_state,
        strategy_service=_service(cache),
        cache=cache,
        account_worker=None,
        now_ms=NOW_MS,
    )

    assert snapshot.symbol == "DOGE/USDT"
    assert snapshot.short_exchange_id == "mexc"
    assert snapshot.long_exchange_id == "bingx"
    assert len(snapshot.strategy_rows) == 6
    ff = next(row for row in snapshot.strategy_rows if row.strategy_id == "futures_futures")
    assert ff.net_profit_usdt is not None
