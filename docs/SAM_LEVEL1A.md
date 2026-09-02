# SAM Integration — Level 1A

Level 1A prepares the complete Operational Analysis model as textual SysML v2 and shows it inside the existing **SysML V2** output view.

This phase does **not** write to SAM. The successful Gate 0 connection remains independent from this preview.

## Scope

Level 1A:

1. reads the current confirmed model;
2. includes the current Operational Scenarios in the complete semantic projection;
3. preserves temporary/unconfirmed input only according to the existing translation policy;
4. generates the SysML v2 text through the existing ArcadiaOA translation contract;
5. exposes an explicit `sysml_v2_level1` preview contract in `/api/state`;
6. renders **Level 1 · Model** in the text-based SysML V2 window;
7. allows the Level 1 text to be exported as `<model>.level1.sysml`;
8. performs no PySAM create/update/commit/publish operation.

## UI behavior

Open the application and select:

`Model output` → `SysML V2`

The view shows:

- **Level 1 · Model** — active;
- **Level 2 · Views** — visible but disabled until Level 2 is implemented;
- model element, relationship, and scenario counts;
- the status **SAM not written**;
- the textual SysML v2 model;
- **Export Level 1 .sysml**.

The SysML V2 view remains textual. It does not create a block diagram.

## Run locally on Windows

```powershell
git fetch
git checkout feature/sam-level1a-sysml-preview
git pull
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python web_app.py
```

Then open the local address shown by Flask, normally `http://127.0.0.1:5000`.

## Tests

Run the Level 1A contract tests:

```powershell
python -m pytest -q tests/test_sysml_level1.py tests/test_sysml_v2_ui_contract.py
```

Run all tests:

```powershell
python -m pytest -q
```

## Acceptance criteria

Level 1A is complete when:

- the complete confirmed model produces textual SysML v2;
- the text updates with the live model;
- the SysML V2 window clearly identifies the output as **Level 1 · Model**;
- Level 2 is not presented as implemented;
- the exported `.sysml` text matches the displayed Level 1 text;
- the UI explicitly reports that SAM has not been written;
- all automated tests pass.

After this phase is validated, Level 1B can use the same Level 1 projection as the input contract for PySAM synchronization to the configured SAM test project.
