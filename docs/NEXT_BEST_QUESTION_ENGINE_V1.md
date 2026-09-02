# Next Best Question Engine v1

## Purpose

The Next Best Question Engine reduces cognitive load during refinement by selecting one useful next modeling question from the current approved graph state.

The engine is advisory. It never writes to the model. Existing deterministic validation and graph write barriers remain authoritative.

## Ranking

The current v1 priority order is:

1. Missing goal.
2. Missing participant or context element.
3. Active participant with no action.
4. Action with no performer.
5. Action with no goal connection.
6. Existing cross-participant interaction with no communication method.
7. Review interactions when multiple actions exist but no interaction is recorded.
8. Review characteristics or limits when none have been captured.

The first six items represent deterministic structural gaps. Interaction and characteristic reviews are lower-priority refinement suggestions and may be dismissed after review.

## User-facing policy

The UI does not expose Arcadia terminology. A recommendation is shown as a simple task such as:

```text
Recommended: Describe what Operator does
Recommended: Connect 'Monitor area' to a goal
Recommended: Add how Operator and Visitor communicate
```

The user may accept the recommendation, choose another task, check the model, save, or finish.

Accepting a recommendation only opens the corresponding normal guided question. No model mutation occurs until the user answers and the existing deterministic validation accepts the answer.

## Architecture

```text
Approved NetworkX model
        |
        v
Next Best Question Engine
(read-only ranking)
        |
        v
One recommended task
        |
        v
Existing guided question flow
        |
        v
User answer
        |
        v
Validation + write barrier
        |
        v
Approved NetworkX model
```

`next_best_question.py` contains the pure ranking logic. `next_best_question_flow.py` adapts the Web refinement loop and routes accepted recommendations to existing guided methods.

The terminal lifecycle is intentionally unchanged in v1.

## Communication rule

A communication method is recommended only when an already-recorded interaction connects actions performed by different participants and no communication relationship exists between those participants. The engine does not require a communication method merely because two participants are present.

## Safety and cognitive-load constraints

- One recommendation at a time.
- Domain-neutral wording.
- No autonomous graph writes.
- No LLM dependency for ranking.
- Existing user confirmation remains authoritative.
- Optional refinements do not repeatedly nag after the user has reviewed them.
