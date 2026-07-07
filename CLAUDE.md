# CLAUDE.md — Arbitrator project

USDT-M perpetual futures arbitrage screener & strategy engine.
FastAPI + static web UI, live data over WebSocket, ccxt.pro for exchange I/O.

## Commands

| Task | Command |
| ---- | ------- |
| Run all tests | `.venv\Scripts\python.exe -m pytest tests/ -q` |
| Run strategy tests | `.venv\Scripts\python.exe -m pytest tests/ -k strategy -q` |
| Type check | `.venv\Scripts\mypy.exe --strict src/arbitrator` |
| Lint | `.venv\Scripts\ruff.exe check src tests` |
| Format | `.venv\Scripts\black.exe src tests` |
| Run app | `.venv\Scripts\uvicorn.exe main:app` |
| Rebuild UI HTML | `.venv\Scripts\python.exe scripts/build_ui.py` |

**Always run tools from `.venv`**, never from the global Python. The global
interpreter does not have `arbitrator` or any dev deps installed.
Do not use `poetry run` — it can hang in this environment.

## Architecture

```
presentation/  →  application/  →  domain/  ←  exchanges/
                                          ←  config/
```

| Layer | Contains | May NOT import |
| ----- | -------- | -------------- |
| `domain/` | Entities, value objects, abstractions | anything outer |
| `application/` | Use-cases, services orchestrating domain | exchanges, presentation |
| `exchanges/` | ccxt.pro adapters, exchange Factory | presentation |
| `config/` | `Settings`, `logger`, JSON repos | presentation, exchanges, application |
| `data/` | Mutable JSON data files (no Python) | — |
| `presentation/` | FastAPI app (static UI + WebSocket only) | (top layer) |

Wiring of concrete implementations happens in `main.py` (composition root).

## OOP rules

- One class per file. Filename = class name in `snake_case`.
- No free-floating functions except thin entry-point scripts (`main.py`).
- Prefer composition over inheritance.
- Data containers: `pydantic.BaseModel(frozen=True)` or `@dataclass(frozen=True, slots=True)`.
- Methods that don't use `self` → `@staticmethod` or `@classmethod`.

## SOLID

- **S**: one class, one reason to change.
- **O**: extend via new subclasses/strategies; don't edit existing code to add behavior.
- **L**: subclasses are drop-in replacements for their base.
- **I**: many small abstractions, never one fat one.
- **D**: depend on `abc.ABC` or `typing.Protocol`; inject every collaborator via `__init__`.

## Typing

- `mypy --strict` must pass at all times.
- Never use `typing.Any`. Use `object` + `isinstance`, generics, or proper unions.
- `from __future__ import annotations` at the top of every module.
- Public methods must have complete type hints (parameters + return).
- Pydantic models are the source of truth for runtime types.

## Async

- All I/O-bound work uses `asyncio`.
- Exchange data uses **ccxt.pro** `watch_*` WebSocket methods — NOT REST `fetch_*` polling.
- `watch_tickers` chunked via `Settings.watch_tickers_chunk_size` (default 50);
  at most `Settings.watch_tickers_max_concurrent_chunks` (default 3) run at once.
- Always close async resources in `finally` or `async with`.
- The browser UI communicates over **WebSocket only** (`presentation/ws/`).
  No `/api/*` HTTP endpoints for the frontend.
- Run the app with **uvicorn** (not Streamlit).

## Configuration

- All runtime parameters live in `src/arbitrator/config/settings.py` in a single
  `Settings(pydantic_settings.BaseSettings)` class, frozen.
- Values read from `.env` at project root (`.env.example` shows defaults; `.env` is gitignored).
- No hardcoded magic values in domain/application/exchanges/presentation code.
- `Settings` constructed once in `main.py` and injected via constructors.
- Exchange credentials: use `Settings.credentials_for(exchange_id)` — never read
  env vars elsewhere.

## Markets — USDT-M perpetual futures ONLY

- Symbol format: `BASE/USDT:USDT` (e.g. `BTC/USDT:USDT`).
- Every exchange adapter: `options.defaultType = "swap"`.
- Do not load spot, coin-M (inverse) futures, or options markets.
- New exchange adapter checklist:
  1. File under `exchanges/`, inherits `CcxtBase`.
  2. `exchange_id` and `display_name` as `ClassVar[str]`.
  3. Override `_create_client` with USDT-M swap defaults.
  4. Register in `Factory._registry` (`exchanges/factory.py`).

## Logging

Use the project-wide Loguru logger — never `print()` or `logging.getLogger()`.

```python
from arbitrator.config.logger import logger
```

- Positional `{}` placeholders, never f-strings: `logger.info("x={} y={}", x, y)`.
- Inside `except` blocks: `logger.exception("static msg | ctx={}", ctx)`.
- `init_logger(...)` called once in `main.py` only.

Required logging points: exchange/gateway lifecycle, every `except Exception:`,
config errors, stream startup/shutdown, retry loops (at `debug`).

## Exchange data access

| Channel | Protocol | Purpose |
| ------- | -------- | ------- |
| UI ↔ server | WebSocket `/ws/*` + static files | All UI data and commands |
| Server ↔ exchange | ccxt.pro `watch_*` (priority), ccxt `fetch_*` (fallback) | Market and account I/O |

Browser never calls exchange REST or internal `/api/*`.

Use `watch_*` first. REST only when: no matching `watch*` capability exists, or
the operation is inherently request/response (set leverage, place order, one-shot fee).

## Error handling

- Prefer returning a result/`Optional` over raising for expected business outcomes.
- Use static error messages; pass dynamic data separately.
- Always log the full exception — never just `str(error)`.

## Third-party library APIs

Never invent method names, parameters, or signatures for third-party libraries.
When unsure about the current API (pydantic, ccxt, fastapi, etc.):
1. Use the **Context7 MCP** server to look up docs (`resolve-library-id` then `get-library-docs`).
2. Fallback: `WebSearch` / `WebFetch` on the official docs URL.
3. If still unknown — say so; do not fabricate.

## UI templates

HTML source lives in partials, assembled into `static/index.html`:

```bash
.venv\Scripts\python.exe scripts/build_ui.py
```

```
presentation/static/
  partials/
    layout/head.html, scripts.html
    sidebar.html
    pages/screener.html, opportunity.html, orders.html, settings.html
    opportunity/topbar.html, ex-info-row.html, strategy-table.html,
                params.html, orders-panel.html, chart.html, order-books.html
  css/app.css
  js/core/          # ws_client, dom, delta_router
  js/render/        # per-screen render + delta handlers
  index.html        # build output — do not edit by hand
```

No hardcoded market data in partials. No inline `style="..."` except dynamic JS values.
Visual reference: `maket/index.html`. Data channel: WebSocket snapshot + delta.

## Feature specs

- `specs/001-mockup-ui/` — UI spec and plan.
- `specs/002-strategy-engine/` — strategy engine: 6-strategy calc, signals, hedged execution,
  in-process cache. Read `specs/002-strategy-engine/plan.md` and
  `specs/002-strategy-engine/contracts/strategy-data-catalog.md` for current context.
- `specs/002-strategy-engine/strategies/` — **per-strategy logic docs** (entry/exit conditions,
  formulas, DCA, guards, settings). One file per strategy. Index:
  `specs/002-strategy-engine/strategies/README.md`.

## Strategy docs maintenance rule

When modifying strategy logic in code (entry conditions, exit conditions, DCA,
guards, slippage checks, settings) — **update the corresponding strategy doc**
in `specs/002-strategy-engine/strategies/`. Add a row to "Історія змін" table
with the date and a short description of what changed.

## Agent diagnostics — scripts first (no trading)

When investigating exchange data or trading situations, **run existing
`scripts/` CLIs** before ad-hoc ccxt/REST or one-off code. Skill:
`.cursor/skills/exchange-read-only-inspect/`.

| Situation | Script |
| --------- | ------ |
| Credentials, balance, positions, open orders | `scripts/inspect_exchanges.py --json verify` / `account` |
| Public ticker, order book, symbols | `scripts/inspect_exchanges.py --json ticker` / `orderbook` / `list-symbols` |
| Open + closed positions (Orders UI parity) | `scripts/trade_report.py` (`--refresh` bypasses cache) |
| Paper orders vs OHLCV audit | `scripts/audit_paper_orders.py` |
| FF strategy historical backtest | `scripts/backtest_ff.py` |
| Cross-exchange token contract check | `scripts/check_token_identity.py` |

```bash
.venv\Scripts\python.exe scripts/inspect_exchanges.py --json verify
.venv\Scripts\python.exe scripts/inspect_exchanges.py --json account --exchange bitget
.venv\Scripts\python.exe scripts/trade_report.py
.venv\Scripts\python.exe scripts/audit_paper_orders.py
```

**Never** call `open_market_position`, `close_market_position`, `create_order`,
`cancel_order`, `set_leverage`, or `audit_paper_orders.py --fix` without explicit
user approval.