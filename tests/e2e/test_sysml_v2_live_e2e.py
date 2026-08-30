from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


PROJECT_DIR = Path(__file__).resolve().parents[2]
BASE_URL = "http://127.0.0.1:5011"


def _wait_for_server(timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(BASE_URL, timeout=1.0) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        time.sleep(0.2)
    raise RuntimeError(f"Web app did not start in time: {last_error}")


@pytest.fixture(scope="module")
def web_server_sysml_v2():
    env = os.environ.copy()
    env["MBSE_WEB_SECRET"] = "ci-sysml-v2-secret"
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            "import web_app; web_app.app.run(host='127.0.0.1', port=5011, debug=False, threaded=True)",
        ],
        cwd=PROJECT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        _wait_for_server()
        yield process
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_sysml_view_is_generated_from_arcadiaoa_contract_and_updates_after_load(
    web_server_sysml_v2,
    tmp_path,
):
    from playwright.sync_api import expect, sync_playwright

    model = {
        "directed": True,
        "multigraph": True,
        "graph": {
            "model": "Arcadia Operational Analysis",
            "model_name": "SysML contract E2E",
        },
        "nodes": [
            {
                "id": "entity:center",
                "type": "OperationalEntity",
                "name": "Control Center",
                "nature": "infrastructure_or_facility",
            },
            {
                "id": "actor:operator",
                "type": "OperationalActor",
                "name": "Operator",
                "nature": "human_individual",
            },
            {
                "id": "activity:detect",
                "type": "OperationalActivity",
                "name": "Detect Threat",
            },
            {
                "id": "activity:assess",
                "type": "OperationalActivity",
                "name": "Assess Threat",
            },
        ],
        "edges": [
            {
                "source": "entity:center",
                "target": "actor:operator",
                "key": 0,
                "type": "CONTAINS",
            },
            {
                "source": "actor:operator",
                "target": "activity:detect",
                "key": 0,
                "type": "PERFORMS",
            },
            {
                "source": "entity:center",
                "target": "activity:assess",
                "key": 0,
                "type": "PERFORMS",
            },
            {
                "source": "activity:detect",
                "target": "activity:assess",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Threat Information",
            },
            {
                "source": "actor:operator",
                "target": "entity:center",
                "key": 0,
                "type": "COMMUNICATION_MEAN",
                "name": "Radio",
            },
        ],
    }
    model_file = tmp_path / "sysml-contract-e2e.json"
    model_file.write_text(json.dumps(model), encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1050})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            page.locator("#loadModelInput").set_input_files(str(model_file))
            expect(page.locator("#modelFileName")).to_have_text(
                "SysML contract E2E",
                timeout=20_000,
            )

            page.locator('[data-output-tab="sysml"]').click()
            code = page.locator("#utilitySysmlView code")
            expect(code).to_contain_text("flow def OperationalExchange;", timeout=20_000)
            expect(code).to_contain_text("connection def CommunicationMean;")
            expect(code).to_contain_text(
                "flow oa_exchange_Threat_Information : OperationalExchange"
            )
            expect(code).to_contain_text(
                "connection oa_communication_Radio : CommunicationMean connect"
            )
            expect(code).not_to_contain_text("port oa_communication_Radio")
        finally:
            browser.close()
