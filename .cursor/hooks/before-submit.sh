#!/usr/bin/env bash
# Before-submit hook (Linux / macOS)
# Runs before the prompt is sent to the model.
# TODO: save state before context compaction, scrub secrets, etc.

set -euo pipefail
mkdir -p .cursor/logs
echo "$(date -Iseconds) before-submit" >> .cursor/logs/hooks.log
