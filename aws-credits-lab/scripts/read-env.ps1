# Reads aws-credits-lab/.env for Terraform external data source.
# Outputs JSON: {"AWS_RDS_PASSWORD":"..."}
$ErrorActionPreference = "Stop"

$envPath = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
if (-not (Test-Path $envPath)) {
    Write-Error ".env not found at $envPath - copy .env.example to .env and set AWS_RDS_PASSWORD."
    exit 1
}

$vars = @{}
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
    $vars[$key] = $value
}

$password = $vars['AWS_RDS_PASSWORD']
if ([string]::IsNullOrWhiteSpace($password)) {
    Write-Error "AWS_RDS_PASSWORD is missing or empty in $envPath"
    exit 1
}

[ordered]@{ AWS_RDS_PASSWORD = $password } | ConvertTo-Json -Compress
