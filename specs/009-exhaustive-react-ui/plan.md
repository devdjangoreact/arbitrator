# Implementation Plan: Exhaustive React UI Parity

**Branch**: `009-exhaustive-react-ui` | **Date**: 2026-07-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/009-exhaustive-react-ui/spec.md`

## Summary

Migrate the legacy Vanilla JS/HTML static UI to a modern React + Vite application while maintaining 100% functional and visual parity. This includes exact formatting replication, implementation of complex data tables (Screener, Monitors, Orders), action buttons (Copy to Form, Fast Trade), and real-time charting (Opportunity Chart). Playwright will be used to ensure visual regression testing confirms identical outputs.

## Technical Context

**Language/Version**: TypeScript, Node.js 18+

**Primary Dependencies**: React 18, Vite, `recharts` (for Opportunity Chart), Playwright (for testing)

**Storage**: Local State Management (React Context or Zustand depending on complexity of `live_state` from websockets)

**Testing**: Playwright (E2E/Visual Regression)

**Target Platform**: Web Browser (Chrome, Firefox, Safari)

**Project Type**: SPA (Single Page Application) frontend communicating via WebSocket and REST to a FastAPI backend.

**Performance Goals**: Sub-100ms render updates for high-frequency websocket messages (e.g. `screener.delta`, `msg.data.live_state`).

**Constraints**: Must match legacy UI formatting pixel-perfectly. Must handle WebSocket disconnects/reconnects gracefully.

**Scale/Scope**: ~10 screens/complex components, high real-time data throughput.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Rule 0/Formatting**: The plan mandates a centralized `utils/format.ts` to enforce the strict formatting rules outlined in the spec.
- **Visual Verification**: The plan integrates Playwright for automated visual regression to satisfy the `feedback_ui_mcp_playwright.md` memory rule.

*(Passes all gates. Moving to Phase 0).*

## Project Structure

### Documentation (this feature)

```text
specs/009-exhaustive-react-ui/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command)
```

### Source Code (repository root)

```text
src/arbitrator/presentation/react-ui/
├── src/
│   ├── components/      # Reusable UI parts (LiveMonitorCard, Tables)
│   ├── pages/           # Main views (Settings, Screener, Opportunity, Monitors)
│   ├── utils/           # format.ts (CRITICAL for parity)
│   ├── hooks/           # useWebsocket, useSettings
│   ├── store/           # Global state (if needed for active monitors)
│   ├── App.tsx          # Router & Layout
│   └── index.css        # Global styles mapping legacy CSS vars
└── tests/
    └── e2e/             # Playwright visual regression tests
```

**Structure Decision**: A standard Vite React SPA structure nested within the existing backend repo path. Focus is placed on a robust `utils/format.ts` and `components` directory to match the legacy modular JS files.

## Phase 0: Outline & Research

*(Since there are no "NEEDS CLARIFICATION" tags and the tech stack is well-understood (React, Vite, Recharts, Playwright), a formal `research.md` is minimal, focusing only on the specific charting library choice to ensure it meets the real-time requirements of the Opportunity Chart.)*

## Phase 1: Design & Contracts

*(Moving to generate `research.md`, `data-model.md`, `contracts/`, and `quickstart.md`)*