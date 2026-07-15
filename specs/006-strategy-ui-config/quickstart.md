# Quickstart & Validation: Strategy UI Configuration

## Prerequisites
1. Application running (`.venv\Scripts\uvicorn.exe main:app`).
2. REST client (e.g., curl, Postman) or the built-in Swagger UI at `http://127.0.0.1:8000/docs`.

## Validation Scenarios

### Scenario 1: Fetch Current Config
1. **Action**: `GET /api/config/strategy`
2. **Expected Outcome**: Returns a 200 OK with a JSON object containing all the fields defined in the data model (defaulting to the values previously in `.env`).

### Scenario 2: Update Config
1. **Action**: Send a `PUT /api/config/strategy` with `{"live_auto_trade_enabled": true}`.
2. **Expected Outcome**: Returns a 200 OK indicating success.

### Scenario 3: Verify Persistence
1. **Action**: Stop the application server (`Ctrl+C`).
2. **Action**: Start the application server again (`.venv\Scripts\uvicorn.exe main:app`).
3. **Action**: Fetch the config again (`GET /api/config/strategy`).
4. **Expected Outcome**: The response should show `"live_auto_trade_enabled": true`, proving the setting survived the restart.
