# Post-tool-use hook — fires after every file edit Claude performs.
param([string]$EventJson)

$logDir = ".claude/logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
"$(Get-Date -Format o) post-tool-use" | Add-Content -Path "$logDir/hooks.log"