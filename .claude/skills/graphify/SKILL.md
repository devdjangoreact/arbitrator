---
name: graphify
description: Graphify code exploration pipeline rules and usage limits (for unknown code paths only).
---

# graphify (arbitrator)

Graph at `graphify-out/`. Full pipeline: `.claude/skills/graphify/SKILL.md` — trigger `/graphify`.

## When to use (saves tokens)

Run `graphify query|path|explain` **only** for **unknown code paths** — multi-file, cross-layer, dependency tracing.

Skip graphify for:

- Exchange / account / PnL / open orders → `scripts/inspect_exchanges.py --json`, `scripts/trade_report.py`
  For trade analysis: `trade_report.py --refresh [--last N]` then read `src/arbitrator/data/trade_report.json`
- Known file, class, or line range → Read/Edit directly
- Tests, lint, mypy, script execution
- Runtime facts on a symbol (EVAA, BTC, …) — diagnostics CLI, not graphify

Prefer narrow code-vocabulary queries: `hedged exit spread calculation`, not `EVAA hedge PnL…`.

After graphify orients you → Read/Grep **specific lines only**. After code edits → `graphify update .`.

Canonical rule: `.cursor/rules/graphify.mdc`.
