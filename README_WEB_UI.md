# Web chat interface prototype

This branch adds a browser interface without replacing the existing terminal application.
The existing guided workflow remains the authoritative source for sequencing, validation,
confirmation, undo, save, checks, composition/decomposition and characteristics.

## Layout

- Left ~2/3: chat-like guided interaction.
- Right ~1/3: live model panel, with Textual as the default view.
- Confirmed model elements use the confirmed color.
- User input waiting for confirmation is shown as temporary with a different color.
- Common commands are available as buttons above the chat.
- Questions are visually emphasized while explanations and expected-answer guidance are secondary.

## Permanent structured-input contract

The web UI follows a permanent cognitive-load rule: if the answer can be selected, the user
clicks it; typing is reserved for genuinely new free-text content.

- Every yes/no question is rendered as clickable **Yes** and **No** controls.
- Every numbered/fixed choice is rendered as clickable labels; the user never needs to type
  `1`, `2`, `3`, and so on.
- Continue steps are rendered as a clickable **Continue** control.
- The free-text composer is hidden for all structured interactions.
- Structured control values (`yes`, `no`, numeric indexes, Continue) are never persistent or
  temporary model facts.

The worker emits an explicit interaction contract and the browser contains a defensive fallback
that detects visible yes/no or numbered prompts. This two-layer enforcement prevents an old or
malformed free-text state from making a structured question require typing.

## Run on Windows

```powershell
cd MBSE-App
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python web_app.py
```

Then open `http://127.0.0.1:5000` in a browser.

The original terminal version is still available with:

```powershell
python app.py
```

## Runtime AI assistance

The web application starts each new modeling session in deterministic mode. AI support is
an explicit user choice and does not require editing `config.json` or restarting the model.

The compact header control intentionally exposes only the state and one action:

- red indicator + **AI Off** + **Activate AI** when disabled;
- green indicator + **AI On** + **Deactivate AI** when active.

Selecting **Activate AI** queries the local Ollama service for the models actually installed on
the computer and displays those names in a dropdown. Selecting a model activates that
`OllamaLLM` client for the current web session only. **Deactivate AI** immediately returns the
same session to deterministic mode. The selected model name remains internal session state and
is not shown in the compact header.

No model name is hardcoded in the web control. AI remains advisory: deterministic write rules
and user confirmation remain authoritative for persistent model facts.

## Architecture

`web_app.py` hosts the local Flask UI. `web_bridge.py` adapts browser messages to the
existing terminal workflow. `web_worker.py` runs the existing OAApp in a child Python process
and uses an autosaving `OAGraph` subclass so the right-hand model view is updated after every
accepted graph change.

`web_ai.py` provides local-model discovery plus a session-local control channel. AI control
messages are separate from modeling answers, so selecting or disabling an AI model cannot be
mistaken for model content.

## Semantic neutrality

The runtime separates deterministic rules from vocabulary:

- `ontology.py` contains structural concepts, relations and definitions only.
- `participant_lexicon.json` contains replaceable, domain-neutral participant vocabulary.
- `semantic_policy.json` contains replaceable linguistic and solution-bias heuristics.
- `ui_guidance.json` contains structural placeholders and disables literal domain examples.
- User facts are written to the model only after explicit user confirmation.

The participant base lexicon can be replaced without Python changes:

```powershell
$env:MBSE_PARTICIPANT_LEXICON_PATH = "<path-to-json>"
```

Optional participant vocabulary can be added separately:

```powershell
$env:MBSE_PARTICIPANT_LEXICON_EXTENSIONS_PATH = "<path-to-json>"
```

The semantic heuristic policy can also be replaced:

```powershell
$env:MBSE_SEMANTIC_POLICY_PATH = "<path-to-json>"
```

These files contain no application scenario. Domain-specific vocabulary belongs only in
an explicitly selected local configuration, not in runtime Python or the ontology.
