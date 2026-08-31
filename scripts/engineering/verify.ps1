param(
    [Parameter(Mandatory = $true)][string]$Gate,
    [Parameter(Mandatory = $true)][string]$Task,
    [Parameter(Mandatory = $true)][int]$ContractVersion,
    [Parameter(Mandatory = $true)][string]$SubjectSha,
    [Parameter(Mandatory = $true)][ValidateSet('worker', 'reviewer', 'verifier', 'ci', 'human')][string]$Provenance,
    [string]$SourceUri,
    [string]$Python = 'python'
)

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$Arguments = @(
    (Join-Path $PSScriptRoot 'gate_runner.py'),
    $Gate,
    '--task', $Task,
    '--contract-version', $ContractVersion,
    '--subject-sha', $SubjectSha,
    '--provenance', $Provenance,
    '--repo-root', $RepoRoot
)
if ($SourceUri) {
    $Arguments += @('--source-uri', $SourceUri)
}

& $Python @Arguments
exit $LASTEXITCODE
