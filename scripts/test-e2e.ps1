param(
    [string[]]$Tests = @("tests/e2e")
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    & python -c "import playwright" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Playwright is not installed in the active environment."
        Write-Host "Install locally with:"
        Write-Host "  pip install playwright"
        Write-Host "  python -m playwright install chromium"
        exit 2
    }

    $previousRunE2E = $env:RUN_E2E
    try {
        $env:RUN_E2E = "1"
        Write-Host "Running local browser E2E..."
        & python -m pytest -q @Tests
        exit $LASTEXITCODE
    }
    finally {
        if ($null -eq $previousRunE2E) {
            Remove-Item Env:RUN_E2E -ErrorAction SilentlyContinue
        }
        else {
            $env:RUN_E2E = $previousRunE2E
        }
    }
}
finally {
    Pop-Location
}
