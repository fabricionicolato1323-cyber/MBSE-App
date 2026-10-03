# MBSE-App Development Workflow

## Purpose

MBSE-App uses a **specification-driven, local-first, agent-assisted workflow**. The objective is to protect model semantics and cognitive-load rules while minimizing repeated LLM context and remote CI cost.

```text
Problem / desired behavior
        ↓
Semantic + UX decision
        ↓
Short active task + referenced feature spec
        ↓
One Codex coordinator
        ↓
Local implementation
        ↓
Focused local tests
        ↓
Required local regression / E2E
        ↓
Architecture + behavior review
        ↓
User decision: push / merge / optional remote CI
```

Detailed operating commands live in `docs/LOCAL_DEVELOPMENT.md`. Durable agent rules live in `AGENTS.md`.

## Responsibilities

### Product / methodology discussion

Decide what the modeling concept means, what user decision is required, what must remain deterministic, what the LLM may only suggest, and whether Arcadia/SysML semantics change.

For Class B/C/D changes, capture those decisions in a feature spec under `docs/specs/`.

### Codex coordinator

The primary coding agent is the sole user-facing coordinator. It should inspect only relevant files, plan briefly, implement, run local verification, review the diff, and return a concise result. Routine steps should not require user approval.

Subagents are exceptional and hidden behind the coordinator. See `AGENTS.md`.

## Change classes

- **Class A — local presentation:** non-semantic visual/text adjustment.
- **Class B — application behavior:** guided flow, resume behavior, interaction behavior.
- **Class C — model semantic:** relation, validation, persistent attributes, model element behavior.
- **Class D — architecture:** boundaries, mutation ownership, persistence mechanism, major structural change.

Class B/C/D requires a feature spec. Class C/D requires explicit semantic/architecture impact review.

## Active task contract

Normal work begins from the local file:

```text
.agent/current-task.md
```

Create it with:

```powershell
.\scripts\new-task.ps1
```

The file is intentionally ignored by Git and should remain short. It references durable specs instead of duplicating them.

## Test strategy

Use local tests by default.

### Fast feedback

```powershell
.\scripts\test-fast.ps1
```

The selector uses the Git diff/last commit to choose nearby tests without LLM reasoning.

### Full regression

Required locally before completion of Class B/C/D work:

```powershell
.\scripts\test-full.ps1
```

### Browser-visible behavior

```powershell
.\scripts\test-e2e.ps1
```

Use the narrow E2E path during iteration when possible; run broader E2E before completing a broad browser change.

### Automated local gate

```powershell
.\scripts\preflight.ps1
```

This reads the active task card and automatically applies the required local test tiers.

## Remote CI policy

GitHub Actions is manual-only. It must not run on ordinary pushes or PR updates.

A remote run is justified only when explicitly requested for a merge/milestone/release or when cross-platform/browser uncertainty remains after local verification. Use the smallest manual profile that answers the uncertainty.

## Cross-layer review for semantic changes

Explicitly check affected/not affected for ontology, canonical graph, validation, persistence, application flow, web/UI, scenarios, diagrams, undo, knowledge/SHACL, SysML, SAM, unit tests, contract tests, and E2E.

## Review questions

1. Did implementation change methodology beyond the spec?
2. Can advisory/LLM code persist without deterministic validation and required user confirmation?
3. Is the same model fact represented in more than one semantic authority?
4. Did UI convenience introduce a semantic rule outside the canonical model layer?
5. Are load/resume, diagrams, scenarios, SysML, or SAM inconsistent with the canonical graph?
6. Did the change increase user cognitive load?
7. Do tests prove behavior rather than mirror implementation?

## Branch / PR pattern

Use one branch per coherent task/spec. Keep unrelated cleanup out of the same PR. A PR records semantic/architecture impact and **local** test evidence. Remote CI evidence is optional unless explicitly requested.

## Transition rule

Improve boundaries incrementally; do not reorganize the whole repository without a concrete feature reason.

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

LLM services remain advisory and never become persistence authority.
