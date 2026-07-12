# Implementation Tasks: Strategy UI Configuration

## Phase 1: Setup

- [x] T001 Define `StrategyUIConfig` Pydantic model in `src/arbitrator/config/ui_config.py` based on `data-model.md`.
- [x] T002 Implement `UIConfigManager` singleton in `src/arbitrator/config/ui_config_manager.py` to handle JSON file persistence (`data/ui_config.json`).
- [x] T003 Implement one-time `.env` migration logic within `UIConfigManager` initialization to populate defaults if the JSON file is missing.
- [x] T004 Implement corruption fail-safe in `UIConfigManager` to halt application startup if `ui_config.json` is unparseable.

## Phase 2: Foundational

- [x] T005 Strip migrated strategy parameters from `Settings` class in `src/arbitrator/config/settings.py`.
- [x] T006 Update global references to `settings.<parameter>` to use `UIConfigManager.get_config().<parameter>` across domain services (e.g., auto-traders, monitors, liquidation guards).

## Phase 3: [US1] Configure and Persist Trading Strategy

**Story Goal:** Allow users to fetch and update strategy settings via API and UI, persisting them across restarts.
**Independent Test:** Fetch via GET, update via PUT, and verify the JSON file reflects changes.

- [x] T007 [US1] Implement `GET /api/config/strategy` endpoint in `src/arbitrator/presentation/api/routers/config.py`.
- [x] T008 [US1] Implement `PUT /api/config/strategy` endpoint in `src/arbitrator/presentation/api/routers/config.py` with partial update support.
- [x] T009 [P] [US1] Register `config.py` router in the main FastAPI application setup `src/arbitrator/presentation/api/app.py`.
- [x] T010 [P] [US1] Update or create the frontend `StrategySettings` component to fetch defaults from `GET /api/config/strategy`.
- [x] T011 [US1] Implement save functionality in the frontend `StrategySettings` component to send `PUT /api/config/strategy` requests.
- [x] T012 [US1] Add form validation in the frontend matching the constraints defined in `StrategyUIConfig`.


## Phase 4: Polish & UX Improvements

- [x] T013 [US1] Create a metadata dictionary in the frontend mapping technical keys to human-readable labels, categories, and descriptions.
- [x] T014 [US1] Refactor frontend `renderStrategyConfig` to group fields into visual sections (tabs/cards) based on their category.
- [x] T015 [US1] Update the UI fields to display the explanatory description text below or alongside each parameter input.

## Dependencies

- Phase 2 depends on Phase 1 completing the `UIConfigManager`.
- Phase 3 API endpoints depend on Phase 1 models and manager.
- Frontend tasks (T010-T012) can be parallelized with backend API development once contracts are defined.

## Parallel Execution Opportunities

- T007/T008 (Backend API) can be executed in parallel with T010/T012 (Frontend UI structure and validation) by different agents.
- T009 can be done at any point after T007/T008 are defined.
