param(
    [string]$BaseRef = "",
    [switch]$ForceFull,
    [switch]$ForceE2E
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$taskPath = Join-Path $root ".agent\current-task.md"

if (-not (Test-Path $taskPath)) {
    Write-Host "No active task card found."
    Write-Host "Create one with: .\scripts\new-task.ps1"
    exit 2
}

$task = Get-Content $taskPath -Raw

function Get-TaskField([string]$Name) {
    $escaped = [regex]::Escape($Name)
    $match = [regex]::Match($task, "(?im)^" + $escaped + ":\s*(.+?)\s*$")
    if ($match.Success) {
        return $match.Groups[1].Value.Trim()
    }
    return ""
}

$changeClass = (Get-TaskField "Change class").ToUpperInvariant()
$browserVisible = (Get-TaskField "Browser-visible").ToLowerInvariant()

if ($changeClass -notin @("A", "B", "C", "D")) {
    Write-Error "Change class must be A, B, C, or D in .agent/current-task.md"
    exit 2
}

Write-Host "Local preflight for Class $changeClass"
Remove-Item Env:MBSE_FAST_RAN_FULL -ErrorAction SilentlyContinue

& "$PSScriptRoot\test-fast.ps1" -BaseRef $BaseRef
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$runFull = $ForceFull -or ($changeClass -in @("B", "C", "D"))
$fullAlreadyRan = $env:MBSE_FAST_RAN_FULL -eq "1"
if ($runFull -and -not $fullAlreadyRan) {
    & "$PSScriptRoot\test-full.ps1"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$runE2E = $ForceE2E -or ($browserVisible -in @("yes", "true", "y"))
if ($runE2E) {
    & "$PSScriptRoot\test-e2e.ps1"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Remove-Item Env:MBSE_FAST_RAN_FULL -ErrorAction SilentlyContinue
Write-Host "Preflight passed."
Write-Host "No push, merge, release, or GitHub Actions run was performed."
exit 0
