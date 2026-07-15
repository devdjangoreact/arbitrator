from __future__ import annotations

import asyncio
import threading
import time
from typing import TYPE_CHECKING

from arbitrator.config.logger import logger
from arbitrator.domain.account.position_leg import PositionLeg

if TYPE_CHECKING:
    from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
    from arbitrator.application.trading.hedged_execution_service import HedgedExecutionService
    from arbitrator.config.settings import Settings
    from arbitrator.domain.exchange.exchange_gateway import ExchangeGateway


class LiveFundingProtectionService:
    """Close live hedged pairs when upcoming funding cost exceeds round-trip fees.

    Does not reopen — LiveAutoTrader opens new pairs when screener conditions match.
    """

    def __init__(
        self,
        gateways: dict[str, ExchangeGateway],
        execution_service: HedgedExecutionService,
        market_cache: MarketDataCacheMemory,
        settings: Settings,
        *,
        check_interval_seconds: float = 30.0,
        act_window_seconds: float = 300.0,
        skip_within_seconds: float = 60.0,
        min_reopen_spread_pct: float = 0.1,
        default_taker_fee: float = 0.0006,
    ) -> None:
        self._gateways = gateways
        self._exec = execution_service
        self._cache = market_cache
        self._settings = settings
        self._interval = check_interval_seconds
        self._act_window = act_window_seconds
        self._skip_window = skip_within_seconds
        _ = min_reopen_spread_pct  # kept for wiring compat; reopen removed
        self._default_taker_fee = default_taker_fee
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._thread_main,
            name="live-funding-protect",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "live funding protection started | act_window={}s close_only=true",
            self._act_window,
        )

    def stop(self) -> None:
        self._stop.set()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_main())
        except asyncio.CancelledError:
            logger.info("live funding protection stopped")
        except Exception:
            logger.exception("live funding protection crashed")

    async def _async_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("live funding protection tick failed")
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._loop.create_future()),
                    timeout=self._interval,
                )
            except (TimeoutError, asyncio.CancelledError):
                if self._stop.is_set():
                    raise asyncio.CancelledError

    async def _tick(self) -> None:
        now_ms = int(time.time() * 1000)

        positions_by_symbol: dict[str, list[tuple[str, PositionLeg]]] = {}
        for exchange_id, gateway in self._gateways.items():
            try:
                legs = await gateway.fetch_open_positions()
            except Exception:
                logger.exception(
                    "live funding protect: fetch_open_positions failed | ex={}", exchange_id
                )
                continue
            for leg in legs:
                positions_by_symbol.setdefault(leg.symbol, []).append((exchange_id, leg))

        for symbol, entries in positions_by_symbol.items():
            short_entries = [(ex, leg) for ex, leg in entries if leg.side == "short"]
            long_entries = [(ex, leg) for ex, leg in entries if leg.side == "long"]
            if not short_entries or not long_entries:
                continue

            short_ex, short_leg = short_entries[0]
            long_ex, long_leg = long_entries[0]

            fi_short = self._cache.get_funding(short_ex, symbol)
            fi_long = self._cache.get_funding(long_ex, symbol)

            times: list[int] = []
            if fi_short and fi_short.next_settlement_ms:
                times.append(fi_short.next_settlement_ms)
            if fi_long and fi_long.next_settlement_ms:
                times.append(fi_long.next_settlement_ms)
            if not times:
                continue

            next_settlement_ms = min(times)
            secs_to_funding = (next_settlement_ms - now_ms) / 1000.0

            if secs_to_funding > self._act_window or secs_to_funding < self._skip_window:
                continue

            notional_short = (
                float(short_leg.contracts) * float(short_leg.contract_size) * float(short_leg.entry_price)
            )
            notional_long = (
                float(long_leg.contracts) * float(long_leg.contract_size) * float(long_leg.entry_price)
            )

            funding_cost = 0.0
            if fi_short and fi_short.rate is not None:
                funding_cost -= notional_short * float(fi_short.rate)
            if fi_long and fi_long.rate is not None:
                funding_cost += notional_long * float(fi_long.rate)

            if funding_cost <= 0.0:
                continue

            fee_short = self._taker_fee(short_ex, symbol)
            fee_long = self._taker_fee(long_ex, symbol)
            round_trip_fees = 2.0 * (notional_short * fee_short + notional_long * fee_long)

            if funding_cost <= round_trip_fees:
                continue

            logger.info(
                "live funding protect: closing pair | sym={} short={} long={} "
                "funding_cost={:.4f} round_trip_fees={:.4f} secs_to_funding={:.0f}",
                symbol, short_ex, long_ex,
                funding_cost, round_trip_fees, secs_to_funding,
            )
            logger["trades/live_trades.log"].info(
                "FUNDING_CLOSE | sym={} short={} long={} funding_cost={:.4f}"
                " round_trip_fees={:.4f} secs_to_funding={:.0f}",
                symbol, short_ex, long_ex, funding_cost, round_trip_fees, secs_to_funding,
            )

            try:
                close_outcome = await self._exec.close_all(
                    symbol=symbol,
                    short_exchange_id=short_ex,
                    long_exchange_id=long_ex,
                )
                logger.info(
                    "live funding protect: closed | sym={} status={} imbalance={}",
                    symbol, close_outcome.status.value, close_outcome.imbalance_pct,
                )
            except Exception:
                logger.exception(
                    "live funding protect: close_all failed | sym={} short={} long={}",
                    symbol, short_ex, long_ex,
                )

    def _taker_fee(self, exchange_id: str, symbol: str) -> float:
        fee_schedule = self._cache.get_fees(exchange_id, symbol)
        if fee_schedule is not None and fee_schedule.futures_taker is not None:
            return float(fee_schedule.futures_taker)
        return self._default_taker_fee
