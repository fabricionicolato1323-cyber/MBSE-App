## Summary

Describe the change in terms of behavior and architecture, not only files edited.

## Feature specification

- Spec: `docs/specs/...`
- Change class: A / B / C / D

## Semantic impact

- [ ] No Arcadia/model semantics changed
- [ ] Semantic changes are explicitly defined in the linked spec
- [ ] No duplicate source of truth for model semantics was introduced
- [ ] Deterministic write barrier is preserved
- [ ] LLM/advisory paths cannot persist unconfirmed model facts

## Cross-layer impact

Mark affected areas and briefly explain below when needed.

- [ ] Ontology / allowed relations
- [ ] Canonical graph / mutation rules
- [ ] Validation
- [ ] Persistence / load-resume
- [ ] Guided application flow
- [ ] Web bridge / worker / app
- [ ] UI / static presentation
- [ ] Scenarios
- [ ] Diagrams
- [ ] Undo / revision
- [ ] Knowledge graph / SHACL
- [ ] SysML v2
- [ ] SAM projection / synchronization

## Cognitive-load review

- [ ] The change does not present unnecessary decisions or information at once
- [ ] Explicit user confirmation remains where persistent model decisions occur
- [ ] User-facing wording preserves the friendly/domain-neutral vocabulary policy

## Tests

List commands actually run.

```text
python -m pytest -q ...
```

- [ ] Focused unit/contract tests pass
- [ ] Full regression suite passes for Class B/C/D changes
- [ ] Relevant E2E tests pass when browser-visible behavior changed
- [ ] SysML/SAM contracts pass when affected
- [ ] Windows/Ubuntu CI coverage has not been weakened

## Compatibility

- Existing saved models:
- Existing UI behavior:
- Existing SysML/SAM behavior:
- Migration required: yes / no

## Remaining debt / follow-up

List intentionally deferred items. Keep unrelated cleanup out of this PR.
