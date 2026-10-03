# 0001 — Architecture Boundary Consolidation

## 1. Summary

Consolidate the MBSE-App around an explicit application-operation boundary between interaction/advisory code and the canonical deterministic model graph. The migration must preserve existing behavior and Arcadia semantics while reducing the risk that future features implement model rules independently in UI, LLM, persistence, or projection code.

This is an incremental architecture migration, not a rewrite.

## 2. Current situation

The repository already has strong foundations:

- `ontology.py` defines the restricted persistent OA ontology and allowed relations;
- `graph_model.py` and `graph_model_base.py` enforce canonical graph mutation rules and maintain undo checkpoints;
- the README explicitly defines the deterministic Python layer as the write barrier;
- Ollama remains advisory and the application can continue in deterministic mode;
- the repository has broad unit/contract coverage, Windows + Ubuntu CI, and Chromium E2E tests.

The primary architecture pressure is orchestration coupling rather than a broken semantic model.

`app_base.py` currently combines multiple responsibilities, including terminal interaction, application orchestration, knowledge-base access, candidate interpretation, LLM coordination, and direct use of the canonical graph. The web experience is layered over the terminal workflow through `web_bridge.py` / `web_worker.py`, including terminal-process and prompt-protocol concerns.

This structure has worked well for rapid evolution, but future semantic features increasingly risk requiring coordinated edits across large modules and multiple presentation/projection paths.

## 3. User/product problem

As the MBSE-App grows, a local implementation change can become inconsistent with another view of the same model. That creates two risks:

1. methodology drift — code behavior begins to define semantics instead of the agreed modeling method defining code behavior;
2. cognitive-load regression — a UI or flow shortcut bypasses the guided, explicit-decision interaction model.

The architecture should make the correct path easier: interpret intent, construct a proposed deterministic operation, validate it, apply it to the canonical graph only after the required user decision, and then project/read the result elsewhere.

## 4. Scope

### In scope

- define an explicit application-operation boundary for persistent model changes;
- keep `OAGraph` as the canonical model and deterministic mutation authority;
- make user-confirmed operations reusable by terminal and web interaction paths;
- separate advisory interpretation from persistent application operations;
- make operation results explicit enough for UI feedback, testing, and future auditability;
- migrate incrementally using vertical slices;
- preserve undo/checkpoint semantics;
- preserve save/load, diagrams, scenarios, SysML v2, and SAM behavior;
- improve testability of application behavior without relying only on terminal-text interaction.

### Out of scope

- replacing NetworkX;
- changing Arcadia semantics;
- changing the persistent file format unless a later spec explicitly requires it;
- replacing Ollama or selecting a specific LLM model;
- redesigning the web UI;
- rewriting all current modules into a new package hierarchy in one change;
- replacing the current web bridge in the first migration step;
- adding new modeling concepts as part of this refactor.

## 5. Architectural invariants

1. The canonical user model remains the deterministic `OAGraph` / NetworkX model.
2. Ontology and relation legality remain deterministic.
3. A persistent mutation occurs only through a deterministic model/application operation.
4. An LLM may propose operation inputs but cannot execute a persistent operation on its own authority.
5. Any operation based on inferred content must carry the same explicit user-confirmation requirement that exists today.
6. Transient parsing concepts remain outside the persistent OA graph.
7. No UI layer may introduce a second copy of a semantic rule that can disagree with the canonical deterministic rule.
8. Projections (diagram, SysML, SAM, knowledge comparison) are consumers of confirmed model state; they do not become model authorities.
9. Undo remains aligned with accepted persistent changes, not advisory or display-only events.
10. Existing saved models remain loadable unless a separately approved migration spec changes the format.

## 6. Desired logical direction

```text
User / Web / Terminal
        |
        v
Interaction + interpretation
  deterministic parsing and/or
  advisory LLM suggestion
        |
        v
Proposed application operation
        |
        v
Explicit user decision when required
        |
        v
Deterministic application operation
        |
        v
Ontology + graph invariant validation
        |
        v
Canonical OAGraph mutation
        |
        +-----------------------+
        |                       |
        v                       v
Persistence / resume      Read-only projections
                          diagrams / scenarios /
                          knowledge compare /
                          SysML / SAM
```

The diagram is a logical boundary. It does not require creating these exact directories or classes.

## 7. Operation contract

The migration should introduce a small explicit contract for application mutations. The exact Python representation is an implementation decision, but it must make these concepts observable:

- operation kind;
- validated inputs;
- whether explicit user confirmation is required/has been provided;
- success/failure;
- deterministic validation message when rejected;
- identifiers of model elements affected when successful;
- whether a persistent mutation occurred.

The operation layer must not duplicate ontology legality. It should call the canonical graph/domain rules.

## 8. Migration plan

### Phase 0 — Baseline protection

Before structural migration:

- run the current unit/contract suite;
- run relevant E2E coverage;
- record any existing failing tests separately;
- do not change behavior to make architecture work easier.

### Phase 1 — Introduce the application-operation seam

Add a small deterministic operation API around existing graph methods.

Requirements:

- no user-visible behavior change;
- no ontology change;
- no persistence-format change;
- direct tests proving accepted and rejected operations;
- operation code delegates semantic legality to existing graph/ontology rules.

Start with a low-risk existing mutation that has good test coverage. Do not migrate every mutation at once.

### Phase 2 — Migrate one vertical slice

Move one complete workflow slice to the shared operation boundary. A suitable slice should include:

- user input/selection;
- confirmation where required;
- deterministic operation;
- graph result;
- UI feedback;
- undo behavior;
- persistence/load regression test when relevant.

Candidate slices include characteristic editing, a simple participant/action relation, or another well-covered mutation. The coding agent must select the least risky slice after inspecting current tests.

### Phase 3 — Expand to model-semantic mutations

Migrate additional node/relation/decomposition/scenario mutations only after the first slice proves the contract.

For each migrated operation:

- preserve exact semantic validation;
- remove old direct mutation paths after tests prove the shared operation path;
- do not leave compatibility wrappers that can mutate independently indefinitely.

### Phase 4 — Reduce presentation/orchestration coupling

Once both terminal and web paths can use shared deterministic operations, gradually reduce reliance on terminal-text/protocol behavior for application semantics.

This phase may later justify a separate spec for replacing the terminal-process bridge. It is not required by this spec's first implementation PR.

## 9. Cross-layer impact

```text
[x] ontology.py / ontology rules — must remain semantically unchanged
[x] graph_model.py / graph_model_base.py — canonical mutation authority preserved
[x] validator.py — deterministic validation responsibilities preserved
[x] model_io.py / load + save compatibility — regression protection required
[x] guided terminal/application flow — progressively routed through shared operations
[x] web bridge / web worker / web application — progressively routed through shared operations
[ ] templates / static presentation — no redesign required
[x] operational scenarios — eventually migrate semantic mutations; not first slice unless selected
[x] diagrams — regression only; remain read-only projection
[x] revision / undo behavior — must map to accepted persistent operations
[x] knowledge graph / SHACL comparison — regression only; read-only
[x] SysML v2 export — regression only; read-only projection
[x] SAM synchronization/projection — regression only; read-only projection/sync behavior preserved
[x] unit tests
[x] UI contract tests when migrated behavior crosses UI boundary
[x] E2E tests when browser-visible behavior is migrated
```

## 10. Acceptance criteria for the first implementation PR

1. A deterministic application-operation seam exists and is covered by focused tests.
2. At least one existing persistent mutation uses the seam end-to-end.
3. The migrated operation still relies on canonical graph/ontology validation rather than copied rules.
4. No LLM code can invoke the migrated persistent operation without the same user-confirmation gate required by current behavior.
5. Undo behavior remains correct for the migrated operation.
6. Existing save/load behavior remains compatible.
7. No Arcadia concept meaning or allowed relation changes.
8. No user-visible workflow becomes more complex.
9. The full Python regression suite passes.
10. Relevant web contract/E2E tests pass if the migrated slice is browser-visible.
11. SysML/SAM tests remain green when the migrated model state participates in those projections.

## 11. Test plan

### Focused tests

Add tests for:

- valid operation accepted;
- invalid operation rejected with deterministic reason;
- no mutation on rejection;
- user-confirmation gate when required;
- affected node/relation IDs reported correctly;
- undo restores prior graph state after accepted operation.

### Regression

```bash
python -m pytest -q
```

### Browser-visible slice

Run the relevant contract test plus the narrow E2E test. Run the full E2E suite before merge when the shared operation changes broad interaction plumbing:

```bash
RUN_E2E=1 python -m pytest -q tests/e2e
```

### SysML/SAM

If the selected vertical slice affects model facts consumed by SysML/SAM, run the corresponding projection/synchronization contract tests explicitly in addition to the full suite.

## 12. Risks and mitigations

### Risk: operation layer becomes a second semantic authority

Mitigation: operation code orchestrates and delegates legality to `OAGraph`/ontology; it does not copy relation matrices or decomposition rules.

### Risk: overly broad refactor destabilizes the app

Mitigation: migrate one vertical slice at a time and keep old behavior until the replacement path has regression evidence.

### Risk: UI and terminal flows diverge

Mitigation: share deterministic application operations, not presentation code.

### Risk: undo history changes meaning

Mitigation: checkpoint only on accepted persistent graph mutations, preserving current `OAGraph` semantics.

### Risk: agent optimizes structure at the expense of methodology

Mitigation: `AGENTS.md`, this spec, and PR review checklist make semantic invariants explicit.

## 13. Definition of done for this architecture initiative

The initiative is complete when persistent model mutations are consistently executed through a deterministic application-operation boundary used by interaction surfaces, while `OAGraph` remains the canonical semantic authority; advisory LLM code is unable to bypass confirmation/validation; projections remain read-only consumers; and legacy direct mutation paths have been removed with regression coverage.

Completion may require multiple PRs. This spec intentionally supports incremental delivery.
