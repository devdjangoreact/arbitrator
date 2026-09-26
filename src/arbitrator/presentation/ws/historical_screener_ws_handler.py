from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from arbitrator.application.app_runtime import AppRuntime
from arbitrator.config.logger import logger
from arbitrator.config.monitor_config_store import MonitorConfig
from arbitrator.config.settings import Settings
from arbitrator.config.ui_config_manager import UIConfigManager


class HistoricalScreenerWsHandler:
    def __init__(
        self,
        settings: Settings,
        runtime: AppRuntime,
    ) -> None:
        self._settings = settings
        self._runtime = runtime

    async def handle(self, websocket: WebSocket) -> None:
        await websocket.accept()
        logger.info("historical screener ws client connected")

        await self._send_update(websocket)

        try:
            while websocket.client_state == WebSocketState.CONNECTED:
                push_interval = UIConfigManager.get_config().historical_screener_push_interval_seconds
                try:
                    data = await asyncio.wait_for(
                        websocket.receive_json(), timeout=float(push_interval)
                    )
                except TimeoutError:
                    await self._send_update(websocket)
                    continue
                except RuntimeError:
                    break

                # React UI sends {type, payload} envelope; legacy clients send {cmd, ...flat}
                cmd = data.get("type") or data.get("cmd")
                if not cmd:
                    continue
                p: Any = data.get("payload") or data

                worker = self._runtime.historical_screener_worker
                auto_trader = self._runtime.historical_auto_trader
                store = self._runtime.monitor_store

                if cmd == "refresh":
                    await self._send_update(websocket)

                elif cmd == "start":
                    if worker:
                        worker.start()
                    await self._send_update(websocket)

                elif cmd == "stop":
                    if worker:
                        worker.stop()
                    await self._send_update(websocket)

                elif cmd == "update_filters":
                    raw = {
                        "lookback_seconds": p.get("lookback_seconds"),
                        "spread_threshold_pct": p.get("min_spread_pct"),
                        "min_volume_usdt": p.get("min_volume_usdt"),
                        "min_analysis_volume_usdt": p.get("min_analysis_volume_usdt"),
                        "push_interval_seconds": p.get("push_interval_seconds"),
                        "candle_interval_seconds": p.get("candle_interval_seconds"),
                        "price_deviation_filter_pct": p.get("price_deviation_filter_pct"),
                    }
                    kwargs: dict[str, Any] = {}
                    for k, v in raw.items():
                        if v not in (None, ""):
                            if k in ("lookback_seconds", "push_interval_seconds", "candle_interval_seconds"):
                                kwargs[k] = int(float(v))
                            else:
                                kwargs[k] = float(v)
                    if worker:
                        worker.update_filters(**kwargs)
                    await self._send_update(websocket)

                elif cmd == "add_monitor":
                    symbol = p.get("symbol")
                    short_exchange = p.get("short_exchange")
                    long_exchange = p.get("long_exchange")
                    max_spread = float(p.get("max_spread", 0.0))
                    auto_start = bool(p.get("auto_start", False))

                    if not symbol or not short_exchange or not long_exchange:
                        continue

                    monitor_id = f"{symbol}:{short_exchange}:{long_exchange}"
                    if store.get(monitor_id):
                        await websocket.send_json({
                            "type": "error",
                            "data": {"code": "duplicate_monitor", "monitor_id": monitor_id}
                        })
                        continue

                    cfg = UIConfigManager.get_config()
                    config = MonitorConfig(
                        symbol=symbol,
                        short_exchange=short_exchange,
                        long_exchange=long_exchange,
                        open_spread_pct=cfg.historical_monitor_open_spread_pct,
                        close_spread_pct=cfg.historical_monitor_close_spread_pct,
                        order_size_usdt=cfg.historical_monitor_notional_usdt,
                        max_historical_spread_pct=max_spread,
                        is_active=auto_start,
                    )
                    store.put(config)
                    await self._send_update(websocket)

                elif cmd == "remove":
                    monitor_id = p.get("monitor_id")
                    if monitor_id:
                        if auto_trader:
                            auto_trader.close_all_positions(monitor_id)
                        store.delete(monitor_id)
                    await self._send_update(websocket)

                elif cmd == "update_config":
                    monitor_id = p.get("monitor_id")
                    config_data = p.get("config", {})
                    if monitor_id:
                        existing = store.get(monitor_id)
                        if existing:
                            prev_force_stop = existing.force_stop
                            for k, v in config_data.items():
                                if hasattr(existing, k):
                                    setattr(existing, k, v)
                            store.put(existing)
                            # force_stop just activated → close all positions immediately
                            if existing.force_stop and not prev_force_stop and auto_trader:
                                auto_trader.close_all_positions(monitor_id)
                                logger.info("force_stop activated — closed all positions | monitor_id={}", monitor_id)
                    await self._send_update(websocket)

                elif cmd == "restart":
                    monitor_id = p.get("monitor_id")
                    if monitor_id and auto_trader:
                        auto_trader.restart(monitor_id)
                    await self._send_update(websocket)

        except WebSocketDisconnect:
            pass
        except RuntimeError:
            pass
        except Exception:
            logger.exception("historical screener ws error")
        finally:
            logger.info("historical screener ws client disconnected")

    async def _send_update(self, websocket: WebSocket) -> None:
        if websocket.client_state != WebSocketState.CONNECTED:
            return

        store = self._runtime.monitor_store
        configs = store.get_all()

        opportunities = []
        status = "Idle"
        if self._runtime.historical_screener_worker:
            status, opps = self._runtime.historical_screener_worker.read_opportunities()
            opportunities = [
                {
                    "symbol": o.symbol,
                    "short_exchange": o.short_ex,
                    "long_exchange": o.long_ex,
                    "current_spread_pct": o.current_spread_pct,
                    "max_historical_spread_pct": o.max_historical_spread_pct,
                    "signal_time_seconds": o.signal_time_seconds,
                    "short_funding_rate": o.short_funding_rate,
                    "long_funding_rate": o.long_funding_rate,
                    "short_next_funding": o.short_next_funding,
                    "long_next_funding": o.long_next_funding,
                    "short_price": o.short_price,
                    "long_price": o.long_price,
                    "short_volume_24h": o.short_volume_24h,
                    "long_volume_24h": o.long_volume_24h,
                    "detected_at": o.detected_at,
                    "lookback_seconds": o.lookback_seconds,
                }
                for o in opps
            ]

        monitors_payload = []
        for c in configs:
            monitors_payload.append({
                "id": c.id,
                "symbol": c.symbol,
                "short_exchange": c.short_exchange,
                "long_exchange": c.long_exchange,
                "side": c.side,
                "open_spread_pct": c.open_spread_pct,
                "open_ticks": c.open_ticks,
                "close_spread_pct": c.close_spread_pct,
                "close_ticks": c.close_ticks,
                "order_size_usdt": c.order_size_usdt,
                "max_orders": c.max_orders,
                "allowed_size_usdt": c.allowed_size_usdt,
                "allowed_size_current_usdt": c.allowed_size_current_usdt,
                "force_stop": c.force_stop,
                "total_stop": c.total_stop,
                "is_active": c.is_active,
                "adjustment_mode": c.adjustment_mode,
                "max_historical_spread_pct": c.max_historical_spread_pct,
                "short_leverage": c.short_leverage,
                "long_leverage": c.long_leverage,
            })

        payload = {
            "type": "historical_screener_update",
            "data": {
                "status": status,
                "supports_analysis_volume_filter": False,
                "opportunities": opportunities,
                "monitors": monitors_payload,
                "live_state": (
                    self._runtime.historical_auto_trader.get_live_state()
                    if self._runtime.historical_auto_trader else {}
                ),
            },
        }
        with contextlib.suppress(Exception):
            await websocket.send_json(payload)
