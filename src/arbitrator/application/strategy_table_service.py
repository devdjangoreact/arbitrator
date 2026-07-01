from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.opportunity_strategy_service import OpportunityStrategyService
from arbitrator.application.strategy_inputs_assembler import StrategyInputsAssembler
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.strategy.strategy_engine import StrategyEngine
from arbitrator.domain.strategy.strategy_math import StrategyMath
from arbitrator.domain.strategy.strategy_table import StrategyTable
from arbitrator.domain.ticker import Ticker


class StrategyTableService:
    """Screener live recompute: futures ticker snapshot -> per-symbol StrategyTable.

    Ingests futures bid/ask/last into the cache, picks the exchange pair by the
    max cross price (higher = short, lower = long; C1/FR-020), and recomputes
    only the symbols whose price changed since the last tick (FR-006/SC-004).
    """

    def __init__(
        self,
        cache: MarketDataCacheMemory,
        assembler: StrategyInputsAssembler,
        engine: StrategyEngine,
        settings: Settings,
    ) -> None:
        self._cache = cache
        self._assembler = assembler
        self._engine = engine
        self._settings = settings
        self._notional = Decimal(str(settings.arb_default_notional_usdt))
        self._default_leverage = settings.opp_default_leverage
        self._last_price: dict[tuple[str, str], float] = {}
        self._tables: dict[str, StrategyTable] = {}

    def refresh(
        self,
        tickers: Mapping[tuple[str, str], Ticker],
        now_ms: int,
    ) -> dict[str, StrategyTable]:
        by_symbol: dict[str, dict[str, Ticker]] = {}
        changed: set[str] = set()
        for (exchange_id, symbol), ticker in tickers.items():
            by_symbol.setdefault(symbol, {})[exchange_id] = ticker
            self._cache.put_quote(
                Quote(
                    exchange_id=exchange_id,
                    symbol=symbol,
                    market_type="futures",
                    bid=StrategyMath.to_decimal(ticker.bid),
                    ask=StrategyMath.to_decimal(ticker.ask),
                    last=StrategyMath.to_decimal(ticker.last),
                    recv_time_ms=now_ms,
                )
            )
            price = ticker.last or 0.0
            if self._last_price.get((exchange_id, symbol)) != price:
                changed.add(symbol)
                self._last_price[(exchange_id, symbol)] = price

        for symbol in changed:
            table = self._compute_symbol(symbol, by_symbol[symbol], now_ms)
            if table is not None:
                self._tables[symbol] = table

        for stale_symbol in [s for s in self._tables if s not in by_symbol]:
            del self._tables[stale_symbol]

        logger.debug(
            "strategy recompute | changed={} symbols={}",
            len(changed),
            len(by_symbol),
        )
        return dict(self._tables)

    def create_opportunity_service(self) -> OpportunityStrategyService:
        return OpportunityStrategyService(
            assembler=self._assembler,
            engine=self._engine,
            settings=self._settings,
        )

    def _compute_symbol(
        self,
        symbol: str,
        tickers_by_exchange: Mapping[str, Ticker],
        now_ms: int,
    ) -> StrategyTable | None:
        priced = {
            exchange_id: ticker.last
            for exchange_id, ticker in tickers_by_exchange.items()
            if ticker.last is not None and ticker.last > 0.0
        }
        if len(priced) < 2:
            return None
        short_exchange_id = max(priced, key=lambda ex: priced[ex])
        long_exchange_id = min(priced, key=lambda ex: priced[ex])
        leverage = dict.fromkeys(tickers_by_exchange, self._default_leverage)
        inputs = self._assembler.assemble(
            symbol=symbol,
            short_exchange_id=short_exchange_id,
            long_exchange_id=long_exchange_id,
            target_volume_usdt=self._notional,
            leverage=leverage,
            now_ms=now_ms,
        )
        return self._engine.compute(inputs)
