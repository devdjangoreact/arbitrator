# CLAUDE.md — Arbitrator

> **Single source of truth for project principles:** `.specify/memory/constitution.md` (v1.5.0).
> Tactical details live in `.cursor/rules/*.mdc`. This file is a thin pointer +
> command reference. It does **not** re-state principles — read the constitution
> and the relevant `.mdc` when you need them.

USDT-M perp + USDT spot arb screener + strategy engine. FastAPI + React UI, ccxt.pro.

## Language — HARD RULE

All final reports, completion messages, clarification questions, summaries, and explanations MUST be written in **Ukrainian**.
Code, file names, identifiers, and technical strings stay in English.

## UI Verification — HARD RULE

All React UI changes MUST be verified in the browser (via Playwright headless or manual) before marking the task done.
- Run `pnpm build` in `react-ui/`, restart the backend, then open the page.
- For any button action (Start, Stop, Fast Trade, ×) — assert the observable state change in the UI.
- E2E tests MUST use real backend data — no mocked WS responses.
- Any JS error in `pageerror` or `console.error` during the test = FAIL.

## Trading Safety — §15

No trading actions (`create_order`, `cancel_order`, `set_leverage`, `open_market_position`, `close_market_position`) without **explicit user approval per session**.
- `mock_data` / `paper` modes: allowed without per-call approval if `Settings.arb_auto_open_enabled = true`.
- **Live mode**: requires explicit user confirmation. User has confirmed live mode for the current task.

## Commands

Always `.venv\Scripts\*.exe` — never global Python, never `poetry run`.

| Task | Command |
| ---- | ------- |
| Tests | `.venv\Scripts\python.exe -m pytest tests/ -q` |
| Strategy tests | `.venv\Scripts\python.exe -m pytest tests/ -k strategy -q` |
| Mypy | `.venv\Scripts\mypy.exe --strict src/arbitrator` |
| Lint | `.venv\Scripts\ruff.exe check src tests` |
| Format | `.venv\Scripts\black.exe src tests` |
| Run app | `.venv\Scripts\uvicorn.exe main:app` |
| Run app (lifecycle) | `.venv\Scripts\python.exe scripts/run_app.py` |
| Rebuild legacy UI | `.venv\Scripts\python.exe scripts/build_ui.py` |
| Build React UI | `pnpm build` (in `src/arbitrator/presentation/react-ui/`) |

## Agent Workflow

- **Read the constitution first** when the task touches principles — `.specify/memory/constitution.md`. Then the relevant `.cursor/rules/*.mdc`.
- **Scope prompts**: file + method/lines + expected vs actual; forbid whole-project reads.
- **Explore code**: `graphify query|path|explain` when the implementation path is unknown; skip for known files/lines and for exchange diagnostics. Full rules: `.cursor/rules/graphify.mdc`.
- **After code edits**: run `graphify update .`; audit docs per `.cursor/rules/documentation-sync.mdc`.
- **Diagnostics**: `scripts/inspect_exchanges.py --json`, `trade_report.py --refresh`. Never use cached files for trade analysis.
- **No trading** without explicit user approval — Constitution §15.
- **Adding strategy parameters**: environment-bound → `Settings`; user-tunable knob → `StrategyUIConfig` (`src/arbitrator/config/ui_config.py`).
- **Context7**: before writing/reviewing code that uses any third-party library, look up via `mcp__context7__resolve-library-id` → `mcp__context7__query-docs`. Never invent third-party APIs.

## Superpowers Skills

**New feature work uses Superpowers only** — not Spec Kit (`/speckit-*`, new `specs/NNN-*`).
Designs: `docs/superpowers/specs/`. Plans: `docs/superpowers/plans/`.

Skills auto-trigger based on context. Manual invocation when needed:

| Skill | When |
| ----- | ---- |
| `/brainstorming` | Before any new feature or plan |
| `/systematic-debugging` | Bug investigation |
| `/writing-plans` | Creating implementation plans |
| `/executing-plans` | Following an existing plan |
| `/test-driven-development` | Writing new features with tests |
| `/verification-before-completion` | Before marking a task done |
| `/finishing-a-development-branch` | Before merging / creating PR |
| `/requesting-code-review` | Requesting review |
| `/subagent-driven-development` | Large parallel implementation |
| `/using-git-worktrees` | Parallel isolated workstreams |

## Where to Look

| Concern | Location |
| ------- | -------- |
| Principles (the *why*) | `.specify/memory/constitution.md` |
| Python architecture, layers, typing, async | `.cursor/rules/architecture.mdc` |
| Tooling / venv / Poetry | `.cursor/rules/tooling.mdc` |
| Logging (Loguru) | `.cursor/rules/logging.mdc` |
| Exchange data (WS vs REST, no trading) | `.cursor/rules/exchange-data.mdc` |
| FastAPI / WebSocket presentation | `.cursor/rules/fastapi-presentation.mdc` |
| UI templates (legacy vanilla) | `.cursor/rules/ui-templates.mdc` |
| Opportunity screen layout | `.cursor/rules/opportunity-ui.mdc` |
| Feature development (Superpowers) | `.cursor/rules/feature-development.mdc` |
| Compact code + dead-code removal | `.cursor/rules/compact-code.mdc` |
| Context7 docs lookups | `.cursor/rules/context7-lookup.mdc` |
| Graphify usage | `.cursor/rules/graphify.mdc` |
| Doc sync after edits | `.cursor/rules/documentation-sync.mdc` |
| Design docs / plans | `docs/superpowers/specs/`, `docs/superpowers/plans/` |
