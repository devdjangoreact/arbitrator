# UX + Data Wiring Checklist: LiveMonitorCard Bug Fix (Phase 13)

**Purpose**: Validate requirement quality for FR-026/027/028 and FR-011 wiring before implementing T061–T067
**Created**: 2026-07-16
**Feature**: [spec.md](../spec.md) — Phase 13, T061–T067

## Requirement Completeness

- [x] CHK001 — Are all 29 FR-011 fields listed with their null-fallback behavior ("—") explicitly documented for every field, or only generically stated? [Completeness, Spec FR-011] — FR-011 lists all fields + "display '—' when absent or null" covers all generically
- [x] CHK002 — Is the condition under which `liveState[config.id]` is populated at card creation time (vs. first push) specified? [Completeness, Gap — T061 root cause] — FR-010 guarantees composite key contract; T061 handles timing
- [x] CHK003 — Are requirements defined for what the card displays when the WS connection is established but no push has arrived yet (zero-state)? [Completeness, Edge Case] — FR-011 null-fallback ("—") covers zero-state

## Requirement Clarity

- [x] CHK004 — Is "~70% of screen width" in FR-026 quantified as a specific CSS unit (`70vw`) or left ambiguous? [Clarity, Spec FR-026] — Intentionally approximate; T066 implements as `70vw`
- [x] CHK005 — Is "pulsing green dot" in FR-027 described with specific visual properties (size, animation duration, color hex), or only functionally? [Clarity, Spec FR-027] — Functional spec; Tailwind `animate-pulse` is implementation detail in T063
- [x] CHK006 — Does FR-013 clearly distinguish between `SpreadChart` (two spread lines in card) and `SpreadHistoryModal` (price + spread diff charts), or are they conflated? [Clarity, Spec FR-013] — FR-013 = SpreadChart; clarifications section explicitly describes SpreadHistoryModal as three canvas charts

## Requirement Consistency

- [x] CHK007 — Are SC-004 and SC-008 consistent — SC-004 says "within one push cycle", SC-008 also says "within one push cycle"; do they refer to the same trigger or different? [Consistency, Spec SC-004/SC-008] — Same trigger, complementary phrasing (SC-004 general, SC-008 enumerates specific fields)
- [x] CHK008 — Does FR-014 (editable params send `update_config`) and FR-028 (`adjustment_mode` sends `update_config`) use the same command protocol and payload shape consistently? [Consistency, Spec FR-014/FR-028] — Both use `update_config` with same payload shape

## Scenario Coverage

- [x] CHK009 — Are requirements defined for `adjustment_mode` behavior when the backend is unavailable (optimistic UI update vs. wait for confirmation)? [Coverage, Gap — FR-028] — FR-024 guarantees backend continuity; optimistic UI not needed; next push confirms
- [x] CHK010 — Is the "restarting" visual state of the card (FR-015 mentions it) specified with the same detail as active/stopped in FR-027? [Coverage, Gap — FR-015/FR-027] — FR-015 states "restarting state visually"; T063 can add spinner; acceptable for implementation

## Acceptance Criteria Quality

- [x] CHK011 — Can SC-010 ("SpreadChart accumulates ≥1 visible data point per 5s push cycle") be objectively verified — is "visible" defined (minimum pixel height, non-zero Y range)? [Measurability, Spec SC-010] — "Visible" = non-empty chart with non-zero Y range; standard canvas rendering
- [x] CHK012 — Is SC-011 ("no internal scrollbar") testable without ambiguity — does it apply at all zoom levels or only at 100%? [Measurability, Spec SC-011] — SC-011 explicitly states "viewport height ≥ 600 px"; 100% zoom implied

## Dependencies & Assumptions

- [x] CHK013 — Is the assumption that `config.id` = `"symbol:short_exchange:long_exchange"` validated as a guaranteed contract from the backend, or only assumed by the frontend? [Assumption, Spec FR-010/T061] — FR-010 explicitly states `live_state` keyed by composite key — guaranteed backend contract
