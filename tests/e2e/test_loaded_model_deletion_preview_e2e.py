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
BASE_URL = "http://127.0.0.1:5008"


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
def web_server_deletion_preview():
    env = os.environ.copy()
    env["MBSE_WEB_SECRET"] = "ci-deletion-preview-secret"
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            "import web_app; web_app.app.run(host='127.0.0.1', port=5008, debug=False, threaded=True)",
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


def _model() -> dict:
    return {
        "directed": True,
        "multigraph": True,
        "graph": {
            "model": "Arcadia Operational Analysis",
            "model_name": "Deletion preview model",
        },
        "nodes": [
            {
                "id": "goal",
                "type": "OperationalCapability",
                "name": "Respond to threat",
            },
            {
                "id": "operator",
                "type": "OperationalActor",
                "name": "Operator",
                "nature": "human_individual",
                "expects_activity": True,
            },
            {
                "id": "center",
                "type": "OperationalEntity",
                "name": "Control Center",
                "nature": "unspecified",
                "expects_activity": True,
            },
            {
                "id": "detect",
                "type": "OperationalActivity",
                "name": "Detect Threat",
            },
            {
                "id": "assess",
                "type": "OperationalActivity",
                "name": "Assess Threat",
            },
        ],
        "edges": [
            {"source": "operator", "target": "detect", "key": 0, "type": "PERFORMS"},
            {"source": "center", "target": "assess", "key": 0, "type": "PERFORMS"},
            {"source": "detect", "target": "goal", "key": 0, "type": "SUPPORTS_CAPABILITY"},
            {
                "source": "detect",
                "target": "assess",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Threat Information",
            },
            {
                "source": "operator",
                "target": "center",
                "key": 0,
                "type": "COMMUNICATION_MEAN",
                "name": "Radio",
                "exchange_refs": [
                    {
                        "source_activity_id": "detect",
                        "target_activity_id": "assess",
                        "edge_key": 0,
                        "exchange_name": "Threat Information",
                    }
                ],
            },
        ],
    }


def _start_activity_delete(page) -> None:
    page.get_by_role("button", name="Delete something", exact=True).click()
    page.get_by_role("button", name="Activities", exact=True).click()
    page.get_by_role("button", name="Detect Threat", exact=True).click()


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_deletion_preview_is_red_orange_and_requires_confirmation(
    web_server_deletion_preview,
    tmp_path,
):
    from playwright.sync_api import expect, sync_playwright

    model_file = tmp_path / "deletion-preview-model.json"
    model_file.write_text(json.dumps(_model()), encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1050})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            page.locator("#loadModelInput").set_input_files(str(model_file))

            expect(page.get_by_role("button", name="Delete something", exact=True)).to_be_visible(
                timeout=20_000
            )
            _start_activity_delete(page)

            expect(page.get_by_text("Delete 'Detect Threat'?", exact=True)).to_be_visible(
                timeout=20_000
            )
            expect(page.get_by_role("button", name="Yes", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="No", exact=True)).to_be_visible()

            # The canonical model is untouched while confirmation is pending.
            preview_state = page.evaluate(
                """async () => {
                    const state = await fetch('/api/state').then(response => response.json());
                    return {
                      preview: state.model.deletion_preview,
                      hasDetect: state.model.nodes.some(node => node.id === 'detect')
                    };
                }"""
            )
            assert preview_state["hasDetect"] is True
            assert preview_state["preview"]["target"]["name"] == "Detect Threat"
            assert "detect" in preview_state["preview"]["target_node_ids"]
            assert "operator" in preview_state["preview"]["impact_node_ids"]

            # Pseudo-code: target red, side-effect context orange.
            page.get_by_role("tab", name="Pseudo-code", exact=True).click()
            expect(page.locator("#utilityTextView .oa-deletion-preview-summary")).to_be_visible(
                timeout=20_000
            )
            expect(
                page.locator("#modelTextual .oa-deletion-target").filter(has_text="Detect Threat")
            ).to_have_count(1)
            expect(
                page.locator("#modelTextual .oa-deletion-impact").filter(has_text="Operator").first
            ).to_be_visible()

            # Diagram: the deleted component itself is red and impacted participants are orange.
            page.get_by_role("tab", name="Diagram", exact=True).click()
            expect(page.locator('[data-node-id="detect"].oa-deletion-target')).to_be_visible(timeout=20_000)
            expect(page.locator('[data-node-id="operator"].oa-deletion-impact')).to_be_visible(timeout=20_000)
            expect(page.locator("#diagramTab .oa-deletion-preview-summary")).to_contain_text(
                "Red — pending deletion"
            )
            expect(page.locator("#diagramTab .oa-deletion-preview-summary")).to_contain_text(
                "Orange — affected"
            )

            # SysML remains the real current text, but the declaration to be deleted is red
            # and lines that will be affected are orange.
            page.get_by_role("tab", name="SysML V2", exact=True).click()
            expect(
                page.locator("#utilitySysmlView .oa-sysml-deletion-line").filter(
                    has_text="oa_activity_Detect_Threat"
                )
            ).to_have_count(1)
            expect(page.locator("#utilitySysmlView .oa-sysml-impact-line").first).to_be_visible()

            # No cancels the destructive action and removes the entire preview state.
            page.get_by_role("button", name="No", exact=True).click()
            expect(page.get_by_role("button", name="Delete something", exact=True)).to_be_visible(
                timeout=20_000
            )
            cancelled_state = page.evaluate(
                """async () => {
                    const state = await fetch('/api/state').then(response => response.json());
                    return {
                      preview: state.model.deletion_preview || null,
                      hasDetect: state.model.nodes.some(node => node.id === 'detect')
                    };
                }"""
            )
            assert cancelled_state == {"preview": None, "hasDetect": True}

            # Repeat and confirm. Only now does the persisted model lose the activity.
            _start_activity_delete(page)
            expect(page.get_by_text("Delete 'Detect Threat'?", exact=True)).to_be_visible(
                timeout=20_000
            )
            page.get_by_role("button", name="Yes", exact=True).click()
            expect(page.get_by_role("button", name="Delete something", exact=True)).to_be_visible(
                timeout=20_000
            )
            confirmed_state = page.evaluate(
                """async () => {
                    const state = await fetch('/api/state').then(response => response.json());
                    const radio = state.model.edges.find(edge => edge.type === 'COMMUNICATION_MEAN');
                    return {
                      preview: state.model.deletion_preview || null,
                      hasDetect: state.model.nodes.some(node => node.id === 'detect'),
                      hasThreatExchange: state.model.edges.some(edge => edge.name === 'Threat Information'),
                      radioRefs: radio?.exchange_refs || []
                    };
                }"""
            )
            assert confirmed_state == {
                "preview": None,
                "hasDetect": False,
                "hasThreatExchange": False,
                "radioRefs": [],
            }
        finally:
            browser.close()
