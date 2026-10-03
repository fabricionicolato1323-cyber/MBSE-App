# Codex Start Prompt — Architecture Boundary Phase 1

This task should be run through the local-first coordinator workflow.

Create/edit `.agent/current-task.md` from `.agent/TASK_TEMPLATE.md` and set:

```text
Goal: Implement only Phase 1 of docs/specs/0001-architecture-boundary-consolidation.md, plus the smallest low-risk vertical slice needed to prove the seam.
Change class: D
Browser-visible: no
SysML/SAM impact: review
```

Then start the coordinator with only:

```text
Work the active task in .agent/current-task.md.
Follow AGENTS.md.
Read docs/specs/0001-architecture-boundary-consolidation.md.
Execute routine implementation and local verification without asking me for each step.
Stop only at a decision gate defined in AGENTS.md.
```

The coordinator must preserve the deterministic write barrier, canonical `OAGraph` authority, current confirmation semantics, undo behavior, save/load compatibility, SysML/SAM semantics, and UI wording policy.

Use `.\scripts\preflight.ps1` as the final local gate. Do not trigger GitHub Actions unless the user explicitly requests remote verification.
