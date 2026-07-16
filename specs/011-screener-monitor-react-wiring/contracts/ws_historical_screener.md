# WebSocket Contract: `/ws/historical_screener`

**Endpoint**: `ws://<host>/ws/historical_screener`
**Direction**: bidirectional — server pushes every 5 s; client sends commands
**Existing endpoint**: yes — additive changes only (FR-018)

---

## Server → Client push (every 5 s)

```json
{
  "type": "historical_screener_update",
  "data": {
    "status": "Running | Idle | Stopping",
    "supports_analysis_volume_filter": false,
    "opportunities": [
      {
        "symbol": "BP",
        "short_exchange": "GATEIO",
        "long_exchange": "MEXC",
        "current_spread_pct": 3.15,
        "max_historical_spread_pct": 3.29,
        "signal_time_seconds": 9,
        "short_funding_rate": -0.0022,
        "long_funding_rate": -0.0043,
        "short_next_funding": "15:00:00 (01:58:16) | 4h",
        "long_next_funding": "15:00:00 (01:58:16) | 4h",
        "short_price": 0.14599,
        "long_price": 0.15058,
        "short_volume_24h": 6649788.0,
        "long_volume_24h": 11760942.0,
        "detected_at": 1752700000.0,
        "lookback_seconds": 1800
      }
    ],
    "monitors": [
      {
        "id": "BP:GATEIO:MEXC",
        "symbol": "BP",
        "short_exchange": "GATEIO",
        "long_exchange": "MEXC",
        "side": "auto",
        "open_spread_pct": 23.89,
        "open_ticks": 2,
        "close_spread_pct": 23.19,
        "close_ticks": 2,
        "order_size_usdt": 500.0,
        "max_orders": 0,
        "allowed_size_usdt": 4000.0,
        "allowed_size_current_usdt": 0.0,
        "force_stop": false,
        "total_stop": false,
        "is_active": true,
        "adjustment_mode": "notify_only",
        "max_historical_spread_pct": 3.29
      }
    ],
    "live_state": {
      "BP:GATEIO:MEXC": {
        "short_funding_rate": 0.00005,
        "long_funding_rate": 0.00008,
        "short_next_funding": "15:00:00 (01:57:45) | 4h",
        "long_next_funding": "15:00:00 (01:57:45) | 4h",
        "short_ask": 0.70438,
        "long_ask": 0.56383,
        "short_bid": 0.69626,
        "long_bid": 0.55277,
        "short_size": null,
        "long_size": null,
        "leverage": 10.0,
        "max_size_short": 300000.0,
        "max_size_long": 4000.0,
        "short_price": null,
        "long_price": null,
        "short_pnl": null,
        "long_pnl": null,
        "short_realized_pnl": 0.0,
        "long_realized_pnl": 0.0,
        "enter_spread_short": null,
        "enter_spread_long": null,
        "short_orders": 0,
        "long_orders": 0,
        "open_spread_current": 23.487,
        "open_spread_min": 23.411,
        "open_spread_max": 23.531,
        "close_spread_current": 27.428,
        "close_spread_min": 27.405,
        "close_spread_max": 27.438
      }
    }
  }
}
```

---

## Client → Server commands

### `start` — запустити screener worker
```json
{ "cmd": "start" }
```

### `stop` — зупинити screener worker
```json
{ "cmd": "stop" }
```

### `update_filters` — оновити фільтри screener
```json
{
  "cmd": "update_filters",
  "lookback_seconds": 1800,
  "min_spread_pct": 2.0,
  "min_volume_usdt": 1000000.0,
  "min_analysis_volume_usdt": 500000.0,
  "push_interval_seconds": 5,
  "candle_interval_seconds": 5,
  "price_deviation_filter_pct": 0.0
}
```
*`min_analysis_volume_usdt` — ignored if `supports_analysis_volume_filter: false`*
*`push_interval_seconds` — інтервал пушу в секундах (default 5, min 1); зберігається в `StrategyUIConfig.historical_screener_push_interval_seconds`*
*`candle_interval_seconds` — таймфрейм свічок для аналізу спреду: 5 / 15 / 30 / 60 (default 5); зберігається в `StrategyUIConfig.historical_screener_candle_interval_seconds`*
*`price_deviation_filter_pct` — фільтр відхилення ціни (max-min) %; 0.0 = вимкнено (default); якщо > 0 — виключає символи з меншим відхиленням*

### `add_monitor` — додати монітор з таблиці
```json
{
  "cmd": "add_monitor",
  "symbol": "BP",
  "short_exchange": "GATEIO",
  "long_exchange": "MEXC",
  "max_spread": 3.29,
  "auto_start": true
}
```
**Error response** (duplicate triplet):
```json
{ "type": "error", "data": { "code": "duplicate_monitor", "monitor_id": "BP:GATEIO:MEXC" } }
```

### `remove` — видалити монітор (× кнопка на картці, FR-025)
```json
{ "cmd": "remove", "monitor_id": "BP:GATEIO:MEXC" }
```
Backend: зупиняє тік → **закриває всі відкриті позиції** для цього монітора → видаляє з реєстру моніторів. Картка зникає коли наступний пуш не містить цей `monitor_id` в масиві `monitors`.

### `update_config` — оновити параметр картки
```json
{
  "cmd": "update_config",
  "monitor_id": "BP:GATEIO:MEXC",
  "config": {
    "open_spread_pct": 24.0
  }
}
```

### `restart` — перепідключити монітор (NEW)
```json
{ "cmd": "restart", "monitor_id": "BP:GATEIO:MEXC" }
```
Backend: зупиняє тік для цього монітора → fetch open orders з бірж → перераховує live_state → відновлює тік.
