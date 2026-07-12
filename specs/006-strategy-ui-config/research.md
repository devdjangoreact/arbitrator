# Research

## Findings

### Persistent Storage for UI Config
- **Decision**: JSON file repository (e.g., `ui_config.json`) managed by a new service/repository layer in the domain.
- **Rationale**: The project already relies heavily on JSON file persistence for its lightweight local needs (`paper_orders.json`, `monitor_configs.json`, `arb_markers.json`). Reusing this pattern ensures consistency and avoids introducing a new database dependency just for settings.
- **Alternatives considered**: SQLite, Redis. Both are overkill for a simple configuration object with low write frequency.

### Backend Delivery mechanism
- **Decision**: A Singleton `ConfigManager` or a repository that loads from disk and updates in memory, exposing these values to the domain layer. The `Settings` object (`.env`) will serve purely as fallback/defaults if the JSON is empty, and will only define the absolute core requirements (like API keys, port, exchange proxies).
- **Rationale**: Need a way to read and write without restarting the app. The current `Settings` is a frozen Pydantic model. We need a mutable configuration state.
- **Alternatives considered**: Making Pydantic `Settings` mutable. Not ideal for `.env` driven setups; separating "Runtime Config" from "Environment Config" is cleaner.

### Pydantic Model for Configurations
- **Decision**: Create a `StrategyUIConfig` Pydantic model representing all the extracted fields.
- **Rationale**: Easy validation, serialization, and typing support for the FastAPI endpoints.