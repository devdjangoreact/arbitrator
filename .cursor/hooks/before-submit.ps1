# Before-submit hook (Windows / PowerShell)
# Runs before the prompt is sent to the model.
# TODO: save state before context compaction, scrub secrets, etc.

$logDir = ".cursor/logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
"$(Get-Date -Format o) before-submit" | Add-Content -Path "$logDir/hooks.log"
