param(
    [ValidateRange(0, 10)]
    [int]$MaxRepairCycles = 2
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$taskPath = Join-Path $root ".agent\current-task.md"
$preflightPath = Join-Path $PSScriptRoot "preflight.ps1"

function Get-CodexCommand {
    foreach ($name in @("codex.cmd", "codex.exe", "codex")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($command) {
            return $command.Source
        }
    }
    return $null
}

function Invoke-CodexTurn {
    param(
        [string]$CodexCommand,
        [string[]]$Arguments,
        [ref]$ThreadId,
        [ref]$DecisionRequired
    )

    & $CodexCommand @Arguments | ForEach-Object {
        $line = $_
        try {
            $event = $line | ConvertFrom-Json
        }
        catch {
            Write-Host $line
            return
        }

        if ($event.type -eq "thread.started" -and $event.thread_id) {
            $ThreadId.Value = $event.thread_id
            Write-Host "Codex coordinator: $($event.thread_id)"
            return
        }

        if ($event.type -eq "item.started" -and $event.item.type -eq "command_execution") {
            Write-Host "Codex command: $($event.item.command)"
            return
        }

        if ($event.type -eq "item.completed" -and $event.item.type -eq "agent_message") {
            $message = [string]$event.item.text
            Write-Host $message
            if ($message -match "(?im)^USER_DECISION_REQUIRED:\s*(yes|no)\s*$") {
                $DecisionRequired.Value = $Matches[1].ToLowerInvariant() -eq "yes"
            }
            return
        }

        if ($event.type -in @("turn.failed", "error")) {
            $detail = if ($event.message) { $event.message } elseif ($event.error.message) { $event.error.message } else { $line }
            Write-Warning "Codex reported: $detail"
        }
    }

    return $LASTEXITCODE
}

function Invoke-Preflight {
    param([ref]$Output)

    $captured = [System.Collections.Generic.List[string]]::new()
    $writeLine = {
        param($Value)
        $line = [string]$Value
        $captured.Add($line)
        Write-Host $line
    }

    try {
        & $preflightPath 2>&1 | ForEach-Object { & $writeLine $_ }
        $exitCode = $LASTEXITCODE
    }
    catch {
        & $writeLine $_
        $exitCode = 1
    }

    $Output.Value = $captured.ToArray()
    return $exitCode
}

function Write-CompletionSummary {
    param(
        [string]$TestResult,
        [bool]$DecisionRequired
    )

    Write-Host ""
    Write-Host "Git status:"
    & git status --short --branch
    Write-Host ""
    Write-Host "Diff summary:"
    & git diff --stat
    Write-Host ""
    Write-Host "Test result: $TestResult"
    Write-Host "User decision required: $(if ($DecisionRequired) { 'yes' } else { 'no' })"
}

Push-Location $root
try {
    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Could not determine the current Git branch." -ErrorAction Continue
        exit 2
    }
    if ($branch -eq "main") {
        Write-Error "Refusing to run on main. Create or switch to a task branch first." -ErrorAction Continue
        exit 2
    }

    if (-not (Test-Path $taskPath -PathType Leaf)) {
        Write-Error "Active task card not found: $taskPath" -ErrorAction Continue
        exit 2
    }

    $task = Get-Content $taskPath -Raw
    $goal = [regex]::Match($task, "(?im)^Goal:\s*(.+?)\s*$")
    $changeClass = [regex]::Match($task, "(?im)^Change class:\s*([A-D])\s*$")
    if (-not $goal.Success -or $goal.Groups[1].Value.Trim() -in @("", "<one sentence>") -or -not $changeClass.Success) {
        Write-Error "The active task card must contain a concrete Goal and a Change class from A through D." -ErrorAction Continue
        exit 2
    }

    if (-not (Test-Path $preflightPath -PathType Leaf)) {
        Write-Error "Preflight script not found: $preflightPath" -ErrorAction Continue
        exit 2
    }

    $codexCommand = Get-CodexCommand
    if (-not $codexCommand) {
        Write-Error "Codex CLI not found. Install it and ensure codex is available on PATH." -ErrorAction Continue
        exit 2
    }

    $coordinatorPrompt = @"
Work the already user-approved active task in .agent/current-task.md. Follow AGENTS.md. Implement and verify it locally.
Do not ask for design or plan confirmation. A bounded task with acceptance criteria is not a user decision gate.
Use the active python command for local tests. Do not assume .venv\Scripts\python.exe.
Do not load optional user-level plugins or configuration. Keep token/context usage minimal.
Work autonomously: inspect, edit, run focused tests, diagnose failures, and retry without asking for routine permission.
Do not run scripts/preflight.ps1; the outer development script owns the final preflight gate.
Do not push, merge, commit, release, or trigger GitHub Actions. Use zero subagents by default.
Stop only at a decision gate defined in AGENTS.md.
End your final response with exactly one line: USER_DECISION_REQUIRED: yes or no
"@

    $threadId = $null
    $decisionRequired = $null
    $commonArgs = @(
        "exec",
        "--approve-for-me",
        "--ignore-user-config",
        "--cd", $root
    )
    # Batch launchers truncate multiline arguments; keep each prompt in one argument.
    $initialArgs = $commonArgs + @("--json", ($coordinatorPrompt -replace "\r?\n", " "))

    Write-Host "Starting Codex coordinator for .agent/current-task.md..."
    $codexExit = Invoke-CodexTurn -CodexCommand $codexCommand -Arguments $initialArgs -ThreadId ([ref]$threadId) -DecisionRequired ([ref]$decisionRequired)
    if ($codexExit -ne 0 -or -not $threadId) {
        Write-CompletionSummary -TestResult "not run (Codex coordinator failed)" -DecisionRequired $true
        exit 1
    }
    if ($decisionRequired -ne $false) {
        Write-CompletionSummary -TestResult "not run (user decision required)" -DecisionRequired $true
        exit 2
    }

    $preflightOutput = @()
    $preflightExit = Invoke-Preflight -Output ([ref]$preflightOutput)
    $repairCycle = 0

    while ($preflightExit -ne 0 -and $repairCycle -lt $MaxRepairCycles) {
        $repairCycle++
        $failureTail = @($preflightOutput | Select-Object -Last 200) -join [Environment]::NewLine
        $repairPrompt = @"
The outer local preflight failed (automatic repair cycle $repairCycle of $MaxRepairCycles).
Diagnose the failure, make the smallest in-scope repair, and run only focused checks needed to validate it.
Do not run scripts/preflight.ps1; the outer development script will retry it.
Do not push, merge, commit, release, or trigger GitHub Actions.

Preflight output:
$failureTail

End your final response with exactly one line: USER_DECISION_REQUIRED: yes or no
"@
        $decisionRequired = $null
        $resumeArgs = $commonArgs + @("resume", "--json", $threadId, ($repairPrompt -replace "\r?\n", " "))
        Write-Host ""
        Write-Host "Resuming the same Codex coordinator for repair cycle $repairCycle..."
        $codexExit = Invoke-CodexTurn -CodexCommand $codexCommand -Arguments $resumeArgs -ThreadId ([ref]$threadId) -DecisionRequired ([ref]$decisionRequired)
        if ($codexExit -ne 0 -or $decisionRequired -ne $false) {
            break
        }

        $preflightOutput = @()
        $preflightExit = Invoke-Preflight -Output ([ref]$preflightOutput)
    }

    $passed = $preflightExit -eq 0
    $needsDecision = (-not $passed) -or ($decisionRequired -ne $false) -or ($codexExit -ne 0)
    $testResult = if ($passed) { "preflight passed" } else { "preflight failed after $repairCycle repair cycle(s)" }
    Write-CompletionSummary -TestResult $testResult -DecisionRequired $needsDecision

    if ($passed -and -not $needsDecision) {
        exit 0
    }
    exit 1
}
finally {
    Pop-Location
}
