# arbitrator_2 Connector (Stage 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `src/arbitrator_2` as a CEX connector that streams spot + perp order books (trades optional) from binance/mexc/bitget/gate/bingx via ccxt.pro, with isolated clients, non-blocking normalize, pytest coverage, and a demo script that prints live exchange data.

**Architecture:** One asyncio runtime owns Book/Trades/Meta ccxt.pro clients (never mixed). Book updates apply in-place to a BBO store, then a non-blocking queue feeds a unified tick for analysis. Five venues share one `CcxtProVenue` parameterized by capabilities; tests use a fake venue. No imports from `arbitrator.application` / presentation / trading.

**Tech Stack:** Python 3.11, ccxt.pro, pytest, mypy `--strict`. Commands via `.venv\Scripts\python.exe`.

## Global Constraints

- Do not import `arbitrator.application`, `arbitrator.presentation`, or `arbitrator.exchanges` from `arbitrator_2`.
- Book client: no API keys, no `load_markets`, no REST `fetch_order_book` in steady state.
- Trades: separate public client, only when requested.
- Meta: separate instance for `load_markets` only.
- Normalize must not `await` on the book apply path; full queue drops normalize only.
- Spot symbol `BASE/USDT`; perp `BASE/USDT:USDT`.
- No orders, leverage, private balances, UI, DEX, or strategies in this stage.
- One class per file; `from __future__ import annotations`; no `Any`.
- Tests: `.venv\Scripts\python.exe -m pytest tests/unit/arbitrator_2 -q`
- Mypy: `.venv\Scripts\mypy.exe --strict src/arbitrator_2`

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `pyproject.toml` | Modify | Include package `arbitrator_2` |
| `src/arbitrator_2/__init__.py` | Create | Package marker |
| `src/arbitrator_2/connector/__init__.py` | Create | Public exports |
| `src/arbitrator_2/connector/client_role.py` | Create | `ClientRole` enum |
| `src/arbitrator_2/connector/market_kind.py` | Create | `MarketKind` literal enum |
| `src/arbitrator_2/connector/market_id.py` | Create | `MarketId` frozen dataclass |
| `src/arbitrator_2/connector/bbo.py` | Create | `Bbo` frozen dataclass |
| `src/arbitrator_2/connector/unified_tick.py` | Create | `UnifiedTick` frozen dataclass |
| `src/arbitrator_2/connector/venue_capabilities.py` | Create | Per-venue caps |
| `src/arbitrator_2/connector/ccxt_session_factory.py` | Create | Isolated ccxt.pro clients by role |
| `src/arbitrator_2/connector/book_store.py` | Create | In-place BBO apply |
| `src/arbitrator_2/connector/latency_metrics.py` | Create | Counters / percentiles |
| `src/arbitrator_2/connector/normalize_queue.py` | Create | Drop-oldest / drop-new queue |
| `src/arbitrator_2/connector/venue_adapter.py` | Create | Protocol |
| `src/arbitrator_2/connector/ccxt_pro_venue.py` | Create | Real ccxt.pro adapter |
| `src/arbitrator_2/connector/venue_registry.py` | Create | Five CEX + fake |
| `src/arbitrator_2/connector/connector_runtime.py` | Create | Subscribe / loop / isolation |
| `scripts/arbitrator_2_show_books.py` | Create | Live print of books (+ optional trades) |
| `tests/unit/arbitrator_2/test_import_graph.py` | Create | Forbidden-import guard |
| `tests/unit/arbitrator_2/test_ccxt_session_factory.py` | Create | Role isolation |
| `tests/unit/arbitrator_2/test_book_store.py` | Create | Apply + timestamps |
| `tests/unit/arbitrator_2/test_normalize_queue.py` | Create | Non-blocking drop |
| `tests/unit/arbitrator_2/test_connector_runtime.py` | Create | Fake venue end-to-end |
| `tests/unit/arbitrator_2/test_venue_registry.py` | Create | Five venues registered |

Do **not** modify `src/arbitrator/**` in this plan.

---

### Task 1: Package + types + import-graph guard

**Files:**
- Modify: `pyproject.toml`
- Create: `src/arbitrator_2/__init__.py`
- Create: `src/arbitrator_2/connector/__init__.py`
- Create: `src/arbitrator_2/connector/client_role.py`
- Create: `src/arbitrator_2/connector/market_kind.py`
- Create: `src/arbitrator_2/connector/market_id.py`
- Create: `src/arbitrator_2/connector/bbo.py`
- Create: `src/arbitrator_2/connector/unified_tick.py`
- Test: `tests/unit/arbitrator_2/test_import_graph.py`

**Interfaces:**
- Produces: `ClientRole`, `MarketKind`, `MarketId`, `Bbo`, `UnifiedTick`

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN = ("arbitrator.application", "arbitrator.presentation", "arbitrator.exchanges")


def test_arbitrator_2_does_not_import_legacy_app_stack() -> None:
    root = Path("src/arbitrator_2")
    hits: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module == f or node.module.startswith(f + ".") for f in FORBIDDEN):
                    hits.append(f"{path}: from {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == f or alias.name.startswith(f + ".") for f in FORBIDDEN):
                        hits.append(f"{path}: import {alias.name}")
    assert hits == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/arbitrator_2/test_import_graph.py -v`

Expected: FAIL — `src/arbitrator_2` does not exist (or collection error).

- [ ] **Step 3: Write minimal implementation**

In `pyproject.toml` under `[tool.poetry]`:

```toml
packages = [
    {include = "arbitrator", from = "src"},
    {include = "arbitrator_2", from = "src"},
]
```

`src/arbitrator_2/__init__.py` — empty.

`src/arbitrator_2/connector/client_role.py`:

```python
from __future__ import annotations

from enum import StrEnum


class ClientRole(StrEnum):
    BOOK = "book"
    TRADES = "trades"
    META = "meta"
```

`src/arbitrator_2/connector/market_kind.py`:

```python
from __future__ import annotations

from enum import StrEnum


class MarketKind(StrEnum):
    SPOT = "spot"
    PERP = "perp"
```

`src/arbitrator_2/connector/market_id.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from arbitrator_2.connector.market_kind import MarketKind


@dataclass(frozen=True, slots=True)
class MarketId:
    venue: str
    kind: MarketKind
    symbol: str
```

`src/arbitrator_2/connector/bbo.py`:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Bbo:
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    exchange_ts_ms: int | None
    recv_ts_ns: int
    apply_ts_ns: int
```

`src/arbitrator_2/connector/unified_tick.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from arbitrator_2.connector.market_id import MarketId


@dataclass(frozen=True, slots=True)
class UnifiedTick:
    market: MarketId
    bid: float
    ask: float
    bid_size: float
    ask_size: float
    exchange_ts_ms: int | None
    recv_ts_ns: int
    apply_ts_ns: int
    norm_ts_ns: int
```

`src/arbitrator_2/connector/__init__.py`:

```python
from arbitrator_2.connector.bbo import Bbo
from arbitrator_2.connector.client_role import ClientRole
from arbitrator_2.connector.market_id import MarketId
from arbitrator_2.connector.market_kind import MarketKind
from arbitrator_2.connector.unified_tick import UnifiedTick

__all__ = ["Bbo", "ClientRole", "MarketId", "MarketKind", "UnifiedTick"]
```

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/arbitrator_2/test_import_graph.py -v`

Expected: PASS

- [ ] **Step 5: Commit** (only if the user asked to commit)

```bash
git add pyproject.toml src/arbitrator_2 tests/unit/arbitrator_2/test_import_graph.py
git commit -m "feat(arbitrator_2): add connector package types and import-graph guard"
```

---

### Task 2: Isolated ccxt session factory

**Files:**
- Create: `src/arbitrator_2/connector/ccxt_session_factory.py`
- Test: `tests/unit/arbitrator_2/test_ccxt_session_factory.py`

**Interfaces:**
- Consumes: `ClientRole`
- Produces: `CcxtSessionFactory.create(venue_id: str, role: ClientRole, market_kind: MarketKind) -> object` (ccxt.pro exchange instance). Book/trades clients created with empty credentials. Distinct Python objects per (venue, role, kind).

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from arbitrator_2.connector.ccxt_session_factory import CcxtSessionFactory
from arbitrator_2.connector.client_role import ClientRole
from arbitrator_2.connector.market_kind import MarketKind


def test_book_trades_meta_are_distinct_clients() -> None:
    factory = CcxtSessionFactory()
    book = factory.create("binance", ClientRole.BOOK, MarketKind.PERP)
    trades = factory.create("binance", ClientRole.TRADES, MarketKind.PERP)
    meta = factory.create("binance", ClientRole.META, MarketKind.PERP)
    assert book is not trades
    assert book is not meta
    assert trades is not meta
    assert getattr(book, "apiKey", "") in ("", None)
    assert getattr(book, "secret", "") in ("", None)


def test_book_client_has_no_private_keys_even_if_env_exists() -> None:
    factory = CcxtSessionFactory()
    book = factory.create("binance", ClientRole.BOOK, MarketKind.SPOT)
    assert not getattr(book, "apiKey", None)
    assert not getattr(book, "secret", None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/arbitrator_2/test_ccxt_session_factory.py -v`

Expected: FAIL — `CcxtSessionFactory` not defined.

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

from typing import cast

import ccxt.pro as ccxtpro

from arbitrator_2.connector.client_role import ClientRole
from arbitrator_2.connector.market_kind import MarketKind

_DEFAULT_TYPE = {MarketKind.SPOT: "spot", MarketKind.PERP: "swap"}


class CcxtSessionFactory:
    def create(self, venue_id: str, role: ClientRole, market_kind: MarketKind) -> object:
        cls = getattr(ccxtpro, venue_id, None)
        if cls is None:
            raise ValueError(f"unknown venue: {venue_id}")
        options = {"defaultType": _DEFAULT_TYPE[market_kind]}
        client = cls({"enableRateLimit": True, "options": options})
        if role != ClientRole.META:
            client.apiKey = ""
            client.secret = ""
            client.password = ""
        return cast(object, client)
```

Note: Meta also has empty keys in Stage 1 (public `load_markets` only). Never copy host `.env` keys onto Book/Trades.

- [ ] **Step 4: Run tests**

Run: `.venv\Scripts\python.exe -m pytest tests/unit/arbitrator_2/test_ccxt_session_factory.py -v`

Expected: PASS

- [ ] **Step 5: Close created clients in tests** (`await client.close()` in an asyncio test if ccxt warns). If tests hang, wrap with `pytest.mark.asyncio` and close.

---

### Task 3: Book store + latency metrics

**Files:**
- Create: `src/arbitrator_2/connector/book_store.py`
- Create: `src/arbitrator_2/connector/latency_metrics.py`
- Test: `tests/unit/arbitrator_2/test_book_store.py`

**Interfaces:**
- Produces:
  - `BookStore.apply(market: MarketId, bids: list[list[float]], asks: list[list[float]], exchange_ts_ms: int | None, recv_ts_ns: int) -> Bbo`
  - `BookStore.get_bbo(market: MarketId) -> Bbo | None`
  - `LatencyMetrics.record_apply(venue: str, kind: MarketKind, recv_ts_ns: int, apply_ts_ns: int, first: bool) -> None`
  - `LatencyMetrics.snapshot() -> dict[str, float]` with keys `apply_lag_p50_ms`, `apply_lag_p95_ms`, `first_bbo_ms` (last first-bbo), `updates`

Apply extracts top bid/ask only (depth 1). Invalid empty book returns previous BBO or raises nothing — skip update.

- [ ] **Step 1: Write the failing test**

```python
from __future__ import annotations

from arbitrator_2.connector.book_store import BookStore
from arbitrator_2.connector.market_id import MarketId
from arbitrator_2.connector.market_kind import MarketKind


def test_apply_stores_bbo_and_apply_lag_is_non_negative() -> None:
    store = BookStore()
    market = MarketId("binance", MarketKind.PERP, "BTC/USDT:USDT")
    recv = 1_000_000_000
    bbo = store.apply(market, [[100.0, 2.0]], [[101.0, 3.0]], 1, recv)
    assert bbo.bid == 100.0
    assert bbo.ask == 101.0
    assert bbo.bid_size == 2.0
    assert bbo.ask_size == 3.0
    assert bbo.apply_ts_ns >= recv
    assert store.get_bbo(market) == bbo
```

- [ ] **Step 2: Run test — expect FAIL** (`BookStore` missing)

- [ ] **Step 3: Implement**

`book_store.py` — use `time.monotonic_ns()` for `apply_ts_ns`.

`latency_metrics.py` — keep a list of apply_lag_ms (cap 10_000 samples); compute p50/p95 with `statistics.quantiles` or sorted index.

- [ ] **Step 4: pytest PASS**

---

### Task 4: Normalize queue never blocks apply

**Files:**
- Create: `src/arbitrator_2/connector/normalize_queue.py`
- Test: `tests/unit/arbitrator_2/test_normalize_queue.py`

**Interfaces:**
- Produces:
  - `NormalizeQueue(maxsize: int = 1024)`
  - `try_put(bbo: Bbo, market: MarketId) -> bool` — `False` if full (increment `dropped`)
  - `async get() -> tuple[MarketId, Bbo]`
  - `dropped: int`

- [ ] **Step 1: Failing test**

```python
from __future__ import annotations

from arbitrator_2.connector.bbo import Bbo
from arbitrator_2.connector.market_id import MarketId
from arbitrator_2.connector.market_kind import MarketKind
from arbitrator_2.connector.normalize_queue import NormalizeQueue


def test_try_put_returns_false_when_full_and_does_not_block() -> None:
    q = NormalizeQueue(maxsize=1)
    market = MarketId("binance", MarketKind.SPOT, "BTC/USDT")
    bbo = Bbo(1.0, 2.0, 1.0, 1.0, None, 1, 2)
    assert q.try_put(market, bbo) is True
    assert q.try_put(market, bbo) is False
    assert q.dropped == 1
```

- [ ] **Step 2: FAIL then implement with `asyncio.Queue` + `put_nowait` / `QueueFull`**

- [ ] **Step 3: pytest PASS**

---

### Task 5: Connector runtime + fake venue (TDD e2e)

**Files:**
- Create: `src/arbitrator_2/connector/venue_adapter.py`
- Create: `src/arbitrator_2/connector/connector_runtime.py`
- Create: `tests/unit/arbitrator_2/fake_venue.py` (test double; class `FakeVenue`)
- Test: `tests/unit/arbitrator_2/test_connector_runtime.py`

**Interfaces:**
- `VenueAdapter` Protocol:
  - `venue_id: str`
  - `async connect() -> None`
  - `async close() -> None`
  - `async load_markets(kind: MarketKind) -> None` — **must use meta client only**
  - `async watch_book(market: MarketId) -> dict[str, object]` — one ccxt-like book dict `bids`/`asks`/`timestamp`
  - `async watch_trades(market: MarketId) -> list[object]` — optional; FakeVenue may raise `NotImplementedError` if trades disabled
- `ConnectorRuntime`:
  - `__init__(self, adapters: list[VenueAdapter], *, enable_trades: bool = False)`
  - `async subscribe(markets: list[MarketId]) -> None`
  - `async run_forever() -> None` — loop watch_book, apply, try_put
  - `get_bbo(market: MarketId) -> Bbo | None`
  - `unified_ticks: asyncio.Queue[UnifiedTick]` (or drain method)
  - `rest_fetch_order_book_calls: int` — always 0 on book path

FakeVenue `watch_book` yields one synthetic book then blocks on `asyncio.Event` until closed.

- [ ] **Step 1: Test**

```python
import asyncio
from arbitrator_2.connector.connector_runtime import ConnectorRuntime
from arbitrator_2.connector.market_id import MarketId
from arbitrator_2.connector.market_kind import MarketKind
from tests.unit.arbitrator_2.fake_venue import FakeVenue

async def test_runtime_applies_book_without_rest_and_emits_unified() -> None:
    venue = FakeVenue("binance")
    runtime = ConnectorRuntime([venue], enable_trades=False)
    market = MarketId("binance", MarketKind.PERP, "BTC/USDT:USDT")
    await runtime.subscribe([market])
    task = asyncio.create_task(runtime.run_forever())
    for _ in range(50):
        if runtime.get_bbo(market) is not None:
            break
        await asyncio.sleep(0.01)
    bbo = runtime.get_bbo(market)
    assert bbo is not None
    assert bbo.bid > 0
    assert runtime.rest_fetch_order_book_calls == 0
    tick = await asyncio.wait_for(runtime.next_unified(), timeout=1.0)
    assert tick.market == market
    assert tick.norm_ts_ns >= tick.apply_ts_ns
    task.cancel()
    await runtime.close()
```

- [ ] **Step 2: Implement FakeVenue + ConnectorRuntime**

Runtime book loop: `recv_ts_ns = time.monotonic_ns()` immediately before apply; never call `fetch_order_book`. Spawn a background task that `await queue.get()` and builds `UnifiedTick`. `enable_trades=False` must not create a trades client.

- [ ] **Step 3: pytest PASS**

---

### Task 6: Five-venue registry + ccxt.pro venue

**Files:**
- Create: `src/arbitrator_2/connector/venue_capabilities.py`
- Create: `src/arbitrator_2/connector/ccxt_pro_venue.py`
- Create: `src/arbitrator_2/connector/venue_registry.py`
- Test: `tests/unit/arbitrator_2/test_venue_registry.py`

**Interfaces:**
- `VenueCapabilities(batch_books: bool, min_depth: int, trades: bool)`
- `VENUES = ("binance", "mexc", "bitget", "gate", "bingx")`
- `build_default_adapters() -> list[CcxtProVenue]`

Caps (Stage 1 defaults; adjust only if a live probe proves otherwise):

| venue | batch_books | min_depth | trades |
|-------|-------------|-----------|--------|
| binance | True | 5 | True |
| bitget | True | 1 | True |
| mexc | False | 5 | True |
| gate | False | 5 | True |
| bingx | False | 5 | True |

`CcxtProVenue.watch_book`: `await book_client.watch_order_book(symbol, limit=caps.min_depth)` — **no** `fetch_order_book`. Use factory: BOOK client for watch, META client for `load_markets` in `connect()`.

- [ ] **Step 1: Test**

```python
from arbitrator_2.connector.venue_registry import VENUES, build_default_adapters

def test_five_cex_registered() -> None:
    adapters = build_default_adapters()
    ids = {a.venue_id for a in adapters}
    assert ids == set(VENUES)
    assert len(VENUES) == 5
```

- [ ] **Step 2: Implement registry + CcxtProVenue**

- [ ] **Step 3: pytest PASS** (no live network in this test)

---

### Task 7: Demo script that prints live books

**Files:**
- Create: `scripts/arbitrator_2_show_books.py`

**Behavior:**
- Subscribe default markets: for each of 5 venues, `BTC/USDT` (spot) and `BTC/USDT:USDT` (perp).
- Print a line per update (or a redraw every 500 ms) showing venue, kind, symbol, bid, ask, sizes, apply_lag_ms, staleness_ms.
- Optional `--trades` to also print last public trade (separate client).
- `--seconds 30` default run window, then print p50/p95 apply_lag per venue/kind and `rest_fetch_order_book_calls`.
- Uses `.venv` when invoked as: `.venv\Scripts\python.exe scripts/arbitrator_2_show_books.py`
- Must show **actual bid/ask numbers** from exchanges, not only metrics.
- On venue failure, print error for that venue and continue others (do not abort the whole script).

```python
# CLI sketch
# python scripts/arbitrator_2_show_books.py --seconds 30
# python scripts/arbitrator_2_show_books.py --seconds 30 --trades
```

- [ ] **Step 1: Implement script using `ConnectorRuntime` + `build_default_adapters()`**
- [ ] **Step 2: Manual run** (acceptance): output contains rows for multiple venues and both `spot` and `perp`.
- [ ] **Step 3: Unit tests stay green** (script is not unit-tested against live nets).

---

### Task 8: Verification gate

- [ ] Run: `.venv\Scripts\python.exe -m pytest tests/unit/arbitrator_2 -q` — all PASS
- [ ] Run: `.venv\Scripts\mypy.exe --strict src/arbitrator_2` — PASS
- [ ] Run: `.venv\Scripts\ruff.exe check src/arbitrator_2 tests/unit/arbitrator_2`
- [ ] Run demo: `.venv\Scripts\python.exe scripts/arbitrator_2_show_books.py --seconds 20`
- [ ] Confirm printed books for 5 venues × spot+perp (or explicit per-venue error if a venue is down)
- [ ] Confirm REST fetch counter stays 0
- [ ] Confirm `test_import_graph` still PASS

Stage 1 is **done** only when tests are green **and** the demo prints live exchange BBO data.

---

## Spec coverage

| Design requirement | Task |
|--------------------|------|
| `src/arbitrator_2` package, no legacy app imports | 1, 8 |
| 5 CEX | 6, 7 |
| Spot + futures books | 5–7 |
| Isolated Book / Trades / Meta | 2, 5 |
| Fast apply + queued normalize | 3, 4, 5 |
| Metrics apply_lag / first_bbo | 3, 7 |
| Tests | 1–6, 8 |
| Demo script prints live data | 7, 8 |
| No strategies/UI/DEX/orders | all (omitted) |

## Handoff

Plan saved to `docs/superpowers/plans/2026-08-14-arbitrator-2-connector.md`.

**How to execute:**

1. **Subagent-Driven (recommended)** — one subagent per task, review between tasks  
2. **Inline** — implement in this chat, checkpoint after each task  

Which approach?
