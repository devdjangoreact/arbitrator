from __future__ import annotations

import asyncio
import threading
import time
from decimal import Decimal
from typing import TYPE_CHECKING

from arbitrator.application.hedged_execution_service import HedgedExecutionService
from arbitrator.application.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.application.screener_stream_worker import ScreenerStreamWorker
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.strategy.quote import Quote
from arbitrator.domain.symbol_market_info import SymbolMarketInfo
from arbitrator.domain.ticker import Ticker

if TYPE_CHECKING:
    from arbitrator.application.token_identity_service import TokenIdentityService


class LiveAutoTrader:
    """Auto-trader for live mode: places real orders via HedgedExecutionService.

    Mirrors ScreenerAutoTrader logic (same open/close/validation pass) but:
    - Calls HedgedExecutionService.open / close_all instead of PaperExecutionGateway
    - Recovers open pairs from exchange positions on startup (no local store)
    - Runs on its own asyncio event loop (own thread, like FundingRateWorker)

    Open pair state is keyed by (symbol, short_exchange_id, long_exchange_id).
    On restart the pair set is rebuilt from fetch_open_positions across all
    enabled exchanges — we know short/long exchange by position side:
    short position on exchange A + long position on exchange B = one pair.
    """

    def __init__(
        self,
        settings: Settings,
        screener_worker: ScreenerStreamWorker,
        execution_service: HedgedExecutionService,
        market_cache: MarketDataCacheMemory,
        token_identity: "TokenIdentityService | None" = None,
    ) -> None:
        self._settings = settings
        self._screener = screener_worker
        self._exec = execution_service
        self._cache = market_cache
        self._token_identity = token_identity
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._main_task: asyncio.Task[None] | None = None
        # (symbol, short_ex, long_ex) -> open_since_monotonic
        self._open_pairs: dict[tuple[str, str, str], float] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._thread_main,
            name="live-auto-trader",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "live auto trader started | max_pos={} open_spread={}% close_spread={}%",
            self._settings.screener_auto_trade_max_positions,
            self._settings.screener_auto_trade_open_spread_pct,
            self._settings.screener_auto_trade_close_spread_pct,
        )

    def stop(self) -> None:
        self._stop.set()
        loop = self._loop
        task = self._main_task
        if loop is not None and task is not None and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ #
    # Thread + async entry
    # ------------------------------------------------------------------ #

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._async_main())
        except asyncio.CancelledError:
            logger.info("live auto trader stopped")
        except Exception:
            logger.exception("live auto trader crashed")

    async def _async_main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._main_task = asyncio.current_task()
        await self._restore_open_pairs()
        interval = self._settings.screener_auto_trade_check_seconds
        while not self._stop.is_set():
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("live auto trader tick failed")
            try:
                await asyncio.wait_for(
                    asyncio.shield(asyncio.get_event_loop().create_future()),
                    timeout=interval,
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                if self._stop.is_set():
                    raise asyncio.CancelledError
                pass

    # ------------------------------------------------------------------ #
    # Restore open pairs from exchange positions on startup
    # ------------------------------------------------------------------ #

    async def _restore_open_pairs(self) -> None:
        """Rebuild in-memory pair set from live exchange positions.

        Pairs are matched by symbol: a short position on one exchange and a
        long position on another exchange for the same symbol = one open pair.
        Only considers exchanges that HedgedExecutionService has gateways for.
        """
        positions_by_symbol: dict[str, list[tuple[str, str]]] = {}
        for exchange_id, gateway in self._exec._gateways.items():
            try:
                legs = await gateway.fetch_open_positions()
            except Exception:
                logger.exception("live auto trader: failed to fetch positions | ex={}", exchange_id)
                continue
            for leg in legs:
                entry = (exchange_id, leg.side)
                positions_by_symbol.setdefault(leg.symbol, []).append(entry)

        for symbol, entries in positions_by_symbol.items():
            short_exs = [ex for ex, side in entries if side == "short"]
            long_exs = [ex for ex, side in entries if side == "long"]
            if not short_exs or not long_exs:
                continue
            short_ex = short_exs[0]
            long_ex = long_exs[0]
            key = (symbol, short_ex, long_ex)
            self._open_pairs[key] = time.monotonic()
            logger.info(
                "live auto trader: restored open pair | sym={} short={} long={}",
                symbol, short_ex, long_ex,
            )

        logger.info("live auto trader: restored {} open pairs", len(self._open_pairs))

    # ------------------------------------------------------------------ #
    # Main tick
    # ------------------------------------------------------------------ #

    async def _tick(self) -> None:
        tickers, _symbols, _updates, status, _threshold = self._screener.read_state()
        if status != "Live":
            return

        open_spread_pct = self._settings.screener_auto_trade_open_spread_pct
        close_spread_pct = self._settings.screener_auto_trade_close_spread_pct
        max_pos = self._settings.screener_auto_trade_max_positions

        # --- build ranked candidates ---
        by_symbol: dict[str, dict[str, float]] = {}
        for (exchange_id, symbol), ticker in tickers.items():
            if ticker.last is not None and ticker.last > 0.0:
                by_symbol.setdefault(symbol, {})[exchange_id] = ticker.last

        candidates: list[tuple[float, str, str, str, float, float]] = []
        for symbol, prices in by_symbol.items():
            if len(prices) < 2:
                continue
            short_ex = max(prices, key=lambda ex: prices[ex])
            long_ex = min(prices, key=lambda ex: prices[ex])
            short_ticker = tickers.get((short_ex, symbol))
            long_ticker = tickers.get((long_ex, symbol))
            short_bid = (
                short_ticker.bid if short_ticker and short_ticker.bid
                else short_ticker.last if short_ticker else None
            )
            long_ask = (
                long_ticker.ask if long_ticker and long_ticker.ask
                else long_ticker.last if long_ticker else None
            )
            if short_bid is None or long_ask is None or long_ask <= 0.0:
                continue
            spread = (short_bid - long_ask) / long_ask * 100.0
            candidates.append((spread, symbol, short_ex, long_ex, short_bid, long_ask))

        candidates.sort(key=lambda c: c[0], reverse=True)

        # --- close pass ---
        to_remove: list[tuple[str, str, str]] = []
        for key, _opened_at in list(self._open_pairs.items()):
            sym, s_ex, l_ex = key
            s_ticker = tickers.get((s_ex, sym))
            l_ticker = tickers.get((l_ex, sym))
            short_ask = (
                s_ticker.ask if s_ticker and s_ticker.ask
                else s_ticker.last if s_ticker else None
            )
            long_bid = (
                l_ticker.bid if l_ticker and l_ticker.bid
                else l_ticker.last if l_ticker else None
            )
            if short_ask is None or long_bid is None or long_bid <= 0.0:
                continue
            exit_spread = (short_ask - long_bid) / long_bid * 100.0
            if exit_spread > close_spread_pct:
                continue
            logger.info(
                "live auto close | sym={} short={} long={} exit_spread={:.3f}%",
                sym, s_ex, l_ex, exit_spread,
            )
            outcome = await self._exec.close_all(
                symbol=sym,
                short_exchange_id=s_ex,
                long_exchange_id=l_ex,
            )
            logger.info(
                "live auto close result | sym={} status={} imbalance={}",
                sym, outcome.status.value, outcome.imbalance_pct,
            )
            to_remove.append(key)

        for key in to_remove:
            self._open_pairs.pop(key, None)

        # --- open pass ---
        open_count = len(self._open_pairs)
        already_open_symbols = {sym for (sym, _s, _l) in self._open_pairs}

        for _net, symbol, short_ex, long_ex, short_bid, long_ask in candidates:
            if open_count >= max_pos:
                break
            if symbol in already_open_symbols:
                continue
            # Skip if no gateway for either exchange
            if short_ex not in self._exec._gateways or long_ex not in self._exec._gateways:
                continue
            entry_spread = (short_bid - long_ask) / long_ask * 100.0
            if entry_spread < open_spread_pct:
                continue
            notional_float = self._resolve_min_notional(symbol, short_ex, long_ex, short_bid, long_ask)
            if notional_float is None:
                logger.debug(
                    "live open skipped: market info not yet cached | sym={} short={} long={}",
                    symbol, short_ex, long_ex,
                )
                continue
            rejection = self._validate_cross_pair(symbol, short_ex, long_ex, notional_float)
            if rejection is not None:
                logger.warning(
                    "live open skipped: {} | sym={} short={} long={}",
                    rejection, symbol, short_ex, long_ex,
                )
                continue
            # Final spread re-check from freshest cached quotes
            fresh = self._fresh_spread(symbol, short_ex, long_ex)
            if fresh is None:
                logger.debug(
                    "live open skipped: no fresh quote for recheck | sym={} short={} long={}",
                    symbol, short_ex, long_ex,
                )
                continue
            fresh_bid, fresh_ask, fresh_spread = fresh
            if fresh_spread < open_spread_pct:
                logger.debug(
                    "live open skipped: spread dropped | sym={} was={:.3f}% now={:.3f}%",
                    symbol, entry_spread, fresh_spread,
                )
                continue
            if fresh_spread > self._settings.anomaly_max_spread_pct:
                logger.warning(
                    "live open blocked: anomaly spread — likely different tokens | "
                    "sym={} short={} long={} spread={:.1f}% max={}%",
                    symbol, short_ex, long_ex, fresh_spread,
                    self._settings.anomaly_max_spread_pct,
                )
                continue
            # Set cross-margin mode on both exchanges before opening
            await self._set_cross_margin(symbol, short_ex)
            await self._set_cross_margin(symbol, long_ex)
            notional = Decimal(str(notional_float))
            price = Decimal(str(fresh_bid))
            logger.info(
                "live auto open | sym={} short={} long={} spread={:.3f}% notional={}",
                symbol, short_ex, long_ex, fresh_spread, notional,
            )
            outcome = await self._exec.open(
                symbol=symbol,
                short_exchange_id=short_ex,
                long_exchange_id=long_ex,
                notional_usdt=notional,
                price=price,
            )
            logger.info(
                "live auto open result | sym={} status={} imbalance={}",
                symbol, outcome.status.value, outcome.imbalance_pct,
            )
            if outcome.status.value in ("success", "partial"):
                key = (symbol, short_ex, long_ex)
                self._open_pairs[key] = time.monotonic()
                already_open_symbols.add(symbol)
                open_count += 1

    # ------------------------------------------------------------------ #
    # Helpers — identical logic to ScreenerAutoTrader
    # ------------------------------------------------------------------ #

    async def _set_cross_margin(self, symbol: str, exchange_id: str) -> None:
        gateway = self._exec._gateways.get(exchange_id)
        if gateway is None:
            return
        try:
            await gateway.set_margin_mode(symbol, "cross")
        except Exception:
            logger.exception(
                "set_margin_mode failed (non-fatal) | ex={} sym={}", exchange_id, symbol
            )

    def _min_notional_for_exchange(
        self,
        symbol: str,
        exchange_id: str,
        live_price: float | None,
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
        min_a = self._min_notional_for_exchange(symbol, short_ex, short_price)
        min_b = self._min_notional_for_exchange(symbol, long_ex, long_price)
        if min_a is None or min_b is None:
            return None
        floor = self._settings.screener_auto_trade_notional_usdt
        return max(min_a, min_b, floor)

    def _fresh_spread(
        self,
        symbol: str,
        short_ex: str,
        long_ex: str,
    ) -> tuple[float, float, float] | None:
        q_short = self._cache.get_quote(short_ex, symbol, "futures")
        q_long = self._cache.get_quote(long_ex, symbol, "futures")
        if q_short is None or q_long is None:
            return None
        bid = float(q_short.bid) if q_short.bid is not None else (
            float(q_short.last) if q_short.last is not None else None
        )
        ask = float(q_long.ask) if q_long.ask is not None else (
            float(q_long.last) if q_long.last is not None else None
        )
        if bid is None or ask is None or ask <= 0.0:
            return None
        spread = (bid - ask) / ask * 100.0
        return bid, ask, spread

    def _validate_cross_pair(
        self,
        symbol: str,
        exchange_a: str,
        exchange_b: str,
        notional_usdt: float,
    ) -> str | None:
        from arbitrator.domain.symbol_normalizer import SymbolNormalizer

        expected_base = SymbolNormalizer.base_asset(symbol)
        tickers_snapshot = self._screener.read_state()[0]
        ticker_a = tickers_snapshot.get((exchange_a, symbol))
        ticker_b = tickers_snapshot.get((exchange_b, symbol))

        for ticker, ex in ((ticker_a, exchange_a), (ticker_b, exchange_b)):
            if ticker is not None:
                ticker_base = ticker.base_asset.upper()
                if ticker_base and ticker_base != expected_base.upper():
                    return f"ticker_base_mismatch:{ex}:{ticker_base}!={expected_base}"

        for ticker, ex in ((ticker_a, exchange_a), (ticker_b, exchange_b)):
            if ticker is not None:
                q = ticker.quote_asset.upper()
                if q and q != "USDT":
                    return f"quote_asset_not_usdt:{ex}:{q}"

        info_a = self._cache.get_market_info(exchange_a, symbol)
        info_b = self._cache.get_market_info(exchange_b, symbol)
        if info_a is None:
            return f"market_info_missing:{exchange_a}"
        if info_b is None:
            return f"market_info_missing:{exchange_b}"

        if info_a.base_asset.upper() != info_b.base_asset.upper():
            return (
                f"market_base_mismatch:"
                f"{exchange_a}:{info_a.base_asset}"
                f"!={exchange_b}:{info_b.base_asset}"
            )

        for info, ex in ((info_a, exchange_a), (info_b, exchange_b)):
            if info.min_order_volume_usdt is not None and notional_usdt < info.min_order_volume_usdt:
                return (
                    f"below_min_notional:{ex}:"
                    f"{notional_usdt:.2f}<{info.min_order_volume_usdt:.2f}"
                )

        if self._token_identity is not None:
            result = self._token_identity.compare(expected_base, exchange_a, exchange_b)
            if result.should_block:
                return (
                    f"token_identity_conflict:{expected_base}:"
                    f"{exchange_a}/{exchange_b}:{result.notes}"
                )
            if result.match_type == "symbol_only_ccxt_dedup":
                logger.debug(
                    "token_identity unverified, proceeding | base={} {}/{} notes={}",
                    expected_base, exchange_a, exchange_b, result.notes,
                )

        return None
