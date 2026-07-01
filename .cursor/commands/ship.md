---
description: Format, lint, type-check, test, run.
---

# /ship

Run the full quality pipeline against the project. Stop on the first failing
step and surface the exact log.

Windows (PowerShell):

```powershell
.venv\Scripts\black.exe .
.venv\Scripts\ruff.exe check . --fix
.venv\Scripts\mypy.exe src main.py
.venv\Scripts\pytest.exe
.venv\Scripts\uvicorn.exe main:app --reload --host 127.0.0.1 --port 8000
```

Linux / macOS:

```bash
.venv/bin/black .
.venv/bin/ruff check . --fix
.venv/bin/mypy src main.py
.venv/bin/pytest
.venv/bin/uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
