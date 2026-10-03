# Local-First Development

## Goal

Use one Codex coordinator, deterministic local tools, and local tests for normal development. GitHub Actions is an explicit remote verification step, not part of every push.

## One-time local setup

From the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pytest
```

Install Playwright only when browser E2E is needed:

```powershell
pip install playwright
python -m playwright install chromium
```

## Start a task

Create the local task card:

```powershell
.\scripts\new-task.ps1
```

Edit:

```text
.agent/current-task.md
```

Keep it short. The task card contains the goal, change class, acceptance criteria, invariants, scope, and whether browser E2E is expected.

## Single Codex coordinator

Start Codex in the repository and use one short instruction:

```text
Work the active task in .agent/current-task.md.
Follow AGENTS.md.
Execute routine implementation and local verification without asking me for each step.
Stop only at a decision gate defined in AGENTS.md.
```

Do not repeat architecture history or paste long specs into the prompt. The coordinator should load only the spec/files needed by the task.

## Automatic local verification

Fast feedback:

```powershell
.\scripts\test-fast.ps1
```

Full Python regression:

```powershell
.\scripts\test-full.ps1
```

Browser E2E:

```powershell
.\scripts\test-e2e.ps1
```

One-command task gate:

```powershell
.\scripts\preflight.ps1
```

`preflight.ps1` always runs focused tests. It automatically adds the full regression for Class B/C/D and E2E when `Browser-visible: yes` is set in the task card.

## What the coordinator should do without asking

- inspect relevant files;
- edit code/docs/tests;
- run focused tests;
- diagnose and retry local failures;
- run the required full regression/E2E based on the task card;
- review the final diff;
- prepare a concise commit summary.

## What still requires a user decision

- unresolved methodology/model semantics;
- incompatible/destructive migration;
- push or merge;
- release;
- remote GitHub Actions.

## GitHub Actions policy

The workflow is manual-only (`workflow_dispatch`). Available profiles:

- `linux-tests` — lowest-cost remote Python verification;
- `cross-platform` — Ubuntu + Windows Python regression;
- `sysml` — SysML contract only;
- `e2e` — Chromium browser suite only;
- `full` — cross-platform + SysML + E2E.

Use remote CI only when a milestone, merge, release, or platform-specific doubt justifies the cost.

## Recommended daily loop

```text
Discuss/decide feature
        ↓
short .agent/current-task.md
        ↓
one Codex coordinator
        ↓
local edit + focused tests
        ↓
automatic local preflight
        ↓
coordinator summary
        ↓
user decides push / merge / remote CI
```
