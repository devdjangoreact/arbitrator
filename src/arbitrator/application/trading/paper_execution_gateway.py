from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
from arbitrator.config.logger import logger
from arbitrator.config.paper_order_store import PaperOrderStore
from arbitrator.domain.account.position_leg import PositionLeg
from arbitrator.domain.strategy.execution_outcome import (
    ExecutionOutcome,
    ExecutionStatus,
    LegExecution,
)

class PaperExecutionGateway:
    """Simulates order placement against live prices without sending to exchange.

    On open: records both legs in PaperOrderStore, returns synthetic order ids.
    On close: marks legs closed, computes PnL from entry vs current price.
    """

    def __init__(self, store: PaperOrderStore, cache: MarketDataCacheMemory) -> None:
        self._store = store
        self._cache = cache

    def _taker_fee_rate(self, exchange_id: str, symbol: str) -> float:
        fees = self._cache.get_fees(exchange_id, symbol)
        if fees is not None and fees.futures_taker is not None:
            return float(fees.futures_taker)
        return 0.0

    def open_pair(
        self,
        *,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        short_price: float,
        long_price: float,
        amount: float,
        spread_pct: float | None = None,
        strategy_kind: str | None = None,
    ) -> ExecutionOutcome:
        pair_id = uuid.uuid4().hex[:12]

        short_leg = self._store.record_open(
            pair_id=pair_id,
            symbol=symbol,
            exchange_id=short_exchange_id,
            side="sell",
            amount=amount,
            price=short_price,
            spread_pct=spread_pct,
            taker_fee_rate=self._taker_fee_rate(short_exchange_id, symbol),
            strategy_kind=strategy_kind,
        )
        long_leg = self._store.record_open(
            pair_id=pair_id,
            symbol=symbol,
            exchange_id=long_exchange_id,
            side="buy",
            amount=amount,
            price=long_price,
            spread_pct=spread_pct,
            taker_fee_rate=self._taker_fee_rate(long_exchange_id, symbol),
            strategy_kind=strategy_kind,
        )

        logger.info(
            "Paper pair opened | pair_id={} symbol={} short_ex={} long_ex={} spread_pct={}",
            pair_id, symbol, short_exchange_id, long_exchange_id, spread_pct,
        )
        return ExecutionOutcome(
            action="open",
            status=ExecutionStatus.simulated,
            symbol=symbol,
            short_leg=LegExecution(
                exchange_id=short_exchange_id,
                side="sell",
                symbol=symbol,
                requested_amount=Decimal(str(amount)),
                filled_amount=Decimal(str(amount)),
                order_id=short_leg.order_id,
                ok=True,
            ),
            long_leg=LegExecution(
                exchange_id=long_exchange_id,
                side="buy",
                symbol=symbol,
                requested_amount=Decimal(str(amount)),
                filled_amount=Decimal(str(amount)),
                order_id=long_leg.order_id,
                ok=True,
            ),
            imbalance_pct=Decimal("0"),
            pair_id=pair_id,
        )

    def close_pair(
        self,
        *,
        pair_id: str,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        short_price: float,
        long_price: float,
        amount: float,
        spread_pct: float | None = None,
    ) -> ExecutionOutcome:
        short_closed = self._store.record_close(
            pair_id=pair_id,
            exchange_id=short_exchange_id,
            side="sell",
            amount=amount,
            price=short_price,
            spread_pct=spread_pct,
            taker_fee_rate=self._taker_fee_rate(short_exchange_id, symbol),
        )
        long_closed = self._store.record_close(
            pair_id=pair_id,
            exchange_id=long_exchange_id,
            side="buy",
            amount=amount,
            price=long_price,
            spread_pct=spread_pct,
            taker_fee_rate=self._taker_fee_rate(long_exchange_id, symbol),
        )

        short_ok = short_closed is not None
        long_ok = long_closed is not None
        status = ExecutionStatus.simulated if (short_ok and long_ok) else ExecutionStatus.partial

        short_pnl = short_closed.pnl_usdt if short_closed else None
        long_pnl = long_closed.pnl_usdt if long_closed else None
        total_pnl: float | None = None
        if short_pnl is not None and long_pnl is not None:
            total_pnl = round(short_pnl + long_pnl, 4)

        logger.info(
            "Paper pair closed | pair_id={} symbol={} pnl={}",
            pair_id, symbol, total_pnl,
        )
        return ExecutionOutcome(
            action="close",
            status=status,
            symbol=symbol,
            short_leg=LegExecution(
                exchange_id=short_exchange_id,
                side="buy",
                symbol=symbol,
                requested_amount=Decimal(str(amount)),
                filled_amount=Decimal(str(amount)),
                order_id=short_closed.order_id if short_closed else None,
                ok=short_ok,
            ),
            long_leg=LegExecution(
                exchange_id=long_exchange_id,
                side="sell",
                symbol=symbol,
                requested_amount=Decimal(str(amount)),
                filled_amount=Decimal(str(amount)),
                order_id=long_closed.order_id if long_closed else None,
                ok=long_ok,
            ),
            imbalance_pct=Decimal("0"),
            message=f"pnl={total_pnl}" if total_pnl is not None else None,
        )

    def get_open_positions(self, symbol: str) -> list[PositionLeg]:
        """Return synthetic PositionLeg objects for all open paper pairs on this symbol."""
        records = self._store.load_all()
        positions: list[PositionLeg] = []
        for r in records:
            if r.symbol != symbol or r.action != "open" or r.status != "filled":
                continue
            side_map: dict[Literal["buy", "sell"], Literal["long", "short"]] = {
                "buy": "long",
                "sell": "short",
            }
            positions.append(
                PositionLeg(
                    exchange_id=r.exchange_id,
                    display_name=r.exchange_id,
                    symbol=r.symbol,
                    side=side_map[r.side],
                    contracts=r.amount,
                    contract_size=1.0,
                    entry_price=r.price,
                    mark_price=None,
                    opened_at=r.opened_at,
                    unrealized_pnl=None,
                    accrued_funding=None,
                    opening_fee=None,
                    estimated_close_fee=None,
                    next_funding_at=None,
                    arb_marker_id=r.pair_id,
                    position_id=r.order_id,
                )
            )
        return positions
