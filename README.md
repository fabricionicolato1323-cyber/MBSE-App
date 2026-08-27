# Guided Operational Model Builder

A small, deterministic terminal application for building a solution-independent
view of needs, participants, activities, exchanged items, and communication
methods. The application asks one question at a time and the user remains
responsible for every modeling decision.

The runtime does not require AI or a separate server.

## Persistent model

The guided flow uses six plain-language categories:

1. required outcomes;
2. individual participants;
3. collective or contextual participants;
4. activities;
5. exchanged items;
6. communication methods.

Every concept and relationship has a definition and an example in `ontology.py`.
The flow shows them when a concept or relationship is first introduced, after a
grammar error, and before a consequential composition decision. The same catalog
is embedded in every saved JSON model.

Every element records:

- canonical UUID `id` and an immutable, unique optional `sid` alias;
- an internal category and compatibility mapping, hidden from the guided interface;
- name and mandatory core description;
- optional summary, status, and review data;
- structured parameters and operational constraints;
- ontology definition and example;
- creation and update timestamps.

An individual participant is non-decomposable and is usually human. A proposed
non-human individual displays that warning and is persisted only after explicit
confirmation that it remains non-decomposable.

An entity whose name or description contains the word `system` requires explicit
confirmation that it is an existing external participant rather than the system
of interest being designed.

## Relationships

The deterministic write barrier supports:

- participants performing activities;
- participants and activities contributing to required outcomes;
- producing and consuming activities for exchanged items;
- source and target participants for communication methods;
- communication methods supporting exchanged items;
- containment, location, decomposition, and refinement.

Invalid type combinations, duplicates, multiple endpoint assignments,
self-composition, composition cycles, and multiple composition parents are
rejected before they reach the saved graph.

## Attributes and limitations

For every element, the flow explicitly asks whether a measurable target, range,
capacity, maximum distance, duration, area, or other limitation applies. If it
does, the customer/user supplies:

- measured quantity and description;
- quantity kind and unit;
- minimum, maximum, exact value, or a range with explicit lower and upper limits;
- applicable condition;
- `LOCAL` or `HIERARCHY` scope;
- `SUM`, `MIN`, `MAX`, `ALL`, `ANY`, or `CUSTOM` aggregation when hierarchical.

Nothing is inferred or propagated automatically.

Numeric fields reject nonnumeric and non-finite values, inverted ranges are
rejected, and `CUSTOM` aggregation requires an explicit rule. Recognized
quantity-kind/unit mismatches produce a warning and require the user to keep or
re-enter the supplied values; warnings never change values automatically.

## Composition and editing

- Individual participants are leaves.
- Collective or contextual participants may contain other participants.
- Activities may be broken down into subordinate activities.
- Required outcomes, exchanged items, and communication methods may be refined
  into items of the same category.
- The user may answer **Not now** and return later through `/edit`.
- When a child is created, each existing parent relationship is explicitly kept
  on the parent, moved to the child, or placed at both levels.
- Renaming or editing does not change the stable element ID.
- Invalid edit previews do not replace valid stored data.
- Deletion shows affected relationships and requires explicit confirmation.
- `/undo` and `/back` group compound graph changes into one user-action boundary,
  so endpoint replacement and relationship moves cannot be partly undone.
- Undo reports the element or relationship action that was restored.
- `/retry` discards only the measurable characteristic currently being entered;
  it does not alter the approved Project Graph.

## Validated loading and migration

`/load` parses a saved file into a candidate graph and validates concept types,
UUID identity, unique `sid` aliases, names, descriptions, parameters,
constraints, relationship signatures, endpoint cardinality, parent cardinality,
and cycles before replacing the active graph.

Invalid JSON or graph data leaves the active graph unchanged. Schema-version-1
files are migrated in memory only, show a summary, and require explicit user
confirmation. Missing legacy `sid` values are set to canonical `id`; duplicate
legacy aliases reject migration. The source file is not changed by loading.

## Windows installation

Python 3.12 is recommended.

```powershell
cd D:\AI
git clone https://github.com/fabricionicolato1323-cyber/MBSE-App.git
cd MBSE-App
git switch feature/persistent-oa-ontology
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If the repository is already cloned:

```powershell
cd D:\AI\MBSE-App
git switch feature/persistent-oa-ontology
git pull --ff-only
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python app.py
```

The model is saved as `oa_model.json` in the application folder.

Available commands during any question:

```text
/show  /check  /save  /load  /edit  /delete  /undo  /back  /retry  /clc  /done  /quit
```

`/back` and `/undo` restore the latest graph action; they never navigate to the
previous interview question. While entering a measurable characteristic, use
`/retry` to discard that unpersisted characteristic and start it again.

`/show` displays the complete user-facing model: every item with its full stable
ID, plain-language category, description, status and applicable review metadata;
every measurable attribute with numeric values, unit, scope, aggregation,
condition and warnings; and every relationship with both endpoint IDs. Ranges
show their lower and upper limits explicitly.

## Test

```powershell
python smoke_test.py
python app_flow_test.py
python -m unittest discover -s tests -v
```

The verification covers the six persistent categories, allowed relationships,
composition rules, endpoint cardinality, dimensional constraints, canonical
identity, atomic undo, validated loading, confirmed legacy migration, and
exceptional non-human actor confirmation. Regression coverage also includes
descriptive undo feedback, attribute retry, dimensional warnings, detailed model
review, and confirmation of external systems.

## Files

- `app.py` — deterministic guided interview and editing flow.
- `ontology.py` — internal categories, relationships, plain-language guidance, and grammar rules.
- `graph_model.py` — persistent NetworkX graph and write barrier.
- `arcadia_oa_ontology.mmd` — Mermaid view of the persistent ontology.
- `MODEL_CREATION_SEQUENCE.md` — detailed elicitation sequence.
- `knowledge_base/` — research/reference material; it is not an interactive help service.
