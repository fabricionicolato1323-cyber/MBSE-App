# Arcadia OA Guided Builder

A local, human-in-the-loop assistant for guided construction of an Arcadia
Operational Analysis model.

The application is a support tool. It detects candidates, presents transparent
rules, requests optional advice from a local Ollama model, and checks the graph.
The user remains responsible for every classification and for the quality of the
final model.

## Design principles

- The deterministic Python layer is the write barrier.
- Ollama is advisory and is not required for simple participant classification.
- No candidate becomes a model element without an explicit user decision.
- Operational Actor means one indivisible human person or human role.
- Human collectives and non-human operational participants are Operational Entities.
- Participant type, nature, and operational role are separate dimensions.
- The future System of Interest is not introduced in Operational Analysis.
- Every Ollama operation reports wall-clock response time; Ollama's own API
  duration is also reported when available.
- No model name is hardcoded in source code or documentation.

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

## Commands

```text
/help  /show  /check  /why  /save  /undo  /clc  /done  /quit
```

`/clc` is the only command that clears terminal history.

## Tests

Run all regression scripts:

```powershell
python smoke_test.py
python goal_fast_path_test.py
python participant_classification_test.py
python participant_rules_test.py
python candidate_discovery_test.py
python semantic_frames_test.py
python ollama_service_test.py
```

The Ollama service test uses a fake HTTP response and does not require a running
model. A live end-to-end run requires Ollama.
