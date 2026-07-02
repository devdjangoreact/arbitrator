from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Literal

from pydantic import TypeAdapter

from arbitrator.config.logger import logger
from arbitrator.domain.paper_order import PaperOrder

_ADAPTER: TypeAdapter[list[PaperOrder]] = TypeAdapter(list[PaperOrder])


class PaperOrderStore:
    """Thread-safe JSON store for paper (simulated) orders.

    One file keeps the full history; callers query open pairs by pair_id.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = Lock()

    # --- writes ---

    def record_open(
        self,
        *,
        pair_id: str,
        symbol: str,
        exchange_id: str,
        side: Literal["buy", "sell"],
        amount: float,
        price: float,
        spread_pct: float | None = None,
        taker_fee_rate: float = 0.0,
    ) -> PaperOrder:
        notional = amount * price
        open_fee = round(notional * taker_fee_rate, 6)
        order = PaperOrder(
            order_id=uuid.uuid4().hex[:12],
            pair_id=pair_id,
            symbol=symbol,
            exchange_id=exchange_id,
            side=side,
            action="open",
            amount=amount,
            price=price,
            notional_usdt=notional,
            status="filled",
            opened_at=datetime.now(UTC),
            entry_price=price,
            spread_pct_entry=spread_pct,
            open_fee_usdt=open_fee,
        )
        self._append(order)
        logger.info(
            "Paper open | pair_id={} ex={} side={} symbol={} price={} notional={} fee={}",
            pair_id, exchange_id, side, symbol, price, order.notional_usdt, open_fee,
        )
        return order

    def record_close(
        self,
        *,
        pair_id: str,
        exchange_id: str,
        side: Literal["buy", "sell"],
        amount: float,
        price: float,
        spread_pct: float | None = None,
        taker_fee_rate: float = 0.0,
    ) -> PaperOrder | None:
        """Mark a previously opened order as closed and compute PnL."""
        with self._lock:
            records = self._read()
            open_order = next(
                (
                    r for r in records
                    if r.pair_id == pair_id
                    and r.exchange_id == exchange_id
                    and r.action == "open"
                    and r.status == "filled"
                ),
                None,
            )
            if open_order is None:
                logger.warning(
                    "Paper close: no matching open order | pair_id={} ex={}",
                    pair_id, exchange_id,
                )
                return None

            entry = open_order.entry_price or open_order.price
            if side == "sell":
                price_pnl = (entry - price) * amount
            else:
                price_pnl = (price - entry) * amount

            close_fee = round(amount * price * taker_fee_rate, 6)
            net_pnl = round(
                price_pnl - open_order.open_fee_usdt - close_fee - open_order.accrued_funding_usdt,
                4,
            )

            closed = open_order.model_copy(
                update={
                    "status": "closed",
                    "closed_at": datetime.now(UTC),
                    "pnl_usdt": round(price_pnl, 4),
                    "close_fee_usdt": close_fee,
                    "net_pnl_usdt": net_pnl,
                    "spread_pct_exit": spread_pct,
                    "close_price": price,
                }
            )
            updated = [closed if r.order_id == open_order.order_id else r for r in records]
            self._write(updated)
            logger.info(
                "Paper close | pair_id={} ex={} price_pnl={} net_pnl={}",
                pair_id, exchange_id, closed.pnl_usdt, closed.net_pnl_usdt,
            )
            return closed

    def accrue_funding(
        self,
        *,
        pair_id: str,
        exchange_id: str,
        funding_usdt: float,
    ) -> None:
        """Add funding charge (positive = cost, negative = income) to an open order."""
        with self._lock:
            records = self._read()
            target = next(
                (
                    r for r in records
                    if r.pair_id == pair_id
                    and r.exchange_id == exchange_id
                    and r.action == "open"
                    and r.status == "filled"
                ),
                None,
            )
            if target is None:
                return
            updated_order = target.model_copy(
                update={
                    "accrued_funding_usdt": round(
                        target.accrued_funding_usdt + funding_usdt, 6
                    ),
                }
            )
            self._write(
                [updated_order if r.order_id == target.order_id else r for r in records]
            )
            logger.debug(
                "Paper funding accrued | pair_id={} ex={} delta={} total={}",
                pair_id, exchange_id, funding_usdt, updated_order.accrued_funding_usdt,
            )

    # --- reads ---

    def load_all(self) -> list[PaperOrder]:
        with self._lock:
            return self._read()

    def open_pairs(self) -> list[str]:
        """Return pair_ids that have at least one open (unfilled close) leg."""
        records = self.load_all()
        open_ids = {r.pair_id for r in records if r.action == "open" and r.status == "filled"}
        closed_ids = {r.pair_id for r in records if r.action == "open" and r.status == "closed"}
        return sorted(open_ids - closed_ids)

    def summary(self) -> dict[str, object]:
        records = self.load_all()
        closed = [r for r in records if r.status == "closed" and r.pnl_usdt is not None]
        total_pnl = round(sum(r.pnl_usdt for r in closed if r.pnl_usdt is not None), 4)
        total_net_pnl = round(
            sum(r.net_pnl_usdt for r in closed if r.net_pnl_usdt is not None), 4
        )
        total_fees = round(
            sum(r.open_fee_usdt + r.close_fee_usdt for r in records), 4
        )
        total_funding = round(sum(r.accrued_funding_usdt for r in records), 4)
        return {
            "total_orders": len(records),
            "open_pairs": len(self.open_pairs()),
            "closed_pairs": len(closed) // 2,
            "total_pnl_usdt": total_pnl,
            "total_net_pnl_usdt": total_net_pnl,
            "total_fees_usdt": total_fees,
            "total_funding_usdt": total_funding,
        }

    # --- internals ---

    def _append(self, order: PaperOrder) -> None:
        with self._lock:
            records = self._read()
            records.append(order)
            self._write(records)

    def _read(self) -> list[PaperOrder]:
        if not self._path.exists():
            return []
        try:
            raw = self._path.read_text(encoding="utf-8")
            payload = json.loads(raw) if raw.strip() else []
        except Exception:
            logger.exception("Failed to read paper orders | path={}", self._path)
            return []
        if not isinstance(payload, list):
            return []
        try:
            return _ADAPTER.validate_python(payload)
        except Exception:
            logger.exception("Invalid paper orders schema | path={}", self._path)
            return []

    def _write(self, records: list[PaperOrder]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            payload = _ADAPTER.dump_python(records, mode="json")
            tmp.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(tmp, self._path)
        except Exception:
            logger.exception("Failed to write paper orders | path={}", self._path)
            raise
