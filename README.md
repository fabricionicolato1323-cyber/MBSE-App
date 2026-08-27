# Arcadia OA Guided Builder

A local, human-in-the-loop assistant for guided construction of an Arcadia
Operational Analysis model.

The application is a support tool. It detects candidates, presents transparent
rules, requests optional advice from a local Ollama model, and checks the graph.
The user remains responsible for every classification and for the quality of the
final model.

It is built with Python, a NetworkX `MultiDiGraph`, a dynamically selected local
Ollama model, RDF/OWL knowledge graphs through `rdflib`, and SHACL validation
through `pyshacl`.

## Design principles

- The deterministic Python layer is the write barrier.
- NetworkX `MultiDiGraph` is the executable project model and JSON is its canonical persistence format.
- RDF/OWL, SPARQL and SHACL are authority, query, validation and export layers; they do not replace NetworkX.
- Ollama is advisory and is not required for simple participant classification.
- No candidate becomes a model element without an explicit user decision.
- Operational Actor means one indivisible human person or human role.
- Human collectives and non-human operational participants are Operational Entities.
- Participant type, nature, and operational role are separate dimensions.
- The future System of Interest is not introduced in Operational Analysis.
- Every Ollama operation reports wall-clock response time; Ollama's own API duration is also reported when available.
- No model name is hardcoded in source code or documentation.

## Executable OA scope

The executable model remains restricted to exactly six concepts:

- `OperationalCapability`
- `OperationalActor`
- `OperationalEntity`
- `OperationalActivity`
- `OperationalExchange`
- `CommunicationMean`

The first four are persisted as NetworkX nodes. `OperationalExchange` and
`CommunicationMean` remain typed NetworkX relations. Structural helper relations
such as `PERFORMS`, `SUPPORTS_CAPABILITY`, `CONTAINS`, and `LOCATED_IN` do not
introduce additional executable OA concepts.

## Canonical identity and persistence

Every newly created model element receives a UUID that is independent from its
name. Every new NetworkX relation also receives a UUID.

- Node UUID is the canonical identity.
- `sid` is optional and immutable once assigned.
- Legacy name-derived IDs can be preserved as `sid` during migration.
- JSON save uses schema version `2` and is written atomically through a temporary file followed by replacement.
- Loading a legacy JSON model does **not** migrate silently. The caller must explicitly allow migration.

The application still saves its working model as `oa_model.json`.

A legacy file can be migrated only when explicitly requested by the export tool:

```powershell
python model_export.py oa_model.json --migrate-legacy
```

The original source file is not overwritten by this operation. The migrated copy
is written to the export directory.

## Graph-grounded Arcadia help

The repository includes a curated Arcadia Operational Analysis knowledge base in
[`knowledge_base`](knowledge_base). It contains:

- an in-depth methodology guide;
- an RDF/OWL ontology;
- atomic knowledge claims with source, locator, and guidance status;
- SHACL rules for comparing the user's model with the reference graph;
- an integration and governance blueprint.

The runtime RDF Dataset is divided into seven named graphs:

```text
urn:graph:ontology
urn:graph:arcadia-reference
urn:graph:arcadia-shapes
urn:graph:project-approved
urn:graph:project-candidates
urn:graph:validation
urn:graph:audit
```

Authority is intentionally separated:

- `project-approved` contains only data derived from the user-approved NetworkX model;
- `project-candidates` contains unapproved extraction hypotheses;
- `validation` contains derived SHACL results;
- `audit` records candidate, validation, and export events.

Candidate statements are never promoted to `project-approved` by the RDF layer.
Promotion to the executable model still has to pass the deterministic write
barrier and the user's approval flow.

Use the knowledge graph from any question prompt:

```text
/ask What is the difference between an Operational Actor and an Operational Entity?
/compare
```

`/ask` retrieves a small evidence packet before the local LLM runs. The LLM may
only verbalize those claims in English and must cite their claim IDs. Unknown or
invalid citations are rejected. If no graph evidence is available, the app
abstains instead of completing the answer from model memory.

`/compare` converts the current approved NetworkX model to a separate RDF Project
Graph and runs the curated SHACL rules. Violations, warnings, and information
items never write back to the user model. The same comparison runs automatically
at the end of the guided workflow.

Both operations report elapsed time. The LLM remains unable to write directly to
NetworkX, and the user remains the final authority over model content.

## Approved model export

After saving a model, generate the canonical export package with:

```powershell
python model_export.py oa_model.json
```

Default output directory: `export`.

The command creates:

```text
export/oa_model.json
export/oa_project_approved.ttl
export/oa_validation_report.md
```

- `oa_model.json` — canonical NetworkX/JSON project model with UUID identity.
- `oa_project_approved.ttl` — approved RDF only; candidate statements are excluded.
- `oa_validation_report.md` — SHACL summary and findings.

Choose another output directory with:

```powershell
python model_export.py oa_model.json --output-dir D:\AI\MBSE-export
```

## Processing flow

```text
User text
   |
Deterministic extraction/classification rules
   |
Candidate + rationale/evidence
   |                         \
User decision                Optional Ollama opinion
   |
Ontology validation
   |
WRITE BARRIER
   |
Confirmed NetworkX MultiDiGraph
   |
Derived RDF project graph + SHACL validation
```

Ollama is mainly used for complex semantic frames, optional goal candidate
discovery, ambiguous validation, and an explicitly requested second opinion.
Simple activity phrases and participant classifications have deterministic paths.

## Participant ontology

```text
OperationalParticipant
|- OperationalActor
`- OperationalEntity
   |- organization
   |- organizational_unit
   |- team_or_collective
   |- existing_technical_system
   |- infrastructure_or_facility
   |- external_operational_service
   |- population_or_community
   `- environmental_participant
```

Rules and editable vocabulary are stored in:

```text
participant_rules.py
participant_lexicon.json
```

Each confirmed participant can record:

- `nature`
- `status=confirmed`
- `confirmed_by=user`
- `classification_source`
- `classification_evidence`
- `classification_reason`
- `classification_rules`

## Main relations

```text
OperationalActor/Entity --PERFORMS--> OperationalActivity
OperationalActivity --SUPPORTS_CAPABILITY--> OperationalCapability
OperationalActivity --OPERATIONAL_EXCHANGE--> OperationalActivity
OperationalActor/Entity --COMMUNICATION_MEAN--> OperationalActor/Entity
OperationalEntity --CONTAINS--> OperationalEntity/Actor
OperationalActor/Entity --LOCATED_IN--> OperationalEntity
```

Operational Actors are structural leaves. `CONTAINS` and `LOCATED_IN` are kept
separate so organizational membership is not confused with operational location.

## Ollama configuration

Install and start Ollama, then install an instruct/chat model of your choice.
The application never assumes a particular model.

List installed models:

```powershell
ollama list
```

Select a model using either:

1. The `MBSE_OLLAMA_MODEL` environment variable; or
2. `ollama.model` in `config.json`.

PowerShell example using a placeholder rather than a fixed model:

```powershell
$env:MBSE_OLLAMA_MODEL = "<installed-model-name>"
python app.py
```

If exactly one model is installed and neither setting is supplied, it is selected
automatically. If zero or several models are installed, the app explains how to
select one and continues with deterministic rules.

`config.json`:

```json
{
  "ollama": {
    "enabled": true,
    "base_url": "http://localhost:11434",
    "model": null,
    "model_env": "MBSE_OLLAMA_MODEL",
    "timeout_seconds": 120,
    "keep_alive": "10m",
    "num_ctx": 4096
  }
}
```

Setting `model` to `null` is intentional: it prevents a model from being
hardcoded in the repository.

When a non-human entity is added, the application asks:

```text
Does Restricted Area actively do something in this operation? (yes/no)
```

If the answer is `no`, the entity remains in the model as operational context and
the completeness checker does not require an action for it.

## Write protection

The LLM never writes directly to NetworkX.

```text
User answer
    |
Optional local Ollama model
    |
semantic interpretation
    |
deterministic Python validation
    |
WRITE BARRIER
    |
NetworkX MultiDiGraph
```

The Python layer blocks invalid ontology relations, duplicates, containment
cycles, location cycles, obvious solution/implementation bias, and non-English
natural-language input.

## Commands

The command bar is shown with every question:

```text
/help  /ask QUESTION  /compare  /show  /check  /why  /save  /undo  /clc  /done  /quit
```

- `/ask QUESTION` — answer from retrieved knowledge-graph evidence only
- `/compare` — compare the current model against Arcadia SHACL rules
- `/save` — save canonical JSON atomically
- `/undo` — undo the last accepted graph mutation

`/clc` is the only command that clears the terminal. The normal question flow
preserves terminal history.

## Windows installation

Use Python 3.12.

```powershell
cd D:\AI
git clone https://github.com/fabricionicolato1323-cyber/MBSE-App.git
cd MBSE-App
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

No GGUF file is copied into this repository and `llama-cpp-python` is not used.
Ollama owns local model installation and execution.

## Run

```powershell
python app.py
```

The model is saved as `oa_model.json`.

## Tests

Run the complete regression suite with:

```powershell
python -m pytest -q
```

The pytest suite includes the existing regression scripts plus persistence,
migration, RDF authority separation, approved export, and SHACL integration tests.
The Ollama service regression uses a fake HTTP response and does not require a
running model. A live end-to-end run requires Ollama.

GitHub Actions runs the same pytest suite on:

- Ubuntu latest + Python 3.12
- Windows latest + Python 3.12
