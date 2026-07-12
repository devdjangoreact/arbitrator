# Implementation Plan: React Frontend Architecture

## Technical Context

**Current Architecture:**
- Backend: FastAPI serving static files from `src/arbitrator/presentation/static`.
- Configuration: `src/arbitrator/config/settings.py`.
- Launch: Custom scripts or direct `uvicorn main:app` invocation.

**New Architecture:**
- Tech Stack: React, Vite, pnpm.
- Location: `src/arbitrator/presentation/react-ui`.
- Integration: FastAPI `StaticFiles` mounting conditional on `USE_REACT_FRONTEND` in `settings.py`.
- Launch: Unified Python script (`scripts/run_app.py`) managing `pnpm` lifecycle and FastAPI.

**Unknowns/Clarifications:**
- None. The scope is strictly limited to architectural setup. Functional UI porting is explicitly out of scope for this phase.

## Constitution Check

- **Preserve existing functionality:** Yes, legacy UI is preserved and toggleable.
- **Maintainability:** Yes, Vite + React provides a modern, maintainable frontend structure.
- **Security:** N/A (No new authentication/authorization logic introduced in this architectural phase).

## Implementation Phases

**Phase 1: Foundation (Current Plan)**
- Create React app skeleton using Vite.
- Implement configuration toggle in `settings.py`.
- Update FastAPI routing to serve the correct static directory.
- Create automated launch script.

**Phase 2: Functional Porting (Future Plan)**
- *Out of scope for this task.*

