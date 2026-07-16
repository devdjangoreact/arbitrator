# CLAUDE.md — Arbitrator

## Spec Kit — HARD RULE (cannot be overridden by conversation context)

**BEFORE invoking any `/speckit-*` skill**: do NOT read project files, do NOT create directories, do NOT write any files. Invoke the skill immediately.

**WHILE a spec kit skill runs**: follow ONLY its instructions. Never manually create `spec.md`, `plan.md`, `tasks.md`, feature directories, or any other spec kit artifact. The skill creates them — not you.

Violation = broken workflow. User has corrected this twice.

## Language — HARD RULE

All final reports, completion messages, clarification questions, summaries, and explanations MUST be written in **Ukrainian**.
Code, file names, identifiers, and technical strings stay in English.

> **Single source of truth for project principles:** `.specify/memory/constitution.md` (v1.4.0).
> Tactical details live in `.cursor/rules/*.mdc`. This file is a thin pointer +
> command reference. It does **not** re-state principles — read the constitution
> and the relevant `.mdc` when you need them.

USDT-M perp + USDT spot arb screener + strategy engine. FastAPI + conditional
React/legacy UI, ccxt.pro.

## Commands

Always `.venv\Scripts\*.exe` — never global Python, never `poetry run`.

| Task | Command |
| ---- | ------- |
| Tests | `.venv\Scripts\python.exe -m pytest tests/ -q` |
| Strategy tests | `.venv\Scripts\python.exe -m pytest tests/ -k strategy -q` |
| Mypy | `.venv\Scripts\mypy.exe --strict src/arbitrator` |
| Lint / format | `.venv\Scripts\ruff.exe check src tests` / `.venv\Scripts\black.exe` |
| Run app | `.venv\Scripts\uvicorn.exe main:app` |
| Rebuild legacy UI | `.venv\Scripts\python.exe scripts/build_ui.py` |
| Build React UI | `pnpm build` in `src/arbitrator/presentation/react-ui/` |
| Run app (lifecycle) | `.venv\Scripts\python.exe scripts/run_app.py` |

## Agent workflow (save tokens)

- **Read the constitution first** when the task touches principles —
  `.specify/memory/constitution.md`. Then the relevant `.cursor/rules/*.mdc`.
- **Scope prompts**: file + method/lines + expected vs actual; forbid
  whole-project reads.
- **Explore code**: `graphify query|path|explain` when the implementation path is
  unknown; skip for known files/lines and for exchange diagnostics.
  See `.cursor/rules/graphify.mdc`.
- **Diagnostics**: `scripts/inspect_exchanges.py --json`, `trade_report.py` —
  skill `.cursor/skills/exchange-read-only-inspect/`.
  For trade analysis: run `trade_report.py --refresh [--last N]`, then read
  `src/arbitrator/data/trade_report.json` (not xlsx / not cache alone).
- **No trading** (`create_order`, `set_leverage`, etc.) without explicit user
  approval — Constitution §15.
- **After code edits**: `graphify update .`; also audit docs per
  `.cursor/rules/documentation-sync.mdc`.
- **Adding strategy parameters**: see Constitution §17 — environment-bound →
  `Settings`; user-tunable strategy knob → `StrategyUIConfig`
  (`src/arbitrator/config/ui_config.py`) + `STRATEGY_META` in `settings.js`.

## graphify

Knowledge graph at `graphify-out/`. Full rules: `.cursor/rules/graphify.mdc`.
After code edits run `graphify update .`.

## Spec-Kit Pipeline Rules

**Standing project policy.** Applies every session, every agent, until explicitly
amended in this file. A blanket "do it all" instruction in conversation does NOT
override — each stage needs its own go-ahead.

### What Each Command Does

| Command | Purpose | Produces |
|---------|---------|----------|
| `/speckit.constitution` | Define project principles (simplicity, anti-abstraction, testing philosophy). Run once per project. | `.specify/memory/constitution.md` — articles that govern all downstream decisions |
| `/speckit.specify <desc>` | Turn a natural-language feature description into a structured requirements doc. Creates a git branch. | `specs/NNN-name/spec.md` — requirements, constraints, acceptance criteria |
| `/speckit.clarify` | Ask targeted questions about the spec to close ambiguities before planning. Interactive — user answers. | Updated `spec.md` with clarifications section filled |
| `/speckit.checklist` | Generate a quality/compliance checklist for complex features. | Checklist appended to spec artifacts, each item pass/fail |
| `/speckit.plan <stack>` | Design the implementation: architecture, data model, API contracts, research. | `plan.md`, `research.md`, `data-model.md`, `contracts/` in the spec folder |
| `/speckit.tasks` | Break the plan into ordered, dependency-aware implementation tasks. | `tasks.md` — grouped by user story, `[P]` marks parallelizable tasks |
| `/speckit.analyze` | Cross-check spec vs plan vs tasks for consistency gaps before coding. | Console report: critical/warning gaps that must be resolved |
| `/speckit.taskstoissues` | Convert tasks.md into GitHub issues for distributed execution. | GitHub issues with links back to tasks.md |
| `/speckit.implement` | Execute tasks in order: write tests first (red), then code (green). | Code + tests in the codebase, tasks marked done |
| `/speckit.converge` | Compare actual code against spec/plan/tasks, find drift. | Drift report; unbuilt work appended as new tasks |

### Branch Rule: Feature Branches Are Mandatory

Every Spec Kit feature **must** run on its own branch:

```
git checkout -b feature/NNN-short-name   # before /speckit.specify
```

- Branch created **before** the first spec-kit command, not after.
- Never commit Spec Kit work directly to `main`.
- Merge via PR only after `/speckit.converge` passes.
- Branch name format: `feature/NNN-short-name` matching the spec folder number.

### Core Rule: One Stage Per Turn

1. Run exactly one `/speckit.*` command.
2. Stop. Report result (format below).
3. If criterion fails → state what's wrong, propose fix, wait.
4. If criterion passes → propose next stage, wait for confirmation.

### Pipeline

| # | Stage | Command | Skip when | Pass criterion |
|---|-------|---------|-----------|----------------|
| 0 | Constitution | `/speckit.constitution` | Already exists with Art VII+VIII | constitution.md has Art VII, VIII |
| 1 | Spec | `/speckit.specify <desc>` | Never | `spec.md` created, no unresolved `[NEEDS CLARIFICATION]` |
| 2 | Clarify | `/speckit.clarify` | Spike/throwaway | Ambiguities closed |
| 3 | Plan | `/speckit.plan <stack>` | Never | `plan.md` + artifacts created |
| 3b | Self-audit | Check plan for sequencing gaps + over-engineering | Trivial single-step feature | Confirmed clean, or problems listed |
| 4 | Tasks | `/speckit.tasks` | Never | `tasks.md` created, deps explicit, `[P]` only for independent files |
| 5 | Analyze | `/speckit.analyze` | ≤2 tasks | No critical gaps |
| 6 | Implement | `/speckit.implement` | Never | Tests first (Art III), dependency order respected |
| 7 | Converge | `/speckit.converge` | No drift suspected | Drift report; drift → new tasks, not silent drops |

Optional stages (add only when needed):
- **2b Checklist** (`/speckit.checklist`) — complex/compliance features only.
- **5b Issues** (`/speckit.taskstoissues`) — distributed execution only.

### Report Format (every stop)

```
STAGE: <# and name>
DONE: <what ran, what changed>
CHECK: <pass/fail + why>
NEXT: <proposed stage>
WHY: <1-2 sentences>
```

Then: "Waiting for confirmation." — full stop.

### Recovery Paths

- **Stage fails partway** → State what completed. Propose: retry, partial
  rollback, or re-plan from stage N. Wait.
- **Spec wrong during implement** → Stop implement. Amend spec (stage 1).
  Re-run affected downstream stages. Wait for confirmation at each.
- **Converge finds drift** → Fold new tasks into next tasks/implement pass.
  Do NOT restart from stage 0.

### Explicit Override

To bypass one gate: say `pipeline override: <reason>`. Logged in the report.
Does not cascade — next gate still requires confirmation.

### Forbidden

- Two+ spec-kit commands without stop + confirmation between them.
- Implement when analyze found unresolved critical gaps.
- Silent modification of `constitution.md`.
- `[P]` on tasks touching the same file.

---

## Where to look

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
| Feature development (Spec Kit gate) | `.cursor/rules/feature-development.mdc` |
| Compact code + dead-code removal | `.cursor/rules/compact-code.mdc` |
| Context7 docs lookups | `.cursor/rules/context7-lookup.mdc` |
| Graphify usage | `.cursor/rules/graphify.mdc` |
| Doc sync after edits | `.cursor/rules/documentation-sync.mdc` |
