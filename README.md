# Arcadia OA Guided Builder

A local **Arcadia Operational Analysis** prototype built with:

- Python
- `llama-cpp-python`
- a local GGUF instruct/chat model
- NetworkX `MultiDiGraph`
- RDF/OWL knowledge graphs with `rdflib`
- SHACL model comparison with `pyshacl`

The application is focused on **guided construction** of an Operational Analysis model. The user does not need to know Arcadia terminology.

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

## User-facing dialogue

The assistant asks small questions such as:

```text
What is the main goal?
Who or what is involved?
Does this place actively do something in the operation?
What does Field Soldier do?
Is Field Soldier part of another group or facility?
Where does Field Soldier operate?
What is exchanged?
Which action receives it?
How do they communicate?
```

The dialogue is English-only. Minor English mistakes may be corrected without blocking a semantically clear answer.

## Internal ontology

The user-facing language is intentionally simple, but the graph internally uses:

- `OperationalCapability`
- `OperationalActor`
- `OperationalEntity`
- `OperationalActivity`
- `OperationalExchange`
- `CommunicationMean`

### Main relations

```text
OperationalActor  --PERFORMS--> OperationalActivity
OperationalEntity --PERFORMS--> OperationalActivity

OperationalActivity --SUPPORTS_CAPABILITY--> OperationalCapability
OperationalActivity --OPERATIONAL_EXCHANGE--> OperationalActivity

OperationalActor/Entity --COMMUNICATION_MEAN--> OperationalActor/Entity
```

### Structure and environment

Operational Entities may represent organizations, groups, facilities, buildings,
areas, environments, locations, or other non-human operational elements.

```text
OperationalEntity --CONTAINS--> OperationalEntity
OperationalEntity --CONTAINS--> OperationalActor

OperationalActor  --LOCATED_IN--> OperationalEntity
OperationalEntity --LOCATED_IN--> OperationalEntity
```

`PART_OF` is the inverse meaning of `CONTAINS`; the graph stores only the
`CONTAINS` edge so the same fact is not duplicated.

`CONTAINS/PART_OF` and `LOCATED_IN` are intentionally separate:

```text
Patrol Team --CONTAINS--> Field Soldier
Field Soldier --LOCATED_IN--> Restricted Area
```

This lets the model distinguish organizational/structural membership from the
environment or place where something operates.

Operational Actors are treated as structural leaves: they can be contained by an
Operational Entity but cannot contain other participants.

## Context-only entities

A place or environmental element does not have to perform an activity.

Example:

```text
Restricted Area
Military Base
Building A
```

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
Local GGUF LLM
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
py -3.12 --version
```

If needed:

```powershell
winget install -e --id Python.Python.3.12
```

Clone the repository:

```powershell
cd D:\AI
git clone https://github.com/fabricionicolato1323-cyber/MBSE-App.git
cd MBSE-App
```

Create and activate the environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Install the dependencies using the pre-built CPU wheel for `llama-cpp-python`:

```powershell
pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --prefer-binary
```

Do **not** use plain `pip install -r requirements.txt` on this Windows setup if it
starts compiling `llama-cpp-python` with CMake.

## GGUF model

Place the Qwen GGUF at:

```text
models\model.gguf
```

Current test model:

```text
qwen2.5-3b-instruct-q4_k_m.gguf
```

Test loading:

```powershell
python -c "from llama_cpp import Llama; llm=Llama(model_path='models/model.gguf', n_ctx=4096, verbose=False); print('MODEL LOADED OK')"
```

## Tests

Run:

```powershell
python smoke_test.py
python knowledge_graph_test.py
```

Expected:

```text
Smoke test passed.
Knowledge graph test passed.
```

## Run

```powershell
python app.py
```

The graph is saved as:

```text
oa_model.json
```

The GGUF model, `.venv`, Python cache files, and saved user model are excluded
from Git by `.gitignore`.
