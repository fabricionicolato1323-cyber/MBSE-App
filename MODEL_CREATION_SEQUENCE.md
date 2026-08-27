# Guided model creation sequence

The end user does not need to know Arcadia terminology. Runtime help uses
structural placeholders loaded from `ui_guidance.json`; repository defaults do
not contain scenario-specific examples.

## 1. Capture the goal

The UI presents the expected structure rather than a domain example:

```text
What is the main goal?
Expected: <verb + desired operational outcome>
```

Internally the confirmed answer becomes an `OperationalCapability`.

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

The repository base classifier uses generic semantic-class vocabulary from
`participant_lexicon.json`. Domain- or organization-specific terms belong in
`participant_lexicon_extensions.json` or another extension file selected with
`MBSE_PARTICIPANT_LEXICON_EXTENSIONS_PATH`.

## 4. Determine whether an entity acts or only provides context

An Operational Entity may actively perform behavior or may only provide
operational context. Human actors are treated as active participants.

## 5. Capture and parse operational behavior

For each active participant the application asks:

```text
What does <participant> do?
Expected: <verb + object or complement>
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

The assistant asks directly for each participant/context element. This same
input pattern is used whether or not any participant has already been accepted:

```text
Who or what is involved?
> <participant/context name>

Who or what else is involved?
> <participant/context name>
```

The user enters one element at a time and types `done` when the list is complete.
`done` is also valid when no participant has been accepted yet:

```text
Who or what is involved?
> done
```

There is no separate yes/no gate and no mandatory first-participant trap after a
candidate is rejected. The model may therefore proceed with no participant, but
`/check` will report the resulting completeness gap. Classification,
confirmation, language, and write-barrier rules remain unchanged for every
element that is actually added.

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

## 8. Refine composition and decomposition

Before interactions are captured, the user may break a broad model item into
smaller parts through one consistent user-facing flow:

```text
Goal
Participant / context
Action
```

Internally the existing graph semantics remain authoritative:

```text
OperationalCapability --DECOMPOSES--> OperationalCapability
OperationalActivity   --DECOMPOSES--> OperationalActivity
OperationalEntity     --CONTAINS-->   OperationalEntity
OperationalEntity     --CONTAINS-->   OperationalActor
```

Participant/context composition deliberately reuses `CONTAINS`; the model does
not store a second competing composition edge for the same structural fact.
Only Operational Entities are offered as composition parents. Operational Actors
remain structural leaves.

The user may either reuse an existing participant/context element or add a new
one under the selected parent. If a newly contained element is active, its
actions are captured immediately so the later interaction and communication
stages can use them.

Deterministic rules enforce:

- no self-composition or self-decomposition;
- no composition/decomposition cycles;
- one parent per child for each hierarchy;
- goal-to-goal and action-to-action explicit decomposition only;
- entity-to-entity or entity-to-actor structural composition only;
- Operational Actors remain leaves.

Nothing is inherited automatically from a parent. In particular, a smaller
action does not automatically receive the parent's performer, goal connection,
or characteristics. The user is asked explicitly when those relationships are
needed.

`/show` includes goal, participant/context, and action hierarchies.

## 9. Capture operational interactions

Actions may exchange information, material, requests, or other operational items.
Actions created during composition/decomposition are already available here.
The UI guidance uses the neutral placeholder:

```text
<information, material, request, or exchanged item>
```

## 10. Capture communication means

When an interaction crosses participant boundaries, the assistant can ask how
the relevant participants communicate. Shared activities with multiple performers
are supported. The default guidance uses:

```text
<real-world communication method>
```

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

## UI guidance policy

`ui_guidance.json` is the default external source for UI placeholders. A different
file may be selected with `MBSE_UI_GUIDANCE_PATH`. By default,
`allow_literal_domain_examples` is `false`, so literal examples passed by legacy
flow code are ignored at the rendering boundary.

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
