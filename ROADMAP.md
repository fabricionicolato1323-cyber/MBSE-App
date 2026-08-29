# Implementation Roadmap

This file records planned capabilities that are intentionally not active yet.
It must not be interpreted as user-facing functionality until the corresponding
feature is implemented and tested.

## Planned feature: global model editing with impact analysis

Planned command:

```text
/edit
```

Status: **planned, not implemented**.

### Goal

Allow the user to select any existing model item, relationship, or characteristic
and propose a change at any time without bypassing deterministic model rules.

### Planned editing scope

The edit flow should eventually support:

- rename or revise a goal, participant/context item, action, interaction, or communication method;
- revise structured characteristics, including numeric values and lower/upper range bounds;
- change explicit action-to-goal and performer assignments;
- change composition/decomposition relationships;
- change interaction endpoints or exchanged content;
- change communication relationships;
- remove an item or relationship when the user explicitly confirms removal.

### Required impact analysis

Before any edit is applied, the app should show the direct and indirect model
elements that may be affected. The analysis should cover, when applicable:

- parent and child composition/decomposition;
- performers and action ownership;
- action-to-goal connections;
- interactions and their endpoints;
- communication methods that support cross-participant interactions;
- characteristics attached to an edited or removed item;
- completeness and structural validation consequences;
- NetworkX-to-RDF consistency consequences.

### Change policy

- No impact-driven change is propagated automatically.
- The user must confirm the proposed edit after seeing its impact.
- Invalid edits remain blocked by the deterministic write barrier.
- The edit must create an undo checkpoint.
- After an accepted edit, `/check` and `/compare` must evaluate the updated model.
- Internal ontology identifiers should remain hidden from the standard UI.
- Impact analysis should use model structure and rules, never domain examples
  hardcoded into source code.

### Implementation note

The initial implementation should separate:

1. edit target selection;
2. proposed change;
3. impact preview;
4. user confirmation;
5. deterministic write;
6. post-change consistency check.

This separation is intended to make later change propagation explicit,
traceable, and reversible.
