from __future__ import annotations

from arbitrator.application.account_stream_worker import AccountStreamWorker
from arbitrator.application.exchange_orders_service import ExchangeOrdersService
from arbitrator.application.fee_snapshot_service import FeeSnapshotService
from arbitrator.application.funding_accrual_service import FundingAccrualService
from arbitrator.application.funding_rate_worker import FundingRateWorker
from arbitrator.application.funding_reentry_service import FundingReentryService
from arbitrator.application.liquidation_guard_service import LiquidationGuardService
from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.paper_execution_gateway import PaperExecutionGateway
from arbitrator.application.screener_auto_trader import ScreenerAutoTrader
from arbitrator.application.screener_stream_worker import ScreenerStreamWorker
from arbitrator.application.strategy_refresh_worker import StrategyRefreshWorker
from arbitrator.application.strategy_inputs_assembler import StrategyInputsAssembler
from arbitrator.application.strategy_table_service import StrategyTableService
from arbitrator.application.symbol_universe_service import SymbolUniverseService
from arbitrator.config.json_symbol_exclusions_repository import JsonSymbolExclusionsRepository
from arbitrator.config.json_symbol_universe_repository import JsonSymbolUniverseRepository
from arbitrator.config.logger import logger
from arbitrator.config.paper_order_store import PaperOrderStore
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
    """Composition root: mock provider and optional live/paper stream workers."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.mock_provider = MockDataProvider(enabled_exchanges=settings.enabled_exchanges)
        self.screener_worker: ScreenerStreamWorker | None = None
        self.account_worker: AccountStreamWorker | None = None
        self.funding_worker: FundingRateWorker | None = None
        self.market_cache: MarketDataCacheMemory | None = None
        self.strategy_table_service: StrategyTableService | None = None
        self.paper_store = PaperOrderStore(path=settings.paper_orders_path)
        self.paper_gateway: PaperExecutionGateway | None = None
        self.funding_accrual_service: FundingAccrualService | None = None
        self.exchange_orders_service: ExchangeOrdersService | None = None
        self.screener_auto_trader: ScreenerAutoTrader | None = None
        self.liquidation_guard: LiquidationGuardService | None = None
        self.funding_reentry: FundingReentryService | None = None
        self.strategy_refresh_worker: StrategyRefreshWorker | None = None

    def start(self) -> None:
        mode = self._settings.ui_data_mode
        if mode == "live":
            self._start_live_workers()
        elif mode == "paper":
            self._start_paper_workers()
        else:
            logger.info("ui_data_mode=mock_data | stream workers skipped")

    def stop(self) -> None:
        if self.exchange_orders_service is not None:
            self.exchange_orders_service.stop()
            logger.info("exchange orders service stopped")
        if self.funding_accrual_service is not None:
            self.funding_accrual_service.stop()
            logger.info("funding accrual service stopped")
        if self.strategy_refresh_worker is not None:
            self.strategy_refresh_worker.stop()
            logger.info("strategy refresh worker stopped")
        if self.funding_reentry is not None:
            self.funding_reentry.stop()
            logger.info("funding reentry service stopped")
        if self.liquidation_guard is not None:
            self.liquidation_guard.stop()
            logger.info("liquidation guard stopped")
        if self.screener_auto_trader is not None:
            self.screener_auto_trader.stop()
            logger.info("screener auto trader stopped")
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
        if self._settings.ui_data_mode not in ("live", "paper"):
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
        self._start_stream_workers(factory)
        logger.info("live workers started | mode=live")

    def _start_paper_workers(self) -> None:
        factory = Factory(settings=self._settings)
        self._start_stream_workers(factory)
        assert self.market_cache is not None
        self.paper_gateway = PaperExecutionGateway(
            store=self.paper_store, cache=self.market_cache
        )
        self.funding_accrual_service = FundingAccrualService(
            store=self.paper_store,
            cache=self.market_cache,
            interval_seconds=self._settings.funding_refresh_seconds,
        )
        self.funding_accrual_service.start()
        if self._settings.screener_auto_trade_enabled:
            self._start_screener_auto_trader()
        if self._settings.liq_guard_enabled:
            self._start_liquidation_guard()
        if self._settings.funding_reentry_enabled:
            self._start_funding_reentry()
        logger.info("paper workers started | mode=paper orders_path={}", self._settings.paper_orders_path)

    def _start_screener_auto_trader(self) -> None:
        if (
            self.screener_worker is None
            or self.strategy_table_service is None
            or self.paper_gateway is None
        ):
            logger.warning("screener auto trader skipped — workers not ready")
            return
        self.screener_auto_trader = ScreenerAutoTrader(
            settings=self._settings,
            screener_worker=self.screener_worker,
            paper_gateway=self.paper_gateway,
            market_cache=self.market_cache,
        )
        self.screener_auto_trader.start()

    def _start_funding_reentry(self) -> None:
        if self.paper_gateway is None or self.market_cache is None:
            logger.warning("funding reentry service skipped — paper gateway or cache not ready")
            return
        self.funding_reentry = FundingReentryService(
            store=self.paper_store,
            paper_gateway=self.paper_gateway,
            market_cache=self.market_cache,
            settings=self._settings,
            check_interval_seconds=self._settings.funding_reentry_check_interval_seconds,
            act_window_seconds=self._settings.funding_reentry_act_window_seconds,
            skip_within_seconds=self._settings.funding_reentry_skip_within_seconds,
            min_reopen_spread_pct=self._settings.funding_reentry_min_spread_pct,
        )
        self.funding_reentry.start()

    def _start_liquidation_guard(self) -> None:
        if self.paper_gateway is None or self.market_cache is None:
            logger.warning("liquidation guard skipped — paper gateway or cache not ready")
            return
        self.liquidation_guard = LiquidationGuardService(
            store=self.paper_store,
            paper_gateway=self.paper_gateway,
            market_cache=self.market_cache,
            settings=self._settings,
            check_interval_seconds=self._settings.liq_guard_check_interval_seconds,
            warning_pct_to_liq=self._settings.liq_guard_warning_pct_to_liq,
        )
        self.liquidation_guard.start()

    def _start_stream_workers(self, factory: Factory) -> None:
        self.screener_worker = self._create_screener_worker(
            reconnect_nonce=0,
            volume_threshold_usdt=self._settings.stream_min_quote_volume_usdt,
        )
        self.screener_worker.start()
        logger.info("screener worker started")

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
        self.strategy_refresh_worker = StrategyRefreshWorker(
            screener_worker=self.screener_worker,
            table_service=self.strategy_table_service,
            interval_seconds=self._settings.screener_ws_push_seconds,
        )
        self.strategy_refresh_worker.start()
        logger.info("strategy refresh worker started")

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
        logger.info("funding worker started")

        self.account_worker = AccountStreamWorker(settings=self._settings, factory=factory)
        self.account_worker.ensure_running(self._settings.enabled_exchanges)
        logger.info("account worker started")

        self.exchange_orders_service = ExchangeOrdersService(
            settings=self._settings,
            factory=factory,
            account_worker=self.account_worker,
        )
        self.exchange_orders_service.start()
        logger.info("exchange orders service started")
