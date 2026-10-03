# MBSE-App Agent Instructions

Keep this file compact. It is loaded frequently and should contain only durable rules.

## Product intent

MBSE-App is a human-in-the-loop builder for Arcadia Operational Analysis. Reduce cognitive load, preserve explicit user decisions, and keep persistent model semantics deterministic.

## Non-negotiable invariants

1. **Canonical model authority**
   - `OAGraph` / NetworkX is the single source of truth for the persistent user model.
   - Ontology, relation legality, validation, and persistent mutations remain deterministic.

2. **LLM is advisory**
   - LLM/Ollama may interpret, suggest, explain, rank, or propose inputs.
   - It must never persist model facts directly or bypass deterministic validation.

3. **Human approval before semantic persistence**
   - Inferred candidates, relationships, or semantic frames require the same explicit user decision as today before persistence.
   - Transient parsing concepts stay outside the persistent graph.

4. **No invented methodology**
   - Do not change Arcadia/MBSE meaning to simplify implementation.
   - If a task requires a semantic decision not already specified, stop at that decision boundary and report it.

5. **No duplicate semantic source of truth**
   - Do not copy model rules into UI, LLM, caches, exports, or parallel stores.
   - Projections consume confirmed model state; they do not become authorities.

6. **Cognitive-load policy**
   - Prefer one small user decision at a time.
   - Preserve progressive disclosure and the existing friendly/domain-neutral wording policy.

7. **Deterministic mode remains viable**
   - Do not make Ollama mandatory for paths that can work deterministically.
   - Do not hardcode a specific model name.

## Single-coordinator operating model

- The primary Codex agent is the only user-facing coordinator.
- Execute routine repository inspection, editing, formatting, focused tests, regression tests, and diff review without asking the user for step-by-step permission.
- Default to **zero subagents**.
- A subagent is allowed only when independent work materially reduces risk or time, normally for Class C/D work or after two failed diagnosis attempts.
- Subagents never interact with the user. They return conclusions to the coordinator.
- Do not create more than two subagents unless the active task explicitly allows it.

Stop and ask the user only for a real decision, such as:
- unresolved model/methodology semantics;
- destructive or incompatible migration;
- use of secrets or an external account not already authorized;
- push, merge, release, or remote GitHub Actions execution.

## Active task

Use `.agent/current-task.md` as the short-lived task contract. It is local and intentionally ignored by Git.

Read only the repository files and detailed docs needed for the active task. Do not preload large documentation sets "just in case".

For Class B/C/D work, the active task must reference the relevant spec in `docs/specs/`.

## Local-first workflow

1. Read this file and `.agent/current-task.md`.
2. Inspect only the implementation paths needed for the task.
3. Produce a compact implementation plan grounded in those files.
4. Make the smallest coherent change.
5. Run `.\scripts\test-fast.ps1`.
6. For Class B/C/D work, run `.\scripts\test-full.ps1`.
7. For browser-visible behavior, run `.\scripts\test-e2e.ps1` or the narrow relevant E2E path.
8. Run `.\scripts\preflight.ps1` before proposing a commit/push.
9. Review the diff for duplicated semantics, hidden writes, accidental coupling, and UX complexity.
10. Return a concise summary: files changed, tests/results, remaining risk, and the next decision needed from the user.

## Cost and context policy

- Prefer deterministic local tools first: Git, search, Python, pytest, Playwright, formatters, and scripts.
- Reuse `AGENTS.md`, the active task card, and existing specs instead of repeating long prompts.
- Search narrowly before reading whole files; read whole subsystems only when necessary.
- Do not run the full regression repeatedly during edit/debug cycles; use focused tests first.
- Do not trigger GitHub Actions unless the user explicitly requests it.
- Keep agent output concise and decision-oriented.

## Repository orientation

- `ontology.py` — persistent OA ontology / allowed relations.
- `graph_model.py`, `graph_model_base.py` — canonical graph behavior and integrity.
- `validator.py` — deterministic checks.
- `model_io.py` — persistence.
- `llm_service.py`, `web_ai.py` — advisory AI.
- `operational_scenario.py` — scenario behavior.
- `sysml_v2.py`, `sysml_level1.py`, `sam_*.py` — projections/synchronization.
- `web_*.py`, `templates/`, `static/` — web interaction/presentation.
- `tests/`, `tests/e2e/` — regression coverage.
- `knowledge_base/` — methodology / RDF / SHACL references.

## Definition of done

A change is done when the active acceptance criteria are met, the deterministic write barrier and user-confirmation rules remain intact, relevant local tests pass, no second semantic authority was introduced, and any remaining debt/risk is stated explicitly.
