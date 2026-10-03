from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools import select_tests


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_untracked_non_ignored_files_participate_in_focused_selection(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    repo = tmp_path / "repo"
    tests = repo / "tests"
    tests.mkdir(parents=True)
    _git(repo, "init")

    (repo / ".gitignore").write_text("ignored.py\ntests/test_ignored.py\n", encoding="utf-8")
    (repo / "new_feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tests / "test_new_feature.py").write_text("def test_new_feature(): pass\n", encoding="utf-8")
    (repo / "ignored.py").write_text("VALUE = 2\n", encoding="utf-8")
    (tests / "test_ignored.py").write_text("def test_ignored(): pass\n", encoding="utf-8")

    monkeypatch.setattr(select_tests, "ROOT", repo)
    monkeypatch.setattr(sys, "argv", ["select_tests.py"])

    assert set(select_tests.changed_paths(None)) == {
        ".gitignore",
        "new_feature.py",
        "tests/test_new_feature.py",
    }
    assert select_tests.main() == 0
    assert capsys.readouterr().out.splitlines() == ["tests/test_new_feature.py"]
