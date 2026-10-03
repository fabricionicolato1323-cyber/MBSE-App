param()

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    Write-Host "Running full local Python regression..."
    & python -m pytest -q
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
