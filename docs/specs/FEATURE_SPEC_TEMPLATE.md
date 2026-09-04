# Feature Specification Template

> Copy this file to `docs/specs/NNNN-short-feature-name.md` for any non-trivial application, semantic, or architectural change.

## 1. Summary

One paragraph describing the desired behavior and why it matters.

## 2. User problem

Describe the user problem, not the implementation solution.

- What is difficult or missing today?
- What decision should become easier or safer?
- How does this relate to cognitive-load reduction?

## 3. Scope

### In scope

- 

### Out of scope

- 

## 4. Semantic rules

List the rules that define the meaning of the feature.

Examples of useful rule styles:

- A persistent relationship may exist only when ...
- A user must explicitly confirm ... before ...
- The LLM may suggest ... but may not ...
- A loaded model must preserve ...
- The canonical graph remains the source of truth for ...

If no model semantics change, state that explicitly.

## 5. User interaction rules

Describe the user-facing behavior.

- What is the smallest decision presented at each step?
- What happens when the user is unsure or skips?
- What information is progressively disclosed?
- Which internal terms must remain hidden from user-facing text?

## 6. Deterministic / AI boundary

### Deterministic responsibilities

- validation;
- persistent graph mutation;
- invariant enforcement;
- 

### AI / LLM responsibilities

- interpretation/suggestion only;
- explanation/ranking when useful;
- 

### Explicit prohibition

The LLM must not mutate the persistent model directly or convert an unconfirmed inference into a model fact.

## 7. Data and model impact

Mark each item and explain the impact when affected.

```text
[ ] ontology
[ ] graph nodes
[ ] graph relations
[ ] persistent attributes
[ ] decomposition/composition
[ ] scenarios
[ ] validation
[ ] save/load compatibility
[ ] undo/revision
[ ] diagrams
[ ] knowledge graph / SHACL
[ ] SysML v2
[ ] SAM synchronization/projection
```

## 8. Application/UI impact

```text
[ ] terminal flow
[ ] guided flow
[ ] web bridge / worker
[ ] templates
[ ] static JS/CSS
[ ] browser interaction
[ ] help/guidance text
```

## 9. Compatibility and migration

- Existing saved models:
- Existing UI behavior:
- Existing SysML/SAM projections:
- Existing API/file formats:
- Migration required: yes / no

If migration is required, describe a backward-compatible path.

## 10. Acceptance criteria

Use externally testable statements.

1. Given ..., when ..., then ...
2. Given ..., when ..., then ...
3. No LLM path can ...
4. Existing ... continues to ...

## 11. Test plan

### Focused unit/contract tests

- 

### Integration tests

- 

### E2E tests

- 

### Regression suite

```bash
python -m pytest -q
```

## 12. Implementation notes

Optional. Use this section only for constraints that genuinely belong in the spec. Do not over-prescribe filenames before the coding agent has inspected the current repository.

## 13. Risks

- semantic ambiguity:
- backward compatibility:
- duplicated source of truth:
- UI cognitive-load regression:
- projection mismatch:
- platform-specific behavior:

## 14. Definition of done

- [ ] acceptance criteria satisfied
- [ ] deterministic write barrier preserved
- [ ] explicit user confirmation preserved where persistence occurs
- [ ] no duplicated semantic source of truth introduced
- [ ] relevant tests added/updated
- [ ] focused tests pass
- [ ] full regression suite passes
- [ ] browser E2E passes when applicable
- [ ] SysML/SAM contracts pass when applicable
- [ ] documentation updated when behavior or architecture changed
