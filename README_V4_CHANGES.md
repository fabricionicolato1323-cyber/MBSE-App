# v4 validation changes

This revision makes the guided input less brittle with small local LLMs.

- Short English action phrases are not rejected solely because the LLM mislabels the language.
- Action phrases beginning with a usable English verb can follow the deterministic action path.
- Short verb-object phrases remain valid even when the local model considers them vague.
- Additional complements remain part of the action semantics instead of being forced into another concept.
- Obvious non-English input is still rejected.
- Clear implementation/solution bias is still rejected before the graph write barrier.
- LLM suggestions are prevented from silently replacing the user's intended fact.
- Documentation and runtime guidance use domain-neutral structural placeholders instead of scenario examples.
