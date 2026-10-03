param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$template = Join-Path $root ".agent\TASK_TEMPLATE.md"
$target = Join-Path $root ".agent\current-task.md"

if (-not (Test-Path $template)) {
    Write-Error "Task template not found: $template"
    exit 2
}

if ((Test-Path $target) -and -not $Force) {
    Write-Host "Active task already exists: $target"
    Write-Host "Use -Force to replace it."
    exit 0
}

Copy-Item $template $target -Force
Write-Host "Created local active task: $target"
Write-Host "Edit it, then start the Codex coordinator."
