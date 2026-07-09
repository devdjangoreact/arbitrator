# CLAUDE.md — Arbitrator

USDT-M perp futures arb screener + strategy engine. FastAPI + static UI, ccxt.pro.

## Commands

Always `.venv\Scripts\*.exe` — never global Python, never `poetry run`.

| Task | Command |
| ---- | ------- |
| Tests | `.venv\Scripts\python.exe -m pytest tests/ -q` |
| Strategy tests | `.venv\Scripts\python.exe -m pytest tests/ -k strategy -q` |
| Mypy | `.venv\Scripts\mypy.exe --strict src/arbitrator` |
| Lint / format | `.venv\Scripts\ruff.exe check src tests` / `black.exe` |
| Run app | `.venv\Scripts\uvicorn.exe main:app` |
| Rebuild UI | `.venv\Scripts\python.exe scripts/build_ui.py` |

## Rules index (`.cursor/rules/`)

| Topic | File |
| ---- | ---- |
| Layers, typing, Settings, markets | `architecture.mdc` |
| Exchange I/O, bid/ask spreads | `exchange-data.mdc` |
| Loguru logger | `logging.mdc` |
| Compact code | `compact-code.mdc` |
| graphify for code exploration (when useful) | `graphify.mdc` |
| Tooling / venv | `tooling.mdc` |
| Third-party APIs | `context7-lookup.mdc` |
| UI partials | `ui-templates.mdc` |
| Docs sync after structural edits | `documentation-sync.mdc` |

## Specs

- `specs/002-strategy-engine/` — strategy engine; per-strategy logic in `strategies/`
- `specs/001-mockup-ui/` — UI mockup

## Agent workflow (save tokens)

- **Scope prompts**: file + method/lines + expected vs actual; forbid whole-project reads.
- **Explore code**: `graphify query|path|explain` when the implementation path is unknown; skip for known files/lines and for exchange diagnostics (`inspect_exchanges.py`, `trade_report.py`).
- **Diagnostics**: `scripts/inspect_exchanges.py --json`, `trade_report.py` — skill `.cursor/skills/exchange-read-only-inspect/`.
  For trade analysis: run `trade_report.py --refresh [--last N]`, then read `src/arbitrator/data/trade_report.json` (not xlsx / not cache alone).
- **No trading** (`create_order`, `set_leverage`, etc.) without explicit user approval.
- After code edits: `graphify update .`
