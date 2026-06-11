# Tasks: Arbitrator Streamlit app migration & containerization

**Feature**: `001-arbitrator-streamlit-migration` | **Plan**: [plan.md](./plan.md)

## Phase 1: Migration (US1)

- [X] T001 Create feature branch `001-arbitrator-streamlit-migration` in the submodule.
- [X] T002 Remove the static placeholder (`index.html`) from the app-repo.
- [X] T003 Copy the Arbitrator source into the submodule, excluding `.venv`, caches, `logs/`, and `.env`; keep `.git` and `.github/workflows/build.yml`.

## Phase 2: Production image (US1)

- [X] T004 Write multi-stage production `Dockerfile` (Poetry builder + runtime, Streamlit on port 80, health check).
- [X] T005 Write `.dockerignore` excluding venv/caches/secrets/docs from the build context.

## Phase 3: Development stack (US2)

- [X] T006 Write `Dockerfile.dev` (dev dependencies, hot reload, port 8501).
- [X] T007 Write `docker-compose.dev.yml` (bind-mount `src/` and `main.py`, optional `.env`, port 8501).

## Phase 4: Spec-kit integration (FR-006)

- [X] T008 Copy `.specify/` engine and spec-kit skills into the submodule.
- [X] T009 Add the always-use-spec-kit rule and a project `specify-rules.mdc`.
- [X] T010 Record this feature under `specs/001-arbitrator-streamlit-migration/`.

## Phase 5: Docs & validation

- [ ] T011 Rewrite `README.md` for the Streamlit app, Docker dev/prod usage, and deploy contract.
- [ ] T012 Validate `docker compose -f docker-compose.dev.yml config` and commit on the feature branch.
