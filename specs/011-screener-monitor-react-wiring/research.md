# Research: Screener History React UI Parity

**Feature**: 011-screener-monitor-react-wiring
**Date**: 2026-07-16

## 1. Backend `get_live_state()` gap analysis

**Decision**: Expand `HistoricalAutoTrader._live_state` dict to emit all FR-011 fields per monitor.

**Current state**: `get_live_state()` returns per-symbol:
```python
{
    "open_spread": float,
    "close_spread": float,
    "open_ticks": int,
    "close_ticks": int,
    "open_orders": int,
}
```

**Missing fields** (must be added to `_tick()` update loop):
- `short_funding_rate`, `long_funding_rate` — from `market_cache`
- `short_next_funding`, `long_next_funding` — from `market_cache`
- `short_ask`, `long_ask`, `short_bid`, `long_bid` — from `market_cache` (orderbook top)
- `short_size`, `long_size` — orderbook top size
- `leverage` — from config or exchange (per exchange)
- `max_size_short`, `max_size_long` — from exchange position limits or cache
- `short_price`, `long_price` — last price from cache
- `short_pnl`, `long_pnl` — from paper/live position
- `short_realized_pnl`, `long_realized_pnl` — from paper/live position
- `enter_spread_short`, `enter_spread_long` — spread at which the position was opened
- `short_orders`, `long_orders` — separate per-leg order counts
- `open_spread_min`, `open_spread_max` — rolling min/max over session
- `close_spread_min`, `close_spread_max` — rolling min/max over session

**Rationale**: All these are already available in `market_cache` or `paper_gateway`. The `_tick()` loop already resolves spreads via `ExecutableSpreadResolver` — adding field extraction to the same loop adds no new I/O.

**Alternatives considered**: Separate WS endpoint per card — rejected per FR-010 and §11 (no new endpoints).

---

## 2. `HistoricalOpportunity` — `signal_time_seconds` field

**Decision**: Add `signal_time_seconds: int` field to `HistoricalOpportunity` dataclass.

**Calculation**: `int(time.time() - detected_at_of_max_spread)`. The screener worker already tracks `detected_at` (timestamp of first detection). Need to additionally track `max_spread_detected_at: float` — timestamp when `max_historical_spread_pct` was last updated.

**Rationale**: Directly supports FR-008 Signal time column. Adds one float field and one subtraction per opportunity.

---

## 3. `MonitorConfig` — missing fields

**Decision**: Add three fields to `MonitorConfig` dataclass:
- `adjustment_mode: Literal["notify_only", "adjust"] = "notify_only"` — leverage adjustment behavior
- `allowed_size_current_usdt: float = 0.0` — running accumulated position size
- `max_allowed_size_usdt: float = 4000.0` — maximum allowed accumulated size (user-configurable)

**Rationale**: `adjustment_mode` is a strategy-level knob (per §17 → `MonitorConfig`, not `Settings`). `allowed_size_current_usdt` is runtime state that must persist to disk to survive restarts. `max_allowed_size_usdt` replaces the current hardcoded "4000" in the UI placeholder.

**Backward compatibility**: `MonitorConfigStore` is JSON-backed. New fields with defaults will deserialize correctly from old JSON via `dataclasses.field(default=...)`.

---

## 4. `live_state` composite key

**Decision**: Change `live_state` dict key from `symbol` to `f"{symbol}:{short_ex}:{long_ex}"` composite.

**Rationale**: FR-010 requires one monitor per `symbol+short_exchange+long_exchange` triplet. Using only `symbol` as key would prevent two monitors on the same symbol with different exchange pairs. Backend `_open_pairs` already uses `pair_id` string — reuse the same format.

**Frontend impact**: `MonitorsPage` passes `live_state[config.symbol + ":" + config.short_ex + ":" + config.long_ex]` as prop to each `LiveMonitorCard`. The `types/index.ts` `MonitorConfig` uses `short_exchange` vs backend's `short_ex` — must align field names in the WS payload mapping.

---

## 5. `OpportunityChart` reuse vs new `SpreadChart`

**Decision**: Create a new lightweight `SpreadChart.tsx` component instead of reusing `OpportunityChart.tsx`.

**Rationale**: `OpportunityChart` renders prices + spread on dual Y-axes using `ComposedChart` with `Area` + two `Line`s. The card needs only two lines (open spread red, close spread green) on a single Y-axis — a fundamentally different layout. Reusing `OpportunityChart` would require prop-hacking or internal changes (violating §12 since `OpportunityChart` is used by `OpportunityPage` and must remain stable).

**Alternatives considered**: Adding a `mode` prop to `OpportunityChart` — rejected as adds conditional branching to a component that currently has no such complexity (anti-pattern per ponytail).

`SpreadChart.tsx` will be a thin wrapper around `recharts LineChart` with:
- X-axis: time labels
- Y-axis: spread %
- Red `Line` for open spread, green `Line` for close spread
- `open_spread_pct` and `close_spread_pct` threshold reference lines (dashed)

---

## 6. `min_analysis_volume_usdt` filter

**Decision**: Add parameter to `update_filters()` signature; mark as unimplemented in screener worker with a `logger.debug` line; frontend disables the filter input if `supports_analysis_volume_filter: false` is returned in WS payload.

**Rationale**: Backend does not currently track per-period volume. Adding it requires changes to the rolling history structure. Deferred to a follow-up; FR-006 + FR-017 already specify graceful degradation.

---

## 7. `restart` WebSocket command

**Decision**: Add `restart` cmd to `HistoricalScreenerWsHandler`. Handler: calls `auto_trader.restart(symbol, short_ex, long_ex)` which: (1) stops the tick for that pair, (2) calls `fetch_open_orders` via gateway to re-sync position, (3) recalculates all live state fields, (4) resumes tick.

**Rationale**: Matches clarification answer: reconnect without clearing state. `fetch_open_orders` is a read-only exchange call (§15 safe).

---

## 8. Frontend field name alignment

**Decision**: Normalize all payload field names to `snake_case` with `_ex` suffix dropped at WS boundary. Backend serializes `short_ex` → frontend receives `short_exchange` in the `monitors` array. The WS handler already does `c.__dict__` serialization — add a mapping step or rename fields in `MonitorConfig` to match frontend.

**Simpler approach**: Rename `MonitorConfig.short_ex` → `MonitorConfig.short_exchange` and `long_ex` → `long_exchange` in the Python dataclass. This also fixes the `id` field: add `id: str = field(default_factory=lambda: "")` computed from `symbol+short_exchange+long_exchange`.

**Rationale**: One rename in the dataclass eliminates the mapping layer in the WS handler and aligns backend+frontend types completely. Existing `MonitorConfigStore` JSON files will need a migration note (old keys `short_ex`/`long_ex` handled by `__post_init__`).
