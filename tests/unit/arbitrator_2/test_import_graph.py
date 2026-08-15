from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN = ("arbitrator.application", "arbitrator.presentation", "arbitrator.exchanges")


def test_arbitrator_2_does_not_import_legacy_app_stack() -> None:
    root = Path("src/arbitrator_2")
    hits: list[str] = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if any(node.module == f or node.module.startswith(f + ".") for f in FORBIDDEN):
                    hits.append(f"{path}: from {node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == f or alias.name.startswith(f + ".") for f in FORBIDDEN):
                        hits.append(f"{path}: import {alias.name}")
    assert hits == []
    assert root.is_dir()
