# AGENTS.md

> Project rules for AI agents. Keep this file **under 200 lines**.

## Project

- **Name**: arbitrator
- **Language**: Python 3.11+
- **Package manager**: Poetry (installed inside `.venv/`)
- **UI**: Streamlit
- **Exchange client**: `ccxt.pro` (async, WebSocket)
- **Validation**: Pydantic v2

## Golden rules

1. Read this file before doing anything.
2. Never edit `*.local.*` files — personal overrides.
3. Never read `.env*` files.
4. Ask before creating new files.
5. English in code, comments, and commit messages.
6. **All code is class-based.** No free-floating logic except `main.py` entry point.
7. After every code/structure change, update Cursor docs and rules to match — see `.cursor/rules/documentation-sync.mdc`.

## Architecture

Strict layering — see `.cursor/rules/architecture.mdc`:

```
presentation/  →  application/  →  domain/  ←  exchanges/
                                          ←  config/  (Settings, logger, JSON repos)
```

| Layer            | Path                                | Responsibility                                |
| ---------------- | ----------------------------------- | --------------------------------------------- |
| `domain/`        | `src/arbitrator/domain/`            | Entities, value objects, abstractions (ABC)   |
| `application/`   | `src/arbitrator/application/`       | Use cases, orchestration                      |
| `exchanges/`     | `src/arbitrator/exchanges/`         | ccxt.pro adapters and exchange factory        |
| `config/`        | `src/arbitrator/config/`            | Settings, project logger, JSON repositories   |
| `data/`          | `src/arbitrator/data/`              | Mutable JSON data (exclusions, universe)      |
| `presentation/`  | `src/arbitrator/presentation/`      | Streamlit UI (header, sidebar with sections)  |

`presentation/sidebar/` hosts every selectable section:
`screener/`, `open_orders/`, `closed_orders/`, `settings/`.

## Commands

All run from project root using the in-project `.venv`:

| Task        | Command                                            |
| ----------- | -------------------------------------------------- |
| Install     | `.venv\Scripts\poetry.exe install`                 |
| Run UI      | `.venv\Scripts\streamlit.exe run main.py`          |
| Add dep     | `.venv\Scripts\poetry.exe add <pkg>`               |
| Add dev dep | `.venv\Scripts\poetry.exe add --group dev <pkg>`   |
| Lint        | `.venv\Scripts\ruff.exe check .`                   |
| Format      | `.venv\Scripts\black.exe .`                        |
| Type check  | `.venv\Scripts\mypy.exe src main.py`               |
| Test        | `.venv\Scripts\pytest.exe`                         |
| Ship        | see `.cursor/commands/ship.md`                     |

On Linux replace `\Scripts\*.exe` with `/bin/*`.

## Code style (Python)

- `mypy --strict` must pass. **No `typing.Any`.** Use `object` + `isinstance`, or proper generics.
- `from __future__ import annotations` at the top of every module.
- One class per file. File name = class name in `snake_case`.
- Prefer composition over inheritance.
- Dependency Inversion: depend on abstractions from `domain/`, inject via constructor.
- Async I/O: use `ccxt.pro` `watch_*` methods, not REST `fetch_*` polling.
- Use `pydantic.BaseModel` for domain entities; mark them `frozen=True` where possible.
- Error handling: log full exception (`logger.exception(...)`), never just `error.message`.

## Where things live

| Concern             | Path                                |
| ------------------- | ----------------------------------- |
| MCP servers         | `.cursor/mcp.json`                  |
| Hooks               | `.cursor/hooks.json` + `.cursor/hooks/` |
| Slash commands      | `.cursor/commands/`                 |
| Subagents           | `.cursor/agents/`                   |
| Custom modes        | `.cursor/modes/`                    |
| Path-scoped rules   | `.cursor/rules/*.mdc`               |
| Settings            | `.cursor/settings.json`             |
| Debug configs       | `.vscode/launch.json`               |
