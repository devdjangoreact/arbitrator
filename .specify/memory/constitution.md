<!--
Sync Impact Report
Version change: 1.3.1
Modified principles: Principle 11 (Data Flow) - clarified exceptions for REST.
Added sections: None
Removed sections: None
Templates requiring updates: plan-template.md
Follow-up TODOs: None.
-->
# Arbitrator Constitution

## Project Stack
FastAPI backend with WebSocket support for real-time communication, React + Vite frontend, Tailwind CSS for styling. Python 3.11+, TypeScript on frontend.

## Core Principles

### 1. Simplicity First
Favor the simplest solution that meets requirements. No premature abstraction, no unused config layers.

### 2. API Contract Discipline
All REST endpoints defined with Pydantic models for request/response validation. WebSocket messages use a typed schema (Pydantic or TypedDict) with explicit message type field, no free-form JSON.

### 3. Real-Time Reliability
WebSocket connections must handle reconnect/disconnect gracefully; no silent message loss. Backend must support broadcasting to multiple clients without blocking the event loop.

### 4. Frontend Consistency
All UI built with Tailwind utility classes, no inline styles, no CSS-in-JS. Shared design tokens (colors, spacing) defined once in `tailwind.config`.

### 5. Component Architecture
React components are functional, typed with TypeScript, no class components. State management stays local unless shared state is proven necessary (no premature global store).

### 6. Testing Standards
Backend: pytest for API and WebSocket logic. Frontend: at minimum, critical user flows covered. No PR merges without passing tests. (Supersedes previous Playwright-only mandate, though Playwright is still required for 100% UI parity).

### 7. Performance Budget
WebSocket message payloads stay minimal (no full-state resends on every update, only deltas where feasible). Vite build stays under [X]MB bundle size.

### 8. No Dead Code
Unused endpoints, components, or config removed immediately, not left "for later."

### 9. E2E Testing
All end-to-end tests written in Python using Playwright. No manual-only verification.

### 10. Feature Definition of Done
A UI feature is NOT considered complete based on visual/static review alone. It must be verified functionally in a real browser: backend running, real data received from backend, user interactions triggering real state changes end-to-end. Screenshot-only or component-in-isolation checks do not satisfy this gate.

### 11. Data Flow
React receives all application data exclusively via WebSocket. REST is used only where WebSocket is not viable:
- Authentication (login, token issuance/refresh) — stateless HTTP semantics required for standard auth flows.
- File upload — binary/multipart transfer not suited to WebSocket message framing.
All other data — application state, entities, live updates — MUST flow through WebSocket only. No REST endpoints for fetching or mutating domain data. Any new REST endpoint outside these two exceptions is a constitutional violation and must be flagged in Complexity Tracking during /speckit-plan.

### 12. 100% UI Parity (Non-Negotiable)
When migrating from the legacy Vanilla JS/HTML UI to the new React UI, the output MUST have 100% functional and visual parity. Every element, column, button, number, percentage, and widget must be transferred "one-to-one". Any deviation from the legacy UI's visual output or data representation requires explicit user approval.

### 13. Code Quality & Formatting Strictness
All React components MUST utilize the central `utils/format.ts` utilities (replicating the legacy `format.js` logic) for rendering numerical data. This ensures consistent rounding, handling of empty/null values (e.g., rendering as `—`), mandatory signs for PnL/percentages, and precise color-coding CSS classes (`.pos`, `.neg`, `.na`). No inline or ad-hoc formatting is permitted.

### 14. Real-World Backend Validation (Always Check with Backend)
Agents working on UI features MUST NEVER assume a component works just because it compiles or renders with static mock data. Before declaring a feature complete, the agent MUST run the full backend (`scripts/run_app.py`) and use Playwright to verify that the UI correctly receives, parses, and renders live data (especially WebSocket streams) without crashing (e.g., "white screen of death" from undefined properties like `row.profits.futures_futures`).

## UI & Feature Migration Constraints

The legacy frontend implementation (`src/arbitrator/presentation/static`) MUST remain completely intact and unmodified during the introduction of the new frontend. The system MUST support serving both implementations conditionally based on configuration (`USE_REACT_FRONTEND`).

The frontend is served via a FastAPI backend. The integration MUST use unified launch scripts (`scripts/run_app.py`) that handle the lifecycle (dependencies, build, serve) of the configured frontend before starting the main application server, ensuring a seamless developer and operator experience.

## Governance

This Constitution supersedes all other project practices. All Spec Kit artifacts (`spec.md`, `plan.md`, `tasks.md`) MUST be checked against these principles during the `/speckit-analyze` and `/speckit-plan` phases. Specifically, the "Constitution Check" gate in `plan.md` MUST explicitly verify compliance with the UI parity and Playwright testing mandates.

Amendments to this constitution require justification and a version bump according to semantic versioning (MAJOR for breaking governance changes, MINOR for new principles, PATCH for clarifications). Any principle change requires updating this file with a version bump and propagation to plan/spec/tasks templates.

**Version**: 1.3.1 | **Ratified**: 2026-07-14 | **Last Amended**: 2026-07-14