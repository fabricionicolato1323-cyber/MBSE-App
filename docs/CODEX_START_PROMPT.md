# Codex Start Prompt — Architecture Boundary Phase 1

Use the prompt below to start the first implementation task after the workflow-governance PR is merged.

```text
Work in the MBSE-App repository.

Read and follow AGENTS.md first.
Then read:
- docs/DEVELOPMENT_WORKFLOW.md
- docs/specs/0001-architecture-boundary-consolidation.md

Task:
Implement only Phase 1 of specification 0001, plus one minimal low-risk vertical slice if necessary to prove the seam. Do not start Phase 2 broadly and do not refactor unrelated modules.

Goals:
1. Introduce a small deterministic application-operation seam around existing persistent OAGraph mutations.
2. Keep OAGraph / ontology.py as the canonical semantic authority. Do not copy allowed-relation, decomposition, or participant rules into the new operation layer.
3. Preserve the current deterministic write barrier and explicit user-confirmation requirements.
4. Do not change Arcadia semantics, saved-model format, SysML/SAM semantics, UI wording policy, or Ollama behavior.
5. Select the lowest-risk existing mutation with good tests to demonstrate the seam end-to-end. Inspect the repository and tests before choosing it.
6. Preserve current undo/checkpoint behavior.

Before editing:
- inspect the current mutation call paths for the candidate slice;
- identify every affected layer;
- give a short implementation plan grounded in actual files;
- state which architecture invariants from spec 0001 are relevant.

Implementation requirements:
- use an explicit result/operation contract that can report success/failure, deterministic rejection reason, affected model IDs, and whether a persistent mutation occurred;
- keep semantic validation delegated to existing graph/domain code;
- do not create a second model store or shadow semantic state;
- keep changes small enough for one reviewable PR;
- remove no existing path until replacement behavior is covered by tests.

Testing:
- add focused tests for valid operation, invalid operation/no mutation, affected IDs, and undo after accepted mutation;
- run the narrow relevant tests first;
- run `python -m pytest -q` before declaring completion;
- if the chosen slice is browser-visible, run the relevant UI contract and E2E tests;
- if it affects facts consumed by SysML/SAM, run those corresponding contract tests explicitly.

At the end:
- summarize changed files and the architectural boundary introduced;
- list every test command run and its result;
- identify any direct mutation paths deliberately left for later phases;
- confirm explicitly that no model semantics or persistence format changed.
```

## Review prompt after implementation

Use this separately after the implementation is complete:

```text
Review the current diff against AGENTS.md and docs/specs/0001-architecture-boundary-consolidation.md.

Look specifically for:
- duplicated semantic validation outside OAGraph/ontology;
- any LLM/advisory path that can trigger persistence without the required explicit user decision;
- operation-layer state that could become a second source of truth;
- broken undo/checkpoint behavior;
- persistence/load-resume incompatibility;
- UI behavior that increases cognitive load;
- missing SysML/SAM or E2E regressions;
- refactoring beyond Phase 1 scope.

Report findings by severity. If there are no blocking findings, state why the boundary is safe enough to merge and list follow-up work for Phase 2.
```
