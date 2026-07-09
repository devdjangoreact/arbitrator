from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from arbitrator.config.logger import logger

if TYPE_CHECKING:
    from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
    from arbitrator.application.trading.paper_execution_gateway import PaperExecutionGateway
    from arbitrator.config.paper_order_store import PaperOrderStore
    from arbitrator.config.settings import Settings


class FundingReentryService:
    """Close and reopen a paper pair when the upcoming funding charge exceeds the
    cost of a round-trip (close fees + reopen fees at a better entry).

    Decision logic per open pair at each funding settlement window:
      net_funding_cost = estimated_next_funding_usdt  (positive = we pay)
      round_trip_fees  = 2 × taker_fee × notional  (close + reopen)
      current_spread   = (short_mid - long_mid) / long_mid × 100

    Reopen is worthwhile when:
      net_funding_cost > round_trip_fees
      AND current_spread >= min_reopen_spread_pct   (ensures we can reopen profitably)

    To avoid acting on the very last moment before settlement (when spread may
    spike temporarily) we check only within a configurable window *before*
    the funding time but not too close (skip if < ``skip_within_seconds``).
    """

    def __init__(
        self,
        store: "PaperOrderStore",
        paper_gateway: "PaperExecutionGateway",
        market_cache: "MarketDataCacheMemory",
        settings: "Settings",
        *,
        check_interval_seconds: float = 30.0,
        act_window_seconds: float = 300.0,
        skip_within_seconds: float = 60.0,
        min_reopen_spread_pct: float = 0.0,
    ) -> None:
        self._store = store
        self._gateway = paper_gateway
        self._cache = market_cache
        self._settings = settings
        self._interval = check_interval_seconds
        self._act_window = act_window_seconds    # check when funding is this many seconds away
        self._skip_window = skip_within_seconds  # do not act when this close to funding
        self._min_spread = min_reopen_spread_pct
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="funding-reentry-service",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "funding reentry service started | act_window={}s min_spread={}%",
            self._act_window, self._min_spread,
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
                logger.exception("funding reentry tick failed")

    def _tick(self) -> None:
        import time as _time
        now_ms = int(_time.time() * 1000)

        records = self._store.load_all()
        open_legs = [r for r in records if r.action == "open" and r.status == "filled"]
        if not open_legs:
            return

        # Group by pair_id
        pair_legs: dict[str, list[Any]] = {}
        for leg in open_legs:
            pair_legs.setdefault(leg.pair_id, []).append(leg)

        for pair_id, legs in pair_legs.items():
            sell_leg = next((l for l in legs if l.side == "sell"), None)
            buy_leg = next((l for l in legs if l.side == "buy"), None)
            if sell_leg is None or buy_leg is None:
                continue

            # Get funding info for each leg
            fi_sell = self._cache.get_funding(sell_leg.exchange_id, sell_leg.symbol)
            fi_buy = self._cache.get_funding(buy_leg.exchange_id, buy_leg.symbol)

            # Find earliest funding settlement
            times = []
            if fi_sell and fi_sell.next_settlement_ms:
                times.append(fi_sell.next_settlement_ms)
            if fi_buy and fi_buy.next_settlement_ms:
                times.append(fi_buy.next_settlement_ms)
            if not times:
                continue
            next_settlement_ms = min(times)
            secs_to_funding = (next_settlement_ms - now_ms) / 1000.0

            # Only act within the action window, but not too close
            if secs_to_funding > self._act_window or secs_to_funding < self._skip_window:
                continue

            # Compute estimated funding cost (positive = we pay)
            funding_cost = 0.0
            if fi_sell and fi_sell.rate is not None:
                # short leg: receives positive funding, pays negative funding
                rate = float(fi_sell.rate)
                funding_cost -= sell_leg.notional_usdt * rate  # short = -rate benefit
            if fi_buy and fi_buy.rate is not None:
                rate = float(fi_buy.rate)
                funding_cost += buy_leg.notional_usdt * rate  # long pays +rate

            if funding_cost <= 0:
                # We actually receive funding — no reason to reopen
                continue

            # Compute round-trip cost
            sell_fee = self._gateway._taker_fee_rate(sell_leg.exchange_id, sell_leg.symbol)
            buy_fee = self._gateway._taker_fee_rate(buy_leg.exchange_id, buy_leg.symbol)
            notional_sell = sell_leg.notional_usdt
            notional_buy = buy_leg.notional_usdt
            round_trip_fees = 2.0 * (notional_sell * sell_fee + notional_buy * buy_fee)

            if funding_cost <= round_trip_fees:
                # Not worth it — fees exceed the funding we'd save
                continue

            # Check current spread to ensure we can reopen
            short_mid = self._get_mid(sell_leg.exchange_id, sell_leg.symbol)
            long_mid = self._get_mid(buy_leg.exchange_id, buy_leg.symbol)
            if short_mid is None or long_mid is None or long_mid <= 0:
                continue
            current_spread_pct = (short_mid - long_mid) / long_mid * 100.0
            if current_spread_pct < self._min_spread:
                logger.info(
                    "funding reentry skipped: spread too low | pair_id={} spread={:.3f}% min={}%",
                    pair_id, current_spread_pct, self._min_spread,
                )
                continue

            logger.info(
                "funding reentry: closing pair for reopen | pair_id={} funding_cost={:.4f} "
                "round_trip_fees={:.4f} spread={:.3f}% secs_to_funding={:.0f}",
                pair_id, funding_cost, round_trip_fees, current_spread_pct, secs_to_funding,
            )

            # Close the pair
            exit_spread = round(current_spread_pct, 4)
            self._store.record_close(
                pair_id=pair_id,
                exchange_id=sell_leg.exchange_id,
                side="sell",
                amount=sell_leg.amount,
                price=short_mid,
                spread_pct=exit_spread,
                taker_fee_rate=sell_fee,
            )
            self._store.record_close(
                pair_id=pair_id,
                exchange_id=buy_leg.exchange_id,
                side="buy",
                amount=buy_leg.amount,
                price=long_mid,
                spread_pct=exit_spread,
                taker_fee_rate=buy_fee,
            )

            # Reopen at minimum notional both exchanges allow.
            # Short opens first at USDT notional; long opens for the same token amount.
            # None means market info not yet cached — skip until data is available.
            notional = self._resolve_min_notional(
                sell_leg.symbol, sell_leg.exchange_id, buy_leg.exchange_id,
                short_price=short_mid, long_price=long_mid,
            )
            if notional is None:
                logger.warning(
                    "funding reentry: market info missing, skipping reopen | sym={} short={} long={}",
                    sell_leg.symbol, sell_leg.exchange_id, buy_leg.exchange_id,
                )
                continue
            if short_mid <= 0:
                continue
            amount = notional / short_mid
            if amount <= 0:
                continue
            self._gateway.open_pair(
                symbol=sell_leg.symbol,
                short_exchange_id=sell_leg.exchange_id,
                long_exchange_id=buy_leg.exchange_id,
                short_price=short_mid,
                long_price=long_mid,
                amount=amount,
                spread_pct=exit_spread,
            )
            logger.info(
                "funding reentry: reopened pair | sym={} short={} long={} spread={:.3f}%",
                sell_leg.symbol, sell_leg.exchange_id, buy_leg.exchange_id, current_spread_pct,
            )

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

    def _resolve_min_notional(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
        short_price: float | None = None,
        long_price: float | None = None,
    ) -> float | None:
        """Return the effective USDT notional satisfying both exchanges and settings floor.

        effective = max(exchange_min_short, exchange_min_long, settings_notional_usdt)

        Returns None when market info for either exchange is missing —
        caller must skip the trade until data is available.
        """
        min_a = self._min_notional_for_exchange(symbol, short_ex, short_price)
        min_b = self._min_notional_for_exchange(symbol, long_ex, long_price)
        if min_a is None or min_b is None:
            return None
        floor = self._settings.screener_auto_trade_notional_usdt
        return max(min_a, min_b, floor)

    def _get_mid(self, exchange_id: str, symbol: str) -> float | None:
        quote = self._cache.get_quote(exchange_id, symbol, "futures")
        if quote is None:
            return None
        if quote.bid and quote.ask:
            return round((float(quote.bid) + float(quote.ask)) / 2, 8)
        if quote.last:
            return round(float(quote.last), 8)
        return None
