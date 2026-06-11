#!/usr/bin/env bash
# Post-tool-use hook (Linux / macOS)
# Fires after every file edit Cursor performs.
# TODO: auto-commit NM-XXX after edits, run lint, etc.

set -euo pipefail
mkdir -p .cursor/logs
echo "$(date -Iseconds) post-tool-use" >> .cursor/logs/hooks.log
