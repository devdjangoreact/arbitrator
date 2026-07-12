from __future__ import annotations

import asyncio

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from arbitrator.application.app_runtime import AppRuntime
from arbitrator.config.logger import logger
from arbitrator.config.monitor_config_store import MonitorConfig
from arbitrator.config.settings import Settings


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
                try:
                    data = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
                except asyncio.TimeoutError:
                    await self._send_update(websocket)
                    continue
                except RuntimeError:
                    break

                cmd = data.get("cmd")
                symbol = data.get("symbol")
                if not cmd:
                    continue

                worker = self._runtime.historical_screener_worker

                if cmd == "refresh":
                    await self._send_update(websocket)
                elif cmd == "update_config" and symbol:
                    config_data = data.get("config", {})
                    store = self._runtime.monitor_store
                    existing = store.get(symbol)
                    if existing:
                        for k, v in config_data.items():
                            if hasattr(existing, k):
                                setattr(existing, k, v)
                        store.put(existing)
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
                    lookback_seconds: int | None = None
                    min_spread_pct: float | None = None
                    min_volume_usdt: float | None = None
                    raw_lb = data.get("lookback_seconds")
                    raw_sp = data.get("min_spread_pct")
                    raw_vol = data.get("min_volume_usdt")
                    if raw_lb not in (None, ""):
                        lookback_seconds = int(raw_lb)
                    if raw_sp not in (None, ""):
                        min_spread_pct = float(raw_sp)
                    if raw_vol not in (None, ""):
                        min_volume_usdt = float(raw_vol)
                    if worker:
                        worker.update_filters(lookback_seconds, min_spread_pct, min_volume_usdt)
                    await self._send_update(websocket)
                elif cmd == "add_monitor" and symbol:
                    short_ex = data.get("short_ex")
                    long_ex = data.get("long_ex")
                    max_spread = data.get("max_spread", 0.0)
                    if not self._runtime.monitor_store.get(symbol):
                        self._runtime.monitor_store.put(
                            MonitorConfig(
                                symbol=symbol,
                                short_ex=short_ex,
                                long_ex=long_ex,
                                open_spread_pct=self._settings.historical_monitor_open_spread_pct,
                                close_spread_pct=self._settings.historical_monitor_close_spread_pct,
                                order_size_usdt=self._settings.historical_monitor_notional_usdt,
                                max_historical_spread_pct=max_spread,
                                is_active=False,
                            )
                        )
                    await self._send_update(websocket)
                elif cmd == "remove" and symbol:
                    self._runtime.monitor_store.delete(symbol)
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
                    "short_ex": o.short_ex,
                    "long_ex": o.long_ex,
                    "current_spread_pct": o.current_spread_pct,
                    "max_historical_spread_pct": o.max_historical_spread_pct,
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

        payload = {
            "type": "historical_screener_update",
            "data": {
                "status": status,
                "opportunities": opportunities,
                "monitors": [c.__dict__ for c in configs],
            },
        }
        try:
            await websocket.send_json(payload)
        except Exception:
            pass
