param(
    [ValidateSet("opus", "sonnet", "fable")]
    [string]$Model = "sonnet",
    [string]$Prompt = "Say hello in one short sentence.",
    [string]$Region = "us-east-1",
    [switch]$UseSystemCredentials
)

$ErrorActionPreference = "Stop"
$LabDir = Split-Path -Parent $PSScriptRoot
Set-Location $LabDir

. (Join-Path $PSScriptRoot "bedrock-preflight.ps1")

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI is required. Install from https://aws.amazon.com/cli/"
}

switch ($Model) {
    "opus"  { $modelId = terraform output -raw bedrock_opus_model_id }
    "fable" { $modelId = terraform output -raw bedrock_fable_model_id }
    default { $modelId = terraform output -raw bedrock_sonnet_model_id }
}

$savedAccessKey = $env:AWS_ACCESS_KEY_ID
$savedSecretKey = $env:AWS_SECRET_ACCESS_KEY
$savedSessionToken = $env:AWS_SESSION_TOKEN
$savedDefaultRegion = $env:AWS_DEFAULT_REGION

try {
    if (-not $UseSystemCredentials) {
        $env:AWS_ACCESS_KEY_ID = terraform output -raw bedrock_access_key_id
        $env:AWS_SECRET_ACCESS_KEY = terraform output -raw bedrock_secret_access_key
        Remove-Item Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
    }

    $env:AWS_DEFAULT_REGION = $Region

    Invoke-BedrockPreflightChecks -Model $Model -ModelId $modelId -Region $Region

    $body = @{
        anthropic_version = "bedrock-2023-05-31"
        max_tokens        = 128
        messages          = @(
            @{
                role    = "user"
                content = $Prompt
            }
        )
    } | ConvertTo-Json -Depth 5 -Compress

    $bodyFile = Join-Path $env:TEMP "bedrock-request.json"
    $responseFile = Join-Path $env:TEMP "bedrock-response.json"

    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($bodyFile, $body, $utf8NoBom)

    $bodyUri = "fileb://$($bodyFile -replace '\\', '/')"
    $responseUri = $responseFile -replace '\\', '/'

    Write-Host "Invoking model: $modelId in $Region"
    Write-Host "Prompt: $Prompt"
    Write-Host ""

    $invokeResult = Invoke-AwsCliText -ArgumentList @(
        "bedrock-runtime", "invoke-model",
        "--region", $Region,
        "--model-id", $modelId,
        "--content-type", "application/json",
        "--accept", "application/json",
        "--body", $bodyUri,
        $responseUri
    )

    if ($invokeResult.ExitCode -ne 0 -or -not (Test-Path $responseFile)) {
        Write-BedrockAccessDeniedHelp -Model $Model -ModelId $modelId -Region $Region -ErrorText $invokeResult.Output
        exit 1
    }

    Get-Content $responseFile -Raw | ConvertFrom-Json | ConvertTo-Json -Depth 10
} finally {
    if ($null -eq $savedAccessKey) {
        Remove-Item Env:AWS_ACCESS_KEY_ID -ErrorAction SilentlyContinue
    } else {
        $env:AWS_ACCESS_KEY_ID = $savedAccessKey
    }
    if ($null -eq $savedSecretKey) {
        Remove-Item Env:AWS_SECRET_ACCESS_KEY -ErrorAction SilentlyContinue
    } else {
        $env:AWS_SECRET_ACCESS_KEY = $savedSecretKey
    }
    if ($null -eq $savedSessionToken) {
        Remove-Item Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
    } else {
        $env:AWS_SESSION_TOKEN = $savedSessionToken
    }
    if ($null -eq $savedDefaultRegion) {
        Remove-Item Env:AWS_DEFAULT_REGION -ErrorAction SilentlyContinue
    } else {
        $env:AWS_DEFAULT_REGION = $savedDefaultRegion
    }
}
