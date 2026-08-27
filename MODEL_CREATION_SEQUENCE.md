# Guided model creation sequence

The end user does not need to know Arcadia terminology.

## 1. Capture the goal

Example:

```text
What is the main goal?
> Maintain safe and effective operations
```

Internally this becomes an `OperationalCapability`.

## 2. Discover candidates from the user's wording

Ollama may extract only noun phrases that occur explicitly in the goal.
The extraction is advisory and protected by an exact-span / duplicate / type
barrier.

A `CandidateMention` is transient. It is not written to NetworkX.

## 3. Ask the user to confirm each candidate

Deterministic rules first propose a type, nature, evidence level, reason, and
rule identifiers. The user may confirm, override, reject, or explicitly request
an Ollama opinion. Only the user's final choice becomes a persistent
`OperationalActor` or `OperationalEntity`.

An Operational Actor is one indivisible human person or role. Human collectives
and non-human operational participants are Operational Entities.

## 4. Determine whether an entity acts or only provides context

An Operational Entity may actively perform behavior or may only provide
operational context. Human actors are treated as active participants.

## 5. Capture and parse operational behavior

For each active participant the application asks:

```text
What does <participant> do?
```

The answer may contain one or several subjects, verbs, objects, recipients,
locations, conditions, time expressions, and other complements.

One simple action is parsed deterministically. Complex language may be sent to
Ollama and is then shown to the user for confirmation. Before writing to the
graph, the answer is represented as transient semantic frames:

```text
SemanticFrame
  |
  +-- SemanticClause
  |     subjects[]
  |     verb
  |     objects[]
  |     recipients[]
  |     locations[]
  |     conditions[]
  |     time[]
  |     other_complements[]
  |     activity_text
  |
  +-- SemanticClause ...
```

General decomposition rules for natural-language input:

```text
one verb + several objects
    -> one OperationalActivity

several independent verbs
    -> several OperationalActivities

several subjects + same action
    -> one OperationalActivity with several PERFORMS relations

subject stated once + following coordinated actions
    -> subject is inherited by the following clauses
```

If the sentence is structurally complex, the application shows the interpreted
subjects/actions/objects/complements and asks the user to confirm the
interpretation. Nothing is written before confirmation.

The persistent OperationalActivity may store semantic attributes such as:

```text
semantic_verb
semantic_objects[]
semantic_recipients[]
semantic_locations[]
semantic_conditions[]
semantic_time[]
semantic_other_complements[]
source_text
```

`SemanticFrame` and `SemanticClause` themselves are not persisted as Arcadia
nodes.

## 6. Ask for anything not mentioned earlier

```text
Is anyone or anything else involved? (yes/no)
```

This prevents the model from being limited to nouns that happened to appear in
the initial goal wording.

## 7. Capture structure and environment

The assistant asks simple questions that map internally to:

```text
OperationalEntity --CONTAINS--> OperationalEntity
OperationalEntity --CONTAINS--> OperationalActor
OperationalActor  --LOCATED_IN--> OperationalEntity
OperationalEntity --LOCATED_IN--> OperationalEntity
```

`PART_OF` is the inverse reading of `CONTAINS` and is not stored as a duplicate edge.
Operational Actors remain structural leaves.

## 8. Capture operational interactions

Actions may exchange information, material, requests, or other operational items.

## 9. Capture communication means

When an interaction crosses participant boundaries, the assistant can ask how
the relevant participants communicate. Shared activities with multiple performers
are supported.

## 10. Refine goals and actions with explicit decomposition

After the basic model exists, the user may break a broad goal or action into
smaller parts.

Internally:

```text
OperationalCapability --DECOMPOSES--> OperationalCapability
OperationalActivity   --DECOMPOSES--> OperationalActivity
```

Participant/context composition continues to use `CONTAINS`; the model does not
store a second competing composition edge for the same structural fact.

Deterministic rules enforce:

- no self-decomposition;
- no decomposition cycles;
- one decomposition parent per child;
- goal-to-goal and action-to-action decomposition only;
- Operational Actors remain leaves.

Nothing is inherited automatically from a parent. In particular, a smaller
action does not automatically receive the parent's performer, goal connection,
or characteristics. The user is asked explicitly when those relationships are
needed.

`/show` includes the resulting hierarchy.

## 11. Capture structured characteristics

The user may add descriptive or measurable characteristics to goals,
participants/context, actions, and interactions. Supported value forms are:

```text
single numeric value + optional unit
numeric range with lower bound + upper bound + optional unit
text value
```

The user supplies every characteristic name and value. The local model does not
invent or infer values. `/show` includes the stored values and `/check` validates
the persisted structure.

## Write barrier

The activity flow is:

```text
User wording
    |
    v
Semantic frame parsing
    |
    v
Subjects / verbs / objects / complements
    |
    v
User confirmation for complex interpretations
    |
    v
OA semantic validation
    |
    v
Deterministic graph rules
    |
    v
NetworkX
```

The candidate flow is:

```text
User wording
    |
    v
Local LLM candidate extraction
    |
    v
Exact-span / duplicate / type filter
    |
    v
User confirmation
    |
    v
OA type validation
    |
    v
Deterministic graph rules
    |
    v
NetworkX
```

The LLM never has direct write access to the graph.
