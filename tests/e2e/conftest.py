"""E2E test fixtures — starts the app server, provides base_url."""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

BASE_URL = "http://127.0.0.1:8000"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="session")
def app_server():
    """Start the uvicorn app in mock_data mode and tear it down after tests."""
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--no-access-log",
        ],
        cwd=str(PROJECT_ROOT),
        env={
            **__import__("os").environ,
            "UI_DATA_MODE": "mock_data",
            "PYTHONPATH": str(PROJECT_ROOT),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # wait for the server to be ready
    import socket

    for _ in range(30):
        try:
            with socket.create_connection(("127.0.0.1", 8000), timeout=1):
                break
        except OSError:
            time.sleep(0.5)
    else:
        proc.terminate()
        pytest.skip("Could not start app server")

    yield BASE_URL

    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="session")
def browser_context(app_server, playwright):  # type: ignore[no-untyped-def]
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    yield context
    context.close()
    browser.close()
