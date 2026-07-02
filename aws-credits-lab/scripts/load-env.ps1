# Loads aws-credits-lab/.env into the current PowerShell session.
# Usage: . .\scripts\load-env.ps1
$ErrorActionPreference = "Stop"

$envPath = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
if (-not (Test-Path $envPath)) {
    Write-Error ".env not found at $envPath — copy .env.example to .env first."
    return
}

Get-Content $envPath -Encoding UTF8 | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#")) {
        return
    }
    $eq = $line.IndexOf("=")
    if ($eq -lt 1) {
        return
    }
    $key = $line.Substring(0, $eq).Trim()
    $value = $line.Substring($eq + 1).Trim()
    if (
        ($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))
    ) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    Set-Item -Path "Env:$key" -Value $value
}

Write-Host "Loaded .env from $envPath"
