from __future__ import annotations

import uuid
from collections.abc import Mapping
from decimal import Decimal

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.domain.strategy.execution_outcome import (
    ExecutionOutcome,
    ExecutionStatus,
    LegExecution,
)
from arbitrator.domain.strategy.futures_execution_gateway import FuturesExecutionGateway

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

    def __init__(
        self,
        gateways: Mapping[str, FuturesExecutionGateway],
        settings: Settings,
        *,
        dry_run: bool = False,
    ) -> None:
        self._gateways = gateways
        self._settings = settings
        self._dry_run = dry_run
        self._tolerance = Decimal(str(settings.leg_imbalance_tolerance_pct))

    async def open(
        self,
        *,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        notional_usdt: Decimal,
        price: Decimal,
    ) -> ExecutionOutcome:
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
    ) -> ExecutionOutcome:
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
    ) -> ExecutionOutcome:
        return await self._exit(
            "close_partial", symbol, short_exchange_id, long_exchange_id, close_percent
        )

    async def close_all(
        self,
        *,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
    ) -> ExecutionOutcome:
        return await self._exit(
            "close_all", symbol, short_exchange_id, long_exchange_id, _HUNDRED
        )

    async def _enter(
        self,
        action: str,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        notional_usdt: Decimal,
        price: Decimal,
    ) -> ExecutionOutcome:
        if price <= _ZERO or notional_usdt <= _ZERO:
            return self._failed(action, symbol, "invalid_sizing")
        amount = notional_usdt / price
        short_gw = self._gateways.get(short_exchange_id)
        long_gw = self._gateways.get(long_exchange_id)
        if short_gw is None or long_gw is None:
            return self._failed(action, symbol, "gateway_missing")

        if self._dry_run:
            return self._simulated_enter(action, symbol, short_exchange_id, long_exchange_id, amount)

        coid = uuid.uuid4().hex[:12]
        before_short = await self._position_base(short_gw, symbol)
        try:
            short_oid = await short_gw.open_market_position(
                symbol, "sell", float(amount), f"HX-{coid}-S"
            )
        except Exception:
            logger.exception("hedge open short failed | symbol={} ex={}", symbol, short_exchange_id)
            return self._failed(action, symbol, "short_leg_failed")
        filled_short = abs(await self._position_base(short_gw, symbol) - before_short)

        before_long = await self._position_base(long_gw, symbol)
        try:
            long_oid = await long_gw.open_market_position(
                symbol, "buy", float(amount), f"HX-{coid}-L"
            )
        except Exception:
            logger.exception("hedge open long failed | symbol={} ex={}", symbol, long_exchange_id)
            return await self._rollback_open(
                action, symbol, short_exchange_id, long_exchange_id,
                short_gw, short_oid, amount, filled_short,
            )
        filled_long = abs(await self._position_base(long_gw, symbol) - before_long)

        short_leg = LegExecution(
            exchange_id=short_exchange_id, side="sell", symbol=symbol,
            requested_amount=amount, filled_amount=filled_short, order_id=short_oid,
        )
        long_leg = LegExecution(
            exchange_id=long_exchange_id, side="buy", symbol=symbol,
            requested_amount=amount, filled_amount=filled_long, order_id=long_oid,
        )
        imbalance = self._imbalance(filled_short, filled_long)
        status = self._enter_status(filled_short, filled_long, imbalance)
        logger.info(
            "hedge {} | symbol={} filled_short={} filled_long={} imbalance_pct={} status={}",
            action, symbol, filled_short, filled_long, imbalance, status.value,
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

    @staticmethod
    def _failed(action: str, symbol: str, reason: str) -> ExecutionOutcome:
        logger.warning("hedge {} rejected | symbol={} reason={}", action, symbol, reason)
        return ExecutionOutcome(
            action=action, status=ExecutionStatus.failed, symbol=symbol, message=reason,
        )
