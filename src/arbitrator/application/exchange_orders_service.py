from __future__ import annotations

import asyncio
import threading
import time
import datetime as _dt
from datetime import datetime
from typing import Literal

from arbitrator.application.account_stream_worker import AccountStreamWorker
from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.domain.closed_position_leg import ClosedPositionLeg
from arbitrator.domain.position_leg import PositionLeg
from arbitrator.exchanges.factory import Factory


class _OrderGroup:
    """Internal helper to build a grouped order snapshot."""

    def __init__(
        self,
        *,
        symbol: str,
        short_exchange_id: str,
        long_exchange_id: str,
        status: Literal["open", "closed"],
    ) -> None:
        self.symbol = symbol
        self.short_exchange_id = short_exchange_id
        self.long_exchange_id = long_exchange_id
        self.status = status
        self.short_leg: PositionLeg | ClosedPositionLeg | None = None
        self.long_leg: PositionLeg | ClosedPositionLeg | None = None


class ExchangeOrdersService:
    """Fetches real exchange positions and groups them for the Orders UI.

    Open positions are read from AccountStreamWorker (already streaming).
    Closed positions are fetched periodically via REST.
    Legs are grouped into arb pairs when the same symbol has a short on one
    exchange and a long on another.
    """

    def __init__(
        self,
        settings: Settings,
        factory: Factory,
        account_worker: AccountStreamWorker,
    ) -> None:
        self._settings = settings
        self._factory = factory
        self._account_worker = account_worker
        self._lock = threading.Lock()
        self._closed_legs: list[ClosedPositionLeg] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_fetch_ms: int = 0

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name="exchange-orders-service",
            daemon=True,
        )
        self._thread.start()
        logger.info("exchange orders service started")

    def stop(self) -> None:
        self._stop.set()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def snapshot(self) -> dict[str, object]:
        """Build the full orders snapshot for the WS handler."""
        open_legs = self._account_worker.read_positions()
        with self._lock:
            closed_legs = list(self._closed_legs)

        groups = self._group_legs(open_legs, closed_legs)
        open_count = sum(1 for g in groups if g["status"] == "open")
        closed_count = sum(1 for g in groups if g["status"] == "closed")
        total_pnl = 0.0
        for g in groups:
            val = g.get("pnl_usdt")
            if isinstance(val, (int, float)):
                total_pnl += val
        return {
            "summary": {
                "open_count": open_count,
                "closed_count": closed_count,
                "total_pnl_usdt": round(total_pnl, 4),
            },
            "groups": groups,
        }

    def _run(self) -> None:
        try:
            self._fetch_closed()
        except Exception:
            logger.exception("exchange orders service initial fetch failed")
        while not self._stop.is_set():
            self._stop.wait(timeout=60.0)
            if self._stop.is_set():
                break
            try:
                self._fetch_closed()
            except Exception:
                logger.exception("exchange orders service fetch failed")

    def _fetch_closed(self) -> None:
        seven_days_ms = 7 * 24 * 3600 * 1000
        since_ms = int(time.time() * 1000) - seven_days_ms
        exchange_ids = [
            eid for eid in self._settings.enabled_exchanges
            if self._settings.credentials_for(eid) is not None
        ]
        if not exchange_ids:
            return

        loop = asyncio.new_event_loop()
        try:
            all_closed = loop.run_until_complete(
                self._async_fetch_closed(exchange_ids, since_ms)
            )
        finally:
            loop.close()

        with self._lock:
            self._closed_legs = all_closed
        self._last_fetch_ms = int(time.time() * 1000)
        logger.debug(
            "exchange orders: fetched closed | count={}", len(all_closed)
        )

    async def _async_fetch_closed(
        self,
        exchange_ids: list[str],
        since_ms: int,
    ) -> list[ClosedPositionLeg]:
        # Use symbols from currently open positions as hints for exchanges
        # that require them (e.g. bingx/fetchMyTrades)
        open_legs = self._account_worker.read_positions()
        known_symbols: list[str] = sorted({leg.symbol for leg in open_legs})

        all_legs: list[ClosedPositionLeg] = []
        for exchange_id in exchange_ids:
            named = self._factory.create(exchange_id)
            try:
                legs = await named.gateway.fetch_closed_positions(
                    since_ms=since_ms, symbols=known_symbols
                )
                all_legs.extend(legs)
            except Exception:
                logger.exception(
                    "fetch closed positions failed | exchange={}",
                    exchange_id,
                )
            finally:
                try:
                    await named.gateway.close()
                except Exception:
                    pass
        return all_legs

    def _group_legs(
        self,
        open_legs: list[PositionLeg],
        closed_legs: list[ClosedPositionLeg],
    ) -> list[dict[str, object]]:
        """Group legs into arb pairs and ungrouped singles.

        Sort order:
        1. Grouped open pairs
        2. Grouped closed pairs
        3. Ungrouped open legs
        4. Ungrouped closed legs
        """
        grouped_open: list[dict[str, object]] = []
        grouped_closed: list[dict[str, object]] = []
        ungrouped_open: list[dict[str, object]] = []
        ungrouped_closed: list[dict[str, object]] = []

        # --- open positions: group by symbol ---
        open_by_symbol: dict[str, list[PositionLeg]] = {}
        for leg in open_legs:
            open_by_symbol.setdefault(leg.symbol, []).append(leg)

        used_open: set[str] = set()
        for symbol, legs in open_by_symbol.items():
            shorts = [l for l in legs if l.side == "short"]
            longs = [l for l in legs if l.side == "long"]
            for short in shorts:
                for long in longs:
                    if short.exchange_id != long.exchange_id:
                        key_s = f"{short.exchange_id}:{short.position_id or id(short)}"
                        key_l = f"{long.exchange_id}:{long.position_id or id(long)}"
                        if key_s in used_open or key_l in used_open:
                            continue
                        used_open.add(key_s)
                        used_open.add(key_l)
                        grouped_open.append(
                            self._open_pair_to_group(short, long)
                        )

            for leg in legs:
                key = f"{leg.exchange_id}:{leg.position_id or id(leg)}"
                if key not in used_open:
                    ungrouped_open.append(self._open_leg_to_single(leg))

        # --- closed positions: group by symbol + arb_marker_id ---
        closed_by_marker: dict[str, list[ClosedPositionLeg]] = {}
        closed_by_symbol: dict[str, list[ClosedPositionLeg]] = {}
        for cl in closed_legs:
            if cl.arb_marker_id:
                closed_by_marker.setdefault(cl.arb_marker_id, []).append(cl)
            else:
                closed_by_symbol.setdefault(cl.symbol, []).append(cl)

        used_closed: set[int] = set()
        for _marker, marker_legs in closed_by_marker.items():
            c_shorts = [l for l in marker_legs if l.side == "short"]
            c_longs = [l for l in marker_legs if l.side == "long"]
            if c_shorts and c_longs:
                s = c_shorts[0]
                lo = c_longs[0]
                used_closed.add(id(s))
                used_closed.add(id(lo))
                grouped_closed.append(self._closed_pair_to_group(s, lo))
            else:
                for cl in marker_legs:
                    if id(cl) not in used_closed:
                        used_closed.add(id(cl))
                        ungrouped_closed.append(self._closed_leg_to_single(cl))

        for _sym, sym_legs in closed_by_symbol.items():
            c_shorts = [l for l in sym_legs if l.side == "short" and id(l) not in used_closed]
            c_longs = [l for l in sym_legs if l.side == "long" and id(l) not in used_closed]
            for c_short in list(c_shorts):
                for c_long in list(c_longs):
                    if c_short.exchange_id != c_long.exchange_id:
                        used_closed.add(id(c_short))
                        used_closed.add(id(c_long))
                        c_shorts.remove(c_short)
                        c_longs.remove(c_long)
                        grouped_closed.append(
                            self._closed_pair_to_group(c_short, c_long)
                        )
                        break

            for cl in sym_legs:
                if id(cl) not in used_closed:
                    ungrouped_closed.append(self._closed_leg_to_single(cl))

        return grouped_open + grouped_closed + ungrouped_open + ungrouped_closed

    @staticmethod
    def _funding_countdown_sec(legs: list[PositionLeg]) -> int | None:
        now = datetime.now().astimezone()
        earliest: datetime | None = None
        for leg in legs:
            if leg.next_funding_at is None:
                continue
            nf = leg.next_funding_at
            if nf.tzinfo is None:
                nf = nf.replace(tzinfo=_dt.UTC)
            if earliest is None or nf < earliest:
                earliest = nf
        if earliest is None:
            return None
        diff = (earliest - now).total_seconds()
        return max(0, int(diff))

    def _open_pair_to_group(
        self, short: PositionLeg, long: PositionLeg
    ) -> dict[str, object]:
        notional = (short.contracts * short.contract_size * short.entry_price) + (
            long.contracts * long.contract_size * long.entry_price
        )
        pnl = (short.unrealized_pnl or 0.0) + (long.unrealized_pnl or 0.0)
        fees = (
            (short.opening_fee or 0.0)
            + (short.estimated_close_fee or 0.0)
            + (long.opening_fee or 0.0)
            + (long.estimated_close_fee or 0.0)
        )
        funding = (short.accrued_funding or 0.0) + (long.accrued_funding or 0.0)
        opened_at = min(short.opened_at, long.opened_at)
        countdown = self._funding_countdown_sec([short, long])
        short_mark = short.mark_price or short.entry_price
        long_mark = long.mark_price or long.entry_price
        current_spread_pct = round(
            (short_mark - long_mark) / long_mark * 100.0, 2
        ) if long_mark > 0 else None
        return {
            "asset": short.symbol.replace("/USDT:USDT", ""),
            "symbol": short.symbol,
            "strategy_code": "FF",
            "short_exchange_id": short.exchange_id,
            "long_exchange_id": long.exchange_id,
            "status": "open",
            "opened_at": _fmt_dt(opened_at),
            "closed_at": None,
            "leverage": "—",
            "volume_usdt": round(notional, 2),
            "fees_usdt": round(fees, 4),
            "funding_usdt": round(funding, 4),
            "pnl_usdt": round(pnl, 4),
            "funding_countdown_sec": countdown,
            "current_spread_pct": current_spread_pct,
            "legs": [
                self._position_leg_dict(short),
                self._position_leg_dict(long),
            ],
        }

    def _closed_pair_to_group(
        self, short: ClosedPositionLeg, long: ClosedPositionLeg
    ) -> dict[str, object]:
        pnl = (short.realized_pnl or 0.0) + (long.realized_pnl or 0.0)
        fees = (short.commission or 0.0) + (long.commission or 0.0)
        funding = (short.funding or 0.0) + (long.funding or 0.0)
        opened_at = short.opened_at or long.opened_at
        closed_at = max(short.closed_at, long.closed_at)
        short_exit = short.exit_price
        long_exit = long.exit_price
        exit_spread_pct = round(
            (short_exit - long_exit) / long_exit * 100.0, 2
        ) if short_exit and long_exit and long_exit > 0 else None
        short_notional = (short.contracts or 0.0) * (short_exit or short.entry_price or 0.0)
        long_notional = (long.contracts or 0.0) * (long_exit or long.entry_price or 0.0)
        volume = round(short_notional + long_notional, 2) if (short_notional + long_notional) > 0 else None
        return {
            "asset": short.symbol.replace("/USDT:USDT", ""),
            "symbol": short.symbol,
            "strategy_code": "FF",
            "short_exchange_id": short.exchange_id,
            "long_exchange_id": long.exchange_id,
            "status": "closed",
            "opened_at": _fmt_dt(opened_at) if opened_at else "—",
            "closed_at": _fmt_dt(closed_at),
            "leverage": "—",
            "volume_usdt": volume,
            "fees_usdt": round(fees, 4),
            "funding_usdt": round(funding, 4),
            "pnl_usdt": round(pnl, 4),
            "exit_spread_pct": exit_spread_pct,
            "legs": [
                self._closed_leg_dict(short),
                self._closed_leg_dict(long),
            ],
        }

    def _open_leg_to_single(self, leg: PositionLeg) -> dict[str, object]:
        notional = leg.contracts * leg.contract_size * leg.entry_price
        return {
            "asset": leg.symbol.replace("/USDT:USDT", ""),
            "symbol": leg.symbol,
            "strategy_code": "—",
            "short_exchange_id": leg.exchange_id if leg.side == "short" else "—",
            "long_exchange_id": leg.exchange_id if leg.side == "long" else "—",
            "status": "open",
            "opened_at": _fmt_dt(leg.opened_at),
            "closed_at": None,
            "leverage": "—",
            "volume_usdt": round(notional, 2),
            "fees_usdt": round((leg.opening_fee or 0.0) + (leg.estimated_close_fee or 0.0), 4),
            "funding_usdt": round(leg.accrued_funding or 0.0, 4),
            "pnl_usdt": round(leg.unrealized_pnl or 0.0, 4),
            "funding_countdown_sec": self._funding_countdown_sec([leg]),
            "legs": [self._position_leg_dict(leg)],
        }

    def _closed_leg_to_single(self, leg: ClosedPositionLeg) -> dict[str, object]:
        opened_at = leg.opened_at
        ref_price = leg.exit_price or leg.entry_price or 0.0
        volume = round((leg.contracts or 0.0) * ref_price, 2) or None
        return {
            "asset": leg.symbol.replace("/USDT:USDT", ""),
            "symbol": leg.symbol,
            "strategy_code": "—",
            "short_exchange_id": leg.exchange_id if leg.side == "short" else "—",
            "long_exchange_id": leg.exchange_id if leg.side == "long" else "—",
            "status": "closed",
            "opened_at": _fmt_dt(opened_at) if opened_at else "—",
            "closed_at": _fmt_dt(leg.closed_at),
            "leverage": "—",
            "volume_usdt": volume,
            "fees_usdt": round(leg.commission or 0.0, 4),
            "funding_usdt": round(leg.funding or 0.0, 4),
            "pnl_usdt": round(leg.realized_pnl or 0.0, 4),
            "legs": [self._closed_leg_dict(leg)],
        }

    @staticmethod
    def _position_leg_dict(leg: PositionLeg) -> dict[str, object]:
        notional = leg.contracts * leg.contract_size * leg.entry_price
        return {
            "exchange_id": leg.exchange_id,
            "side": leg.side,
            "leverage": "—",
            "volume_usdt": round(notional, 2),
            "entry_price": leg.entry_price,
            "exit_price": None,
            "fees_usdt": round(
                (leg.opening_fee or 0.0) + (leg.estimated_close_fee or 0.0), 4
            ),
            "funding_usdt": round(leg.accrued_funding or 0.0, 4),
            "pnl_usdt": round(leg.unrealized_pnl or 0.0, 4),
        }

    @staticmethod
    def _closed_leg_dict(leg: ClosedPositionLeg) -> dict[str, object]:
        ref_price = leg.exit_price or leg.entry_price or 0.0
        volume = round((leg.contracts or 0.0) * ref_price, 2) or None
        return {
            "exchange_id": leg.exchange_id,
            "side": leg.side,
            "leverage": "—",
            "volume_usdt": volume,
            "entry_price": leg.entry_price,
            "exit_price": leg.exit_price,
            "fees_usdt": round(leg.commission or 0.0, 4),
            "funding_usdt": round(leg.funding or 0.0, 4),
            "pnl_usdt": round(leg.realized_pnl or 0.0, 4),
        }


_EPOCH_ZERO = datetime(1970, 1, 1, tzinfo=_dt.timezone.utc)


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is not None and dt <= _EPOCH_ZERO:
        return "—"
    local = dt.astimezone() if dt.tzinfo is not None else dt
    return local.strftime("%m/%d %H:%M")
