---
description: "Task list template for feature implementation"
---

# Tasks: Exhaustive React UI Parity

**Input**: Design documents from `/specs/009-exhaustive-react-ui/`

**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: Playwright tests are REQUIRED to ensure visual parity.

**Organization**: Tasks are grouped by user story (in this case, UI page/module) to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Exact file paths are provided.

## Path Conventions

- All work is within `src/arbitrator/presentation/react-ui/`
- Component paths: `src/components/`
- Page paths: `src/pages/`
- Utils: `src/utils/`
- Tests: `tests/e2e/`

---

## Phase 1: Setup & Foundational

**Purpose**: Core infrastructure that MUST be complete before ANY UI page can be implemented. Crucially, the formatting logic must be rock-solid.

**⚠️ CRITICAL**: No UI page work can begin until this phase is complete.

- [ ] T001 Implement core formatting utilities in `src/arbitrator/presentation/react-ui/src/utils/format.ts`
- [ ] T002 [P] Implement unit tests for formatting utilities in `src/arbitrator/presentation/react-ui/tests/unit/format.test.ts`
- [ ] T003 [P] Define TypeScript interfaces from `data-model.md` in `src/arbitrator/presentation/react-ui/src/types/index.ts`
- [ ] T004 Define core CSS classes (`.pos`, `.neg`, `.na`) reflecting legacy styles in `src/arbitrator/presentation/react-ui/src/index.css`
- [ ] T005 Create baseline Playwright configuration for visual regression in `src/arbitrator/presentation/react-ui/playwright.config.ts`

**Checkpoint**: Foundation ready - Formatting logic is unit-tested and type definitions are available.

---

## Phase 2: User Story 1 - Settings Page (Priority: P1) 🎯 MVP

**Goal**: Migrate the Settings page, allowing API key management and complex strategy configuration (including JSON textareas).

**Independent Test**: Visually compare the rendered Settings page against the legacy UI. Modify an API key and strategy parameter and verify WebSocket/REST payloads.

### Tests for Settings Page

- [ ] T006 [P] [US1] Create Playwright visual parity test for Settings page in `src/arbitrator/presentation/react-ui/tests/e2e/settings-parity.spec.ts`

### Implementation for Settings Page

- [ ] T007 [US1] Create `ExchangeKeyForm` component in `src/arbitrator/presentation/react-ui/src/components/ExchangeKeyForm.tsx`
- [ ] T008 [P] [US1] Create `StrategyConfigPanel` component (handling tabs/categories) in `src/arbitrator/presentation/react-ui/src/components/StrategyConfigPanel.tsx`
- [ ] T009 [P] [US1] Create `JsonEditorTextarea` component in `src/arbitrator/presentation/react-ui/src/components/JsonEditorTextarea.tsx`
- [ ] T010 [US1] Assemble `SettingsPage` integrating the above components and API logic in `src/arbitrator/presentation/react-ui/src/pages/SettingsPage.tsx`

**Checkpoint**: Settings page is functional, visual parity confirmed via Playwright.

---

## Phase 3: User Story 2 - Live Screener Page (Priority: P1)

**Goal**: Migrate the Screener data table with high-frequency updates and exact formatting (`.pos`, `.neg`).

**Independent Test**: Visually compare the data table against the legacy UI under active WebSocket load.

### Tests for Live Screener

- [ ] T011 [P] [US2] Create Playwright visual parity test for Screener page in `src/arbitrator/presentation/react-ui/tests/e2e/screener-parity.spec.ts`

### Implementation for Live Screener

- [ ] T012 [US2] Create `ScreenerFilterPanel` component in `src/arbitrator/presentation/react-ui/src/components/ScreenerFilterPanel.tsx`
- [ ] T013 [P] [US2] Create `ScreenerDataTable` component enforcing `table-layout: auto` and strict formatting in `src/arbitrator/presentation/react-ui/src/components/ScreenerDataTable.tsx`
- [ ] T014 [US2] Assemble `ScreenerPage` handling WebSocket `screener.snapshot` and `screener.delta` in `src/arbitrator/presentation/react-ui/src/pages/ScreenerPage.tsx`

**Checkpoint**: Screener page renders live data perfectly formatted.

---

## Phase 4: User Story 3 - Opportunity Page (Priority: P2)

**Goal**: Migrate the detailed analysis view, including Order Books, Strategy Table (with action buttons), and the critical Opportunity Chart.

**Independent Test**: Open an opportunity, verify the chart renders correctly using `recharts`, and action buttons are present.

### Tests for Opportunity Page

- [ ] T015 [P] [US3] Create Playwright visual parity test for Opportunity page in `src/arbitrator/presentation/react-ui/tests/e2e/opportunity-parity.spec.ts`

### Implementation for Opportunity Page

- [ ] T016 [US3] Implement `OpportunityChart` using `recharts` in `src/arbitrator/presentation/react-ui/src/components/OpportunityChart.tsx`
- [ ] T017 [P] [US3] Implement `StrategyCalculationsTable` with execution buttons in `src/arbitrator/presentation/react-ui/src/components/StrategyCalculationsTable.tsx`
- [ ] T018 [P] [US3] Implement `OrderBookCard` component in `src/arbitrator/presentation/react-ui/src/components/OrderBookCard.tsx`
- [ ] T019 [US3] Assemble `OpportunityPage` in `src/arbitrator/presentation/react-ui/src/pages/OpportunityPage.tsx`

**Checkpoint**: Opportunity page displays all components, including the new chart.

---

## Phase 5: User Story 4 - Orders & Paper Trades (Priority: P2)

**Goal**: Migrate the grouped orders table with expandable legs and summary panels.

**Independent Test**: Expand/collapse order groups and verify PnL/Funding calculations are colored correctly. Ensure filters (All/Open/Closed) work.

### Tests for Orders Page

- [ ] T020 [P] [US4] Create Playwright visual parity test for Orders page in `src/arbitrator/presentation/react-ui/tests/e2e/orders-parity.spec.ts`

### Implementation for Orders Page

- [ ] T021 [US4] Implement `OrdersSummaryPanel` (with functional filters) in `src/arbitrator/presentation/react-ui/src/components/OrdersSummaryPanel.tsx`
- [ ] T022 [P] [US4] Implement `OrderGroupRow` and `OrderLegRow` components in `src/arbitrator/presentation/react-ui/src/components/OrderRow.tsx`
- [ ] T023 [US4] Assemble `OrdersPage` in `src/arbitrator/presentation/react-ui/src/pages/OrdersPage.tsx`

**Checkpoint**: Orders page correctly groups and formats historical trade data.

---

## Phase 6: User Story 5 - Historical Monitors & Live Cards (Priority: P3)

**Goal**: Migrate the most complex module: the historical table with "Copy to Form"/"Fast Trade" buttons, and the active CSS Grid of `LiveMonitorCard`s.

**Independent Test**: Click "Fast Trade" on an opportunity and verify a new `LiveMonitorCard` appears in the grid and sends the start command via WebSocket.

### Tests for Monitors Page

- [ ] T024 [P] [US5] Create Playwright visual parity test for Monitors page in `src/arbitrator/presentation/react-ui/tests/e2e/monitors-parity.spec.ts`

### Implementation for Monitors Page

- [ ] T025 [US5] Implement `HistoricalScreenerTable` with Action buttons in `src/arbitrator/presentation/react-ui/src/components/HistoricalScreenerTable.tsx`
- [ ] T026 [P] [US5] Implement the complex `LiveMonitorCard` with all inputs, validation, and mini-charts in `src/arbitrator/presentation/react-ui/src/components/LiveMonitorCard.tsx`
- [ ] T027 [US5] Assemble `MonitorsPage` managing the CSS grid of active cards and historical table in `src/arbitrator/presentation/react-ui/src/pages/MonitorsPage.tsx`

**Checkpoint**: The most complex page is functional and matches the legacy layout.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Routing, final integration, and validation.

- [ ] T028 Update `App.tsx` with React Router to navigate between the newly created pages.
- [ ] T029 Execute full visual regression suite (`npx playwright test`) and fix any remaining pixel deviations across all components.
- [ ] T030 Perform manual QA of `quickstart.md` scenarios 1, 2, and 3.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Must complete first. Formatting is the bedrock.
- **User Stories (Phases 2-6)**: Can technically proceed in parallel once Phase 1 is done, but recommended to do Settings and Screener first to validate core formatting and WS logic.
- **Polish (Phase 7)**: Depends on all pages being complete.

### Parallel Opportunities

- After Phase 1, different developers can tackle different pages (e.g., Dev A on Screener, Dev B on Orders).
- Within a story, Playwright tests (`.spec.ts`) and child components (e.g., `OpportunityChart` vs `OrderBookCard`) can be developed in parallel.