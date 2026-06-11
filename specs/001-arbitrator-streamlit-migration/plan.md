# Implementation Plan: Arbitrator Streamlit app migration & containerization

**Branch**: `001-arbitrator-streamlit-migration` | **Date**: 2026-06-12 | **Spec**: [spec.md](./spec.md)

## Summary

Replace the previous static `nginx` placeholder in this app-repo with the full
Arbitrator Streamlit application and provide two Docker workflows: a production
image (Streamlit on port 80, consumed by the infra-repo via ECR Public + Traefik)
and a development stack (port 8501, hot reload, source bind-mounted).

## Technical Context

**Language/Version**: Python 3.11 (`>=3.11,<4.0`), managed with Poetry (in-project venv)

**Primary Dependencies**: streamlit, ccxt, pydantic, pydantic-settings, loguru;
dev: mypy, ruff, black, pytest

**App entrypoint**: `streamlit run main.py`; `main.py` wires `Settings`, JSON
repositories, logger, and `StreamlitApp`.

**Project structure**: `src/arbitrator/{application,config,data,domain,exchanges,presentation}`

**Target Platform**: Linux container on AWS EC2 (Ubuntu) behind Traefik; built and
published to Amazon ECR Public as service `solovkadmytro` (domain `solovkadmytro.pp.ua`).

**Constraints**: No secrets in source control or images; production container must
listen on port 80 to match the infra Traefik service label; existing build workflow
(`.github/workflows/build.yml`) must keep working unchanged.

## Project Structure

```text
sites/arbitrator/                  # this submodule (app-repo)
├── src/arbitrator/                # application source
├── main.py                        # Streamlit entrypoint
├── pyproject.toml / poetry.lock   # Poetry project
├── Dockerfile                     # production image (Streamlit on :80)
├── Dockerfile.dev                 # development image (Streamlit on :8501, hot reload)
├── docker-compose.dev.yml         # local dev stack
├── .dockerignore                  # excludes venv/caches/secrets/docs
├── .github/workflows/build.yml    # build -> ECR Public -> dispatch infra (unchanged)
├── .specify/                      # spec-kit engine (templates, scripts, workflows)
├── .cursor/                       # project rules + spec-kit skills
└── specs/001-arbitrator-streamlit-migration/
```

## Approach

1. Copy source into the submodule, excluding `.venv`, caches (`__pycache__`,
   `.mypy_cache`, `.ruff_cache`), `logs/`, and `.env`. Keep `.git` and
   `.github/workflows/build.yml`.
2. Author a multi-stage production `Dockerfile`: a Poetry builder stage installs
   main dependencies into an in-project venv; the runtime stage copies the venv and
   source and launches Streamlit on port 80 with a health check.
3. Author `Dockerfile.dev` + `docker-compose.dev.yml` for local development with a
   bind-mounted source tree and `run-on-save` reload on port 8501.
4. Integrate spec-kit: copy `.specify/` engine and spec-kit skills, add the
   always-use-spec-kit rule and a project `specify-rules.mdc`, and record this
   feature under `specs/`.
5. Validate (`docker compose config`, optional image build) and commit on the
   feature branch inside this submodule.

## Notes

- The infra-repo `compose/docker-compose.yml` Traefik label for `solovkadmytro`
  targets port 80; the production image binds 80 to avoid any infra change.
- `pydantic-settings` reads optional env via `.env`; defaults apply when absent.
