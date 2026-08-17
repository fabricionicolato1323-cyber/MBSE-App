# Arcadia OA Guided Builder v4

A local **Arcadia Operational Analysis** prototype built with:

- Python
- `llama-cpp-python`
- a local GGUF instruct/chat model
- NetworkX `MultiDiGraph`

The application is currently focused on **building** the operational model. It does not implement natural-language model querying yet.

## Design principle

The user does **not** need to know Arcadia terminology.

The dialogue uses simple questions such as:

```text
What is the main goal?
Who or what is involved?
What does Air Traffic Controller do?
What is exchanged?
Which action receives it?
How do they communicate?
```

Internally, the application maps the answers to a restricted Arcadia Operational Analysis ontology.

## Internal ontology

The following concepts are hidden from the normal user dialogue:

- OperationalCapability
- OperationalActor
- OperationalEntity
- OperationalActivity
- OperationalExchange
- CommunicationMean

The graph stores capabilities, participants, activities, exchanges, and communication relationships in a NetworkX `MultiDiGraph`.

## Write protection

The LLM never writes directly to NetworkX.

```text
Simple question
     |
User answer
     |
Local GGUF LLM
semantic validation / classification
     |
Deterministic Python write barrier
     |
accepted? ---- no ---> explain + ask again
     |
    yes
     |
NetworkX MultiDiGraph
```

The application protects model construction by:

- accepting natural-language model input only in English;
- accepting proper names as language-neutral data;
- validating the semantic type expected by the current question;
- detecting obvious solution/design bias;
- allowing only ontology-approved graph connections;
- blocking duplicate elements and duplicate named connections;
- asking one small question at a time;
- using numbered choices when the answer should refer to an existing model element.

## User flow

1. Ask for one main operational goal.
2. Ask whether there are additional goals.
3. Ask who or what participates in the operation.
4. Internally classify each participant as human or non-human.
5. Ask what each participant does.
6. Connect actions to the operational goal.
7. Ask whether actions exchange information, material, requests, or items.
8. Ask which action sends and receives each exchange.
9. When different participants interact, optionally ask how they communicate.
10. Show a friendly model summary and save the graph as JSON.

## Example dialogue

```text
GUIDED OPERATIONAL MODEL BUILDER

I will ask one small question at a time.
Answer in English only. Proper names may stay as written.
You do not need to know any modeling terminology.

What is the main goal?
  Describe the outcome people need, not the system or solution to be built.
  Example: Keep restricted airspace safe
> Keep restricted airspace safe

Added: Keep restricted airspace safe

Is there another important goal? (yes/no)
> no

Who or what is involved?
  Name one person, role, organization, group, facility, or other real-world participant.
  Example: Air Traffic Controller
> Air Traffic Controller

Added: Air Traffic Controller

What does Air Traffic Controller do?
  Use one short action in English.
  Simple wording is fine; grammar does not need to be perfect.
  Example: Provide drone information
> Provide drone information such as position and velocity

Added: Provide drone information such as position and velocity
```

## Commands

```text
/help
/show
/check
/why
/save
/undo
/done
/quit
```

`/why` explains why the current question matters without exposing modeling jargon.

## Project files

```text
arcadia_oa_llamacpp_networkx_v4/
├── app.py
├── graph_model.py
├── llm_service.py
├── ontology.py
├── validator.py
├── config.json
├── requirements.txt
├── .gitignore
└── models/
    ├── PUT_GGUF_HERE.txt
    └── model.gguf
```

# Windows installation — recommended path

> **Important:** use **Python 3.12** for this project on Windows. The commands below deliberately install a pre-built CPU wheel for `llama-cpp-python`. This avoids compiling `llama.cpp` with CMake/Visual Studio.

## 1. Install Python 3.12 if necessary

Check whether Python 3.12 is available:

```powershell
py -3.12 --version
```

Expected output:

```text
Python 3.12.x
```

If Python 3.12 is not installed:

```powershell
winget install -e --id Python.Python.3.12
```

Close and reopen the terminal after installation.

## 2. Open the project folder

Example:

```powershell
cd D:\AI\MBSE_New\arcadia_oa_llamacpp_networkx_v4\arcadia_oa_llamacpp_networkx_v4
```

## 3. Create the virtual environment with Python 3.12

If an old `.venv` already exists and was created with another Python version, remove it first.

```powershell
deactivate
Remove-Item -Recurse -Force .venv
```

If `deactivate` is not recognized, simply continue.

Create the new environment explicitly with Python 3.12:

```powershell
py -3.12 -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Verify the Python version:

```powershell
python --version
```

It should show:

```text
Python 3.12.x
```

Do not continue with Python 3.14 for this setup.

## 4. Upgrade pip

```powershell
python -m pip install --upgrade pip
```

## 5. Install the project dependencies

**Use this exact command instead of plain `pip install -r requirements.txt`:**

```powershell
pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --prefer-binary
```

The extra index tells `pip` to use the pre-built CPU wheel for `llama-cpp-python` instead of trying to compile it locally.

During installation, you should see a wheel compatible with Python 3.12, typically containing `cp312` in its filename.

You should **not** see a long CMake build beginning with:

```text
Building wheel for llama-cpp-python ...
```

## 6. Verify `llama-cpp-python`

```powershell
python -c "import llama_cpp; print('llama-cpp-python:', llama_cpp.__version__)"
```

If a version number is printed, the Python binding is installed correctly.

## 7. Add the GGUF model

Place your model at:

```text
models\model.gguf
```

For the current test setup, the recommended model is:

```text
qwen2.5-3b-instruct-q4_k_m.gguf
```

Rename or copy it to:

```text
models\model.gguf
```

## 8. Test that the GGUF loads

```powershell
python -c "from llama_cpp import Llama; llm=Llama(model_path='models/model.gguf', n_ctx=4096, verbose=False); print('MODEL LOADED OK')"
```

Expected output:

```text
MODEL LOADED OK
```

## 9. Run the application

```powershell
python app.py
```

The saved graph is written to:

```text
oa_model.json
```

# Troubleshooting

## Error: `CMAKE_C_COMPILER not set`, `CMAKE_CXX_COMPILER not set`, or `nmake: no such file or directory`

Example:

```text
CMake Error: CMAKE_C_COMPILER not set
CMake Error: CMAKE_CXX_COMPILER not set
'nmake' failed with: no such file or directory
```

This means `pip` is trying to **compile `llama-cpp-python` from source**.

For this project, do not fix that by installing a compiler. Instead:

1. Confirm that the virtual environment uses Python 3.12:

```powershell
python --version
```

2. Upgrade pip:

```powershell
python -m pip install --upgrade pip
```

3. Install again using the pre-built wheel index:

```powershell
pip install -r requirements.txt --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu --prefer-binary
```

## Configuration

Default `config.json`:

```json
{
  "model_path": "models/model.gguf",
  "n_ctx": 4096,
  "n_threads": 8,
  "n_gpu_layers": 0,
  "chat_format": null
}
```

For a CPU-only first test, keep `n_gpu_layers` at `0`.
