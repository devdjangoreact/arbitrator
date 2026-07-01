from __future__ import annotations

from arbitrator.application.account_stream_worker import AccountStreamWorker
from arbitrator.application.fee_snapshot_service import FeeSnapshotService
from arbitrator.application.funding_rate_worker import FundingRateWorker
from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.screener_stream_worker import ScreenerStreamWorker
from arbitrator.application.strategy_inputs_assembler import StrategyInputsAssembler
from arbitrator.application.strategy_table_service import StrategyTableService
from arbitrator.application.symbol_universe_service import SymbolUniverseService
from arbitrator.config.json_symbol_exclusions_repository import JsonSymbolExclusionsRepository
from arbitrator.config.json_symbol_universe_repository import JsonSymbolUniverseRepository
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
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
from arbitrator.exchanges.factory import Factory
from arbitrator.presentation.mock.mock_data_provider import MockDataProvider


class AppRuntime:
    """Composition root: mock provider and optional live stream workers."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.mock_provider = MockDataProvider(enabled_exchanges=settings.enabled_exchanges)
        self.screener_worker: ScreenerStreamWorker | None = None
        self.account_worker: AccountStreamWorker | None = None
        self.funding_worker: FundingRateWorker | None = None
        self.market_cache: MarketDataCacheMemory | None = None
        self.strategy_table_service: StrategyTableService | None = None

    def start(self) -> None:
        if self._settings.ui_data_mode == "live":
            self._start_live_workers()
        else:
            logger.info("ui_data_mode=mock_data | stream workers skipped")

    def stop(self) -> None:
        if self.screener_worker is not None:
            self.screener_worker.stop()
            logger.info("screener worker stopped")
        if self.account_worker is not None:
            self.account_worker.stop()
            logger.info("account worker stopped")
        if self.funding_worker is not None:
            self.funding_worker.stop()
            logger.info("funding worker stopped")

    def _create_screener_worker(
        self,
        *,
        reconnect_nonce: int,
        volume_threshold_usdt: float,
    ) -> ScreenerStreamWorker:
        factory = Factory(settings=self._settings)
        universe_repo = JsonSymbolUniverseRepository(path=self._settings.symbols_universe_path)
        exclusions_repo = JsonSymbolExclusionsRepository(path=self._settings.exclusions_path)
        universe_service = SymbolUniverseService(
            repository=universe_repo,
            exclusions=exclusions_repo,
            ttl_hours=self._settings.universe_ttl_hours,
            min_exchanges=self._settings.min_exchanges_per_symbol,
        )
        return ScreenerStreamWorker(
            settings=self._settings,
            factory=factory,
            universe_service=universe_service,
            reconnect_nonce=reconnect_nonce,
            volume_threshold_usdt=volume_threshold_usdt,
        )

    def reconnect_screener(self, stream_min_volume_usdt: float) -> None:
        if self._settings.ui_data_mode != "live":
            return
        nonce = 0
        if self.screener_worker is not None:
            nonce = self.screener_worker.reconnect_nonce + 1
            self.screener_worker.stop()
            logger.info(
                "screener reconnect requested | nonce={} stream_min_usdt={}",
                nonce,
                stream_min_volume_usdt,
            )
        self.screener_worker = self._create_screener_worker(
            reconnect_nonce=nonce,
            volume_threshold_usdt=stream_min_volume_usdt,
        )
        self.screener_worker.start()

    def _start_live_workers(self) -> None:
        factory = Factory(settings=self._settings)
        self.screener_worker = self._create_screener_worker(
            reconnect_nonce=0,
            volume_threshold_usdt=self._settings.stream_min_quote_volume_usdt,
        )
        self.screener_worker.start()
        logger.info("screener worker started | mode=live")

        self.market_cache = MarketDataCacheMemory()
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
        assembler = StrategyInputsAssembler(self.market_cache, self._settings)
        self.strategy_table_service = StrategyTableService(
            cache=self.market_cache,
            assembler=assembler,
            engine=engine,
            settings=self._settings,
        )
        self.funding_worker = FundingRateWorker(
            settings=self._settings,
            factory=factory,
            cache=self.market_cache,
            fee_service=FeeSnapshotService(self.market_cache),
            symbols_provider=lambda: (
                self.screener_worker.read_state()[1] if self.screener_worker is not None else []
            ),
        )
        self.funding_worker.start()
        logger.info("funding worker started | mode=live")

        self.account_worker = AccountStreamWorker(settings=self._settings, factory=factory)
        self.account_worker.ensure_running(self._settings.enabled_exchanges)
        logger.info("account worker started | mode=live")
