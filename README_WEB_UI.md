# Web chat interface prototype

This branch adds a browser interface without replacing the existing terminal application.
The existing guided workflow remains the authoritative source for sequencing, validation,
confirmation, undo, save, checks, composition/decomposition and characteristics.

## Layout

- Left ~2/3: chat-like guided interaction.
- Right ~1/3: live model panel.
- Confirmed model elements use the confirmed color.
- User input waiting for confirmation is shown as temporary with a different color.
- Yes/no questions and numbered choices are surfaced as clickable buttons.
- Common commands are available as buttons above the chat.

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

## Architecture

`web_app.py` hosts the local Flask UI. `web_bridge.py` adapts browser messages to the
existing terminal workflow. `web_worker.py` runs the existing OAApp unchanged in a child
Python process and uses an autosaving `OAGraph` subclass so the right-hand model view is
updated after every accepted graph change.
