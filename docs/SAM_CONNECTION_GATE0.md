# SAM Connection Gate 0

Gate 0 verifies that the MBSE App can authenticate to Ansys System Architecture Modeler (SAM) through PySAM SysML2 and load an existing test project.

This step is intentionally read-only. It does not create, edit, commit, or publish model elements.

## 1. Prerequisites

- Python 3.10 or later.
- Access to a SAM server.
- A SAM organization you can access.
- A disposable/test SAM project.
- A SAM Personal Access Token (PAT).

## 2. Required SAM information

Obtain these four values from your SAM environment:

- `SAM_SERVER_URL`
- `SAM_ORGANIZATION_ID`
- `SAM_PROJECT_ID`
- `SAM_ACCESS_TOKEN`

Do not paste the access token into source code, documentation, chat messages, screenshots, or Git commits.

## 3. Prepare the project on Windows

Open PowerShell in the repository folder.

```powershell
git fetch
git checkout feature/sam-connection-gate0
git pull
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If you already have `.venv`, just activate it and install/update the requirements.

## 4. Create the local SAM configuration

Copy the template:

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in the values:

```text
SAM_SERVER_URL=https://your-sam-server
SAM_ORGANIZATION_ID=your-organization-id
SAM_PROJECT_ID=your-test-project-id
SAM_ACCESS_TOKEN=your-personal-access-token
SAM_USE_SSL=true
```

Keep `SAM_USE_SSL=true` when the server has a valid HTTPS certificate. Set it to `false` only when required for a controlled test environment with an invalid/untrusted certificate.

The `.env` file is ignored by Git and must remain local.

## 5. Run the unit tests first

```powershell
python -m unittest tests.test_sam_connection -v
```

These tests use fake connector objects and do not contact SAM.

## 6. Run the real connection smoke test

```powershell
python sam_connection.py
```

Expected output:

```text
SAM Connection - Gate 0
Server ............. https://your-sam-server
Authentication ..... OK
Organization ....... your-organization-id
Project ............ your-test-project-id
Project load ....... OK

Connection test: PASSED
No SAM model data was changed.
```

## 7. If the test fails

Common categories include:

- missing configuration;
- authentication/token failure;
- organization not found or not accessible;
- project not found or not accessible;
- network/VPN/proxy/firewall issue;
- TLS/SSL certificate issue.

When sharing an error for diagnosis, remove any access token or other secret first.

## Gate 0 acceptance criteria

Gate 0 is complete when:

1. the local unit tests pass;
2. PySAM can authenticate;
3. the configured organization is accepted;
4. the configured test project can be loaded with `get_scripting_project()`;
5. no SAM model data is changed.

Only after Gate 0 passes should Level 1 model synchronization be implemented.
