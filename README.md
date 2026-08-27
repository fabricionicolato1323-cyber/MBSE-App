# Arcadia OA Guided Builder

A small, deterministic terminal application for building the persistent portion
of an Arcadia Operational Analysis model. The application asks one question at a
time and the user remains responsible for every modeling decision.

The runtime does not require AI or a separate server.

## Persistent ontology

The saved model contains exactly six OA concepts:

1. `OperationalCapability`
2. `OperationalActor`
3. `OperationalEntity`
4. `OperationalActivity`
5. `OperationalExchange`
6. `CommunicationMean`

Every concept and relationship has a definition and an example in `ontology.py`.
The flow shows them when a concept or relationship is first introduced, after a
grammar error, and before a consequential composition decision. The same catalog
is embedded in every saved JSON model.

Every element records:

- canonical UUID `id` and an immutable, unique optional `sid` alias;
- OA type and Capella mapping;
- name and mandatory core description;
- optional summary, status, and review data;
- structured parameters and operational constraints;
- ontology definition and example;
- creation and update timestamps.

An `OperationalActor` is a non-decomposable `OperationalEntity` and is usually
human. A proposed non-human actor displays that warning and is persisted only
after explicit confirmation that it remains non-decomposable.

## Relationships

The deterministic write barrier supports:

- `PERFORMS`
- `INVOLVED_IN_CAPABILITY`
- `SUPPORTS_CAPABILITY`
- `SOURCE_ACTIVITY`
- `TARGET_ACTIVITY`
- `SOURCE_PARTICIPANT`
- `TARGET_PARTICIPANT`
- `SUPPORTS_EXCHANGE`
- `CONTAINS`
- `LOCATED_IN`
- `DECOMPOSES_INTO`
- `REFINES_INTO`

Invalid type combinations, duplicates, multiple endpoint assignments,
self-composition, composition cycles, and multiple composition parents are
rejected before they reach the saved graph.

## Attributes and limitations

For every element, the flow explicitly asks whether a measurable target, range,
capacity, maximum distance, duration, area, or other limitation applies. If it
does, the customer/user supplies:

- measured quantity and description;
- quantity kind and unit;
- minimum, maximum, exact value, or range;
- applicable condition and rationale;
- `LOCAL` or `HIERARCHY` scope;
- `SUM`, `MIN`, `MAX`, `ALL`, `ANY`, or `CUSTOM` aggregation when hierarchical.

Nothing is inferred or propagated automatically.

## Composition and editing

- Operational Actors are leaves.
- Operational Entities may `CONTAIN` entities or actors.
- Operational Activities may `DECOMPOSE_INTO` activities.
- Capabilities, Exchanges, and Communication Means may `REFINE_INTO` elements of
  the same type.
- The user may answer **Not now** and return later through `/edit`.
- When a child is created, each existing parent relationship is explicitly kept
  on the parent, moved to the child, or placed at both levels.
- Renaming or editing does not change the stable element ID.
- Invalid edit previews do not replace valid stored data.
- Deletion shows affected relationships and requires explicit confirmation.
- `/undo` and `/back` group compound graph changes into one user-action boundary,
  so endpoint replacement and relationship moves cannot be partly undone.

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
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If the repository is already cloned:

```powershell
cd D:\AI\MBSE-App
git pull
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
/show  /check  /save  /load  /edit  /delete  /undo  /back  /clc  /done  /quit
```

## Test

```powershell
python smoke_test.py
python app_flow_test.py
python -m unittest discover -s tests -v
```

The verification covers the six persistent concepts, allowed relationships,
composition rules, endpoint cardinality, dimensional constraints, canonical
identity, atomic undo, validated loading, confirmed legacy migration, and
exceptional non-human actor confirmation.

## Files

- `app.py` — deterministic guided interview and editing flow.
- `ontology.py` — concepts, relationships, definitions, examples, and grammar rules.
- `graph_model.py` — persistent NetworkX graph and write barrier.
- `arcadia_oa_ontology.mmd` — Mermaid view of the persistent ontology.
- `MODEL_CREATION_SEQUENCE.md` — detailed elicitation sequence.
- `knowledge_base/` — research/reference material; it is not an interactive help service.
