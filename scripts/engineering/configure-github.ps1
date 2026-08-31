param(
    [Parameter(Mandatory = $true)][string]$Owner,
    [Parameter(Mandatory = $true)][string]$Repository,
    [string]$Gh = 'gh'
)

$ErrorActionPreference = 'Stop'

if (-not (Get-Command $Gh -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI (gh) is required.'
}

function Invoke-GhJson {
    param(
        [Parameter(Mandatory = $true)][string]$Method,
        [Parameter(Mandatory = $true)][string]$Endpoint,
        [Parameter(Mandatory = $true)][object]$Body
    )

    $TemporaryFile = New-TemporaryFile
    try {
        $Body | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $TemporaryFile -Encoding utf8
        & $Gh api --method $Method $Endpoint --input $TemporaryFile
        if ($LASTEXITCODE -ne 0) {
            throw "GitHub API request failed: $Method $Endpoint"
        }
    }
    finally {
        Remove-Item -LiteralPath $TemporaryFile -Force -ErrorAction SilentlyContinue
    }
}

$UserId = & $Gh api "users/$Owner" --jq '.id'
if ($LASTEXITCODE -ne 0 -or -not $UserId) {
    throw "Unable to resolve GitHub user: $Owner"
}

$ApprovalEnvironments = @('product-approval', 'governance-approval', 'production')

$EnvironmentBody = @{
    wait_timer = 0
    prevent_self_review = $false
    reviewers = @(
        @{
            type = 'User'
            id = [int64]$UserId
        }
    )
    deployment_branch_policy = $null
}

foreach ($Environment in $ApprovalEnvironments) {
    Invoke-GhJson -Method PUT -Endpoint "repos/$Owner/$Repository/environments/$Environment" -Body $EnvironmentBody
}

$RequiredChecks = @(
    'engineering-os/gate-engine-tests',
    'engineering-os/contract-risk',
    'engineering-os/consistency-evidence',
    'engineering-os/project-verification',
    'engineering-os/final-gate',
    'engineering-os/product-approval',
    'engineering-os/governance-approval'
) | ForEach-Object { @{ context = $_ } }

$RulesetBody = @{
    name = 'codex-engineering-os-main'
    target = 'branch'
    enforcement = 'active'
    bypass_actors = @()
    conditions = @{
        ref_name = @{
            include = @('~DEFAULT_BRANCH')
            exclude = @()
        }
    }
    rules = @(
        @{ type = 'deletion' },
        @{ type = 'non_fast_forward' },
        @{
            type = 'pull_request'
            parameters = @{
                required_approving_review_count = 0
                dismiss_stale_reviews_on_push = $true
                require_code_owner_review = $false
                require_last_push_approval = $false
                required_review_thread_resolution = $true
                allowed_merge_methods = @('squash')
            }
        },
        @{
            type = 'required_status_checks'
            parameters = @{
                strict_required_status_checks_policy = $true
                do_not_enforce_on_create = $true
                required_status_checks = $RequiredChecks
            }
        }
    )
}

$ExistingRulesets = & $Gh api "repos/$Owner/$Repository/rulesets" | ConvertFrom-Json
$Existing = $ExistingRulesets | Where-Object { $_.name -eq 'codex-engineering-os-main' } | Select-Object -First 1
if ($Existing) {
    Invoke-GhJson -Method PUT -Endpoint "repos/$Owner/$Repository/rulesets/$($Existing.id)" -Body $RulesetBody
}
else {
    Invoke-GhJson -Method POST -Endpoint "repos/$Owner/$Repository/rulesets" -Body $RulesetBody
}

$BypassEnabled = @()
foreach ($Environment in $ApprovalEnvironments) {
    $EnvironmentState = & $Gh api "repos/$Owner/$Repository/environments/$Environment" | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to verify GitHub Environment: $Environment"
    }
    if ($EnvironmentState.can_admins_bypass -ne $false) {
        $BypassEnabled += $Environment
    }
}

if ($BypassEnabled.Count -gt 0) {
    throw "Administrator bypass must be disabled for GitHub Environments: $($BypassEnabled -join ', ')"
}

Write-Host "Configured environments and main branch ruleset for $Owner/$Repository."
