Run the full quality pipeline. Stop on the first failing step and surface the exact output.

Steps (Windows):

```powershell
.venv\Scripts\black.exe src tests
.venv\Scripts\ruff.exe check src tests --fix
.venv\Scripts\mypy.exe --strict src/arbitrator
.venv\Scripts\python.exe -m pytest tests/ -q
.venv\Scripts\uvicorn.exe main:app --reload --host 127.0.0.1 --port 8000
```