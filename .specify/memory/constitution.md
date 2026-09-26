<!--
Sync Impact Report
Version change: 1.4.1 → 1.5.0 (MINOR — Feature Development Gate: Spec Kit → Superpowers)

Changes:
- Feature Development Gate: new work MUST use Superpowers (brainstorming →
  docs/superpowers/specs/ → writing-plans → docs/superpowers/plans/). Spec Kit
  (`/speckit-*`, new `specs/NNN-*`) is not used for new features; existing
  `specs/**` remain historical archive only.
- Propagated: `.cursor/rules/feature-development.mdc`, `specify-rules.mdc`,
  `CLAUDE.md`.

Sync Impact Report
Version change: 1.4.0 → 1.4.1 (PATCH — clarifications only, no new principles)

Changes:
- §11 renamed "Data Flow — WebSocket First, REST as Fallback": now explicitly covers
  BOTH browser↔FastAPI and backend↔exchange scopes, with clear separation between them.
  Resolves ambiguity where agents could misread §11 as banning all REST.
- §18 slimmed: exchange WS/REST rules consolidated into §11 to eliminate duplication.
- §6: "when feasible" for unit tests replaced with precise carve-outs (data containers,
  exchange adapter shims). Closes the loophole agents exploited to skip tests.
- plan-template.md Constitution Check gate updated to §15–§21 checklist.
- feature-development.mdc step order fixed: /speckit-tasks now precedes implementation.
- architecture.mdc header §16–§20 corrected to §1–§21 (selected).
- CLAUDE.md: black.exe path fixed; graphify section slimmed to pointer.

Sync Impact Report
Version change: 1.3.1 → 1.4.0
Type: MINOR (new principles, no breaking governance change).

Added principles:
- 15. Trading Safety (no orders/leverage without explicit user approval)
- 16. Market Universes — USDT-M Perp + Spot USDT (relaxes prior "perp ONLY")
- 17. Configuration Single Source of Truth (Settings vs StrategyUIConfig split)
- 18. Async-First, REST As Fallback
- 19. Static Typing Gate (mypy --strict + ruff must pass before merge)
- 20. Structured Logging (Loguru singleton, no print, full exception)
- 21. Dead Code Removal (deprecates `.cursor/rules/preserve-code.mdc`)

Modified principles:
- 12. UI Parity: clarified that parity applies to React migration only;
  legacy vanilla JS under `presentation/static/` must remain buildable.

Amended sections:
- Governance: cross-references `.cursor/rules/*.mdc` (tactical detail layer)
  instead of "superseding all practices".
- Feature Development Gate: spec-kit trigger is explicit but agent-judged;
  user may invoke explicitly via "use spec kit" phrasing.

Templates requiring updates: plan-template.md (Constitution Check section).

Follow-up TODOs:
- Update `.cursor/rules/architecture.mdc` §7 to relax perp-ONLY into perp + spot.
- Disable `.cursor/rules/preserve-code.mdc` (point to constitution §21).
- Update `.cursor/rules/feature-development.mdc` alignment text.
- Slim `CLAUDE.md` to a pointer + commands only.
-->
# Arbitrator Constitution

> **Single source of truth for project principles.**
> All agents (Cursor, Claude Code, subagents) MUST treat this document as the
> authoritative statement of *why* the project works the way it does.
> Tactical *how* details live in `.cursor/rules/*.mdc` and are referenced from
> the relevant principle below. If a rule file conflicts with this constitution,
> **the constitution wins** — and the rule file must be fixed.

## Project Stack

FastAPI backend with WebSocket support for real-time communication.
Two frontends served conditionally by `Settings.use_react_frontend`:
- **React + Vite + Tailwind** under `src/arbitrator/presentation/react-ui/` (active).
- **Legacy vanilla JS/HTML partials** under `src/arbitrator/presentation/static/`
  (frozen, must remain buildable — see §12).
Python 3.11+, TypeScript on the frontend. ccxt.pro for exchange I/O.

## Core Principles

### 1. Simplicity First
Favor the simplest solution that meets requirements. No premature abstraction,
no unused config layers. Tactical detail: `.cursor/rules/compact-code.mdc`.

### 2. API Contract Discipline
All REST endpoints defined with Pydantic models for request/response validation.
WebSocket messages use a typed schema (Pydantic or TypedDict) with an explicit
`type` field; no free-form JSON.

### 3. Real-Time Reliability
WebSocket connections must handle reconnect/disconnect gracefully; no silent
message loss. Backend must support broadcasting to multiple clients without
blocking the event loop. See §18 for exchange-side streaming discipline.

### 4. Frontend Consistency
All UI built with Tailwind utility classes; no inline styles, no CSS-in-JS.
Shared design tokens (colors, spacing) defined once in `tailwind.config`.
Applies to the React UI. Legacy vanilla JS keeps its existing `css/app.css`.

### 5. Component Architecture
React components are functional, typed with TypeScript; no class components.
State management stays local unless shared state is proven necessary
(no premature global store).

### 6. Testing Standards
- Backend: `pytest` for API, WebSocket, and strategy/business logic.
- Frontend: critical user flows covered; Playwright required for UI parity (§12).
- No PR merges without passing tests **and** the typing gate (§19).
- New domain classes MUST ship with a unit test unless the class is a pure data
  container (Pydantic model / frozen dataclass) or an exchange adapter shim with
  no logic beyond delegating to ccxt.

### 7. Performance Budget
WebSocket payloads stay minimal — deltas, not full-state resends, where feasible.
Bundle size budget: keep the React production build under **500 KB gzipped**
per entry chunk. If a chunk exceeds it, split the route or lazy-load heavy deps.
No placeholder values in principles — replace budgets with real numbers when
measuring.

### 8. No Dead Code — Deletion Mandate
**Replaces** the historical "keep scratchpads" stance. Unused endpoints,
components, dead functions, commented-out logic, and stale experimental files
MUST be removed in the same change that removes their last caller or in a
dedicated cleanup pass. Do not leave them "for later." See §21 and
`.cursor/rules/compact-code.mdc`.

### 9. E2E Testing
All end-to-end tests written in Python using Playwright. No manual-only
verification for UI features. Reinforced by §10 and §14.

### 10. Feature Definition of Done
A UI feature is NOT complete based on visual/static review alone. It must be
verified functionally in a real browser: backend running, real data received,
user interactions triggering real state changes end-to-end. Screenshots or
component-in-isolation checks do not satisfy this gate.

### 11. Data Flow — WebSocket First, REST as Fallback
**General rule**: use WebSocket wherever the channel exists; use REST only where
WebSocket is not viable. This applies at every layer:

**Browser → FastAPI (UI layer):**
React receives all application data exclusively via WebSocket (`presentation/ws/`).
REST is allowed only for:
- Authentication (login, token issuance/refresh).
- File upload (binary/multipart).
Any other data — application state, entities, live updates — MUST flow through
WebSocket. A new REST endpoint outside these two exceptions is a constitutional
violation and must be flagged during planning.

**Backend → Exchange (exchange adapter layer, §18):**
Exchange data uses `ccxt.pro` `watch_*` WebSocket methods as the priority path.
REST `fetch_*` is a fallback used only when:
- The exchange lacks the matching `watch_*` capability, or
- The operation is inherently request/response (`set_leverage`, place/close order,
  one-shot fee lookup).

These two scopes are independent: §11 governs browser↔FastAPI; §18 governs
backend↔exchange. Tactical detail: `.cursor/rules/exchange-data.mdc`,
`.cursor/rules/fastapi-presentation.mdc`.

### 12. 100% UI Parity (React Migration, Non-Negotiable)
When migrating the legacy vanilla JS/HTML UI under
`src/arbitrator/presentation/static/` to the React UI under
`src/arbitrator/presentation/react-ui/`, the new UI MUST have 100% functional
and visual parity with the legacy UI at the moment of migration. Every
element, column, button, number, percentage, and widget transfers one-to-one.
Any deviation from the legacy UI's visual output or data representation
requires explicit user approval.
**Legacy UI must remain buildable and served** when `use_react_frontend=false`
(`scripts/build_ui.py` continues to work; partials stay under
`presentation/static/partials/`). Tactical detail: `.cursor/rules/ui-templates.mdc`,
`.cursor/rules/opportunity-ui.mdc`.

### 13. Code Quality & Formatting Strictness
All React components MUST utilize the central `utils/format.ts` utilities
(replicating the legacy `static/js/render/format.js` logic) for rendering
numerical data: consistent rounding, empty/null handling (render as `—`),
mandatory signs for PnL/percentages, and precise color-coding CSS classes
(`.pos`, `.neg`, `.na`). No inline or ad-hoc formatting.

### 14. Real-World Backend Validation
Agents working on UI features MUST NEVER assume a component works because it
compiles or renders with static mock data. Before declaring a feature
complete, the agent MUST run the full backend (`scripts/run_app.py`) and use
Playwright to verify the UI correctly receives, parses, and renders live data
(especially WebSocket streams) without crashing.

### 15. Trading Safety (Non-Negotiable)
No code that places, amends, or cancels orders (`create_order`,
`cancel_order`, `open_market_position`, `close_market_position`), modifies
leverage (`set_leverage`), or otherwise exposes the user's capital to risk
MAY be introduced or executed without **explicit user approval**. This applies
to:
- New trading features — must surface in spec and plan and be flagged.
- Auto-trader runs in `live` mode — must be opt-in via `Settings`.
- Any agent-initiated trading action across the application/exchange boundary.
Auto-trading in `mock_data` and `paper` modes is allowed without per-call
approval but still requires `Settings.arb_auto_open_enabled = true`. Diagnostics
must use the read-only scripts — see `.cursor/rules/exchange-data.mdc` and the
skill `.cursor/skills/exchange-read-only-inspect/`.

### 16. Market Universes — USDT-M Perp + USDT Spot
The project operates in **two market universes**:
1. **USDT-margined perpetual futures** — symbols use `BASE/USDT:USDT`
   (e.g. `BTC/USDT:USDT`); ccxt `options.defaultType = "swap"`
   (read from `Settings.default_type`).
2. **USDT spot** — symbols use `BASE/USDT` (e.g. `BTC/USDT`); ccxt
   `options.defaultType = "spot"` (read from `Settings.spot_default_type`).
Each strategy kind declares which universe(s) it operates in (see
`src/arbitrator/domain/strategy/strategy_kind.py` — e.g. `futures_futures`,
`futures_spot_2ex`, `futures_spot_1ex`, `funding_fs`). Spot support is
**opt-in via configuration** (strategy selection in `StrategyUIConfig`, React UI
toggle). It MAY be disabled entirely without affecting perp behavior. A new exchange
MUST: live in its own file under `exchanges/`, inherit `CcxtBase`, set
`exchange_id` + `display_name` (`ClassVar[str]`), override `_create_client`
with the universe's default type, and register in `Factory._registry`. Do not
load coin-M (inverse) futures or options. Tactical detail:
`.cursor/rules/architecture.mdc` §7.

### 17. Configuration Single Source of Truth
All runtime parameters live in `src/arbitrator/config/settings.py` in a single
frozen `Settings` class (`pydantic_settings.BaseSettings`, var `frozen=True`).
No hardcoded magic values. Adding a runtime parameter:
1. Add a typed field with a sensible default.
2. Add the matching `KEY=value` line to `.env.example`.
3. Inject it through the constructor chain. Do not read environment variables
   anywhere else. Agents never read the `.env` file raw — only via `Settings`.
**Exception — trading/strategy logic parameters** (thresholds that are tuned
per-strategy from the UI, not environment-bound): these live in
`StrategyUIConfig` (`src/arbitrator/config/ui_config.py`) and are surfaced via
`STRATEGY_META` in the React UI's `settings.js`. The rule of thumb:
- Environment / deployment-bound → `Settings`.
- User-tunable strategy knob → `StrategyUIConfig`.
Tactical detail: `.cursor/rules/architecture.mdc` §6.

### 18. Async-First
I/O-bound work uses `asyncio`. Exchange WebSocket vs REST fallback rules are
defined in §11 (WebSocket First). Always close async resources in `finally` or
via `async with`. Streams must be implementable as async generators. The
**browser** never calls exchange REST directly — see §11 and
`.cursor/rules/exchange-data.mdc`.

### 19. Static Typing Gate
- `mypy --strict src/arbitrator` MUST pass with zero errors.
- `ruff check src tests` MUST pass.
- **Never use `typing.Any`** — use `object` + `isinstance`, generics, or
  unions. Even temporary `Any` is forbidden.
- Put `from __future__ import annotations` at the top of every Python module.
- Public methods MUST be fully annotated on parameters and return.
- Frontend: TypeScript in strict mode; no `any` (use `unknown`), no loose
  equality (`===` / `!==` only), `const` over `let`, `interface` over `type`
  when interface suffices.
These gates are prereqs for the test gate in §6. Tactical detail:
`.cursor/rules/architecture.mdc` §4, `.cursor/rules/tooling.mdc`.

### 20. Structured Logging
- Never use `print()` in application code (`src/`, `main.py`, project scripts).
- Never use stdlib `logging.getLogger(...)`. Always import the singleton:
  `from arbitrator.config.logger import logger`.
- Use positional `{}` placeholders, never f-strings (Loguru lazy-formats):
  `logger.info("msg | key={} other={}", value, other)`.
- In `except` blocks: `logger.exception("static message | ctx={}", x)` —
  **always log the full exception**, never `str(error)` or `error.message`.
- Static error messages with context passed separately — supports aggregation.
Tactical detail: `.cursor/rules/logging.mdc`.

### 21. Dead Code Removal
When deleting code, ask "Will deleting this break anything?" If the answer is
no, delete it. Dead functions, commented-out logic, unused imports, stale
scratchpads, and experimental files whose last caller is gone MUST be removed
in the same change. This principle **deprecates and overrides**
`.cursor/rules/preserve-code.mdc`. The only thing kept "for reference" is the
git history. Tactical detail: `.cursor/rules/compact-code.mdc`.

## Feature Development Gate

Large updates and new features MUST go through the **Superpowers** process:
`brainstorming` → design in `docs/superpowers/specs/` → `writing-plans` →
plan in `docs/superpowers/plans/` → implement / verify. See
`.cursor/rules/feature-development.mdc` for the workflow.

**Do not** create new Spec Kit feature trees (`specs/NNN-*/`) or run
`/speckit-*` for new work. Existing `specs/**` artifacts are historical
reference only.

**What counts as "large" is agent-judged** against the following signals. If
any one is true, use Superpowers design + plan; if none, inline edits are
acceptable:

- New public WebSocket message type or new `/ws/*` route.
- New page or top-level UI surface in the React app.
- New strategy kind added to `StrategyKind`, or a new exchange adapter
  registered in `Factory._registry`.
- New persistence entity (new JSON file under `src/arbitrator/data/`) with its
  own repository.
- Cross-layer change touching `domain/` + `application/` + `presentation/`
  simultaneously.
- New independent package/core or process-wide startup mode switch.
- Anything that risks capital (touches order placement, leverage, liquidation
  guards) — regardless of size, also subject to §15.

**Explicit override**: a user explicitly saying "just fix it inline" overrides
the gate downward — except for §15 (Trading Safety), which is non-negotiable.

## UI & Feature Migration Constraints

The legacy frontend (`src/arbitrator/presentation/static/`) MUST remain
completely intact and buildable during the React migration. The system MUST
support serving either implementation conditionally based on
`Settings.use_react_frontend`. The frontend is served via FastAPI. Launch
goes through `scripts/run_app.py`, which handles the lifecycle (install, build,
serve) of the configured frontend before starting the main app.

## Governance

This Constitution is the **single source of truth for project principles**.
Where a `.cursor/rules/*.mdc` file expands on a principle tactically, that
file is authoritative for *how*; this document is authoritative for *why* and
for the principle itself. If the two diverge, the constitution wins and the
rule file must be brought back into alignment (see
`.cursor/rules/documentation-sync.mdc`).

`CLAUDE.md` is a thin pointer: project commands, agent workflow shortcuts, and
"read the constitution + relevant `.cursor/rules/*.mdc`". It MUST NOT
re-state principles that already live here.

Superpowers design and plan documents MUST be checked against these
principles before implementation. Plans MUST explicitly verify compliance
with Trading Safety (§15), Markets (§16), Configuration (§17), Async (§18),
Typing Gate (§19), Logging (§20), and UI Parity (§12) where applicable.

Amendments require justification and a version bump per semantic versioning:
MAJOR for breaking governance changes, MINOR for new principles, PATCH for
clarifications. Any principle change requires updating this file with a
version bump, a Sync Impact Report at the top, and propagation to the
`.cursor/rules/*.mdc` files it references.

**Version**: 1.5.0 | **Ratified**: 2026-07-14 | **Last Amended**: 2026-08-03
