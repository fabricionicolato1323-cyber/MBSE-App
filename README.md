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
- Ollama is advisory and is not required for simple participant classification.
- No candidate becomes a model element without an explicit user decision.
- Operational Actor means one indivisible human person or human role.
- Human collectives and non-human operational participants are Operational Entities.
- Participant type, nature, and operational role are separate dimensions.
- Composition/decomposition is explicitly confirmed by the user.
- Smaller actions do not inherit performers, goal links, or characteristics automatically.
- The future System of Interest is not introduced in Operational Analysis.
- Every Ollama operation reports wall-clock response time; Ollama's own API
  duration is also reported when available.
- No model name is hardcoded in source code or documentation.

## Graph-grounded Arcadia help

The repository includes a curated Arcadia Operational Analysis knowledge base in
[`knowledge_base`](knowledge_base). It contains:

- an in-depth methodology guide;
- an RDF/OWL ontology;
- atomic knowledge claims with source, locator, and guidance status;
- SHACL rules for comparing the user's model with the reference graph;
- an integration and governance blueprint.

The runtime keeps three concerns separate:

```text
Arcadia reference graph (read-only facts and provenance)
Arcadia SHACL graph   (comparison rules)
User model graph      (only user-approved model elements)
```

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

## Processing flow

```text
User text
   |
Deterministic extraction/classification rules
   |
Advisory suggestion + explanation
   |                         \
User decision                Optional Ollama opinion
   |
Ontology validation
   |
Confirmed NetworkX model
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

Each confirmed participant records:

- `nature`
- `status=confirmed`
- `confirmed_by=user`
- `classification_source`
- `classification_evidence`
- `classification_reason`
- `classification_rules`

## Internal model

The graph uses:

- `OperationalCapability`
- `OperationalActor`
- `OperationalEntity`
- `OperationalActivity`
- `OperationalExchange`
- `CommunicationMean`

Main relations:

```text
OperationalActor/Entity --PERFORMS--> OperationalActivity
OperationalActivity --SUPPORTS_CAPABILITY--> OperationalCapability
OperationalCapability --DECOMPOSES--> OperationalCapability
OperationalActivity --DECOMPOSES--> OperationalActivity
OperationalActivity --OPERATIONAL_EXCHANGE--> OperationalActivity
OperationalActor/Entity --COMMUNICATION_MEAN--> OperationalActor/Entity
OperationalEntity --CONTAINS--> OperationalEntity/Actor
OperationalActor/Entity --LOCATED_IN--> OperationalEntity
```

Operational Actors are structural leaves. `CONTAINS` and `LOCATED_IN` are kept
separate so organizational membership is not confused with operational location.

## Composition and decomposition

The user sees one consistent refinement step for:

```text
Goal
Participant / context
Action
```

Goals and actions use `DECOMPOSES`. Participant/context structure reuses the
existing `CONTAINS` relation so there is no second competing representation of
the same fact. Only Operational Entities can be structural parents; Operational
Actors remain leaves.

A contained participant/context element can be selected from existing model
elements or added during the refinement step. New active elements have their
actions captured before interaction elicitation, so those actions are available
for later exchanges and communication methods.

The deterministic graph blocks self-composition, cycles, multiple parents, and
invalid cross-type decomposition. Parent performers, goal links, and
characteristics are never copied automatically to smaller actions.

`/show` displays the three hierarchies together with structured characteristics.
`/check` includes composition/decomposition integrity checks.

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

Run all regression scripts:

```powershell
python smoke_test.py
python goal_fast_path_test.py
python participant_classification_test.py
python participant_rules_test.py
python candidate_discovery_test.py
python semantic_frames_test.py
python characteristics_test.py
python decomposition_test.py
python ollama_service_test.py
python knowledge_graph_test.py
```

`decomposition_test.py` checks goal, participant/context, and action hierarchies,
including cycle protection, single-parent rules, actor leaves, inheritance rules,
and `/show` integration.

The Ollama service test uses a fake HTTP response and does not require a running
model. A live end-to-end run requires Ollama.
