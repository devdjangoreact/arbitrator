# Implementation Plan: Strategy UI Configuration

**Branch**: `[006-strategy-ui-config]` | **Date**: 2026-07-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-strategy-ui-config/spec.md`

## Summary

Migrate all strategy, auto-trading, and protection parameters from `.env` to a UI-manageable, persistent configuration. A new `StrategyUIConfig` model will be saved as JSON (`ui_config.json`) and exposed via REST API, updating the runtime state without requiring an application restart.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, Pydantic, React (Frontend UI)

**Storage**: Local JSON file (`data/ui_config.json`)

**Testing**: pytest

**Target Platform**: Linux server/Windows local

**Project Type**: web-service + UI

**Performance Goals**: Sub-millisecond reads from memory (after loading JSON once).

**Constraints**: Configuration changes must apply immediately to active trading loops without restarting processes.

**Scale/Scope**: ~50 parameters moved from `.env` to JSON.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

No violations detected. Reusing the existing JSON-based persistence pattern aligns with the project's lightweight architecture.

## Project Structure

### Documentation (this feature)

```text
specs/006-strategy-ui-config/
├── plan.md              # This file
├── research.md          # Research findings
├── data-model.md        # Pydantic model structure
├── quickstart.md        # API validation guide
├── contracts/           # API Endpoints definition
│   └── api.md
└── tasks.md             # Phase 2 output (next phase)
```

### Source Code (repository root)

```text
src/arbitrator/
├── config/
│   ├── settings.py             # (Modified) Remove strategy parameters
│   └── ui_config_manager.py    # (New) Singleton to handle read/write of JSON config
├── presentation/
│   ├── api/
│   │   └── routers/
│   │       └── config.py       # (New) GET/PUT endpoints
└── data/                       # (Storage)
    └── ui_config.json          # (New runtime file)

ui/                             # (Frontend - assuming static UI exists)
└── src/
    └── components/
        └── StrategySettings/   # (New/Modified) Form to handle these values
```
