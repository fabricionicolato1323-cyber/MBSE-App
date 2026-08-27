# Changelog

## Guided-flow reliability

- Made `/undo` and `/back` identify the graph action that was restored and warn
  when an in-progress attribute draft was not affected.
- Added `/retry` for restarting only the current unpersisted measurable
  characteristic.
- Added finite-number, inverted-range, and explicit `CUSTOM` aggregation checks.
- Added non-blocking quantity-kind/unit warnings without automatic correction.
- Expanded `/show` to include full element and endpoint IDs, relevant metadata,
  complete measurable-characteristic values, and semantic warnings; corrected
  concept pluralization and duplicate review headings.
- Added explicit confirmation for an Operational Entity that appears to be a
  system, preserving the Operational Analysis system-of-interest boundary.
- Added regression coverage for the observed guided-flow scenario.

## Graph integrity foundation

- Aligned Operational Actor guidance with the approved “non-decomposable and
  usually human” definition and added explicit confirmation for non-human actors.
- Added atomic user-action checkpoints for compound relationship changes.
- Preserved canonical UUID `id` separately from the NetworkX JSON node key.
- Added complete candidate-graph validation before replacing the active model.
- Added confirmed, in-memory schema-version-1 migration with deterministic
  missing-`sid` repair and duplicate-`sid` rejection.
- Added focused regression tests for graph integrity, migration, and actor semantics.

## Persistent ontology flow

- Reduced the runtime model to six persistent OA concepts.
- Promoted Operational Exchange and Communication Mean to first-class nodes.
- Added mandatory core descriptions and Capella-oriented metadata.
- Added structured operational parameters, limitations, scope, and aggregation.
- Added deterministic composition, refinement, cycle, and endpoint rules.
- Added contextual definitions and examples for every node and relationship.
- Added editing, deletion impact review, undo, save, and load.
- Replaced open-ended assistance with a deterministic guided interview.
