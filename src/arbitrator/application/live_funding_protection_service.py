from __future__ import annotations

import asyncio
import threading
import time
from decimal import Decimal
from typing import TYPE_CHECKING

from arbitrator.config.logger import logger
from arbitrator.domain.position_leg import PositionLeg

if TYPE_CHECKING:
    from arbitrator.application.hedged_execution_service import HedgedExecutionService
    from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
    from arbitrator.config.settings import Settings
    from arbitrator.domain.exchange_gateway import ExchangeGateway


class LiveFundingProtectionService:
    """Close and reopen live hedged pairs when upcoming funding cost exceeds
    the cost of a round-trip trade.

    Decision logic per open pair at each check:
      net_funding_cost  = funding_charge_we_pay_in_usdt (positive = we pay)
      round_trip_fees   = 2 × (taker_fee_short × notional + taker_fee_long × notional)
      current_spread    = (short_bid - long_ask) / long_ask × 100

    Reopen is worthwhile when:
      net_funding_cost > round_trip_fees
      AND current_spread >= min_reopen_spread_pct

    Only evaluates within a configurable window before settlement, but not
    too close to settlement time (where spreads often spike unreliably).

    Runs on its own background thread with its own asyncio event loop.
    Pair state is taken from live exchange positions each tick (no local store).
    After closing the pair, it immediately calls HedgedExecutionService.open to
    reopen at a fresh notional computed from current market data.
    """

    def __init__(
        self,
        gateways: dict[str, "ExchangeGateway"],
        execution_service: "HedgedExecutionService",
        market_cache: "MarketDataCacheMemory",
        settings: "Settings",
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
        self._min_spread = min_reopen_spread_pct
        self._default_taker_fee = default_taker_fee
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._thread_main,
            name="live-funding-protect",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "live funding protection started | act_window={}s min_spread={}%",
            self._act_window, self._min_spread,
        )

    def stop(self) -> None:
        self._stop.set()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ #
    # Thread entry
    # ------------------------------------------------------------------ #

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
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if self._stop.is_set():
                    raise asyncio.CancelledError

    # ------------------------------------------------------------------ #
    # Main tick
    # ------------------------------------------------------------------ #

    async def _tick(self) -> None:
        now_ms = int(time.time() * 1000)

        # Fetch all live positions → group by symbol
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

            # Funding info from cache
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

            # Net funding cost (positive = we pay)
            notional_short = float(short_leg.contracts) * float(short_leg.contract_size) * float(short_leg.entry_price)
            notional_long = float(long_leg.contracts) * float(long_leg.contract_size) * float(long_leg.entry_price)

            funding_cost = 0.0
            if fi_short and fi_short.rate is not None:
                # Short leg: receives positive funding, pays negative funding
                funding_cost -= notional_short * float(fi_short.rate)
            if fi_long and fi_long.rate is not None:
                # Long leg: pays positive funding, receives negative funding
                funding_cost += notional_long * float(fi_long.rate)

            if funding_cost <= 0.0:
                # We receive net funding — do not reopen
                continue

            # Round-trip fee estimate (2 × open + 2 × close = 4 legs total)
            fee_short = self._taker_fee(short_ex, symbol)
            fee_long = self._taker_fee(long_ex, symbol)
            round_trip_fees = 2.0 * (notional_short * fee_short + notional_long * fee_long)

            if funding_cost <= round_trip_fees:
                continue

            # Current spread check
            short_mid = self._mid_price(short_ex, symbol)
            long_mid = self._mid_price(long_ex, symbol)
            if short_mid is None or long_mid is None or long_mid <= 0.0:
                continue
            current_spread_pct = (short_mid - long_mid) / long_mid * 100.0

            if current_spread_pct < self._min_spread:
                logger.info(
                    "live funding protect skipped: spread too low | sym={} short={} long={} "
                    "spread={:.3f}% min={}%",
                    symbol, short_ex, long_ex, current_spread_pct, self._min_spread,
                )
                continue

            logger.info(
                "live funding protect: closing pair for reopen | sym={} short={} long={} "
                "funding_cost={:.4f} round_trip_fees={:.4f} spread={:.3f}% secs_to_funding={:.0f}",
                symbol, short_ex, long_ex,
                funding_cost, round_trip_fees, current_spread_pct, secs_to_funding,
            )

            # Close via HedgedExecutionService
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
                continue

            # Reopen at fresh notional from current market data
            notional = self._resolve_notional(symbol, short_ex, long_ex, short_mid, long_mid)
            if notional is None:
                logger.warning(
                    "live funding protect: market info missing, cannot reopen | sym={} short={} long={}",
                    symbol, short_ex, long_ex,
                )
                continue
            if short_mid <= 0.0:
                continue

            logger.info(
                "live funding protect: reopening | sym={} short={} long={} notional={:.2f} spread={:.3f}%",
                symbol, short_ex, long_ex, notional, current_spread_pct,
            )
            try:
                open_outcome = await self._exec.open(
                    symbol=symbol,
                    short_exchange_id=short_ex,
                    long_exchange_id=long_ex,
                    notional_usdt=Decimal(str(notional)),
                    price=Decimal(str(short_mid)),
                )
                logger.info(
                    "live funding protect: reopened | sym={} status={} imbalance={}",
                    symbol, open_outcome.status.value, open_outcome.imbalance_pct,
                )
            except Exception:
                logger.exception(
                    "live funding protect: reopen failed | sym={} short={} long={}",
                    symbol, short_ex, long_ex,
                )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _mid_price(self, exchange_id: str, symbol: str) -> float | None:
        quote = self._cache.get_quote(exchange_id, symbol, "futures")
        if quote is None:
            return None
        if quote.bid and quote.ask:
            return round((float(quote.bid) + float(quote.ask)) / 2.0, 8)
        if quote.last:
            return round(float(quote.last), 8)
        return None

    def _taker_fee(self, exchange_id: str, symbol: str) -> float:
        fee_schedule = self._cache.get_fees(exchange_id, symbol)
        if fee_schedule is not None and fee_schedule.futures_taker is not None:
            return float(fee_schedule.futures_taker)
        return self._default_taker_fee

    def _min_notional_for_exchange(
        self, symbol: str, exchange_id: str, live_price: float | None
    ) -> float | None:
        info = self._cache.get_market_info(exchange_id, symbol)
        if info is None:
            return None
        if info.min_order_volume_usdt is not None:
            return info.min_order_volume_usdt
        if (
            info.min_amount_contracts is not None
            and info.contract_size > 0.0
            and live_price is not None
            and live_price > 0.0
        ):
            return info.min_amount_contracts * info.contract_size * live_price
        return None

    def _resolve_notional(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        short_price: float | None = None,
        long_price: float | None = None,
    ) -> float | None:
        min_a = self._min_notional_for_exchange(symbol, short_ex, short_price)
        min_b = self._min_notional_for_exchange(symbol, long_ex, long_price)
        if min_a is None or min_b is None:
            return None
        floor = self._settings.screener_auto_trade_notional_usdt
        return max(min_a, min_b, floor)
