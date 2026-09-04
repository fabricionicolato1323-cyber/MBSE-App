# MBSE-App Development Workflow

## Purpose

The MBSE-App has moved beyond a small prototype. Changes can now affect ontology, graph semantics, persistence, guided interaction, diagrams, SysML/SAM projection, and multiple test layers at the same time.

The development process therefore follows a **specification-driven, agent-assisted workflow**:

```text
Problem / desired behavior
        ↓
Semantic + UX decision
        ↓
Feature specification
        ↓
Repository-wide implementation plan
        ↓
Codex / coding-agent implementation
        ↓
Focused tests
        ↓
Full regression tests / CI
        ↓
Architecture + behavior review
        ↓
Merge
```

The goal is not more documentation. The goal is to prevent local code changes from silently changing model semantics or increasing user cognitive load.

## Responsibilities

### Product / methodology discussion

Use design discussion to decide:

- what the modeling concept means;
- what user decision is required;
- what must remain deterministic;
- what the LLM may only suggest;
- how much information the user sees at one time;
- whether the change affects Arcadia or SysML semantics.

These decisions must be reflected in a feature specification before implementation begins.

### Coding agent / Codex

Use the coding agent to:

- inspect the repository and identify all affected modules;
- propose an implementation plan against the feature spec;
- implement the change across layers;
- update tests;
- run tests and diagnose failures;
- review the diff for accidental coupling or duplicated semantics.

The agent must follow `AGENTS.md`.

## Change classes

### Class A — local presentation change

Examples: spacing, text styling, a non-semantic visual adjustment.

Usually requires:

- UI/static/template change;
- focused contract test;
- E2E only when visible behavior or interaction changed.

A full feature spec is optional if model semantics and workflow are untouched.

### Class B — application behavior change

Examples: new guided question, new user decision path, load/resume behavior, scenario editing behavior.

Requires:

- feature spec;
- application-flow impact review;
- model/persistence impact check;
- focused unit/contract tests;
- E2E when browser-visible.

### Class C — model-semantic change

Examples: new relation, decomposition rule, validation rule, model element behavior, persistent attribute.

Requires:

- feature spec with explicit semantic rules;
- ontology review;
- graph mutation/invariant review;
- validation review;
- persistence compatibility review;
- UI/workflow review;
- SysML/SAM impact review;
- unit + contract tests and relevant E2E coverage.

### Class D — architectural change

Examples: splitting application/domain layers, introducing an operation/command boundary, moving mutation ownership, replacing persistence mechanisms.

Requires:

- architecture spec;
- explicit invariants and non-goals;
- staged migration plan;
- backward-compatibility plan;
- regression evidence before each migration step;
- no big-bang rewrite unless there is a compelling documented reason.

## Feature-spec lifecycle

Feature specifications live in `docs/specs/`.

Use `FEATURE_SPEC_TEMPLATE.md` and give each substantial spec a stable filename, for example:

```text
0001-architecture-boundary-consolidation.md
0002-operational-scenario-refinement.md
0003-sysml-projection-extension.md
```

A spec should answer four things before coding starts:

1. What user/product problem are we solving?
2. What model/semantic rules must hold?
3. Which behavior is explicitly out of scope?
4. How will we prove the implementation is correct?

## Implementation-plan requirement

Before editing code for Class B/C/D work, the coding agent should produce a compact plan containing:

- current implementation paths discovered;
- affected layers;
- invariants that must remain true;
- intended file/module changes;
- tests to add or update;
- compatibility risks.

Do not accept plans that merely repeat the feature spec. The plan must be grounded in the current repository.

## Cross-layer impact checklist

For every semantic change, explicitly mark each item as **affected** or **not affected**:

```text
[ ] ontology.py / ontology rules
[ ] graph_model.py / graph_model_base.py
[ ] validator.py / deterministic validation
[ ] model_io.py / load + save compatibility
[ ] guided terminal/application flow
[ ] web bridge / web worker / web application
[ ] templates / static presentation
[ ] operational scenarios
[ ] diagrams
[ ] revision / undo behavior
[ ] knowledge base / SHACL comparison
[ ] SysML v2 export
[ ] SAM synchronization/projection
[ ] unit tests
[ ] UI contract tests
[ ] E2E tests
```

"Not affected" should be a conscious decision, not an omission.

## Test strategy

### Fast feedback

Run the narrow tests closest to the change first.

Examples:

```bash
python -m pytest -q tests/test_operational_scenario.py
python -m pytest -q tests/test_sysml_v2.py
python -m pytest -q tests/test_web_bridge.py
```

### Repository regression

Before merge of Class B/C/D changes:

```bash
python -m pytest -q
```

### Browser behavior

For browser-visible behavioral changes, run relevant Playwright tests. For broad UI changes:

```bash
RUN_E2E=1 python -m pytest -q tests/e2e
```

CI remains the final cross-platform gate and currently covers Ubuntu, Windows, Python 3.12, SysML contracts, and Chromium E2E.

## Review questions

Every non-trivial PR should be reviewed against these questions:

1. Did the implementation change methodology beyond the spec?
2. Can any LLM path now mutate persistent model state directly or indirectly without deterministic validation?
3. Can inferred content become persistent without an explicit user decision?
4. Is the same model fact now represented in more than one place?
5. Did a UI convenience create a second semantic rule outside the domain/model layer?
6. Did the change increase the amount of information or number of decisions presented to the user at once?
7. Are load/resume, diagrams, scenarios, SysML, or SAM now inconsistent with the canonical graph?
8. Are new tests proving behavior rather than merely reproducing implementation details?

## Recommended branch and PR pattern

Use one branch per coherent spec or tightly scoped fix:

```text
feature/<short-feature-name>
fix/<short-problem-name>
refactor/<short-boundary-name>
```

Each PR should:

- link or name the feature spec;
- summarize the semantic/architectural effect;
- list tests run;
- identify remaining debt or deferred follow-up;
- avoid mixing unrelated cleanup with feature work.

## Transition rule for the current codebase

Do not reorganize the entire repository just to match an ideal layered directory structure. The current code is working and well-covered by tests. Introduce clearer boundaries incrementally when a feature gives a concrete reason to do so.

The desired direction is:

```text
Interaction / presentation
        ↓
Application operations
        ↓
Deterministic domain + ontology rules
        ↓
Canonical model graph
        ↓
Persistence / projections
```

LLM services remain advisory beside the interaction/application layers and never become a persistence authority.
