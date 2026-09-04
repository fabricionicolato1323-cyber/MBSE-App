# MBSE-App Agent Instructions

This file defines durable engineering instructions for coding agents working in this repository.

## Product intent

MBSE-App is a human-in-the-loop guided builder for Arcadia Operational Analysis. Its primary UX goal is to reduce cognitive load by asking for small, explicit decisions while keeping the user in control of every persistent modeling decision.

## Non-negotiable architectural guardrails

1. **Deterministic write barrier**
   - The deterministic Python layer is the only authority allowed to mutate the persistent user model.
   - LLM/Ollama code may interpret, suggest, explain, rank, or propose operations, but must not write directly to the NetworkX model.
   - Every persistent mutation must pass deterministic validation.

2. **Human approval before persistence**
   - Do not turn extracted candidates, LLM suggestions, inferred relationships, or semantic frames into model elements without an explicit user decision.
   - Keep transient parsing concepts out of the persistent OA graph.

3. **Methodology before implementation**
   - Do not invent new Arcadia/MBSE semantics to make a coding task easier.
   - If a requested implementation changes the meaning of an Operational Capability, Actor, Entity, Activity, Exchange, Communication Mean, Scenario, decomposition relation, or SysML projection, stop implementation at the design boundary and document the semantic decision required in the feature spec.

4. **One source of truth for model semantics**
   - Reuse existing graph relations and ontology rules when they already express the intended fact.
   - Do not create parallel representations of the same model fact in another module, cache, UI state, or export layer.

5. **User-facing cognitive-load policy**
   - Prefer one small decision at a time.
   - Preserve progressive disclosure and existing domain-neutral guidance.
   - Do not expose internal Arcadia terminology in user-facing text when the current UI deliberately uses friendly terms such as goal, participant, action, interaction, and communication method.

6. **LLM independence**
   - The application must remain usable in deterministic mode without Ollama for paths that do not require it.
   - Never hardcode a specific model name in code, tests, prompts, or documentation.

7. **Cross-layer consistency**
   Any model-semantic change must be checked across the relevant layers:
   - ontology and relation rules;
   - graph mutation and validation;
   - persistence/load-resume behavior;
   - guided interaction/application flow;
   - web/terminal presentation;
   - diagrams and scenario views;
   - SysML v2 / SAM projections;
   - undo/revision behavior when applicable;
   - unit, contract, and E2E tests.

## Repository orientation

Important existing modules include:

- `ontology.py` — restricted persistent OA ontology and allowed relations.
- `graph_model.py` / `graph_model_base.py` — persistent model graph behavior and model integrity rules.
- `validator.py` — deterministic checks.
- `llm_service.py`, `web_ai.py` — advisory local AI integration.
- `operational_scenario.py` — scenario behavior.
- `model_io.py` — persistence.
- `sysml_v2.py`, `sysml_level1.py`, `sam_*.py` — SysML/SAM projections and synchronization.
- `web_*.py`, `templates/`, `static/` — interaction and web presentation.
- `tests/` and `tests/e2e/` — unit/contract and browser-level regression tests.
- `knowledge_base/` — methodology reference, RDF/OWL claims, and SHACL material.

Do not assume these boundaries are perfect. Improve them incrementally rather than performing a big-bang rewrite.

## Required workflow for non-trivial changes

1. Read the relevant feature spec under `docs/specs/`.
2. Inspect the actual implementation paths before editing.
3. Write a short implementation plan that identifies affected layers and invariants.
4. Make the smallest coherent change that satisfies the spec.
5. Add or update tests for the changed behavior.
6. Run the narrowest relevant tests first, then the broader suite required by the change.
7. Review the final diff for duplicated semantics, new coupling, hidden model writes, and accidental UX complexity.
8. Summarize what changed, tests run, and any remaining architectural debt.

If no feature spec exists for a non-trivial semantic or architectural change, create one from `docs/specs/FEATURE_SPEC_TEMPLATE.md` before implementing.

## Test expectations

At minimum:

```bash
python -m pytest -q
```

For web behavior, run the relevant contract tests and, when behavior is browser-visible, the E2E suite or the narrow E2E test(s):

```bash
RUN_E2E=1 python -m pytest -q tests/e2e
```

For SysML/SAM changes, run the corresponding SysML/SAM contract tests in addition to the normal suite.

The GitHub CI matrix validates Python 3.12 on Ubuntu and Windows and runs Chromium E2E tests. Do not intentionally weaken CI coverage to make a change pass.

## Refactoring policy

- Prefer seams, adapters, extraction, and dependency inversion over wholesale rewrites.
- Preserve externally visible behavior unless the feature spec explicitly changes it.
- Separate interpretation/advice from validated application operations.
- Move model mutation toward explicit deterministic operations rather than allowing UI, LLM, or projection code to mutate model state ad hoc.
- Keep commits reviewable and scoped to one specification.

## Definition of done

A change is done only when:

- the feature spec acceptance criteria are met;
- deterministic model integrity is preserved;
- no LLM path bypasses user confirmation or validation;
- affected persistence and projection paths remain consistent;
- relevant tests pass;
- the implementation does not introduce a second source of truth for model semantics;
- the PR explains the architectural impact and test evidence.
