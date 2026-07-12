from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

from arbitrator.config.logger import logger
from arbitrator.domain.account.position_leg import PositionLeg

if TYPE_CHECKING:
    from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
    from arbitrator.application.trading.hedged_execution_service import HedgedExecutionService
    from arbitrator.config.settings import Settings
    from arbitrator.domain.exchange.exchange_gateway import ExchangeGateway


class LiveLiquidationGuardService:
    """Monitors real open positions across all live exchanges and closes pairs
    that are approaching liquidation price.

    Liquidation price is derived from **real position data** (entry price and
    contracts) plus the leverage value from exchange position metadata when
    available, falling back to `settings.opp_default_leverage`.

    Cross-margin approximation (conservative):
      Short: liq_px = entry * (1 + 1/leverage * (1 - MM_RATE))
      Long:  liq_px = entry * (1 - 1/leverage * (1 - MM_RATE))

    When the current mark/mid price has consumed >= warning_pct_to_liq of the
    margin buffer, the full pair is closed via HedgedExecutionService.close_all.
    If only one leg is found (unhedged state), it is force-closed via the
    exchange gateway directly.

    Runs on its own background thread with its own asyncio event loop.
    """

    _MM_RATE = 0.005  # 0.5% maintenance margin (conservative)

    def __init__(
        self,
        gateways: dict[str, ExchangeGateway],
        execution_service: HedgedExecutionService,
        market_cache: MarketDataCacheMemory,
        settings: Settings,
        *,
        check_interval_seconds: float = 5.0,
        warning_pct_to_liq: float = 80.0,
    ) -> None:
        self._gateways = gateways
        self._exec = execution_service
        self._cache = market_cache
        self._settings = settings
        self._interval = check_interval_seconds
        self._warning_pct = warning_pct_to_liq
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._thread_main,
            name="live-liq-guard",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "live liquidation guard started | interval={}s warning_pct={}%",
            self._interval,
            self._warning_pct,
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
            logger.info("live liquidation guard stopped")
        except Exception:
            logger.exception("live liquidation guard crashed")

    async def _async_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("live liquidation guard tick failed")
            try:
                await asyncio.wait_for(
                    asyncio.shield(self._loop.create_future()),
                    timeout=self._interval,
                )
            except (TimeoutError, asyncio.CancelledError):
                if self._stop.is_set():
                    raise asyncio.CancelledError

    # ------------------------------------------------------------------ #
    # Main tick
    # ------------------------------------------------------------------ #

    async def _tick(self) -> None:
        # Fetch all open positions from each exchange gateway
        # Key: symbol → list of (exchange_id, PositionLeg)
        positions_by_symbol: dict[str, list[tuple[str, PositionLeg]]] = {}
        for exchange_id, gateway in self._gateways.items():
            try:
                legs = await gateway.fetch_open_positions()
            except Exception:
                logger.exception(
                    "live liq guard: fetch_open_positions failed | ex={}", exchange_id
                )
                continue
            for leg in legs:
                positions_by_symbol.setdefault(leg.symbol, []).append((exchange_id, leg))

        if not positions_by_symbol:
            return

        pairs_to_close: set[tuple[str, str, str]] = set()  # (symbol, short_ex, long_ex)
        solo_to_close: list[tuple[str, PositionLeg]] = []  # (exchange_id, PositionLeg)

        for symbol, entries in positions_by_symbol.items():
            short_entries = [(ex, leg) for ex, leg in entries if leg.side == "short"]
            long_entries = [(ex, leg) for ex, leg in entries if leg.side == "long"]

            # Check each leg individually for liquidation proximity
            endangered: list[tuple[str, PositionLeg]] = []
            for ex_id, leg in entries:
                current = self._current_price(ex_id, symbol, leg)
                if current is None:
                    continue
                leverage = self._leverage_from_leg(leg)
                liq = self._liquidation_price(float(leg.entry_price), leverage, leg.side)
                if liq is None:
                    continue
                consumed = self._margin_consumed_pct(
                    float(leg.entry_price), current, liq
                )
                if consumed >= self._warning_pct:
                    logger.warning(
                        "live liq guard: margin {}% consumed | ex={} sym={} side={} "
                        "entry={} current={:.6f} liq={:.6f} leverage={}x",
                        round(consumed, 1),
                        ex_id, symbol, leg.side,
                        leg.entry_price, current, liq, leverage,
                    )
                    endangered.append((ex_id, leg))

            if not endangered:
                continue

            # Determine if this is a full hedged pair or a solo unhedged leg
            if short_entries and long_entries:
                short_ex = short_entries[0][0]
                long_ex = long_entries[0][0]
                key = (symbol, short_ex, long_ex)
                if key not in pairs_to_close:
                    pairs_to_close.add(key)
                    logger.warning(
                        "live liq guard: scheduling pair close | sym={} short={} long={}",
                        symbol, short_ex, long_ex,
                    )
            else:
                # Unhedged single leg — close directly
                for ex_id, leg in endangered:
                    solo_to_close.append((ex_id, leg))
                    logger.warning(
                        "live liq guard: unhedged leg close | ex={} sym={} side={}",
                        ex_id, symbol, leg.side,
                    )

        # Close full pairs via HedgedExecutionService
        for symbol, short_ex, long_ex in pairs_to_close:
            try:
                outcome = await self._exec.close_all(
                    symbol=symbol,
                    short_exchange_id=short_ex,
                    long_exchange_id=long_ex,
                )
                logger.warning(
                    "live liq guard: pair closed | sym={} short={} long={} status={} imbalance={}",
                    symbol, short_ex, long_ex,
                    outcome.status.value, outcome.imbalance_pct,
                )
            except Exception:
                logger.exception(
                    "live liq guard: close_all failed | sym={} short={} long={}",
                    symbol, short_ex, long_ex,
                )

        # Close solo unhedged legs directly through their gateway
        for ex_id, leg in solo_to_close:
            gw = self._gateways.get(ex_id)
            if gw is None:
                continue
            try:
                order_id = await gw.close_market_position(leg)
                logger.warning(
                    "live liq guard: solo leg closed | ex={} sym={} side={} order_id={}",
                    ex_id, leg.symbol, leg.side, order_id,
                )
            except Exception:
                logger.exception(
                    "live liq guard: solo close failed | ex={} sym={} side={}",
                    ex_id, leg.symbol, leg.side,
                )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _current_price(self, exchange_id: str, symbol: str, leg: PositionLeg) -> float | None:
        # Prefer mark_price from position data (most accurate for liquidation calc)
        if leg.mark_price is not None and float(leg.mark_price) > 0.0:
            return float(leg.mark_price)
        # Fall back to market cache mid price
        quote = self._cache.get_quote(exchange_id, symbol, "futures")
        if quote is None:
            return None
        if quote.bid and quote.ask:
            return round((float(quote.bid) + float(quote.ask)) / 2.0, 8)
        if quote.last:
            return round(float(quote.last), 8)
        return None

    def _leverage_from_leg(self, leg: PositionLeg) -> float:
        # PositionLeg does not carry leverage, but mark_price + unrealized_pnl
        # allow rough estimation. Use settings default as fallback.
        entry = float(leg.entry_price)
        contracts = float(leg.contracts)
        contract_size = float(leg.contract_size)
        mark = float(leg.mark_price or 0.0)
        pnl = float(leg.unrealized_pnl or 0.0)
        if (
            entry > 0.0
            and contracts > 0.0
            and contract_size > 0.0
            and mark > 0.0
            and pnl != 0.0
        ):
            position_value = contracts * contract_size * entry
            # Rough margin = (position_value - |pnl|) / position_value  →  leverage ≈ 1/margin
            margin_fraction = (position_value - abs(pnl)) / position_value
            if 0.01 <= margin_fraction <= 1.0:
                return round(1.0 / margin_fraction, 1)
        return float(self._settings.opp_default_leverage)

    @classmethod
    def _liquidation_price(
        cls, entry: float, leverage: float, side: str
    ) -> float | None:
        if leverage <= 0:
            return None
        buffer = (1.0 / leverage) - cls._MM_RATE
        if buffer <= 0:
            return None
        if side == "short":
            return entry * (1.0 + buffer)
        return entry * (1.0 - buffer)

    @staticmethod
    def _margin_consumed_pct(entry: float, current: float, liq: float) -> float:
        total = abs(liq - entry)
        if total <= 0:
            return 0.0
        moved = abs(current - entry)
        return min(100.0, moved / total * 100.0)
