from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.config.telegram_notifier import TelegramNotifier
from arbitrator.domain.account.position_leg import PositionLeg
from arbitrator.domain.strategy.execution_outcome import (
    ExecutionOutcome,
    ExecutionStatus,
    LegExecution,
)
from arbitrator.domain.exchange.spot_gateway import SpotGateway
from arbitrator.domain.strategy.futures_execution_gateway import FuturesExecutionGateway

if TYPE_CHECKING:
    from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


class HedgedExecutionService:
    """Real hedged open/accumulate/close on two futures legs (US4, FR-011..FR-013).

    Position state and fills come from exchange positions, never from intent
    (FR-012). On a one-leg open failure it compensates the filled leg so no
    unhedged exposure remains (FR-013), gated by
    ``Settings.execution_rollback_enabled``. ``dry_run=True`` simulates every
    action with no real orders (verification path, no exchange risk).
    """

    # Strategies where the long leg is spot (short = futures, long = spot buy)
    _SPOT_LONG_STRATEGIES: frozenset[str] = frozenset({
        "futures_spot_2ex",
        "futures_spot_1ex",
        "funding_fs",
    })

    def __init__(
        self,
        gateways: Mapping[str, FuturesExecutionGateway],
        settings: Settings,
        *,
        market_cache: MarketDataCacheMemory | None = None,
        dry_run: bool = False,
        notifier: TelegramNotifier | None = None,
        universe: dict[str, set[str]] | None = None,
        spot_gateways: Mapping[str, SpotGateway] | None = None,
    ) -> None:
        self._gateways = gateways
        self._settings = settings
        self._market_cache = market_cache
        self._dry_run = dry_run
        self._tolerance = Decimal(str(settings.leg_imbalance_tolerance_pct))
        self._notifier = notifier
        self._universe = universe
        self._spot_gateways: Mapping[str, SpotGateway] = spot_gateways or {}

    def _contract_size_for(self, symbol: str, exchange_id: str) -> Decimal:
        """Return contract_size from cache, fallback 1 (= tokens == contracts)."""
        if self._market_cache is None:
            return Decimal("1")
        info = self._market_cache.get_market_info(exchange_id, symbol)
        if info is None or info.contract_size <= 0.0:
            return Decimal("1")
        return Decimal(str(info.contract_size))

    def _amount_step_for(self, symbol: str, exchange_id: str) -> float | None:
        """Return amount_step (precision.amount) from cache."""
        if self._market_cache is None:
            return None
        info = self._market_cache.get_market_info(exchange_id, symbol)
        if info is None:
            return None
        return info.amount_step

    def _harmonize_amounts(
        self,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        notional_usdt: Decimal,
        price: Decimal,
    ) -> tuple[float, float] | None:
        """Pre-compute contract amounts for both legs that produce equal token exposure.

        Finds the Least Common Multiple (LCM) of the token step sizes for both exchanges
        and floors the target token amount to this common step. This guarantees that
        both exchanges receive an order for the exact same number of tokens, satisfying
        both amount_step constraints without any delta exposure.
        """
        short_cs = self._contract_size_for(symbol, short_exchange_id)
        long_cs = self._contract_size_for(symbol, long_exchange_id)
        short_step_raw = self._amount_step_for(symbol, short_exchange_id)
        long_step_raw = self._amount_step_for(symbol, long_exchange_id)

        short_step = Decimal(str(short_step_raw)) if short_step_raw and short_step_raw > 0 else Decimal("1")
        long_step = Decimal(str(long_step_raw)) if long_step_raw and long_step_raw > 0 else Decimal("1")

        # Minimum token increment each exchange can trade
        short_token_step = short_cs * short_step
        long_token_step = long_cs * long_step

        # Calculate Least Common Multiple (LCM) of the two token steps.
        # We multiply by 1e8 to convert to integers for the math.lcm function,
        # then divide back to Decimal. This handles steps like 0.01 and 0.001 cleanly.
        scale = Decimal("100000000")
        short_int = int(short_token_step * scale)
        long_int = int(long_token_step * scale)

        if short_int == 0 or long_int == 0:
            return None

        lcm_int = math.lcm(short_int, long_int)
        common_token_step = Decimal(lcm_int) / scale

        # Target tokens from notional
        target_tokens = notional_usdt / price

        # Floor target tokens to the common step
        steps_count = int(target_tokens / common_token_step)
        final_tokens = Decimal(steps_count) * common_token_step

        if final_tokens <= _ZERO:
            logger.debug(
                "harmonize_amounts rejected: notional too small for common step | sym={} notional={} common_step_tokens={}",
                symbol, notional_usdt, common_token_step
            )
            return None

        # Convert back to contracts for each exchange
        short_contracts = float(final_tokens / short_cs)
        long_contracts = float(final_tokens / long_cs)

        return short_contracts, long_contracts

    def _min_notional_for_exchange(
        self,
        symbol: str,
        exchange_id: str,
        live_price: Decimal | None,
    ) -> Decimal | None:
        """Return minimum USDT notional for one exchange.

        Priority:
        1. limits.cost.min  (bitget, bingx — direct USDT limit)
        2. limits.amount.min * contractSize * live_price  (mexc, gate — contract-unit limit)
        3. None
        """
        if self._market_cache is None:
            return None
        info = self._market_cache.get_market_info(exchange_id, symbol)
        if info is None:
            return None
        if info.min_order_volume_usdt is not None:
            return Decimal(str(info.min_order_volume_usdt))
        if (
            info.min_amount_contracts is not None
            and info.contract_size > 0.0
            and live_price is not None
            and live_price > _ZERO
        ):
            return Decimal(str(info.min_amount_contracts)) * Decimal(str(info.contract_size)) * live_price
        return None

    def resolve_min_notional(
        self,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        fallback: Decimal,
        live_price: Decimal | None = None,
    ) -> Decimal | None:
        """Return the effective USDT notional satisfying both exchanges and the caller's floor.

        effective = max(exchange_min_short, exchange_min_long, fallback)

        Returns ``fallback`` when market cache is absent (no cache injected — tests/dry_run).
        Returns None when cache is present but market info for either exchange is missing —
        caller must abort the trade until data is available.
        Pass ``live_price`` so contract-unit exchanges (mexc, gate) can compute
        their USDT minimum from  min_contracts × contract_size × price.
        """
        if self._market_cache is None:
            return fallback
        min_a = self._min_notional_for_exchange(symbol, short_exchange_id, live_price)
        min_b = self._min_notional_for_exchange(symbol, long_exchange_id, live_price)
        if min_a is None or min_b is None:
            return None
        return max(min_a, min_b, fallback)

    async def open(
        self,
        *,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        notional_usdt: Decimal,
        price: Decimal,
        strategy_kind: str = "futures_futures",
    ) -> ExecutionOutcome:
        if strategy_kind in self._SPOT_LONG_STRATEGIES:
            return await self._enter_spot_long(
                "open", symbol, short_exchange_id, long_exchange_id,
                notional_usdt, price, strategy_kind,
            )
        return await self._enter(
            "open", symbol, short_exchange_id, long_exchange_id, notional_usdt, price
        )

    async def accumulate(
        self,
        *,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        notional_usdt: Decimal,
        price: Decimal,
        strategy_kind: str = "futures_futures",
    ) -> ExecutionOutcome:
        if strategy_kind in self._SPOT_LONG_STRATEGIES:
            return await self._enter_spot_long(
                "accumulate", symbol, short_exchange_id, long_exchange_id,
                notional_usdt, price, strategy_kind,
            )
        return await self._enter(
            "accumulate", symbol, short_exchange_id, long_exchange_id, notional_usdt, price
        )

    async def close_partial(
        self,
        *,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        close_percent: Decimal,
        strategy_kind: str = "futures_futures",
    ) -> ExecutionOutcome:
        if strategy_kind in self._SPOT_LONG_STRATEGIES:
            return await self._exit_spot_long(
                "close_partial", symbol, short_exchange_id, long_exchange_id,
                close_percent, strategy_kind,
            )
        return await self._exit(
            "close_partial", symbol, short_exchange_id, long_exchange_id, close_percent
        )

    async def close_all(
        self,
        *,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        strategy_kind: str = "futures_futures",
    ) -> ExecutionOutcome:
        if strategy_kind in self._SPOT_LONG_STRATEGIES:
            return await self._exit_spot_long(
                "close_all", symbol, short_exchange_id, long_exchange_id,
                _HUNDRED, strategy_kind,
            )
        return await self._exit(
            "close_all", symbol, short_exchange_id, long_exchange_id, _HUNDRED
        )

    async def _exit_spot_long(
        self,
        action: str,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        close_percent: Decimal,
        strategy_kind: str,
    ) -> ExecutionOutcome:
        """Close a futures-short + spot-long hedge."""
        short_gw = self._gateways.get(short_exchange_id)
        spot_gw = self._spot_gateways.get(long_exchange_id)
        if short_gw is None or spot_gw is None:
            return self._failed(action, symbol, "gateway_missing")

        spot_symbol = symbol.replace(":USDT", "")
        base_asset = spot_symbol.split("/")[0]

        # Close futures short
        short_pos = await self._find_leg(short_gw, symbol)
        factor = close_percent / _HUNDRED
        short_ok = await self._close_partial_leg(short_gw, short_pos, factor)

        # Sell spot tokens
        spot_ok = False
        spot_sold = _ZERO
        coid = uuid.uuid4().hex[:12]
        try:
            balance = await spot_gw.fetch_balance(base_asset)
            sell_amount = float(balance * factor)
            if sell_amount > 0:
                await spot_gw.sell_spot_market(spot_symbol, sell_amount, f"HX-{coid}-CL")
                spot_sold = Decimal(str(sell_amount))
                spot_ok = True
            else:
                spot_ok = True
        except Exception:
            logger.exception("spot close sell failed | sym={} ex={}", spot_symbol, long_exchange_id)

        short_leg = LegExecution(
            exchange_id=short_exchange_id, side="buy", symbol=symbol,
            requested_amount=_ZERO, filled_amount=_ZERO,
            ok=short_ok, message=None if short_ok else "close_failed",
            market_type="futures",
        )
        long_leg = LegExecution(
            exchange_id=long_exchange_id, side="sell", symbol=spot_symbol,
            requested_amount=spot_sold, filled_amount=spot_sold,
            ok=spot_ok, message=None if spot_ok else "spot_sell_failed",
            market_type="spot",
        )
        status = self._exit_status(short_ok, spot_ok, None)
        logger.info(
            "spot hedge close | sym={} strategy={} short_ok={} spot_sold={} status={}",
            symbol, strategy_kind, short_ok, spot_sold, status.value,
        )
        return ExecutionOutcome(
            action=action, status=status, symbol=symbol,
            short_leg=short_leg, long_leg=long_leg, imbalance_pct=None,
        )

    async def _enter_spot_long(
        self,
        action: str,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        notional_usdt: Decimal,
        price: Decimal,
        strategy_kind: str,
    ) -> ExecutionOutcome:
        """Open with futures short + spot long (§1/§2/§6 strategies)."""
        if price <= _ZERO or notional_usdt <= _ZERO:
            return self._failed(action, symbol, "invalid_sizing")
        short_gw = self._gateways.get(short_exchange_id)
        spot_gw = self._spot_gateways.get(long_exchange_id)
        if short_gw is None:
            return self._failed(action, symbol, "gateway_missing")
        if spot_gw is None:
            return self._failed(action, symbol, "spot_gateway_missing")

        # Spot symbol: strip ":USDT" suffix → "BTC/USDT"
        spot_symbol = symbol.replace(":USDT", "")
        token_amount = float(notional_usdt / price)

        if self._dry_run:
            amount = Decimal(str(token_amount))
            short_leg = LegExecution(
                exchange_id=short_exchange_id, side="sell", symbol=symbol,
                requested_amount=amount, filled_amount=amount,
                order_id=None, message="dry_run", market_type="futures",
            )
            long_leg = LegExecution(
                exchange_id=long_exchange_id, side="buy", symbol=spot_symbol,
                requested_amount=amount, filled_amount=amount,
                order_id=None, message="dry_run", market_type="spot",
            )
            return ExecutionOutcome(
                action=action, status=ExecutionStatus.simulated, symbol=symbol,
                short_leg=short_leg, long_leg=long_leg, imbalance_pct=_ZERO,
            )

        coid = uuid.uuid4().hex[:12]

        # --- Futures short leg ---
        short_amount = self._compute_futures_amount(symbol, short_exchange_id, token_amount)
        if short_amount <= 0:
            return self._failed(action, symbol, "amount_rounds_to_zero")

        logger["trades/live_trades.log"].debug(
            "SPOT_HEDGE_SEND short | sym={} ex={} amount={} coid=HX-{}-S strategy={}",
            symbol, short_exchange_id, short_amount, coid, strategy_kind,
        )
        before_short = await self._position_base(short_gw, symbol)
        try:
            short_oid = await short_gw.open_market_position(
                symbol, "sell", short_amount, f"HX-{coid}-S"
            )
        except Exception:
            logger.exception("spot hedge short failed | sym={} ex={}", symbol, short_exchange_id)
            return self._failed(action, symbol, "short_leg_failed")
        filled_short = abs(await self._position_base(short_gw, symbol) - before_short)

        # --- Spot long leg: buy tokens ---
        spot_amount = float(filled_short) if filled_short > _ZERO else token_amount
        logger["trades/live_trades.log"].debug(
            "SPOT_HEDGE_SEND long_spot | sym={} ex={} amount={} coid=HX-{}-L",
            spot_symbol, long_exchange_id, spot_amount, coid,
        )
        try:
            long_oid = await spot_gw.buy_spot_market(
                spot_symbol, spot_amount, f"HX-{coid}-L"
            )
        except Exception:
            logger.exception("spot hedge long failed | sym={} ex={}", spot_symbol, long_exchange_id)
            # Rollback futures short
            if self._settings.execution_rollback_enabled and filled_short > _ZERO:
                await self._close_full_leg(short_gw, symbol)
            return self._failed(action, symbol, "spot_long_leg_failed")

        filled_long = Decimal(str(spot_amount))
        short_leg = LegExecution(
            exchange_id=short_exchange_id, side="sell", symbol=symbol,
            requested_amount=Decimal(str(short_amount)), filled_amount=filled_short,
            order_id=short_oid, market_type="futures",
        )
        long_leg = LegExecution(
            exchange_id=long_exchange_id, side="buy", symbol=spot_symbol,
            requested_amount=Decimal(str(spot_amount)), filled_amount=filled_long,
            order_id=long_oid, market_type="spot",
        )
        imbalance = self._imbalance(filled_short, filled_long)
        status = self._enter_status(filled_short, filled_long, imbalance)
        logger.info(
            "spot hedge {} | sym={} strategy={} filled_short={} filled_long_spot={} status={}",
            action, symbol, strategy_kind, filled_short, filled_long, status.value,
        )
        if self._notifier is not None:
            emoji = "✅" if status == ExecutionStatus.success else "⚠️"
            self._notifier.notify(
                f"{emoji} <b>OPEN SPOT HEDGE</b> {action.upper()}\n"
                f"Symbol: <code>{symbol}</code>\n"
                f"Strategy: {strategy_kind}\n"
                f"Short (futures): {short_exchange_id} filled={float(filled_short):.4f}\n"
                f"Long (spot): {long_exchange_id} filled={float(filled_long):.4f}\n"
                f"Status: {status.value}"
            )
        return ExecutionOutcome(
            action=action, status=status, symbol=symbol,
            short_leg=short_leg, long_leg=long_leg, imbalance_pct=imbalance,
        )

    def _compute_futures_amount(
        self, symbol: str, exchange_id: str, token_amount: float
    ) -> float:
        """Convert token amount to contracts, floored to exchange step."""
        cs = self._contract_size_for(symbol, exchange_id)
        step = self._amount_step_for(symbol, exchange_id)
        raw = token_amount / float(cs)
        if step and step > 0:
            raw = math.floor(raw / step) * step
        return raw

    async def _enter(
        self,
        action: str,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        notional_usdt: Decimal,
        price: Decimal,
    ) -> ExecutionOutcome:
        # Use the minimum notional both exchanges allow.
        # None means market info is not yet cached — abort to avoid underfilled orders.
        effective_notional = self.resolve_min_notional(
            symbol, short_exchange_id, long_exchange_id, notional_usdt, live_price=price
        )
        if effective_notional is None:
            return self._failed(action, symbol, "market_info_missing")
        if price <= _ZERO or effective_notional <= _ZERO:
            return self._failed(action, symbol, "invalid_sizing")

        if not self._dry_run:
            margin_rejection = self._check_sufficient_margin(
                symbol, short_exchange_id, long_exchange_id, effective_notional
            )
            if margin_rejection is not None:
                return self._failed(action, symbol, margin_rejection)

        # Pre-compute harmonized contract amounts so both legs get equal token exposure
        # after each exchange floors to its lot step.
        harmonized = self._harmonize_amounts(
            symbol, short_exchange_id, long_exchange_id, effective_notional, price
        )
        if harmonized is None:
            return self._failed(action, symbol, "amount_rounds_to_zero")
        short_amount_f, long_amount_planned = harmonized
        short_amount = Decimal(str(short_amount_f))
        long_cs = self._contract_size_for(symbol, long_exchange_id)
        short_gw = self._gateways.get(short_exchange_id)
        long_gw = self._gateways.get(long_exchange_id)
        if short_gw is None or long_gw is None:
            return self._failed(action, symbol, "gateway_missing")
        if self._universe is not None:
            if symbol not in self._universe.get(short_exchange_id, set()):
                return self._failed(action, symbol, "not_in_universe_short")
            if symbol not in self._universe.get(long_exchange_id, set()):
                return self._failed(action, symbol, "not_in_universe_long")

        if self._dry_run:
            return self._simulated_enter(
                action, symbol, short_exchange_id, long_exchange_id, short_amount
            )

        coid = uuid.uuid4().hex[:12]
        logger["trades/live_trades.log"].debug(
            "ORDER_SEND short | sym={} ex={} side=sell amount={} coid=HX-{}-S"
            " effective_notional={} price={} long_planned={}",
            symbol, short_exchange_id, float(short_amount), coid,
            effective_notional, price, long_amount_planned,
        )
        before_short = await self._position_base(short_gw, symbol)
        try:
            short_oid = await short_gw.open_market_position(
                symbol, "sell", float(short_amount), f"HX-{coid}-S"
            )
        except Exception:
            logger.exception("hedge open short failed | symbol={} ex={}", symbol, short_exchange_id)
            logger["trades/live_trades.log"].error(
                "ORDER_FAIL short | sym={} ex={} coid=HX-{}-S amount={}",
                symbol, short_exchange_id, coid, float(short_amount),
            )
            return self._failed(action, symbol, "short_leg_failed")
        filled_short = abs(await self._position_base(short_gw, symbol) - before_short)
        logger["trades/live_trades.log"].debug(
            "ORDER_FILL short | sym={} ex={} order_id={} requested={} filled={}",
            symbol, short_exchange_id, short_oid, float(short_amount), filled_short,
        )

        # Use filled short tokens to determine long amount (delta-neutral).
        # Floor to long exchange step to avoid the exchange rounding unpredictably.
        filled_short_tokens = filled_short
        long_step = self._amount_step_for(symbol, long_exchange_id)
        if filled_short_tokens > _ZERO:
            raw_long = float(filled_short_tokens / long_cs)
            if long_step and long_step > 0:
                raw_long = math.floor(raw_long / long_step) * long_step
            long_amount = Decimal(str(raw_long))
        else:
            long_amount = Decimal(str(long_amount_planned))
        logger["trades/live_trades.log"].debug(
            "ORDER_SEND long | sym={} ex={} side=buy amount={} coid=HX-{}-L",
            symbol, long_exchange_id, float(long_amount), coid,
        )
        before_long = await self._position_base(long_gw, symbol)
        try:
            long_oid = await long_gw.open_market_position(
                symbol, "buy", float(long_amount), f"HX-{coid}-L"
            )
        except Exception:
            logger.exception("hedge open long failed | symbol={} ex={}", symbol, long_exchange_id)
            logger["trades/live_trades.log"].error(
                "ORDER_FAIL long | sym={} ex={} coid=HX-{}-L amount={} short_filled={}",
                symbol, long_exchange_id, coid, float(long_amount), filled_short,
            )
            return await self._rollback_open(
                action, symbol, short_exchange_id, long_exchange_id,
                short_gw, short_oid, short_amount, filled_short,
            )
        filled_long = abs(await self._position_base(long_gw, symbol) - before_long)
        logger["trades/live_trades.log"].debug(
            "ORDER_FILL long | sym={} ex={} order_id={} requested={} filled={}",
            symbol, long_exchange_id, long_oid, float(long_amount), filled_long,
        )

        short_leg = LegExecution(
            exchange_id=short_exchange_id, side="sell", symbol=symbol,
            requested_amount=short_amount, filled_amount=filled_short, order_id=short_oid,
        )
        long_leg = LegExecution(
            exchange_id=long_exchange_id, side="buy", symbol=symbol,
            requested_amount=long_amount, filled_amount=filled_long, order_id=long_oid,
        )
        imbalance = self._imbalance(filled_short, filled_long)
        status = self._enter_status(filled_short, filled_long, imbalance)
        logger.info(
            "hedge {} | symbol={} filled_short={} filled_long={} imbalance_pct={} status={}",
            action, symbol, filled_short, filled_long, imbalance, status.value,
        )
        if self._notifier is not None:
            emoji = "✅" if status == ExecutionStatus.success else "⚠️"
            self._notifier.notify(
                f"{emoji} <b>OPEN</b> {action.upper()}\n"
                f"Symbol: <code>{symbol}</code>\n"
                f"Short: {short_exchange_id} filled={float(filled_short):.4f}\n"
                f"Long:  {long_exchange_id} filled={float(filled_long):.4f}\n"
                f"Status: {status.value}"
            )
        return ExecutionOutcome(
            action=action, status=status, symbol=symbol,
            short_leg=short_leg, long_leg=long_leg, imbalance_pct=imbalance,
        )

    async def _rollback_open(
        self,
        action: str,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        short_gw: FuturesExecutionGateway,
        short_oid: str,
        amount: Decimal,
        filled_short: Decimal,
    ) -> ExecutionOutcome:
        rolled = False
        if self._settings.execution_rollback_enabled and filled_short > _ZERO:
            rolled = await self._close_full_leg(short_gw, symbol)
        short_leg = LegExecution(
            exchange_id=short_exchange_id, side="sell", symbol=symbol,
            requested_amount=amount, filled_amount=_ZERO if rolled else filled_short,
            order_id=short_oid, ok=True,
            message="rolled_back" if rolled else "unhedged_needs_attention",
        )
        long_leg = LegExecution(
            exchange_id=long_exchange_id, side="buy", symbol=symbol,
            requested_amount=amount, filled_amount=_ZERO, order_id=None, ok=False,
            message="long_leg_failed",
        )
        status = ExecutionStatus.rolled_back if rolled else ExecutionStatus.failed
        logger.warning(
            "hedge {} rollback | symbol={} rolled_back={} short_ex={}",
            action, symbol, rolled, short_exchange_id,
        )
        logger["trades/live_trades.log"].warning(
            "ROLLBACK | sym={} action={} rolled_back={} short_ex={} long_ex={}"
            " short_filled={} short_order={} reason=long_leg_failed",
            symbol, action, rolled, short_exchange_id, long_exchange_id,
            filled_short, short_oid,
        )
        return ExecutionOutcome(
            action=action, status=status, symbol=symbol,
            short_leg=short_leg, long_leg=long_leg, imbalance_pct=None,
            rolled_back=rolled,
            message="one leg failed; compensated" if rolled else "one leg failed; unhedged",
        )

    async def _exit(
        self,
        action: str,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        close_percent: Decimal,
    ) -> ExecutionOutcome:
        if close_percent <= _ZERO or close_percent > _HUNDRED:
            return self._failed(action, symbol, "invalid_close_percent")
        short_gw = self._gateways.get(short_exchange_id)
        long_gw = self._gateways.get(long_exchange_id)
        if short_gw is None or long_gw is None:
            return self._failed(action, symbol, "gateway_missing")

        short_before = await self._position_base(short_gw, symbol)
        long_before = await self._position_base(long_gw, symbol)
        short_pos = await self._find_leg(short_gw, symbol)
        long_pos = await self._find_leg(long_gw, symbol)
        if short_pos is None and long_pos is None:
            return self._failed(action, symbol, "no_position")

        if self._dry_run:
            return self._simulated_exit(
                action, symbol, short_exchange_id, long_exchange_id,
                short_before, long_before, close_percent,
            )

        factor = close_percent / _HUNDRED
        logger["trades/live_trades.log"].debug(
            "CLOSE_SEND | sym={} short_ex={} long_ex={} close_pct={}"
            " short_pos={} long_pos={}",
            symbol, short_exchange_id, long_exchange_id, close_percent,
            float(short_before), float(long_before),
        )
        short_ok = await self._close_partial_leg(short_gw, short_pos, factor)
        long_ok = await self._close_partial_leg(long_gw, long_pos, factor)
        short_after = await self._position_base(short_gw, symbol)
        long_after = await self._position_base(long_gw, symbol)

        short_leg = LegExecution(
            exchange_id=short_exchange_id, side="buy", symbol=symbol,
            requested_amount=short_before * factor, filled_amount=abs(short_before - short_after),
            ok=short_ok, message=None if short_ok else "close_failed",
        )
        long_leg = LegExecution(
            exchange_id=long_exchange_id, side="sell", symbol=symbol,
            requested_amount=long_before * factor, filled_amount=abs(long_before - long_after),
            ok=long_ok, message=None if long_ok else "close_failed",
        )
        imbalance = self._imbalance(short_after, long_after)
        status = self._exit_status(short_ok, long_ok, imbalance)
        logger.info(
            "hedge {} | symbol={} rem_short={} rem_long={} imbalance_pct={} status={}",
            action, symbol, short_after, long_after, imbalance, status.value,
        )
        if self._notifier is not None:
            emoji = "🔴" if status == ExecutionStatus.success else "⚠️"
            self._notifier.notify(
                f"{emoji} <b>CLOSE</b> {action.upper()}\n"
                f"Symbol: <code>{symbol}</code>\n"
                f"Short: {short_exchange_id} closed={float(short_leg.filled_amount):.4f}\n"
                f"Long:  {long_exchange_id} closed={float(long_leg.filled_amount):.4f}\n"
                f"Status: {status.value}"
            )
        return ExecutionOutcome(
            action=action, status=status, symbol=symbol,
            short_leg=short_leg, long_leg=long_leg, imbalance_pct=imbalance,
        )

    async def _close_partial_leg(
        self,
        gateway: FuturesExecutionGateway,
        leg: PositionLeg | None,
        factor: Decimal,
    ) -> bool:
        if leg is None:
            return True
        partial = leg.model_copy(update={"contracts": leg.contracts * float(factor)})
        try:
            await gateway.close_market_position(partial)
            return True
        except Exception:
            logger.exception(
                "hedge close leg failed | symbol={} ex={} side={}",
                leg.symbol, leg.exchange_id, leg.side,
            )
            return False

    async def _close_full_leg(self, gateway: FuturesExecutionGateway, symbol: str) -> bool:
        leg = await self._find_leg(gateway, symbol)
        if leg is None:
            return True
        try:
            await gateway.close_market_position(leg)
            return True
        except Exception:
            logger.exception("hedge rollback close failed | symbol={} ex={}", symbol, leg.exchange_id)
            return False

    def _enter_status(
        self,
        filled_short: Decimal,
        filled_long: Decimal,
        imbalance: Decimal | None,
    ) -> ExecutionStatus:
        if filled_short <= _ZERO and filled_long <= _ZERO:
            return ExecutionStatus.failed
        if filled_short <= _ZERO or filled_long <= _ZERO:
            return ExecutionStatus.partial
        if imbalance is not None and imbalance > self._tolerance:
            return ExecutionStatus.partial
        return ExecutionStatus.success

    def _exit_status(
        self,
        short_ok: bool,
        long_ok: bool,
        imbalance: Decimal | None,
    ) -> ExecutionStatus:
        if not short_ok and not long_ok:
            return ExecutionStatus.failed
        if not short_ok or not long_ok:
            return ExecutionStatus.partial
        if imbalance is not None and imbalance > self._tolerance:
            return ExecutionStatus.partial
        return ExecutionStatus.success

    @staticmethod
    def _imbalance(short_amount: Decimal, long_amount: Decimal) -> Decimal | None:
        base = max(short_amount, long_amount)
        if base <= _ZERO:
            return _ZERO
        return abs(short_amount - long_amount) / base * _HUNDRED

    @staticmethod
    async def _position_base(gateway: FuturesExecutionGateway, symbol: str) -> Decimal:
        total = _ZERO
        for leg in await gateway.fetch_open_positions():
            if leg.symbol == symbol:
                total += Decimal(str(abs(leg.contracts * leg.contract_size)))
        return total

    @staticmethod
    async def _find_leg(gateway: FuturesExecutionGateway, symbol: str) -> PositionLeg | None:
        for leg in await gateway.fetch_open_positions():
            if leg.symbol == symbol:
                return leg
        return None

    def _simulated_enter(
        self,
        action: str,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        amount: Decimal,
    ) -> ExecutionOutcome:
        short_leg = LegExecution(
            exchange_id=short_exchange_id, side="sell", symbol=symbol,
            requested_amount=amount, filled_amount=amount, order_id=None, message="dry_run",
        )
        long_leg = LegExecution(
            exchange_id=long_exchange_id, side="buy", symbol=symbol,
            requested_amount=amount, filled_amount=amount, order_id=None, message="dry_run",
        )
        return ExecutionOutcome(
            action=action, status=ExecutionStatus.simulated, symbol=symbol,
            short_leg=short_leg, long_leg=long_leg, imbalance_pct=_ZERO,
        )

    def _simulated_exit(
        self,
        action: str,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        short_before: Decimal,
        long_before: Decimal,
        close_percent: Decimal,
    ) -> ExecutionOutcome:
        factor = close_percent / _HUNDRED
        short_leg = LegExecution(
            exchange_id=short_exchange_id, side="buy", symbol=symbol,
            requested_amount=short_before * factor, filled_amount=short_before * factor,
            order_id=None, message="dry_run",
        )
        long_leg = LegExecution(
            exchange_id=long_exchange_id, side="sell", symbol=symbol,
            requested_amount=long_before * factor, filled_amount=long_before * factor,
            order_id=None, message="dry_run",
        )
        return ExecutionOutcome(
            action=action, status=ExecutionStatus.simulated, symbol=symbol,
            short_leg=short_leg, long_leg=long_leg, imbalance_pct=_ZERO,
        )

    def _check_sufficient_margin(
        self,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        notional_usdt: Decimal,
    ) -> str | None:
        """Verify cached USDT balance is sufficient for the notional amount on both exchanges."""
        if self._market_cache is None:
            return "cache_missing"

        # Typically margin required = notional / leverage. Assuming cross margin and buffer.
        # This acts as a conservative check (leverage=1) if leverage isn't tracked here,
        # or we can use default leverage from settings.
        leverage = float(self._settings.opp_default_leverage)
        if leverage <= 0:
            leverage = 1.0

        required_margin = float(notional_usdt) / leverage
        # Add 5% buffer for fees and slippage
        required_margin_with_buffer = required_margin * 1.05

        for ex_id in (short_exchange_id, long_exchange_id):
            balance = self._market_cache.get_usdt_balance(ex_id)
            if balance is None:
                return f"balance_unknown:{ex_id}"
            if balance < required_margin_with_buffer:
                logger.warning(
                    "insufficient margin for trade | sym={} ex={} balance={:.2f} required={:.2f}",
                    symbol, ex_id, balance, required_margin_with_buffer
                )
                return f"insufficient_balance:{ex_id}:{balance:.2f}<{required_margin_with_buffer:.2f}"

        return None

    @staticmethod
    def _failed(action: str, symbol: str, reason: str) -> ExecutionOutcome:
        logger.warning("hedge {} rejected | symbol={} reason={}", action, symbol, reason)
        return ExecutionOutcome(
            action=action, status=ExecutionStatus.failed, symbol=symbol, message=reason,
        )
