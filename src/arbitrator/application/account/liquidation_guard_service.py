from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from arbitrator.config.logger import logger

if TYPE_CHECKING:
    from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
    from arbitrator.application.trading.paper_execution_gateway import PaperExecutionGateway
    from arbitrator.config.paper_order_store import PaperOrderStore
    from arbitrator.config.settings import Settings


class LiquidationGuardService:
    """Monitors open paper positions for proximity to liquidation price.

    Cross-margin liquidation price approximation:
      For a short leg: liq_price = entry_price / (1 - leverage * (1 - mm_rate))
        → price rises above entry; long already hedges some of it, but each leg
          has its own liquidation level.
      For a long leg:  liq_price = entry_price / (1 + leverage * (1 - mm_rate))
        → price falls below entry.

    Since all positions are cross-margin the account balance provides a buffer.
    We use a simpler conservative formula:

      Short: liq_px = entry * (1 + 1/leverage * (1 - mm_rate))
             triggers when current_price >= entry * (1 + warning_pct/100)
      Long:  liq_px = entry * (1 - 1/leverage * (1 - mm_rate))
             triggers when current_price <= entry * (1 - warning_pct/100)

    When ``warning_pct`` of the way to liquidation is reached the pair is closed.
    """

    # Maintenance margin rate used for most exchanges (conservative estimate)
    _MM_RATE = 0.005  # 0.5%

    def __init__(
        self,
        store: PaperOrderStore,
        paper_gateway: PaperExecutionGateway,
        market_cache: MarketDataCacheMemory,
        settings: Settings,
        *,
        check_interval_seconds: float = 5.0,
        warning_pct_to_liq: float = 80.0,
    ) -> None:
        self._store = store
        self._gateway = paper_gateway
        self._cache = market_cache
        self._settings = settings
        self._interval = check_interval_seconds
        self._warning_pct = warning_pct_to_liq  # close when this % of margin consumed
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="liquidation-guard",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "liquidation guard started | interval={}s warning_pct={}%",
            self._interval,
            self._warning_pct,
        )

    def stop(self) -> None:
        self._stop.set()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(timeout=self._interval)
            if self._stop.is_set():
                break
            try:
                self._tick()
            except Exception:
                logger.exception("liquidation guard tick failed")

    def _tick(self) -> None:
        records = self._store.load_all()
        open_legs = [r for r in records if r.action == "open" and r.status == "filled"]
        if not open_legs:
            return

        # Group by pair_id to close full pairs together
        pairs_to_close: set[str] = set()

        for leg in open_legs:
            if leg.pair_id in pairs_to_close:
                continue

            current_price = self._get_current_price(leg.exchange_id, leg.symbol)
            if current_price is None or current_price <= 0.0:
                continue

            entry = leg.entry_price or leg.price
            if entry <= 0.0:
                continue

            # Determine leverage: estimate from notional/collateral ratio.
            # Without real exchange data we use the default leverage from settings.
            leverage = float(self._settings.opp_default_leverage)

            liq_price = self._liquidation_price(entry, leverage, leg.side)
            if liq_price is None:
                continue

            consumed_pct = self._margin_consumed_pct(entry, current_price, liq_price)
            if consumed_pct >= self._warning_pct:
                logger.warning(
                    "liquidation guard: margin {}% consumed | pair_id={} ex={} side={} "
                    "entry={} current={} liq={:.6f} leverage={}x",
                    round(consumed_pct, 1),
                    leg.pair_id, leg.exchange_id, leg.side,
                    entry, current_price, liq_price, leverage,
                )
                pairs_to_close.add(leg.pair_id)

        if not pairs_to_close:
            return

        # Find all open pair records and close each pair
        all_records = self._store.load_all()
        for pair_id in pairs_to_close:
            pair_legs = [r for r in all_records if r.pair_id == pair_id and r.status == "filled"]
            if not pair_legs:
                continue

            # Find sell and buy legs
            sell_leg = next((l for l in pair_legs if l.side == "sell"), None)
            buy_leg = next((l for l in pair_legs if l.side == "buy"), None)

            if sell_leg is None or buy_leg is None:
                # Unhedged single leg — close it directly
                solo = sell_leg or buy_leg
                if solo is None:
                    continue
                price = self._get_current_price(solo.exchange_id, solo.symbol)
                if price:
                    self._store.record_close(
                        pair_id=pair_id,
                        exchange_id=solo.exchange_id,
                        side=solo.side,
                        amount=solo.amount,
                        price=price,
                        taker_fee_rate=self._gateway._taker_fee_rate(solo.exchange_id, solo.symbol),
                    )
                continue

            short_price = self._get_current_price(sell_leg.exchange_id, sell_leg.symbol)
            long_price = self._get_current_price(buy_leg.exchange_id, buy_leg.symbol)
            if short_price is None or long_price is None:
                continue

            exit_spread = (short_price - long_price) / long_price * 100.0 if long_price > 0 else None

            self._store.record_close(
                pair_id=pair_id,
                exchange_id=sell_leg.exchange_id,
                side="sell",
                amount=sell_leg.amount,
                price=short_price,
                spread_pct=round(exit_spread, 4) if exit_spread is not None else None,
                taker_fee_rate=self._gateway._taker_fee_rate(sell_leg.exchange_id, sell_leg.symbol),
            )
            self._store.record_close(
                pair_id=pair_id,
                exchange_id=buy_leg.exchange_id,
                side="buy",
                amount=buy_leg.amount,
                price=long_price,
                spread_pct=round(exit_spread, 4) if exit_spread is not None else None,
                taker_fee_rate=self._gateway._taker_fee_rate(buy_leg.exchange_id, buy_leg.symbol),
            )
            logger.warning(
                "liquidation guard: emergency close | pair_id={} short_px={} long_px={}",
                pair_id, short_price, long_price,
            )

    def _get_current_price(self, exchange_id: str, symbol: str) -> float | None:
        quote = self._cache.get_quote(exchange_id, symbol, "futures")
        if quote is None:
            return None
        if quote.bid and quote.ask:
            return round((float(quote.bid) + float(quote.ask)) / 2, 8)
        if quote.last:
            return round(float(quote.last), 8)
        return None

    @classmethod
    def _liquidation_price(
        cls, entry: float, leverage: float, side: str
    ) -> float | None:
        """Approximate cross-margin liquidation price."""
        if leverage <= 0:
            return None
        margin_fraction = 1.0 / leverage  # initial margin fraction
        buffer = margin_fraction - cls._MM_RATE  # usable margin before liquidation
        if buffer <= 0:
            return None
        if side == "sell":
            # Short liquidates when price rises: liq = entry * (1 + buffer)
            return entry * (1.0 + buffer)
        else:
            # Long liquidates when price falls: liq = entry * (1 - buffer)
            return entry * (1.0 - buffer)

    @staticmethod
    def _margin_consumed_pct(
        entry: float, current: float, liq: float
    ) -> float:
        """How much of the margin distance to liquidation has been consumed (0-100%)."""
        total_distance = abs(liq - entry)
        if total_distance <= 0:
            return 0.0
        distance_moved = abs(current - entry)
        return min(100.0, distance_moved / total_distance * 100.0)
