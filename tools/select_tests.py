#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def git_lines(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]


def changed_paths(base: str | None) -> list[str]:
    paths: set[str] = set()

    if base:
        merge_base = git_lines("merge-base", "HEAD", base)
        if merge_base:
            paths.update(git_lines("diff", "--name-only", merge_base[0], "HEAD"))

    paths.update(git_lines("diff", "--name-only"))
    paths.update(git_lines("diff", "--name-only", "--cached"))
    paths.update(git_lines("ls-files", "--others", "--exclude-standard"))

    if not paths:
        paths.update(git_lines("show", "--pretty=format:", "--name-only", "HEAD"))

    return sorted(paths)


def add_if_exists(selected: set[str], relative_path: str) -> bool:
    candidate = ROOT / relative_path
    if candidate.is_file():
        selected.add(relative_path.replace("\\", "/"))
        return True
    return False


def add_glob(selected: set[str], pattern: str) -> None:
    for path in ROOT.glob(pattern):
        if path.is_file():
            selected.add(path.relative_to(ROOT).as_posix())


def tests_for_path(path: str) -> set[str]:
    selected: set[str] = set()
    p = Path(path)
    name = p.name
    stem = p.stem

    if path == "scripts/dev.ps1":
        add_if_exists(selected, "tests/test_dev_script.py")

    if path.startswith("tests/") and path.endswith(".py") and not path.startswith("tests/e2e/"):
        add_if_exists(selected, path)
        return selected

    if path.endswith(".py"):
        add_if_exists(selected, f"tests/test_{stem}.py")
        add_if_exists(selected, f"{stem}_test.py")

    if path in {"ontology.py", "graph_model.py", "graph_model_base.py", "validator.py", "model_io.py", "semantic_policy.py"}:
        for candidate in (
            "tests/test_semantic_policy.py",
            "tests/test_model_io.py",
            "tests/test_operational_scenario.py",
            "tests/test_participant_classification_simple.py",
        ):
            add_if_exists(selected, candidate)

    if path == "operational_scenario.py" or "scenario" in name:
        add_if_exists(selected, "tests/test_operational_scenario.py")

    if path.startswith("web_") or path.startswith("templates/") or path.startswith("static/"):
        for candidate in (
            "tests/test_web_app.py",
            "tests/test_web_bridge.py",
            "tests/test_web_ui_policy.py",
        ):
            add_if_exists(selected, candidate)

    if path.startswith("static/oa_") or "diagram" in name:
        for candidate in (
            "tests/test_oa_diagram_v3_contract.py",
            "tests/test_oa_interactive_diagram_contract.py",
            "tests/test_oa_workspace_layout_contract.py",
        ):
            add_if_exists(selected, candidate)

    if path.startswith("sysml") or "/sysml" in path or name.startswith("sysml"):
        add_glob(selected, "tests/test_sysml*.py")

    if name.startswith("sam_"):
        add_if_exists(selected, f"tests/test_{stem}.py")

    if path.startswith("knowledge_graph"):
        add_if_exists(selected, "knowledge_graph_test.py")

    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Select focused local tests from the current Git diff.")
    parser.add_argument("--base", default=None, help="Optional base ref; merge-base..HEAD is included.")
    parser.add_argument("--python-files", action="store_true", help="Print changed Python files instead of tests.")
    parser.add_argument("--show-changed", action="store_true", help="Print changed paths and exit.")
    args = parser.parse_args()

    changed = changed_paths(args.base)

    if args.show_changed:
        for path in changed:
            print(path)
        return 0

    if args.python_files:
        for path in changed:
            if path.endswith(".py") and (ROOT / path).is_file():
                print(path)
        return 0

    selected: set[str] = set()
    unrecognized_code = False

    for path in changed:
        mapped = tests_for_path(path)
        selected.update(mapped)

        if Path(path).suffix.lower() in {".py", ".js", ".html"}:
            if not mapped and not path.startswith(("scripts/", "tools/")):
                unrecognized_code = True

    for test in sorted(selected):
        print(test)

    if unrecognized_code:
        print("__FULL__")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
