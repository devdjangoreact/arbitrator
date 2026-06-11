# Post-tool-use hook (Windows / PowerShell)
# Fires after every file edit Cursor performs.
# TODO: auto-commit NM-XXX after edits, run lint, etc.

param(
    [string]$EventJson
)

# Example: write a marker so you can confirm the hook fired.
$logDir = ".cursor/logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
"$(Get-Date -Format o) post-tool-use" | Add-Content -Path "$logDir/hooks.log"
