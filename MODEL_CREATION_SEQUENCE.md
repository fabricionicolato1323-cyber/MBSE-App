# Persistent model creation sequence

The flow is a deterministic interview. It introduces only one modeling decision
at a time and does not attempt to answer open-ended methodology questions.

## 1. Create required outcomes

For each required outcome:

1. show its ontology definition and example the first time;
2. require a name in the form `verb + desired state/object + optional condition`;
3. require a one-sentence core description;
4. ask whether measurable attributes or limitations apply;
5. persist only after deterministic validation succeeds.

## 2. Create participants

The user explicitly chooses between:

- individual participant — non-decomposable and usually a human person or role;
- collective or contextual participant — group, organization, place, resource,
  context, or existing external participant.

If a participant name or description contains `system`, the flow asks
the user to confirm that it is an existing external participant and not the
system of interest. An unconfirmed system candidate is not persisted.

For an individual participant, the flow records whether it is human. A proposed
non-human actor triggers the usual-human warning and requires explicit
confirmation that it remains non-decomposable. The flow then asks whether the
participant contributes to a required outcome.

## 3. Create activities

An activity name must use `action verb + object + optional complements`. The
user selects one or more performers and the required outcome supported by the activity.

## 4. Create exchanged items

An exchange is a persistent element, not a label on an edge. It requires:

- noun-phrase name;
- core description;
- one source activity;
- one target activity.

## 5. Create communication methods

A communication method is also a persistent element. It requires:

- noun-phrase name;
- core description;
- one source participant;
- one target participant;
- optional supported exchange.

## 6. Capture structure and location

The flow keeps structural containment separate from location. Collective or
contextual participants may contain other participants, while any participant
may be linked to a modeled place or context.

An actor cannot contain another participant. A child has at most one composition
parent, and a composition or location cycle is rejected.

## 7. Ask about decomposition and refinement

| Parent category | Rule |
|---|---|
| Individual participant | Leaf; cannot decompose |
| Collective or contextual participant | May contain either participant category |
| Activity | May break down into activities |
| Required outcome | May refine into required outcomes |
| Exchanged item | May refine into exchanged items |
| Communication method | May refine into communication methods |

The user may answer **Not now**. After creating a child, every existing parent
relationship must be explicitly retained, moved, or duplicated when the ontology
allows it. Constraints remain local or apply through the hierarchy according to
the customer-supplied scope and aggregation rule.

Numeric constraint values must be finite, ranges cannot be inverted, and a
`CUSTOM` aggregation requires an explicit multi-word rule. Quantity-kind/unit
mismatches are non-blocking warnings that require the user to keep or re-enter
the supplied values.

## 8. Review, load, and edit

The review loop supports adding, editing, decomposing, deleting, checking, saving,
and finishing. Every element keeps the same stable ID after an edit. An invalid
edit remains a preview and cannot overwrite the current valid model. Deletion
shows all affected relationships before confirmation.

Saved JSON is validated as a complete candidate graph before `/load` replaces
the active graph. A schema-version-1 model is migrated only in memory, shows a
summary, and requires explicit confirmation. Missing legacy `sid` values are set
to the canonical UUID `id`; duplicate `sid` values reject migration.

`/undo` and `/back` restore the graph state before the latest complete compound
mutation. Endpoint replacement and relationship moves therefore do not expose
partial low-level rollback states. The resulting notice identifies the graph
action that was undone. These commands do not navigate between questions.

During entry of one measurable characteristic, `/retry` discards that current
unpersisted characteristic and restarts it from its name. It does not modify any
previously approved graph element or relationship.

Model review displays the complete characteristic values, scope, aggregation,
condition, semantic warnings, and relationships instead of showing only
parameter and constraint counts. A range displays both its lower and upper
limits. `/show` also displays each element's full stable ID, plain-language
category, status, applicable summary/review metadata, and relationship endpoint
IDs.

## Presentation policy

A node or relationship definition and one example are shown:

1. when it is first introduced;
2. after a grammar or ontology validation error;
3. before a consequential composition decision;
4. when an existing element is edited.

Normal follow-up questions show only the requested input structure. This keeps
the flow short without hiding the rules that control persistence.
