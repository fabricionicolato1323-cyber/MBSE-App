from __future__ import annotations

import json
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
        '@echo off\npython "%~dp0fake_codex.py" %*\n', encoding="utf-8"
    )
    (fake_bin / "fake_codex.py").write_text(
        """import json
import os
import sys
from pathlib import Path

with Path(os.environ["FAKE_CODEX_LOG"]).open("a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
print(json.dumps({"type": "thread.started", "thread_id": "test-thread"}))
print(json.dumps({"type": "item.completed", "item": {
    "type": "agent_message", "text": "done\\nUSER_DECISION_REQUIRED: no"
}}))
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

    invocations = [json.loads(line) for line in (root / "codex.log").read_text(encoding="utf-8").splitlines()]
    assert len(invocations) == 3
    common = [
            "exec",
            "--approve-for-me",
            "--ignore-user-config",
            "-c",
            "model_reasoning_effort=low",
            "-c",
            "model_verbosity=low",
            "--cd",
            str(root),
        ]
    assert invocations[0][:-1] == common + ["--json"]
    for invocation in invocations[1:]:
        assert invocation[:-1] == common + ["resume", "--json", "test-thread"]
        assert "Do not run scripts/preflight.ps1" in invocation[-1]
        assert "Do not push, merge, commit, release, or trigger GitHub Actions" in invocation[-1]


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


def test_dev_sends_approved_task_and_active_python_instructions(tmp_path: Path) -> None:
    root, fake_bin, script = _make_repo(tmp_path, "task/test")

    result = _run_dev(root, fake_bin, script, failures=0)

    assert result.returncode == 0, result.stdout
    invocation = json.loads((root / "codex.log").read_text(encoding="utf-8"))
    prompt = invocation[-1]
    assert "already user-approved" in prompt
    assert "Do not ask for design or plan confirmation" in prompt
    assert "A bounded task with acceptance criteria is not a user decision gate" in prompt
    assert "Use the active python command for local tests" in prompt
    assert "Do not assume .venv" in prompt
    assert "Do not load optional user-level plugins or configuration" in prompt
    assert "Do not run scripts/preflight.ps1" in prompt
    assert "Do not push, merge, commit, release, or trigger GitHub Actions" in prompt
    assert "Use zero subagents by default" in prompt
    assert "Stop only at a decision gate defined in AGENTS.md" in prompt
    assert "USER_DECISION_REQUIRED: yes or no" in prompt
