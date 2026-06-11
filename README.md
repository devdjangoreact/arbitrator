# arbitrator

Arbitrator is a [Streamlit](https://streamlit.io/) dashboard for multi-exchange
crypto market screening (built on `ccxt`). This repository is an app-repo: it
builds its own image and publishes it to Amazon ECR Public, then notifies the
infra-repo to deploy. It contains no deployment, SSH, or cloud credentials.

- Project: `arbitrator`
- Service / ECR image: `solovkadmytro`
- Domain: `solovkadmytro.pp.ua`

## Project layout

```text
src/arbitrator/        application source (application, config, data, domain, exchanges, presentation)
main.py                Streamlit entrypoint
pyproject.toml         Poetry project (Python 3.11)
Dockerfile             production image (Streamlit on port 80)
Dockerfile.dev         development image (Streamlit on port 8501, hot reload)
docker-compose.dev.yml local development stack
```

## Local development (Docker)

```bash
docker compose -f docker-compose.dev.yml up --build
# open http://localhost:8501
```

Source under `src/` and `main.py` are bind-mounted, so edits reload live.
Optional configuration is read from a local `.env` (never committed); see
`.env.example`.

## Local development (Poetry)

```bash
poetry install --with dev
poetry run streamlit run main.py
# open http://localhost:8501
```

## Production image

```bash
docker build -t arbitrator .
docker run --rm -p 8080:80 arbitrator
# open http://localhost:8080
```

The production container serves Streamlit on port 80 to match the infra-repo
Traefik service label for this domain.

## Deploy (AWS)

Push to `main`. GitHub Actions (`.github/workflows/build.yml`) builds the image,
pushes `:latest` and `:<sha>` to ECR Public, and dispatches a `deploy` event to
`devdjangoreact/infra`, which rolls the container on the EC2 host behind Traefik.

## Spec Kit

This project uses Spec Kit. Feature artifacts live under `specs/`; the spec-kit
engine and skills are in `.specify/` and `.cursor/`. Start new work with
`speckit-specify` -> `speckit-plan` -> `speckit-tasks` -> `speckit-implement`.
