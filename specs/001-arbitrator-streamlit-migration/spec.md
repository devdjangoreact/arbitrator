# Feature Specification: Arbitrator Streamlit app migration & containerization

**Feature Branch**: `001-arbitrator-streamlit-migration`

**Created**: 2026-06-12

**Status**: Draft

**Input**: Migrate the standalone Arbitrator Streamlit project into this app-repo,
replacing the previous static placeholder, and provide Docker images for local
development and production deployment.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Run the Arbitrator UI in production (Priority: P1)

A visitor opens the project's public domain and sees the live Arbitrator
Streamlit dashboard (screener, orders, settings) served over HTTPS.

**Why this priority**: This is the reason the app-repo exists; without it the
domain serves nothing useful.

**Independent Test**: Build the production image and run it; the Streamlit app
responds on container port 80 and its health endpoint returns `ok`.

**Acceptance Scenarios**:

1. **Given** the production `Dockerfile`, **When** the image is built and run, **Then** Streamlit serves the app on port 80 and `/_stcore/health` returns `ok`.
2. **Given** a push to `main`, **When** the build workflow runs, **Then** the image is published to ECR Public and a `deploy` dispatch is sent to the infra-repo.

---

### User Story 2 - Develop locally with hot reload (Priority: P2)

A developer runs the app locally in a container, edits source files, and sees
changes reload automatically without rebuilding the image.

**Why this priority**: Fast feedback loop for ongoing development.

**Independent Test**: `docker compose -f docker-compose.dev.yml up --build`
serves the app on `http://localhost:8501` and reloads on source edits.

**Acceptance Scenarios**:

1. **Given** the dev compose stack is up, **When** a source file under `src/` changes, **Then** Streamlit reloads the app automatically.

---

### Edge Cases

- Missing `.env`: the app falls back to `Settings` defaults and still starts.
- Port 80 is privileged: the production container runs the Streamlit process as
  root so it can bind port 80, matching the infra Traefik service label.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST contain the full Arbitrator Streamlit source (`src/arbitrator`, `main.py`, Poetry config), replacing the prior static placeholder.
- **FR-002**: A production `Dockerfile` MUST build an image that serves the Streamlit app on container port 80.
- **FR-003**: A development Docker setup (`Dockerfile.dev` + `docker-compose.dev.yml`) MUST run the app on port 8501 with source bind-mounted and hot reload enabled.
- **FR-004**: Secrets (`.env`) MUST NOT be committed or copied into images; `.gitignore` and `.dockerignore` MUST exclude them.
- **FR-005**: The existing build/deploy contract MUST be preserved: the build workflow builds the root `Dockerfile`, pushes to ECR Public, and dispatches `deploy` to the infra-repo.
- **FR-006**: The repository MUST be spec-kit enabled (`.specify/` engine, spec-kit skills, and the always-use-spec-kit rule present).

### Key Entities

- **Static Site Service**: The deployable unit for the domain; maps to the infra service `solovkadmytro` (domain `solovkadmytro.pp.ua`), now backed by a Streamlit image instead of nginx.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The production image builds successfully and the running container returns `ok` from `/_stcore/health`.
- **SC-002**: The dev stack serves the app on `http://localhost:8501` and reloads on source changes.
- **SC-003**: No secret files are present in the repository or built image.

## Assumptions

- The infra-repo Traefik service for this domain routes to container port 80 (existing `solovkadmytro` label is unchanged).
- The app reads optional configuration from environment variables / `.env` via `pydantic-settings`, defaulting sensibly when absent.
- Deployment to AWS EC2 is owned by the infra-repo; this repo only builds and publishes its image.
