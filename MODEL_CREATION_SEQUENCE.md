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

The local LLM extracts only noun phrases that occur explicitly in the goal.
The extraction is advisory and protected by an exact-span / duplicate / type
barrier.

A `CandidateMention` is transient. It is not written to NetworkX.

## 3. Ask the user to confirm each candidate

Only a confirmed candidate becomes a persistent `OperationalActor` or
`OperationalEntity`.

## 4. Determine whether an entity acts or only provides context

A non-human participant/context element may actively perform behavior or may only
provide operational context. Human actors are treated as active participants.

## 5. Capture and parse operational behavior

For each active participant the application asks:

```text
What does <participant> do?
```

The answer may contain one or several subjects, verbs, objects, recipients,
locations, conditions, time expressions, and other complements.

Before writing to the graph, the answer is parsed into transient semantic frames:

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

General decomposition rules:

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

## 8. Capture operational interactions

Actions may exchange information, material, requests, or other operational items.

## 9. Capture communication means

When an interaction crosses participant boundaries, the assistant can ask how
the relevant participants communicate. Shared activities with multiple performers
are supported.

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
