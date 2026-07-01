# Arbitrator

USDT-M perpetual futures arbitrage screener & strategy engine. FastAPI + static
web UI, live data over WebSocket, ccxt.pro for exchange I/O.

## Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/) (virtualenv lives in-project at `.venv`)

## Setup

```powershell
poetry install
copy .env.example .env   # then edit .env
```

`UI_DATA_MODE` in `.env` chooses the runtime:

| Mode | Value | Needs API keys | Data source |
| ---- | ----- | -------------- | ----------- |
| Test (default) | `UI_DATA_MODE=mock_data` | No | `src/arbitrator/data/mock_data.json` |
| Live | `UI_DATA_MODE=live` | Yes (for funding/fees/trading) | Real exchanges via ccxt.pro |

Run the app (both modes use the same command):

```powershell
.venv\Scripts\uvicorn.exe main:app
# or: .venv\Scripts\python.exe main.py
```

Open http://127.0.0.1:8000 (host/port configurable via `FASTAPI_HOST` / `FASTAPI_PORT`).

## Test mode (mock_data)

No exchange connection. The UI streams deterministic mock snapshots — good for
front-end work and demos.

```powershell
# .env
UI_DATA_MODE=mock_data
```

Start the app and open the URL above. Screener/Opportunity/Orders are populated
from the mock seed; no credentials required.

## Live mode

Streams real markets. Set credentials for the exchanges you use, then enable live:

```powershell
# .env
UI_DATA_MODE=live
ENABLED_EXCHANGES=["binance","mexc","bitget","gate","bingx"]

BINANCE_API_KEY=...
BINANCE_API_SECRET=...
# (and the other exchanges you trade on; BITGET also needs *_API_PASSWORD)
```

On start the app launches the stream workers (futures tickers, funding rates,
fees, account). The Screener computes the `futures_futures` strategy from live
quotes; strategies that need data not yet sourced (e.g. spot) show `N/A`.

> Read-only / no-trade: the live workers only read market and account data.
> Order placement is a separate, opt-in feature.

## Development

| Task | Command (PowerShell) |
| ---- | -------------------- |
| Run all tests | `.venv\Scripts\python.exe -m pytest tests/ -q` |
| Run strategy tests | `.venv\Scripts\python.exe -m pytest tests/ -k strategy -q` |
| Type check | `.venv\Scripts\mypy.exe --strict src/arbitrator` |
| Lint | `.venv\Scripts\ruff.exe check src tests` |
| Rebuild UI HTML | `.venv\Scripts\python.exe scripts/build_ui.py` |
