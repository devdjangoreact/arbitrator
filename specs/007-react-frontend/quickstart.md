# Quickstart: React Frontend Architecture

## Prerequisites

1. Node.js (v18+ recommended)
2. pnpm installed globally (`npm install -g pnpm`)
3. Python environment setup as per `CLAUDE.md`.

## Setup and Validation

**Scenario 1: Running the Legacy Frontend (Default)**

1. Ensure `.env` (if used) does not set `USE_REACT_FRONTEND=True`, or ensure `settings.py` defaults to `False`.
2. Run the launch script:
   ```bash
   .venv\Scripts\python.exe scripts/run_app.py
   ```
3. Open a browser to `http://localhost:8000`.
4. Verify the original Vanilla JS/HTML UI loads.
5. Notice in the console output that no `pnpm` build steps were executed.

**Scenario 2: Running the Modern React Frontend**

1. Set `USE_REACT_FRONTEND=True` (either in `.env` or hardcoded in `settings.py` for testing).
2. Run the launch script:
   ```bash
   .venv\Scripts\python.exe scripts/run_app.py
   ```
3. Observe the console output. You should see `pnpm install` and `pnpm build` executing in the `src/arbitrator/presentation/react-ui` directory.
4. Once the server starts, open a browser to `http://localhost:8000`.
5. Verify the new React (Vite default "Hello World") UI loads instead of the legacy UI.
