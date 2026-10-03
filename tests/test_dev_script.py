from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")

pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="Windows PowerShell is required")


def _make_repo(tmp_path: Path, branch: str, *, valid_task: bool = True) -> tuple[Path, Path, Path]:
    root = tmp_path / "repo"
    scripts = root / "scripts"
    agent = root / ".agent"
    fake_bin = root / "fake-bin"
    scripts.mkdir(parents=True)
    agent.mkdir()
    fake_bin.mkdir()

    shutil.copy2(ROOT / "scripts" / "dev.ps1", scripts / "dev.ps1")
    task = """# Active Task

Goal: Exercise the local orchestrator.
Change class: A
"""
    if not valid_task:
        task = task.replace("Exercise the local orchestrator.", "<one sentence>")
    (agent / "current-task.md").write_text(task, encoding="utf-8")

    (scripts / "preflight.ps1").write_text(
        """$ErrorActionPreference = "Stop"
$countPath = $env:FAKE_PREFLIGHT_COUNT
$count = 0
if (Test-Path $countPath) { $count = [int](Get-Content $countPath -Raw) }
$count++
Set-Content -Path $countPath -Value $count
Write-Host "preflight run $count"
if ($count -le [int]$env:FAKE_PREFLIGHT_FAILURES) { Write-Error "simulated preflight failure" }
exit 0
""",
        encoding="utf-8",
    )
    (fake_bin / "codex.cmd").write_text(
        """@echo off
if not "%~1"=="exec" goto invalid
if not "%~2"=="--approve-for-me" goto invalid
if not "%~3"=="--cd" goto invalid
if not "%~4"=="%FAKE_REPO_ROOT%" goto invalid
if "%~5"=="resume" goto resume
if not "%~5"=="--json" goto invalid
echo initial>>"%FAKE_CODEX_LOG%"
goto output
:resume
if not "%~6"=="--json" goto invalid
if not "%~7"=="test-thread" goto invalid
echo resume:%~7>>"%FAKE_CODEX_LOG%"
:output
echo {"type":"thread.started","thread_id":"test-thread"}
echo {"type":"item.completed","item":{"type":"agent_message","text":"done\\nUSER_DECISION_REQUIRED: no"}}
exit /b 0
:invalid
exit /b 9
""",
        encoding="utf-8",
    )

    subprocess.run(
        ["git", "init", "-b", branch],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return root, fake_bin, scripts / "dev.ps1"


def _run_dev(root: Path, fake_bin: Path, script: Path, *, failures: int) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    env["FAKE_CODEX_LOG"] = str(root / "codex.log")
    env["FAKE_REPO_ROOT"] = str(root)
    env["FAKE_PREFLIGHT_COUNT"] = str(root / "preflight-count.txt")
    env["FAKE_PREFLIGHT_FAILURES"] = str(failures)
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )


def test_dev_refuses_main_before_starting_codex(tmp_path: Path) -> None:
    root, fake_bin, script = _make_repo(tmp_path, "main")

    result = _run_dev(root, fake_bin, script, failures=0)

    assert result.returncode == 2
    assert "Refusing to run on main" in result.stdout
    assert not (root / "codex.log").exists()


def test_dev_reuses_coordinator_and_retries_preflight_twice(tmp_path: Path) -> None:
    root, fake_bin, script = _make_repo(tmp_path, "task/test")

    result = _run_dev(root, fake_bin, script, failures=2)

    assert result.returncode == 0, result.stdout
    assert "Test result: preflight passed" in result.stdout
    assert "User decision required: no" in result.stdout
    assert (root / "preflight-count.txt").read_text(encoding="utf-8").strip() == "3"

    invocations = (root / "codex.log").read_text(encoding="utf-8").splitlines()
    assert invocations == ["initial", "resume:test-thread", "resume:test-thread"]


def test_dev_reports_failure_after_default_repair_limit(tmp_path: Path) -> None:
    root, fake_bin, script = _make_repo(tmp_path, "task/test")

    result = _run_dev(root, fake_bin, script, failures=3)

    assert result.returncode == 1
    assert "Test result: preflight failed after 2 repair cycle(s)" in result.stdout
    assert "User decision required: yes" in result.stdout
    assert (root / "preflight-count.txt").read_text(encoding="utf-8").strip() == "3"


def test_dev_rejects_placeholder_task(tmp_path: Path) -> None:
    root, fake_bin, script = _make_repo(tmp_path, "task/test", valid_task=False)

    result = _run_dev(root, fake_bin, script, failures=0)

    assert result.returncode == 2
    assert "must contain a concrete Goal" in result.stdout
    assert not (root / "codex.log").exists()
