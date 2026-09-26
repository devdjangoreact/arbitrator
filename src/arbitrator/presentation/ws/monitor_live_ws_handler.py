from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from arbitrator.application.app_runtime import AppRuntime
from arbitrator.config.logger import logger


class MonitorLiveWsHandler:
    """Per-monitor live WebSocket: pushes market data every ~1s for one card."""

    PUSH_INTERVAL = 1.0

    def __init__(self, runtime: AppRuntime) -> None:
        self._runtime = runtime

    async def handle(self, websocket: WebSocket, monitor_id: str) -> None:
        await websocket.accept()

        logger.info("monitor live ws connected | monitor_id={}", monitor_id)

        try:
            while websocket.client_state == WebSocketState.CONNECTED:
                payload = self._build_payload(monitor_id)
                with contextlib.suppress(Exception):
                    await websocket.send_json(payload)

                # Wait for push interval, bail early on disconnect
                try:
                    await asyncio.wait_for(
                        websocket.receive_text(), timeout=self.PUSH_INTERVAL
                    )
                except (asyncio.TimeoutError, Exception):
                    pass

        except Exception:
            logger.exception("monitor live ws error | monitor_id={}", monitor_id)
        finally:
            logger.info("monitor live ws disconnected | monitor_id={}", monitor_id)

    def _build_payload(self, monitor_id: str) -> dict[str, Any]:
        trader = self._runtime.historical_auto_trader
        cache = self._runtime.market_cache

        # Try live_state from trader first
        if trader is not None:
            state = trader.get_live_state().get(monitor_id)
            if state:
                return {"type": "monitor_update", "data": state}

        # Fallback: build snapshot directly from market cache
        if cache is None:
            return {"type": "monitor_update", "data": {}}

        store = self._runtime.monitor_store
        config = store.get(monitor_id)
        if config is None:
            return {"type": "monitor_update", "data": {}}

        short_ex = config.short_exchange
        long_ex = config.long_exchange
        symbol = config.symbol

        def _flt(val: Any) -> float | None:
            try:
                return float(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        def _rate(fi: Any) -> float | None:
            r = getattr(fi, "rate", None)
            return float(r * 100) if r is not None else None

        def _fmt_next_funding(fi: Any) -> str | None:
            ms = getattr(fi, "next_settlement_ms", None)
            if ms is None:
                return None
            secs = max(0, int(ms / 1000 - time.time()))
            h, rem = divmod(secs, 3600)
            m, s_rem = divmod(rem, 60)
            return f"{h:02d}:{m:02d}:{s_rem:02d}"

        sf = cache.get_funding(short_ex, symbol)
        lf = cache.get_funding(long_ex, symbol)

        def _top(ex: str) -> tuple[float | None, float | None]:
            ob = cache.get_order_book(ex, symbol)
            if ob and ob.bids and ob.asks:
                return _flt(ob.bids[0].price), _flt(ob.asks[0].price)
            q = cache.get_quote(ex, symbol, "futures")
            if q:
                return _flt(getattr(q, "bid", None)), _flt(getattr(q, "ask", None))
            return None, None

        short_bid, short_ask = _top(short_ex)
        long_bid, long_ask = _top(long_ex)
        sq = cache.get_quote(short_ex, symbol, "futures")
        lq = cache.get_quote(long_ex, symbol, "futures")

        data: dict[str, Any] = {
            "active_short": short_ex,
            "active_long": long_ex,
            "short_funding_rate": _rate(sf),
            "long_funding_rate": _rate(lf),
            "short_next_funding": _fmt_next_funding(sf),
            "long_next_funding": _fmt_next_funding(lf),
            "short_ask": short_ask,
            "long_ask": long_ask,
            "short_bid": short_bid,
            "long_bid": long_bid,
            "short_size": _flt(getattr(sq, "ask_size", None)) if sq else None,
            "long_size": _flt(getattr(lq, "bid_size", None)) if lq else None,
            "short_price": short_ask or short_bid,
            "long_price": long_bid or long_ask,
            "short_leverage": config.short_leverage,
            "long_leverage": config.long_leverage,
            "max_size_short": _flt(getattr(cache.get_market_info(short_ex, symbol), "max_order_volume_usdt", None)),
            "max_size_long": _flt(getattr(cache.get_market_info(long_ex, symbol), "max_order_volume_usdt", None)),
            "min_size_short": _flt(getattr(cache.get_market_info(short_ex, symbol), "min_order_volume_usdt", None)),
            "min_size_long": _flt(getattr(cache.get_market_info(long_ex, symbol), "min_order_volume_usdt", None)),
            "short_pnl": None,
            "long_pnl": None,
            "short_realized_pnl": 0.0,
            "long_realized_pnl": 0.0,
            "enter_spread_short": None,
            "enter_spread_long": None,
            "allowed_short": (cache.get_usdt_balance(short_ex) or 0.0) * (config.short_leverage or 1) or None,
            "allowed_long": (cache.get_usdt_balance(long_ex) or 0.0) * (config.long_leverage or 1) or None,
            "short_orders": 0,
            "long_orders": 0,
            "open_spread_current": 0.0,
            "open_spread_min": 0.0,
            "open_spread_max": 0.0,
            "close_spread_current": 0.0,
            "close_spread_min": 0.0,
            "close_spread_max": 0.0,
        }
        return {"type": "monitor_update", "data": data}
