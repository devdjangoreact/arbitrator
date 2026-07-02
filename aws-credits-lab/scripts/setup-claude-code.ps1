# Generates Claude Code settings for Bedrock (Opus 4.8, Sonnet 5, Fable 5).
# Run from aws-credits-lab after `terraform apply`.
param(
    [ValidateSet("project", "user")]
    [string]$Target = "project",
    [switch]$IncludeBedrockKeys
)

$ErrorActionPreference = "Stop"
$labRoot = Split-Path -Parent $PSScriptRoot
Set-Location $labRoot

function Get-TerraformOutput {
    param([string]$Name)
    return (terraform output -raw $Name).Trim()
}

$region = Get-TerraformOutput "bedrock_region"
$opusModel = Get-TerraformOutput "bedrock_opus_model_id"
$sonnetModel = Get-TerraformOutput "bedrock_sonnet_model_id"
$fableModel = Get-TerraformOutput "bedrock_fable_model_id"

$envBlock = [ordered]@{
    CLAUDE_CODE_USE_BEDROCK = "1"
    AWS_REGION = $region
    ANTHROPIC_DEFAULT_OPUS_MODEL = $opusModel
    ANTHROPIC_DEFAULT_SONNET_MODEL = $sonnetModel
    ANTHROPIC_DEFAULT_FABLE_MODEL = $fableModel
}

if ($IncludeBedrockKeys) {
    $envBlock["AWS_ACCESS_KEY_ID"] = Get-TerraformOutput "bedrock_access_key_id"
    $envBlock["AWS_SECRET_ACCESS_KEY"] = Get-TerraformOutput "bedrock_secret_access_key"
}

$settings = [ordered]@{
    "`$schema" = "https://json.schemastore.org/claude-code-settings.json"
    env = $envBlock
    availableModels = @("opus", "sonnet", "fable")
    modelOverrides = [ordered]@{
        "claude-opus-4-8" = $opusModel
        "claude-sonnet-5" = $sonnetModel
        "claude-fable-5" = $fableModel
    }
}

$json = ($settings | ConvertTo-Json -Depth 6)

if ($Target -eq "project") {
    $destDir = Join-Path $labRoot ".claude"
    $destFile = Join-Path $destDir "settings.local.json"
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    Set-Content -Path $destFile -Value $json -Encoding utf8
    Write-Host "Wrote $destFile"
    Write-Host ""
    Write-Host "Copy .vscode/settings.json.example to .vscode/settings.json (disableLoginPrompt)."
} else {
    $destDir = Join-Path $env:USERPROFILE ".claude"
    $destFile = Join-Path $destDir "settings.json"
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    if (Test-Path $destFile) {
        Write-Warning "$destFile already exists - merge manually or back up first."
        $backup = "$destFile.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
        Copy-Item $destFile $backup
        Write-Host "Backup: $backup"
    }
    Set-Content -Path $destFile -Value $json -Encoding utf8
    Write-Host "Wrote $destFile (global Claude Code settings)."
}

Write-Host ""
if ($IncludeBedrockKeys) {
    Write-Host "Bedrock IAM keys embedded in settings (from terraform outputs)."
} else {
    Write-Host "Using system AWS credentials (default credential chain)."
    Write-Host "Ensure AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY or AWS profile are set before opening Cursor."
}
Write-Host "Verify in Claude Code chat: /status then send a test prompt."
Write-Host "Switch models: /model opus | /model sonnet | /model fable"
