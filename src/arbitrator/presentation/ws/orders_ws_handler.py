from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal, cast

from fastapi import WebSocket, WebSocketDisconnect

from arbitrator.config.logger import logger
from arbitrator.config.settings import Settings
from arbitrator.presentation.mock.mock_data_provider import MockDataProvider
from arbitrator.presentation.ws.ws_envelope import WsEnvelope

if TYPE_CHECKING:
    from arbitrator.application.app_runtime import AppRuntime
    from arbitrator.application.exchange_orders_service import ExchangeOrdersService
    from arbitrator.config.paper_order_store import PaperOrderStore

_STRATEGY_LABELS: dict[str | None, str] = {
    "futures_futures": "FF",
    "futures_spot_2ex": "FS-2",
    "futures_spot_1ex": "FS-1",
    "funding_ff": "Fund-FF",
    "funding_fs": "Fund-FS",
    "funding_diff_dates": "Fund-DD",
}


def _strategy_label(kind: str | None, *, paper: bool = False) -> str:
    base = _STRATEGY_LABELS.get(kind, kind or "—")
    return f"{base} paper" if paper else base


class OrdersWsHandler:
    """WebSocket handler for /ws/orders."""

    def __init__(
        self,
        settings: Settings,
        mock_provider: MockDataProvider | None,
        paper_store: "PaperOrderStore | None" = None,
        runtime: "AppRuntime | None" = None,
    ) -> None:
        self._settings = settings
        self._mock_provider = mock_provider
        self._paper_store = paper_store
        self._runtime = runtime
        self._last_summary: tuple[int, int] | None = None

    @property
    def _exchange_orders_service(self) -> "ExchangeOrdersService | None":
        if self._runtime is not None:
            return self._runtime.exchange_orders_service
        return None

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("ws connected | endpoint=/ws/orders")
        push_interval = self._settings.screener_ws_push_seconds
        try:
            if self._settings.ui_data_mode == "mock_data":
                await self._mock_loop(websocket, push_interval)
            elif self._exchange_orders_service is not None:
                await self._exchange_orders_loop(websocket, push_interval)
            elif self._settings.ui_data_mode == "paper" and self._paper_store is not None:
                await self._paper_loop(websocket, push_interval)
            else:
                await self._live_loop(websocket, push_interval)
        except WebSocketDisconnect:
            logger.info("ws disconnected | endpoint=/ws/orders")
        except Exception:
            logger.exception("ws error | endpoint=/ws/orders")
        finally:
            await WsEnvelope.safe_close(websocket)

    async def _paper_loop(self, websocket: WebSocket, push_interval: float) -> None:
        assert self._paper_store is not None
        store = self._paper_store
        active_filter: Literal["all", "open", "closed"] = "all"
        receiver = asyncio.create_task(self._receive_paper_commands(websocket))
        try:
            while True:
                orders = store.load_all()
                if active_filter == "open":
                    orders = [o for o in orders if o.status == "filled"]
                elif active_filter == "closed":
                    orders = [o for o in orders if o.status == "closed"]

                open_count = sum(1 for o in store.load_all() if o.status == "filled")
                closed_count = sum(1 for o in store.load_all() if o.status == "closed")
                summary = store.summary()

                groups = self._build_groups(orders)
                snapshot: dict[str, object] = {
                    "summary": {
                        "open_count": open_count,
                        "closed_count": closed_count,
                        "total_pnl_usdt": summary.get("total_pnl_usdt", 0.0),
                    },
                    "filter": active_filter,
                    "groups": groups,
                }
                await WsEnvelope.send_dict(websocket, "orders.snapshot", snapshot)

                new_summary = (open_count, closed_count)
                if new_summary != self._last_summary:
                    self._last_summary = new_summary
                    await WsEnvelope.send_dict(websocket, "orders.summary", cast(dict[str, object], snapshot["summary"]))

                cmd = await self._poll_command(receiver, push_interval)
                if cmd is not None:
                    filter_val = str(cmd.get("filter", "all"))
                    if filter_val in {"all", "open", "closed"}:
                        active_filter = filter_val  # type: ignore[assignment]
        finally:
            receiver.cancel()
            await WsEnvelope.await_receiver(receiver)

    async def _exchange_orders_loop(
        self, websocket: WebSocket, push_interval: float
    ) -> None:
        assert self._exchange_orders_service is not None
        service = self._exchange_orders_service
        active_filter: Literal["all", "open", "closed"] = "all"
        receiver = asyncio.create_task(self._receive_paper_commands(websocket))
        try:
            while True:
                raw_snapshot = service.snapshot()
                groups = raw_snapshot.get("groups", [])
                if not isinstance(groups, list):
                    groups = []

                if active_filter == "open":
                    groups = [g for g in groups if g.get("status") == "open"]
                elif active_filter == "closed":
                    groups = [g for g in groups if g.get("status") == "closed"]

                open_count = sum(1 for g in groups if g.get("status") == "open")
                closed_count = sum(1 for g in groups if g.get("status") == "closed")
                total_pnl = 0.0
                for g in groups:
                    v = g.get("pnl_usdt")
                    if isinstance(v, (int, float)):
                        total_pnl += v

                snapshot: dict[str, object] = {
                    "summary": {
                        "open_count": open_count,
                        "closed_count": closed_count,
                        "total_pnl_usdt": round(total_pnl, 4),
                    },
                    "filter": active_filter,
                    "groups": groups,
                }
                await WsEnvelope.send_dict(websocket, "orders.snapshot", snapshot)

                new_summary = (open_count, closed_count)
                if new_summary != self._last_summary:
                    self._last_summary = new_summary
                    await WsEnvelope.send_dict(
                        websocket,
                        "orders.summary",
                        cast(dict[str, object], snapshot["summary"]),
                    )

                cmd = await self._poll_command(receiver, push_interval)
                if cmd is not None:
                    filter_val = str(cmd.get("filter", "all"))
                    if filter_val in {"all", "open", "closed"}:
                        active_filter = filter_val  # type: ignore[assignment]
                    receiver = asyncio.create_task(
                        self._receive_paper_commands(websocket)
                    )
        finally:
            receiver.cancel()
            await WsEnvelope.await_receiver(receiver)

    def _build_paper_order_groups(self) -> list[dict[str, object]]:
        """Convert paper orders into the same group format as exchange orders."""
        assert self._paper_store is not None
        from arbitrator.domain.paper_order import PaperOrder

        orders = self._paper_store.load_all()
        by_pair: dict[str, list[PaperOrder]] = {}
        for o in orders:
            by_pair.setdefault(o.pair_id, []).append(o)

        groups: list[dict[str, object]] = []
        for pair_id, legs in by_pair.items():
            sell_leg = next((l for l in legs if l.side == "sell"), None)
            buy_leg = next((l for l in legs if l.side == "buy"), None)
            is_open = any(l.status == "filled" for l in legs)
            total_pnl = sum(l.pnl_usdt for l in legs if l.pnl_usdt is not None)
            total_fees = sum(l.open_fee_usdt + l.close_fee_usdt for l in legs)
            total_funding = sum(l.accrued_funding_usdt for l in legs)
            notional = sum(l.notional_usdt for l in legs)

            short_ex = sell_leg.exchange_id if sell_leg else "—"
            long_ex = buy_leg.exchange_id if buy_leg else "—"
            opened_at = legs[0].opened_at.strftime("%m/%d %H:%M")
            closed_at_dt = sell_leg.closed_at if sell_leg and sell_leg.closed_at else None
            closed_str = closed_at_dt.strftime("%m/%d %H:%M") if closed_at_dt else None

            # Use strategy_kind from the order record (first leg that has it)
            raw_strategy = next(
                (l.strategy_kind for l in legs if l.strategy_kind), None
            )
            strategy_label = _strategy_label(raw_strategy, paper=True)

            groups.append({
                "asset": legs[0].symbol.replace("/USDT:USDT", ""),
                "symbol": legs[0].symbol,
                "strategy_code": strategy_label,
                "short_exchange_id": short_ex,
                "long_exchange_id": long_ex,
                "status": "open" if is_open else "closed",
                "opened_at": opened_at,
                "closed_at": closed_str,
                "leverage": "—",
                "volume_usdt": round(notional, 2),
                "fees_usdt": round(total_fees, 4),
                "funding_usdt": round(total_funding, 4),
                "pnl_usdt": round(total_pnl, 4),
                "legs": [
                    {
                        "exchange_id": l.exchange_id,
                        "side": "short" if l.side == "sell" else "long",
                        "leverage": "—",
                        "volume_usdt": round(l.notional_usdt, 2),
                        "entry_price": l.entry_price,
                        "exit_price": None,
                        "fees_usdt": round(l.open_fee_usdt + l.close_fee_usdt, 4),
                        "funding_usdt": round(l.accrued_funding_usdt, 4),
                        "pnl_usdt": round(l.pnl_usdt, 4) if l.pnl_usdt is not None else None,
                    }
                    for l in legs
                ],
            })

        # Sort: open first, then closed
        groups.sort(key=lambda g: 0 if g["status"] == "open" else 1)
        return groups

    async def _receive_paper_commands(self, websocket: WebSocket) -> dict[str, object]:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(msg, dict) and msg.get("type") == "orders.set_filter":
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
    def _build_groups(orders: list["PaperOrder"]) -> list[dict[str, object]]:  # type: ignore[name-defined]
        from arbitrator.domain.paper_order import PaperOrder

        by_pair: dict[str, list[PaperOrder]] = {}
        for o in orders:
            by_pair.setdefault(o.pair_id, []).append(o)
        groups: list[dict[str, object]] = []
        for pair_id, legs in by_pair.items():
            first = legs[0]
            total_pnl = sum(l.pnl_usdt for l in legs if l.pnl_usdt is not None)
            groups.append(
                {
                    "pair_id": pair_id,
                    "symbol": first.symbol,
                    "status": "open" if any(l.status == "filled" for l in legs) else "closed",
                    "opened_at": first.opened_at.isoformat(),
                    "pnl_usdt": round(total_pnl, 4),
                    "legs": [
                        {
                            "order_id": l.order_id,
                            "exchange_id": l.exchange_id,
                            "side": l.side,
                            "action": l.action,
                            "amount": l.amount,
                            "price": l.price,
                            "notional_usdt": l.notional_usdt,
                            "status": l.status,
                            "pnl_usdt": l.pnl_usdt,
                        }
                        for l in legs
                    ],
                }
            )
        return groups

    async def _live_loop(self, websocket: WebSocket, push_interval: float) -> None:
        snapshot: dict[str, object] = {
            "summary": {"open_count": 0, "closed_count": 0},
            "filter": "all",
            "groups": [],
        }
        await WsEnvelope.send_dict(websocket, "orders.snapshot", snapshot)
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("type") == "orders.set_filter":
                payload = message.get("payload")
                if isinstance(payload, dict):
                    snapshot["filter"] = payload.get("filter", "all")
                await WsEnvelope.send_dict(websocket, "orders.snapshot", snapshot)

    async def _mock_loop(self, websocket: WebSocket, push_interval: float) -> None:
        if self._mock_provider is None:
            return
        provider = self._mock_provider
        receiver = asyncio.create_task(self._receive_commands(websocket, provider))
        try:
            while True:
                provider.tick()
                snapshot = provider.orders_snapshot()
                await WsEnvelope.send(websocket, "orders.snapshot", snapshot)
                summary = (snapshot.summary.open_count, snapshot.summary.closed_count)
                if summary != self._last_summary:
                    self._last_summary = summary
                    await WsEnvelope.send(websocket, "orders.summary", snapshot.summary)
                await asyncio.sleep(push_interval)
        finally:
            receiver.cancel()
            await WsEnvelope.await_receiver(receiver)

    async def _receive_commands(self, websocket: WebSocket, provider: MockDataProvider) -> None:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("type") != "orders.set_filter":
                continue
            payload = message.get("payload")
            if not isinstance(payload, Mapping):
                continue
            filter_value = str(payload.get("filter", "all"))
            if filter_value in {"all", "open", "closed"}:
                typed_filter: Literal["all", "open", "closed"] = filter_value  # type: ignore[assignment]
                provider.set_orders_filter(typed_filter)
                await WsEnvelope.send(
                    websocket,
                    "orders.snapshot",
                    provider.orders_snapshot(),
                )
