# WebSocket Contracts (єдиний канал UI ↔ сервер)

Усі дані, команди та відповіді UI йдуть через WebSocket.  
REST до бірж — політика проєкту: `.cursor/rules/exchange-data.mdc`.

## Envelope

**Server → client**:

```json
{ "type": "<message_type>", "payload": { } }
```

**Client → server**:

```json
{ "type": "<command_type>", "payload": { } }
```

---

## `/ws/screener`

**Connection**: `ws://{host}:{port}/ws/screener`

**Server push interval**: `Settings.screener_ws_push_seconds` (default: 1)

### Server → client

#### `screener.snapshot`

```json
{
  "type": "screener.snapshot",
  "payload": {
    "status": "filtered",
    "symbol_count": 5,
    "exchanges": ["mexc", "bitget", "gate", "bingx"],
    "filters": {
      "min_volume_k_usdt": 0.0,
      "stream_min_volume_usdt": 50000.0,
      "min_spread_pct": 0.0
    },
    "updated_at": "2026-06-30T12:00:00Z",
    "rows": []
  }
}
```

Row shape — див. [data-model.md](../data-model.md) `ScreenerRowDto`.

#### `screener.delta`

Incremental update after the first snapshot. Див. [ws-ui-protocol.md](./ws-ui-protocol.md).

```json
{
  "type": "screener.delta",
  "payload": {
    "rows_changed": [],
    "rows_removed": []
  }
}
```

#### `screener.action_result`

Відповідь на команди `screener.set_filters` / `screener.reconnect`:

```json
{
  "type": "screener.action_result",
  "payload": { "success": true, "message": "filters updated" }
}
```

#### `screener.error`

```json
{
  "type": "screener.error",
  "payload": { "message": "worker not running" }
}
```

### Client → server

#### `screener.set_filters`

```json
{
  "type": "screener.set_filters",
  "payload": {
    "min_volume_k_usdt": 0.0,
    "stream_min_volume_usdt": 50000.0,
    "min_spread_pct": 0.5
  }
}
```

#### `screener.reconnect`

```json
{ "type": "screener.reconnect", "payload": {} }
```

#### `ping`

```json
{ "type": "ping", "payload": {} }
```

---

## `/ws/opportunity`

**Connection**: `ws://{host}:{port}/ws/opportunity?symbol=DOGE%2FUSDT&short=mexc&long=bingx`

Query params: `symbol` (ccxt unified, e.g. `DOGE/USDT`), `short`, `long` (exchange ids). Do **not** put the symbol in the URL path — encoded `/` (`%2F`) is rejected with HTTP 403.

| Query | Required |
|-------|----------|
| `short` | Short exchange id |
| `long` | Long exchange id |

### Server → client

#### `opportunity.snapshot`

Full `OpportunitySnapshotDto` — [data-model.md](../data-model.md).

#### `opportunity.delta`

Incremental chart/book/card updates. Див. [ws-ui-protocol.md](./ws-ui-protocol.md).

#### `opportunity.action_result`

```json
{
  "type": "opportunity.action_result",
  "payload": {
    "action": "accumulate",
    "success": true,
    "message": "submitted"
  }
}
```

#### `opportunity.error`

```json
{
  "type": "opportunity.error",
  "payload": { "message": "insufficient balance" }
}
```

### Client → server

#### `opportunity.set_params`

```json
{
  "type": "opportunity.set_params",
  "payload": {
    "active_strategy_id": "futures_futures",
    "target_volume_usdt": 500.0,
    "open_spread_threshold_pct": 0.7,
    "close_spread_threshold_pct": 0.05,
    "accumulate_volume_usdt": 50.0,
    "accumulate_volume_pct": 10.0,
    "close_volume_usdt": 50.0,
    "close_volume_pct": 10.0,
    "auto_accumulate_enabled": true,
    "auto_close_enabled": false
  }
}
```

#### `opportunity.accumulate`

```json
{
  "type": "opportunity.accumulate",
  "payload": { "volume_usdt": 50.0, "volume_pct": null }
}
```

#### `opportunity.close_partial`

```json
{
  "type": "opportunity.close_partial",
  "payload": { "volume_usdt": 50.0, "volume_pct": null }
}
```

#### `opportunity.close_all`

```json
{ "type": "opportunity.close_all", "payload": {} }
```

#### `opportunity.set_focus`

Client-side focus change (reconnect `/ws/opportunity` with new query params after ack):

```json
{
  "type": "opportunity.set_focus",
  "payload": {
    "symbol": "DOGE/USDT",
    "short_exchange_id": "mexc",
    "long_exchange_id": "bingx"
  }
}
```

#### `opportunity.set_leverage`

```json
{
  "type": "opportunity.set_leverage",
  "payload": { "exchange_id": "mexc", "leverage": 10 }
}
```

Сервер викликає ccxt `set_leverage` через application layer (див. `exchange-data.mdc`).

---

## `/ws/orders`

**Connection**: `ws://{host}:{port}/ws/orders`

### Server → client

#### `orders.snapshot`

```json
{
  "type": "orders.snapshot",
  "payload": {
    "summary": { "open_count": 2, "closed_count": 14 },
    "filter": "all",
    "groups": []
  }
}
```

#### `orders.summary` (delta)

Push при зміні лічильників (оновлення sidebar badge):

```json
{
  "type": "orders.summary",
  "payload": { "open_count": 2, "closed_count": 14 }
}
```

### Client → server

#### `orders.set_filter`

```json
{
  "type": "orders.set_filter",
  "payload": { "filter": "open" }
}
```

---

## `/ws/settings`

**Connection**: `ws://{host}:{port}/ws/settings`

### Server → client

#### `settings.snapshot`

```json
{
  "type": "settings.snapshot",
  "payload": {
    "exchanges": [
      {
        "exchange_id": "mexc",
        "api_key_masked": "••••••••••••",
        "configured": true,
        "has_secret": true,
        "has_password": false
      }
    ]
  }
}
```

Ніколи не повертати сирі секрети.

#### `settings.action_result`

```json
{
  "type": "settings.action_result",
  "payload": { "success": true, "exchange_id": "mexc" }
}
```

### Client → server

#### `settings.save_exchange`

```json
{
  "type": "settings.save_exchange",
  "payload": {
    "exchange_id": "mexc",
    "api_key": "...",
    "api_secret": "...",
    "api_password": ""
  }
}
```

---

## Disconnect behavior

- `logger.info("ws disconnected | endpoint={}", ...)`
- `OpportunityStreamWorker.stop()` on opportunity WS close.
- Global `ScreenerStreamWorker` / `AccountStreamWorker` — lifespan-managed, survive UI disconnect.
