# API Contracts: Strategy UI Configuration

## Endpoints

### `GET /api/config/strategy`
Retrieves the current active strategy configuration.

**Response (200 OK)**:
```json
{
  "live_auto_trade_enabled": false,
  "live_auto_trade_post_fill_min_spread_pct": 0.5,
  ... (all fields defined in data-model.md)
}
```

### `PUT /api/config/strategy`
Updates the strategy configuration. Merges the provided fields with the existing configuration and persists to disk.

**Request Body**:
```json
{
  "live_auto_trade_enabled": true,
  "screener_auto_trade_max_positions": 5
}
```
*(Accepts partial updates)*

**Response (200 OK)**:
```json
{
  "status": "success",
  "config": {
    "live_auto_trade_enabled": true,
    ... (updated full config)
  }
}
```
