param(
    [string]$BaseRef = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

try {
    $selectorArgs = @("tools/select_tests.py")
    if ($BaseRef) {
        $selectorArgs += @("--base", $BaseRef)
    }

    $pythonArgs = @("tools/select_tests.py", "--python-files")
    if ($BaseRef) {
        $pythonArgs += @("--base", $BaseRef)
    }

    $pythonFiles = @(& python @pythonArgs)
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Could not inspect changed Python files."
        exit $LASTEXITCODE
    }

    if ($pythonFiles.Count -gt 0) {
        Write-Host "Syntax-checking changed Python files..."
        & python -m py_compile @pythonFiles
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }

    $tests = @(& python @selectorArgs)
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Focused test selection failed."
        exit $LASTEXITCODE
    }

    $requiresFull = $tests -contains "__FULL__"
    $tests = @($tests | Where-Object { $_ -ne "__FULL__" })

    if ($tests.Count -gt 0) {
        Write-Host "Focused tests:"
        $tests | ForEach-Object { Write-Host "  $_" }
        & python -m pytest -q @tests
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    else {
        Write-Host "No focused tests mapped for the current change."
    }

    if ($requiresFull) {
        Write-Host "At least one changed code path has no focused mapping; running full regression as safe fallback."
        & "$PSScriptRoot\test-full.ps1"
        exit $LASTEXITCODE
    }

    exit 0
}
finally {
    Pop-Location
}
