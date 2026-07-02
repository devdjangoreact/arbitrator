# Shared Bedrock preflight + AccessDenied diagnostics for invoke-bedrock.ps1
$script:BedrockLabRegion = "us-east-1"

function Invoke-AwsCliText {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$ArgumentList
    )

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $raw = & aws @ArgumentList 2>&1
        $lines = @(
            foreach ($item in @($raw)) {
                if ($item -is [System.Management.Automation.ErrorRecord]) {
                    $item.ToString()
                } else {
                    [string]$item
                }
            }
        )
        return [PSCustomObject]@{
            ExitCode = $LASTEXITCODE
            Output   = ($lines -join [Environment]::NewLine).Trim()
        }
    } finally {
        $ErrorActionPreference = $previousPreference
    }
}

function Write-BedrockPreflightHeader {
    param(
        [string]$Model,
        [string]$ModelId,
        [string]$Region
    )
    Write-Host "Bedrock preflight | model=$Model id=$ModelId region=$Region"
    if ($Region -ne $script:BedrockLabRegion) {
        Write-Host ""
        Write-Host "[region] Expected us-east-1 for this lab; you passed $Region." -ForegroundColor Yellow
        Write-Host "         Switch console/CLI/Terraform to US East (N. Virginia)." -ForegroundColor Yellow
    }
}

function Invoke-BedrockPreflightChecks {
    param(
        [string]$Model,
        [string]$ModelId,
        [string]$Region
    )

    Write-BedrockPreflightHeader -Model $Model -ModelId $ModelId -Region $Region

    $identity = Invoke-AwsCliText -ArgumentList @("sts", "get-caller-identity", "--region", $Region)
    if ($identity.ExitCode -ne 0) {
        Write-Host ""
        Write-Host "[credentials] AWS credentials are missing or invalid." -ForegroundColor Red
        Write-Host $identity.Output
        return
    }

    $accountId = ($identity.Output | ConvertFrom-Json).Account
    Write-Host "[credentials] caller account $accountId"

    $modelCheck = Invoke-AwsCliText -ArgumentList @(
        "bedrock", "get-foundation-model",
        "--model-identifier", $ModelId,
        "--region", $Region
    )
    if ($modelCheck.ExitCode -ne 0) {
        Write-Host ""
        Write-Host "[model catalog] Could not read foundation model metadata (geo IDs often fail here; invoke may still work):" -ForegroundColor Yellow
        if ($modelCheck.Output) {
            Write-Host $modelCheck.Output
        }
    } else {
        Write-Host "[model catalog] foundation model metadata OK"
    }

    if ($Model -eq "fable") {
        $retention = Invoke-AwsCliText -ArgumentList @("bedrock", "get-account-data-retention", "--region", $Region)
        if ($retention.ExitCode -ne 0) {
            Write-Host ""
            Write-Host "[fable retention] Could not read account data retention setting:" -ForegroundColor Yellow
            if ($retention.Output) {
                Write-Host $retention.Output
            }
            Write-Host "                  Fable 5 requires 30-day provider data retention in Bedrock Console." -ForegroundColor Yellow
        } else {
            $mode = ($retention.Output | ConvertFrom-Json).mode
            Write-Host "[fable retention] mode=$mode"
            if ($mode -ne "provider_data_share") {
                Write-Host ""
                Write-Host "[fable retention] Fable 5 needs provider_data_share (30-day retention)." -ForegroundColor Yellow
                Write-Host "                  Accept it in Bedrock Console before invoking Fable." -ForegroundColor Yellow
            }
        }
    }

    Write-Host ""
}

function Write-BedrockAccessDeniedHelp {
    param(
        [string]$Model,
        [string]$ModelId,
        [string]$Region,
        [string]$ErrorText
    )

    Write-Host ""
    Write-Host "=== Bedrock invoke failed ===" -ForegroundColor Red
    Write-Host $ErrorText
    Write-Host ""

    $lower = $ErrorText.ToLowerInvariant()

    if ($lower -match "not available for this account|contact aws sales|model use case|submit use case") {
        Write-Host "[likely cause: (a) use-case / account entitlement]" -ForegroundColor Yellow
        Write-Host "  - Open Bedrock Model catalog in us-east-1 and submit Anthropic use case for $ModelId."
        Write-Host "  - Trial accounts may not get Sonnet 5 / Opus 4.8 immediately; check model card status."
        if ($Model -eq "fable") {
            Write-Host "  - Fable 5 is RESTRICTED; AWS Sales approval may be required."
        }
    }

    if ($Model -eq "fable" -and $lower -match "data retention|provider_data_share|mythos|retention mode") {
        Write-Host "[likely cause: (b) Fable data retention not accepted]" -ForegroundColor Yellow
        Write-Host "  - In Bedrock Console (us-east-1) accept 30-day data retention for Mythos-class models."
    }

    if ($lower -match "not authorized to perform|explicit deny|with an explicit deny|accessdenied.*bedrock:invoke") {
        Write-Host "[likely cause: (c) IAM permissions]" -ForegroundColor Yellow
        Write-Host "  - Re-run terraform apply to refresh bedrock IAM policy."
        Write-Host "  - Ensure invoke uses credentials allowed by aws-credits-lab-bedrock user or equivalent policy."
    }

    if ($Region -ne $script:BedrockLabRegion) {
        Write-Host "[also check] Region mismatch: lab expects us-east-1, you used $Region." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "Terraform cannot automate use-case forms, Fable RESTRICTED approval, or data retention opt-in."
    Write-Host "See README section 2 for manual console steps."
    Write-Host ""
}
