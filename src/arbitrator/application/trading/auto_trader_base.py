from arbitrator.config.ui_config_manager import UIConfigManager
from collections.abc import Mapping

from arbitrator.application.account.token_identity_service import TokenIdentityService
from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.market.order_book_level import OrderBookLevel
from arbitrator.domain.market.ticker import Ticker
from arbitrator.domain.universe.symbol_normalizer import SymbolNormalizer


class AutoTraderBase:
    """Base class for shared logic between LiveAutoTrader and ScreenerAutoTrader."""

    def __init__(
        self,
        settings: Settings,
        market_cache: MarketDataCacheMemory | None = None,
        token_identity: TokenIdentityService | None = None,
    ):
        self._settings = settings
        self._market_cache = market_cache
        self._token_identity = token_identity

    def _min_notional_for_exchange(
        self,
        symbol: str,
        exchange_id: str,
        live_price: float | None,
    ) -> float | None:
        if self._market_cache is None:
            return None
        info = self._market_cache.get_market_info(exchange_id, symbol)
        if info is None:
            return None
        from_contracts: float | None = None
        if (
            info.min_amount_contracts is not None
            and info.contract_size > 0.0
            and live_price is not None
            and live_price > 0.0
        ):
            from_contracts = info.min_amount_contracts * info.contract_size * live_price
        if info.min_order_volume_usdt is not None and from_contracts is not None:
            return max(info.min_order_volume_usdt, from_contracts)
        if info.min_order_volume_usdt is not None:
            return info.min_order_volume_usdt
        return from_contracts

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
        floor = UIConfigManager.get_config().screener_auto_trade_notional_usdt
        return max(min_a, min_b, floor)

    @staticmethod
    def _side_depth_usdt(
        levels: tuple[OrderBookLevel, ...],
        price_limit_pct: float,
    ) -> float:
        if not levels:
            return 0.0
        best = levels[0].price
        if best <= 0.0:
            return 0.0
        cutoff_high = best * (1.0 + price_limit_pct)
        cutoff_low = best * (1.0 - price_limit_pct)
        total = 0.0
        for level in levels:
            if level.price < cutoff_low or level.price > cutoff_high:
                break
            total += level.price * level.size
        return total

    def _check_order_book_depth(
        self,
        symbol: str,
        exchange_a: str,
        exchange_b: str,
        notional_usdt: float,
        *,
        fail_on_missing_book: bool = False,
        **kwargs,
    ) -> str | None:
        if self._market_cache is None:
            return None
        required = notional_usdt * 2.0
        for exchange_id in (exchange_a, exchange_b):
            book = self._market_cache.get_order_book(exchange_id, symbol)
            if book is None:
                if fail_on_missing_book:
                    return f"no_order_book:{exchange_id}"
                logger.debug(
                    "order book depth check skipped: no cached book | sym={} ex={}",
                    symbol, exchange_id,
                )
                continue

            ask_depth = self._side_depth_usdt(book.asks, price_limit_pct=0.004)
            bid_depth = self._side_depth_usdt(book.bids, price_limit_pct=0.004)

            if ask_depth < required:
                return f"insufficient_ask_depth:{exchange_id}:{ask_depth:.0f}<{required:.0f}"
            if bid_depth < required:
                return f"insufficient_bid_depth:{exchange_id}:{bid_depth:.0f}<{required:.0f}"
        return None

    def _validate_cross_pair(
        self,
        symbol: str,
        exchange_a: str,
        exchange_b: str,
        notional_usdt: float,
        *,
        tickers_snapshot: Mapping[tuple[str, str], Ticker] | None = None,
        fail_on_missing_book: bool = False,
        **kwargs,
    ) -> str | None:
        if "tickers" in kwargs and tickers_snapshot is None:
            tickers_snapshot = kwargs["tickers"]
        expected_base = SymbolNormalizer.base_asset(symbol)

        if tickers_snapshot is not None:
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

        if self._market_cache is not None:
            info_a = self._market_cache.get_market_info(exchange_a, symbol)
            info_b = self._market_cache.get_market_info(exchange_b, symbol)

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

        depth_rejection = self._check_order_book_depth(
            symbol, exchange_a, exchange_b, notional_usdt, fail_on_missing_book=fail_on_missing_book
        )
        if depth_rejection is not None:
            return depth_rejection

        return None

