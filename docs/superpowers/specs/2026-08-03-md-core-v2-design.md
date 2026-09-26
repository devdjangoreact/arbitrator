# Design: arbitrator_2 — Exchange Connector (Stage 1)

**Date**: 2026-08-03 (revised 2026-08-04)  
**Branch**: `feature/012-md-core-v2`  
**Status**: Draft (revised scope)  
**Workflow**: Superpowers (`brainstorming` → design → `writing-plans`)

## One-sentence goal

Build **`src/arbitrator_2`** as a new product line that **for now only connects to CEX and acquires market data** (order books required; trades optional), taking the best lessons from `src/arbitrator` and dropping its latency bottlenecks. Strategies, UI, trading — **later**.

## What this stage is / is not

| In scope (Stage 1) | Out of scope (later) |
|--------------------|----------------------|
| Package `src/arbitrator_2` | Strategies, sniper, slippage |
| CEX connectors for 5 venues | DEX |
| Order books: **spot + futures** | Order placement / private trading logic |
| Optional public trades (off by default or per subscribe) | Full app UI / React |
| Separate ccxt clients by role | Replacing legacy `arbitrator` entirely |
| Fast raw path + async normalize to one format | Auto-traders, hedged execution |
| Latency probe on all 5 venues | |

Legacy `src/arbitrator` stays untouched as the running v1. Stage 1 does not require wiring v2 into production UI.

---

## Lessons taken from `src/arbitrator` (keep)

- Five CEX already known: **binance, mexc, bitget, gate, bingx**
- Two market universes: **USDT spot** + **USDT-M perp** (`BASE/USDT` vs `BASE/USDT:USDT`)
- ccxt.pro `watch_*` for live books (not REST polling on the hot path)
- Need for executable bid/ask from the book (not ticker `last`)

## Lessons rejected from `src/arbitrator` (do not copy)

- ~1 s polling / `Event.wait(1.0)` on detection path
- REST `fetch_order_book` on every open / steady-state read
- One shared client for public WS + private + meta + history
- Thread-per-worker + Lock + full snapshot copy on the hot path
- Oversized book depth “just in case”
- Mixing slow work onto the book stream client

---

## Architecture (Stage 1)

```text
src/arbitrator_2/
  __init__.py
  connector/                 # exchange connector only
    runtime.py               # one asyncio loop for public streams
    registry.py              # venue id → adapter
    connections.py           # client factory by role (isolation)
    adapters/
      base.py                # Protocol + capabilities
      binance.py
      mexc.py
      bitget.py
      gate.py
      bingx.py
    book/                    # subscribe + local BBO/L2 handle
    trades/                  # optional subscribe
    normalize/               # async / queued unify to one schema
    metrics/                 # latency counters + probe helpers
  scripts/ or tools/         # live probe: 5 venues × spot+perp
```

No dependency from `arbitrator_2` on `arbitrator.application` / strategies / presentation.  
Reusing small pure ideas from old code is fine **by copy/adapt**, not by importing the old app stack.

---

## Connection roles (MUST)

| Role | Client | Purpose | Keys |
|------|--------|---------|------|
| **Book** | Always | `watch_order_book` spot + futures | No |
| **Trades** | Optional separate public client | `watch_trades` when requested | No |
| **Meta** | Separate instance | `load_markets`, symbol resolve | No |
| **Private** | Not in Stage 1 (stub/forbidden on book client) | balance / orders later | Yes later |
| **History** | Not in Stage 1 | OHLCV / history later | No |

Rules:

1. **Book client never** loads markets, never holds API keys, never does history REST.
2. **Trades** = separate public client when enabled (books always; trades not always).
3. **Meta** = separate instance for `load_markets` before subscribe.
4. Spot book and futures book may share the Book client **only if** that does not stall either stream; otherwise split spot-book vs futures-book clients per venue (capability-driven).

---

## Markets: spot + futures

For each of the five venues, Stage 1 must be able to:

- Subscribe **spot** order book(s)
- Subscribe **futures (USDT-M perp)** order book(s)
- Run probe on both universes

Default probe symbols: one liquid spot + one liquid perp per venue (e.g. BTC/USDT and BTC/USDT:USDT), adjustable.

---

## Data path: speed first, one format second

```text
WS frame (ccxt)
  → recv_ts
  → apply to local book FAST (minimal work)     ← never wait on normalize
  → notify "raw/fast" consumers (optional)
  → enqueue normalize job (non-blocking)
  → unified record for later analysis           ← may lag slightly; must not block book apply
```

**Unified format** (for later analysis) — same fields for spot and futures, all venues:

- `venue`, `market_kind` (`spot` | `perp`), `symbol`
- `bid`, `ask`, `bid_size`, `ask_size` (top)
- optional top-N levels
- `exchange_ts_ms` (if any), `recv_ts_ms`, `apply_ts_ms`, `norm_ts_ms`
- sequence / age if available

Normalize runs **off** the critical apply path (queue + worker task). If the normalize queue is full → drop normalize updates + counter; **book apply continues**.

---

## Required venues

| Venue | Spot book | Futures book | Trades (optional) | Live probe |
|-------|-----------|--------------|-------------------|------------|
| binance | yes | yes | optional | yes |
| mexc | yes | yes | optional | yes |
| bitget | yes | yes | optional | yes |
| gate | yes | yes | optional | yes |
| bingx | yes | yes | optional | yes |

Each venue adapter declares **capabilities** (batch subscribe, min depth, trade stream, timestamp quality, known limits). Acceptance = works per capabilities, not “identical to Binance”.

---

## Latency measurement

Timestamps: `exchange_ts` (if valid) / `recv_ts` (monotonic) / `apply_ts` / `norm_ts`.

| Metric | Meaning |
|--------|---------|
| `apply_lag_ms` | apply − recv (local hot path) |
| `norm_lag_ms` | norm − apply (must not feed back into apply) |
| `e2e_lag_ms` | apply − exchange_ts (only if ts sane) |
| `first_bbo_ms` | subscribe → first valid BBO |
| `staleness_ms` | now − last apply (dead stream detector) |
| `updates_per_sec` | throughput per venue/market_kind |

**Probe (required):** script runs against all 5 venues × spot + perp for a fixed window; prints p50/p95/p99; REST order-book calls on Book client must stay **0** in steady state.

Target: p95 `apply_lag_ms` &lt; 5 ms on a reference machine (local only).

---

## Success criteria (Stage 1)

1. `src/arbitrator_2` exists as connector-focused package; no strategy/UI/trading modules required yet.
2. All 5 CEX: spot + futures books stream in live probe.
3. Book / Trades / Meta use separate client instances as specified.
4. Unified normalize format exists; normalize never blocks book apply (overload drops normalize only).
5. Latency metrics available per venue and per market kind (spot/perp).
6. Steady-state Book client: zero REST `fetch_order_book`.
7. `arbitrator_2` does not import `arbitrator.application` / presentation / trading stacks.
8. **Tests** (pytest): fake/mock adapter path covers subscribe → apply → unified record; client-role isolation; normalize non-blocking under backlog; import-graph guard.
9. **Demo script** (human-runnable): connects to real exchanges, prints live data received (BBO / optional trades) for the 5 venues × spot+perp in a readable table or line stream, plus short latency summary. This script is the primary “see what we get from exchanges” proof.

### Done means

- `pytest` for `arbitrator_2` connector tests is green.
- Demo script run shows real book (and optional trade) lines from exchanges — not only internal metrics.

---

## Non-goals (Stage 1)

- Strategies, execution, private balances/orders UI
- DEX
- Full replacement of `src/arbitrator` in production
- Raw WS instead of ccxt.pro
- Making normalize perfectly zero-lag (speed of book apply wins)

## Next stages (not now)

- Wire host entrypoint / switch to run `arbitrator_2` connector in-process
- Private client (Class B), history (Class D)
- Strategy consumers on unified stream
- UI
