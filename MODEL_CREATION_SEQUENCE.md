# Guided model creation sequence

The end user does not need to know Arcadia terminology.

## 1. Capture the goal

Example:

```text
What is the main goal?
> Keep infrastructure and soldiers safe
```

Internally this becomes an `OperationalCapability`.

## 2. Discover candidates from the user's wording

The local LLM extracts only noun phrases that occur explicitly in the goal.
The extraction is advisory and is protected by a deterministic exact-span filter.

Example internal candidates:

```text
infrastructure -> candidate OperationalEntity
soldiers       -> candidate OperationalActor
```

A `CandidateMention` is transient. It is not written to NetworkX.

## 3. Ask the user to confirm each candidate

```text
You mentioned "infrastructure".
Should it be included in the operational picture? (yes/no)
```

and:

```text
You mentioned "soldiers".
Should it be included in the operational picture? (yes/no)
```

Only a confirmed candidate becomes a persistent `OperationalActor` or
`OperationalEntity`.

## 4. Determine whether an entity acts or only provides context

For a non-human entity/context element:

```text
Does infrastructure actively do something in this operation? (yes/no)
```

If `no`, it remains contextual and no activity is required.

Human actors are treated as active participants.

## 5. Capture actions

For each active participant:

```text
What do soldiers do?
```

The answer becomes an `OperationalActivity` after validation.

## 6. Ask for anything not mentioned in the goals

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
the participants communicate.

## Write barrier

The flow is:

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
