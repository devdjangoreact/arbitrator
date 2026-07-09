from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Literal

from fastapi import WebSocket, WebSocketDisconnect

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.presentation.ws.ws_envelope import WsEnvelope

if TYPE_CHECKING:
    from arbitrator.application.app_runtime import AppRuntime
    from arbitrator.application.market_data.market_data_cache_memory import MarketDataCacheMemory
    from arbitrator.config.paper_order_store import PaperOrderStore
    from arbitrator.domain.opportunity.paper_order import PaperOrder


class PaperTradesWsHandler:
    """WebSocket handler for /ws/paper_trades.

    Sends a live snapshot of all paper (simulated) orders every push_interval
    seconds.  Each pair is returned as a group with open/closed status and
    per-leg detail.  Closed pairs include realised PnL; open pairs include the
    entry spread so the browser can compute an unrealised estimate.
    """

    def __init__(
        self,
        settings: Settings,
        paper_store: "PaperOrderStore | None" = None,
        runtime: "AppRuntime | None" = None,
    ) -> None:
        self._settings = settings
        self._paper_store = paper_store
        self._runtime = runtime

    @property
    def _market_cache(self) -> "MarketDataCacheMemory | None":
        if self._runtime is not None:
            return self._runtime.market_cache
        return None

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("ws connected | endpoint=/ws/paper_trades")
        push_interval = 1.0
        try:
            if self._paper_store is not None:
                await self._paper_loop(websocket, push_interval)
            else:
                await self._empty_loop(websocket)
        except WebSocketDisconnect:
            logger.info("ws disconnected | endpoint=/ws/paper_trades")
        except Exception:
            logger.exception("ws error | endpoint=/ws/paper_trades")
        finally:
            await WsEnvelope.safe_close(websocket)

    # ------------------------------------------------------------------ #

    async def _paper_loop(self, websocket: WebSocket, push_interval: float) -> None:
        assert self._paper_store is not None
        store = self._paper_store
        active_filter: Literal["all", "open", "closed"] = "all"
        receiver = asyncio.create_task(self._receive_commands(websocket))
        try:
            while True:
                all_orders = store.load_all()
                summary = store.summary()

                if active_filter == "open":
                    display = [o for o in all_orders if o.status == "filled"]
                elif active_filter == "closed":
                    display = [o for o in all_orders if o.status == "closed"]
                else:
                    display = all_orders

                groups = self._build_groups(display, all_orders, self._market_cache)

                snapshot: dict[str, object] = {
                    "filter": active_filter,
                    "summary": {
                        "open_pairs": summary.get("open_pairs", 0),
                        "closed_pairs": summary.get("closed_pairs", 0),
                        "total_pnl_usdt": summary.get("total_pnl_usdt", 0.0),
                        "total_net_pnl_usdt": summary.get("total_net_pnl_usdt", 0.0),
                        "total_fees_usdt": summary.get("total_fees_usdt", 0.0),
                        "total_funding_usdt": summary.get("total_funding_usdt", 0.0),
                        "total_orders": summary.get("total_orders", 0),
                    },
                    "groups": groups,
                }
                await WsEnvelope.send_dict(websocket, "paper_trades.snapshot", snapshot)

                cmd = await self._poll_command(receiver, push_interval)
                if cmd is not None:
                    fv = str(cmd.get("filter", "all"))
                    if fv in {"all", "open", "closed"}:
                        active_filter = fv  # type: ignore[assignment]
                    receiver = asyncio.create_task(self._receive_commands(websocket))
        finally:
            receiver.cancel()
            await WsEnvelope.await_receiver(receiver)

    async def _empty_loop(self, websocket: WebSocket) -> None:
        snapshot: dict[str, object] = {
            "filter": "all",
            "summary": {"open_pairs": 0, "closed_pairs": 0, "total_pnl_usdt": 0.0, "total_orders": 0},
            "groups": [],
        }
        await WsEnvelope.send_dict(websocket, "paper_trades.snapshot", snapshot)
        while True:
            await asyncio.sleep(60)

    async def _receive_commands(self, websocket: WebSocket) -> dict[str, object]:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and msg.get("type") == "paper_trades.set_filter":
                payload = msg.get("payload")
                if isinstance(payload, dict):
                    return payload
        return {}

    @staticmethod
    async def _poll_command(
        receiver: asyncio.Task[dict[str, object]],
        timeout: float,
    ) -> dict[str, object] | None:
        done, _ = await asyncio.wait({receiver}, timeout=timeout)
        if receiver in done:
            return receiver.result()
        return None

    @staticmethod
    def _build_groups(
        display_orders: list["PaperOrder"],
        all_orders: list["PaperOrder"],
        market_cache: "MarketDataCacheMemory | None" = None,
    ) -> list[dict[str, object]]:
        """Group orders by pair_id and enrich with entry/exit spread and PnL."""
        # Build a lookup: pair_id -> all legs (for entry spread)
        all_by_pair: dict[str, list["PaperOrder"]] = {}
        for o in all_orders:
            all_by_pair.setdefault(o.pair_id, []).append(o)

        by_pair: dict[str, list["PaperOrder"]] = {}
        for o in display_orders:
            by_pair.setdefault(o.pair_id, []).append(o)

        groups: list[dict[str, object]] = []
        for pair_id, legs in by_pair.items():
            all_legs = all_by_pair.get(pair_id, legs)
            sell_leg = next((l for l in all_legs if l.side == "sell"), None)
            buy_leg = next((l for l in all_legs if l.side == "buy"), None)

            is_open = any(l.status == "filled" for l in all_legs)

            # Compute unrealized PnL for open legs from live prices
            total_pnl = 0.0
            for leg in all_legs:
                if leg.pnl_usdt is not None:
                    total_pnl += leg.pnl_usdt
                elif leg.status == "filled" and market_cache is not None:
                    quote = market_cache.get_quote(leg.exchange_id, leg.symbol, "futures")
                    if quote is not None:
                        mid = (float(quote.bid) + float(quote.ask)) / 2 if quote.bid and quote.ask else None
                        if mid is not None:
                            entry = leg.entry_price or leg.price
                            if leg.side == "sell":
                                total_pnl += (entry - mid) * leg.amount
                            else:
                                total_pnl += (mid - entry) * leg.amount

            total_fees = sum(
                l.open_fee_usdt + l.close_fee_usdt for l in all_legs
            )
            total_funding = sum(l.accrued_funding_usdt for l in all_legs)
            total_net_pnl = sum(
                l.net_pnl_usdt for l in all_legs if l.net_pnl_usdt is not None
            )

            entry_spread = (
                sell_leg.spread_pct_entry
                if sell_leg and sell_leg.spread_pct_entry is not None
                else None
            )
            exit_spread = (
                sell_leg.spread_pct_exit
                if sell_leg and sell_leg.spread_pct_exit is not None
                else None
            )

            short_ex = sell_leg.exchange_id if sell_leg else "—"
            long_ex = buy_leg.exchange_id if buy_leg else "—"
            short_entry = sell_leg.entry_price if sell_leg else None
            long_entry = buy_leg.entry_price if buy_leg else None
            short_close_price = sell_leg.close_price if sell_leg and sell_leg.status == "closed" else None
            long_close_price = buy_leg.close_price if buy_leg and buy_leg.status == "closed" else None
            closed_leg = next((l for l in all_legs if l.closed_at is not None), None)
            closed_at_iso = closed_leg.closed_at.isoformat() if closed_leg and closed_leg.closed_at else None
            notional = (sell_leg.notional_usdt if sell_leg else 0.0) + (buy_leg.notional_usdt if buy_leg else 0.0)

            # Live exit prices for open pairs (group level, mirrors leg current_price)
            current_short_price: float | None = None
            current_long_price: float | None = None
            if is_open and market_cache is not None:
                if sell_leg is not None and sell_leg.status == "filled":
                    current_short_price = PaperTradesWsHandler._get_mid_price(
                        sell_leg.exchange_id, sell_leg.symbol, market_cache
                    )
                if buy_leg is not None and buy_leg.status == "filled":
                    current_long_price = PaperTradesWsHandler._get_mid_price(
                        buy_leg.exchange_id, buy_leg.symbol, market_cache
                    )

            # Per-leg funding info (countdown + rate per exchange)
            leg_funding_infos: dict[str, dict[str, object]] = {}
            if market_cache is not None:
                for leg in all_legs:
                    if leg.status != "filled":
                        continue
                    fi = market_cache.get_funding(leg.exchange_id, leg.symbol)
                    next_ms: int | None = fi.next_settlement_ms if fi is not None else None
                    rate_pct: float | None = None
                    next_charge: float | None = None
                    if fi is not None and fi.rate is not None:
                        rate_pct = round(float(fi.rate) * 100.0, 4)
                        charge_raw = leg.notional_usdt * float(fi.rate)
                        next_charge = round(charge_raw if leg.side == "buy" else -charge_raw, 4)
                    leg_funding_infos[leg.order_id] = {
                        "next_funding_ms": next_ms,
                        "funding_rate_pct": rate_pct,
                        "next_funding_charge_usdt": next_charge,
                    }

            groups.append({
                "pair_id": pair_id,
                "symbol": legs[0].symbol,
                "status": "open" if is_open else "closed",
                "short_exchange_id": short_ex,
                "long_exchange_id": long_ex,
                "short_entry_price": short_entry,
                "long_entry_price": long_entry,
                "short_close_price": short_close_price,
                "long_close_price": long_close_price,
                "current_short_price": current_short_price,
                "current_long_price": current_long_price,
                "entry_spread_pct": entry_spread,
                "exit_spread_pct": exit_spread,
                "notional_usdt": round(notional, 4),
                "opened_at": legs[0].opened_at.isoformat(),
                "closed_at": closed_at_iso,
                "pnl_usdt": round(total_pnl, 4),
                "fees_usdt": round(total_fees, 4),
                "funding_usdt": round(total_funding, 4),
                "net_pnl_usdt": round(total_net_pnl, 4) if not is_open else round(total_pnl - total_fees - total_funding, 4),
                "legs": [
                    {
                        "order_id": l.order_id,
                        "exchange_id": l.exchange_id,
                        "side": l.side,
                        "amount": l.amount,
                        "entry_price": l.entry_price,
                        "close_price": l.close_price if l.status == "closed" else None,
                        "current_price": PaperTradesWsHandler._get_mid_price(
                            l.exchange_id, l.symbol, market_cache
                        ) if l.status == "filled" else None,
                        "notional_usdt": l.notional_usdt,
                        "status": l.status,
                        "pnl_usdt": l.pnl_usdt,
                        "open_fee_usdt": l.open_fee_usdt,
                        "close_fee_usdt": l.close_fee_usdt,
                        "accrued_funding_usdt": l.accrued_funding_usdt,
                        "net_pnl_usdt": l.net_pnl_usdt,
                        "spread_pct_entry": l.spread_pct_entry,
                        "spread_pct_exit": l.spread_pct_exit,
                        **leg_funding_infos.get(l.order_id, {}),
                    }
                    for l in legs
                ],
            })

        # sort: open first, then by opened_at desc
        groups.sort(key=lambda g: (0 if g["status"] == "open" else 1, str(g["opened_at"])), reverse=False)
        groups.sort(key=lambda g: g["status"] == "closed")
        return groups

    @staticmethod
    def _get_funding_rate_pct(
        exchange_id: str,
        symbol: str,
        market_cache: "MarketDataCacheMemory | None",
    ) -> float | None:
        if market_cache is None:
            return None
        fi = market_cache.get_funding(exchange_id, symbol)
        if fi is None or fi.rate is None:
            return None
        return round(float(fi.rate) * 100.0, 4)

    @staticmethod
    def _get_mid_price(
        exchange_id: str,
        symbol: str,
        market_cache: "MarketDataCacheMemory | None",
    ) -> float | None:
        if market_cache is None:
            return None
        quote = market_cache.get_quote(exchange_id, symbol, "futures")
        if quote is None:
            return None
        if quote.bid and quote.ask:
            return round((float(quote.bid) + float(quote.ask)) / 2, 6)
        if quote.last:
            return round(float(quote.last), 6)
        return None
