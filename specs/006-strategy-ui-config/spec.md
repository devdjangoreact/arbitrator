# Feature Specification: Strategy UI Configuration

**Feature Branch**: `[006-strategy-ui-config]`  
**Created**: 2026-07-12  
**Status**: Draft  
**Input**: Move all strategy parameters, decision-making logic, and auto-trading settings from the `.env` file to the UI. Ensure all settings persist across application restarts. Only core application parameters should remain in `.env`.


## Clarifications
### Session 2026-07-12
- Q: Should the UI display raw technical keys or human-readable descriptions with logical grouping? → A: Human-readable labels with descriptions, grouped by functional categories.
- Q: How should the system handle existing strategy parameters in the `.env` file? → A: One-time migration
- Q: If the persistent storage file is found to be corrupted on startup, what should the system do? → A: Fail safe (Halt)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure and Persist Trading Strategy (Priority: P1)

A user wants to configure their automated trading strategies through the interface so they can easily adjust parameters without touching environment files. They want these settings to remain active even after restarting the application.

**Why this priority**: Moving configuration from `.env` to the UI is the core requirement of this feature, significantly improving usability and flexibility.

**Independent Test**: Start the application, modify a strategy parameter in the UI, restart the application, and verify the parameter retains its modified value in the UI and affects trading behavior.

**Acceptance Scenarios**:

1. **Given** a user is viewing the strategy configuration page, **When** they modify a strategy parameter and save it, **Then** the UI reflects the updated value and the system begins using the new parameter for decision-making.
2. **Given** a user has modified a strategy parameter, **When** they restart the application, **Then** the UI displays the previously saved modified value, and the system continues to use it.
3. **Given** an existing `.env` file containing strategy parameters, **When** the application starts for the first time without a persistent config file, **Then** those parameters are migrated into the persistent UI configuration storage, and the `.env` values are subsequently ignored.

---

### Edge Cases

- The persistent storage file/database is corrupted on startup (system must halt and alert user).
- The persistent storage file is missing on startup (system should perform one-time migration or load defaults).
- A user enters invalid or out-of-bounds values for specific strategy parameters in the UI.
- Concurrent modifications of settings if multiple UI instances are open.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The UI must display all configurable parameters related to strategies, decision-making, auto-trading, and strategy selection.
- **FR-002**: The application must persistently store all strategy configurations modified via the UI.
- **FR-003**: On startup, the application must load the strategy configurations from the persistent storage.
- **FR-004**: The `.env` file must only be used for core application parameters (e.g., port numbers, logging levels, essential API keys). On first startup, existing strategy parameters in `.env` must be migrated to the persistent storage.
- **FR-005**: The UI must provide validation for strategy parameters to prevent invalid inputs.
- **FR-006**: The application must fail safe and halt startup if the persistent configuration storage is detected as corrupted.
- **FR-007**: The UI must group strategy parameters into logical visual categories (e.g., Live Auto-Trade, Protections, Strategy Engine) for better navigation.
- **FR-008**: The UI must display human-readable labels and explanatory descriptions (in Ukrainian/English) for each technical parameter.

### Key Entities *(include if feature involves data)*

- **Strategy Configuration**: Represents the collective settings for a particular trading strategy or general auto-trading behavior.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of strategy-related settings are accessible and modifiable through the UI.
- **SC-002**: Settings modified in the UI are retained across 100% of application restarts.
- **SC-003**: The `.env` file contains zero strategy or decision-making parameters.

## Assumptions

- A robust persistent storage mechanism (e.g., SQLite, JSON file) is available or will be implemented to store the settings.
- The UI framework supports dynamic form generation or comprehensive configuration views for the various strategy parameters.

## Developer Guidelines: Adding New Strategy Parameters

When introducing a new automated trading parameter or strategy setting in the future, follow this strict 3-step rule to ensure it is properly exposed in the UI and persisted:

1. **Backend Model (`ui_config.py`)**: Add the new field to the `StrategyUIConfig` Pydantic model. Define its Python type and a sensible default value. Do **not** add it to `settings.py` or `.env`.
2. **Frontend UI Metadata (`settings.js`)**: Add the exact field key to the `STRATEGY_META` dictionary located in `src/arbitrator/presentation/static/js/render/settings.js`. You **must** define:
   - `label`: A short, human-readable name for the UI.
   - `desc`: A detailed explanation of what the parameter does (acts as a tooltip).
   - `category`: The logical visual group it belongs to (e.g., "Live Auto-Trade", "Движок Стратегій").
3. **Usage**: Access the parameter in your Python domain logic exclusively via `UIConfigManager.get_config().<your_new_parameter>`.

*Note: If a parameter is added to the backend model but forgotten in `STRATEGY_META`, the UI will still render it in an "Інші налаштування" (Other) category using its raw technical key, preventing it from being entirely hidden, but degrading the UX.*
