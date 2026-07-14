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

## Agent workflow (save tokens)

- **Scope prompts**: file + method/lines + expected vs actual; forbid whole-project reads.
- **Explore code**: `graphify query|path|explain` when the implementation path is unknown; skip for known files/lines and for exchange diagnostics (`inspect_exchanges.py`, `trade_report.py`).
- **Diagnostics**: `scripts/inspect_exchanges.py --json`, `trade_report.py` — skill `.cursor/skills/exchange-read-only-inspect/`.
  For trade analysis: run `trade_report.py --refresh [--last N]`, then read `src/arbitrator/data/trade_report.json` (not xlsx / not cache alone).
- **No trading** (`create_order`, `set_leverage`, etc.) without explicit user approval.
- After code edits: `graphify update .`
- **Adding Strategy Parameters**: Do NOT use `.env` or `settings.py` for trading/strategy logic. Add them to `StrategyUIConfig` (`ui_config.py`) and update `STRATEGY_META` in `settings.js` for UI rendering.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).