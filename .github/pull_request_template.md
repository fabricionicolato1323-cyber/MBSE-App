## Summary

Describe behavior/architecture impact, not only files edited.

## Feature specification

- Spec: `docs/specs/...`
- Change class: A / B / C / D

## Semantic impact

- [ ] No Arcadia/model semantics changed, or changes are explicitly defined in the linked spec
- [ ] Deterministic write barrier is preserved
- [ ] No duplicate semantic source of truth was introduced
- [ ] LLM/advisory paths cannot persist unconfirmed model facts

## Cross-layer impact

- [ ] Ontology / graph / validation
- [ ] Persistence / load-resume / undo
- [ ] Guided application / web
- [ ] UI / diagrams / scenarios
- [ ] SysML / SAM / knowledge comparison

## Tests

List commands actually run locally.

- [ ] Focused tests pass
- [ ] Full local regression passes for Class B/C/D
- [ ] Relevant local E2E passes when browser-visible behavior changed
- [ ] SysML/SAM contracts pass when affected
- [ ] Remote CI was not required, or the manually requested profile/result is documented below

Remote CI profile/result (only if explicitly requested):

## Compatibility / remaining debt

- Existing saved models:
- Existing UI behavior:
- Existing SysML/SAM behavior:
- Remaining debt:
