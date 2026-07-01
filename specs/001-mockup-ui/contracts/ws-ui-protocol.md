# UI WebSocket protocol (snapshot + delta)

Browser ↔ server uses **WebSocket only**. After the initial connect, high-frequency
updates use **delta** messages to avoid full DOM rebuilds and large JSON payloads.

## Message envelope

```json
{ "type": "<channel>.<kind>", "payload": { } }
```

| Kind | When |
|------|------|
| `*.snapshot` | First push after connect; after user commands that change structure |
| `*.delta` | Periodic ticks (`Settings.screener_ws_push_seconds`) |

Frontend routing: `static/js/core/delta_router.js` → per-page handlers in `static/js/render/`.

---

## `/ws/screener`

### `screener.snapshot`

Full `ScreenerSnapshotDto` — filters, meta, all visible rows.

### `screener.delta`

Incremental update (`ScreenerDeltaDto`):

| Field | Purpose |
|-------|---------|
| `status`, `symbol_count`, `exchanges`, `filters` | Present only when changed |
| `rows_changed[]` | Full row DTOs to upsert by `asset` |
| `rows_removed[]` | Asset keys to remove from tbody |

Frontend: patch existing `<tr data-asset>` cells; append new rows; remove deleted.

---

## `/ws/opportunity?symbol=&short=&long=`

### `opportunity.snapshot`

Full `OpportunitySnapshotDto` — cards, strategy table, params, orders, chart, books.

### `opportunity.delta`

Incremental update (`OpportunityDeltaDto`):

| Field | Purpose |
|-------|---------|
| `chart_series[]` | `{ key, last_price, point }` — append one point per series |
| `books[]` | Changed order-book panels only — patch `.ob-side` rows |
| `exchange_cards[]` | Full card replace when leverage/funding changes |
| `funding_countdown_sec` | Optional tick without full cards |

Frontend modules: `render/opportunity_chart.js`, `render/order_book.js`.

---

## `/ws/orders`, `/ws/settings`

Snapshot-only (low frequency). `orders.summary` pushes nav badge count.

---

## HTML source layout

Partials live under `presentation/static/partials/`. Build:

```bash
python scripts/build_ui.py
```

Output: `presentation/static/index.html` (no hardcoded market data; placeholders `—` until first snapshot).

Partials structure:

```
partials/
  layout/head.html, scripts.html
  sidebar.html
  pages/screener.html, opportunity.html, orders.html, settings.html
  opportunity/topbar.html, ex-info-row.html, strategy-table.html,
              params.html, orders-panel.html, chart.html, order-books.html
```

Visual reference: `maket/index.html` (design mockup; not served at runtime).
