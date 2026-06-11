# Session-start hook (Windows / PowerShell)
# TODO: load project context on startup (git branch, last NM-XXX, etc).

$logDir = ".cursor/logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
"$(Get-Date -Format o) session-start" | Add-Content -Path "$logDir/hooks.log"
