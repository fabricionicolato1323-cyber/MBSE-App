# v4 validation changes

This revision makes the guided input less brittle with small local LLMs.

- Short English action phrases are not rejected solely because the LLM mislabels the language.
- Action phrases beginning with a known English verb are treated deterministically as actions.
- `Provide drone information` is accepted even if the LLM calls it too vague.
- `Provide drone information such as position and velocity` is accepted as an action, not misclassified as an exchanged item.
- Obvious non-English input is still rejected.
- Clear implementation/solution bias is still rejected before the graph write barrier.
- LLM suggestions are prevented from silently replacing the user's intended fact.
