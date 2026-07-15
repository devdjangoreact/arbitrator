# Research: React Frontend Architecture

## Decision: Frontend Build Tool
**Decision**: Vite.
**Rationale**: Explicitly requested by user. Vite offers significantly faster development server start times and hot module replacement (HMR) compared to traditional bundlers like Webpack or Create React App, making it the modern standard for React applications.

## Decision: Package Manager
**Decision**: pnpm.
**Rationale**: Explicitly requested by user. `pnpm` is faster and more disk-efficient than `npm` or `yarn` due to its global store and symlinking strategy.

## Decision: FastAPI Integration Strategy
**Decision**: Conditional `StaticFiles` mounting.
**Rationale**: FastAPI's `StaticFiles` is the standard way to serve single-page applications (SPAs). By reading `USE_REACT_FRONTEND` from settings at startup, we can conditionally mount either `src/arbitrator/presentation/static` or `src/arbitrator/presentation/react-ui/dist` to the root path `/`.

## Decision: Launch Script
**Decision**: A dedicated Python script `scripts/run_app.py`.
**Rationale**: To fulfill the single command launch requirement, we need a script that can read the Python configuration (`settings.py`), execute shell commands (`pnpm install && pnpm build` via `subprocess`), and then start the ASGI server (`uvicorn`).
