# Data Model: React Frontend Architecture

*Note: This feature introduces architectural scaffolding, not new business entities or data models. The existing data models remain unchanged.*

## Settings Configuration

- **Entity**: `Settings` (in `src/arbitrator/config/settings.py`)
- **New Field**: `USE_REACT_FRONTEND`
  - **Type**: `bool`
  - **Default**: `False`
  - **Description**: Feature toggle to switch between the legacy vanilla JS frontend and the new React/Vite frontend.
