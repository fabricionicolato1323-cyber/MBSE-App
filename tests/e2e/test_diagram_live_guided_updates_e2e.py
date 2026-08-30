from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


PROJECT_DIR = Path(__file__).resolve().parents[2]
BASE_URL = "http://127.0.0.1:5005"


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
def web_server_diagram_live_updates():
    env = os.environ.copy()
    env["MBSE_WEB_SECRET"] = "ci-diagram-live-update-secret"
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            "import web_app; web_app.app.run(host='127.0.0.1', port=5005, debug=False, threaded=True)",
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


def _assigned_communication_model() -> dict:
    exchange_ref = {
        "source_activity_id": "report",
        "target_activity_id": "calculate",
        "exchange_name": "Kill count",
    }
    return {
        "directed": True,
        "multigraph": True,
        "graph": {
            "model": "Arcadia Operational Analysis",
            "model_name": "Live diagram update model",
        },
        "nodes": [
            {
                "id": "goal",
                "type": "OperationalCapability",
                "name": "Keep engagement area safe",
            },
            {
                "id": "soldier",
                "type": "OperationalActor",
                "name": "Soldier",
                "nature": "human_individual",
                "expects_activity": True,
            },
            {
                "id": "detector",
                "type": "OperationalEntity",
                "name": "Threat detection system",
                "nature": "unspecified",
                "expects_activity": True,
            },
            {
                "id": "report",
                "type": "OperationalActivity",
                "name": "Report threat engagement",
            },
            {
                "id": "calculate",
                "type": "OperationalActivity",
                "name": "Calculate rate of kill",
            },
        ],
        "edges": [
            {"source": "soldier", "target": "report", "key": 0, "type": "PERFORMS"},
            {"source": "detector", "target": "calculate", "key": 0, "type": "PERFORMS"},
            {"source": "report", "target": "goal", "key": 0, "type": "SUPPORTS_CAPABILITY"},
            {"source": "calculate", "target": "goal", "key": 0, "type": "SUPPORTS_CAPABILITY"},
            {
                "source": "report",
                "target": "calculate",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Kill count",
                "communication_assignment": "assigned",
            },
            {
                "source": "soldier",
                "target": "detector",
                "key": 0,
                "type": "COMMUNICATION_MEAN",
                "name": "Radio link",
                "exchange_refs": [exchange_ref],
            },
        ],
    }


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_guided_communication_change_updates_detached_model_projections_without_reload(
    web_server_diagram_live_updates,
    tmp_path,
):
    from playwright.sync_api import expect, sync_playwright

    model_file = tmp_path / "live-diagram-update.json"
    model_file.write_text(json.dumps(_assigned_communication_model()), encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1550, "height": 1000})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            page.locator("#loadModelInput").set_input_files(str(model_file))
            expect(
                page.get_by_role("button", name="Change something that already exists", exact=True)
            ).to_be_visible(timeout=20_000)

            # Pseudo-code is a live projection of the same model. It must expose
            # the communication decision and keep updating in its detached window.
            expect(
                page.locator("#modelTextual .exchange-communication-line")
            ).to_contain_text("Communication: Radio link", timeout=10_000)
            with page.expect_popup() as pseudo_popup_info:
                page.locator("#modelPanel [data-panel-action='dock']").click()
            pseudo_window = pseudo_popup_info.value
            pseudo_window.wait_for_load_state("domcontentloaded")
            assert "detachedPanel=text" in pseudo_window.url
            expect(
                pseudo_window.locator("#modelTextual .exchange-communication-line")
            ).to_contain_text("Communication: Radio link", timeout=10_000)

            page.get_by_role("tab", name="Diagram", exact=True).click()
            expect(page.locator("#oaDiagramEdges .source-segment")).to_have_count(1, timeout=10_000)
            expect(page.locator("#oaDiagramEdges .direct-exchange")).to_have_count(0)

            with page.expect_popup() as popup_info:
                page.locator("#modelPanel [data-panel-action='dock']").click()
            diagram_window = popup_info.value
            diagram_window.wait_for_load_state("domcontentloaded")
            assert "detachedPanel=diagram" in diagram_window.url
            expect(diagram_window.locator("#oaDiagramEdges .source-segment")).to_have_count(
                1, timeout=10_000
            )
            expect(diagram_window.locator("#oaDiagramEdges .direct-exchange")).to_have_count(0)

            # Change the communication decision through the normal loaded-model
            # guided flow. All detached projections must follow the persisted
            # model update by polling /api/state; no reload or redock is allowed.
            page.get_by_role("button", name="Change something that already exists", exact=True).click()
            page.get_by_role("button", name="Information or material exchanged", exact=True).click()
            page.get_by_role("button", name=re.compile(r"^Kill count"), exact=False).click()
            page.get_by_role("button", name="Communication method", exact=True).click()
            expect(
                page.get_by_text(
                    "How should 'Kill count' be carried between Soldier and Threat detection system?",
                    exact=True,
                )
            ).to_be_visible(timeout=20_000)
            page.get_by_role(
                "button",
                name="No communication method / leave unassigned",
                exact=True,
            ).click()

            expect(diagram_window.locator("#oaDiagramEdges .source-segment")).to_have_count(
                0, timeout=10_000
            )
            expect(diagram_window.locator("#oaDiagramEdges .target-segment")).to_have_count(0)
            expect(diagram_window.locator("#oaDiagramEdges .direct-exchange")).to_have_count(1)

            expect(
                pseudo_window.locator("#modelTextual .exchange-communication-line")
            ).to_contain_text("Communication: Unassigned", timeout=10_000)
            expect(
                pseudo_window.locator("#modelTextual .communication-unassigned")
            ).to_contain_text(
                "No interaction explicitly assigned to this communication method.",
                timeout=10_000,
            )

            persisted = page.evaluate(
                """async () => {
                    const state = await fetch('/api/state').then(response => response.json());
                    const exchange = state.model.edges.find(edge =>
                        edge.type === 'OPERATIONAL_EXCHANGE' && edge.name === 'Kill count'
                    );
                    const radio = state.model.edges.find(edge =>
                        edge.type === 'COMMUNICATION_MEAN' && edge.name === 'Radio link'
                    );
                    const staleRef = (radio?.exchange_refs || []).some(ref =>
                        ref.source_activity_id === 'report' &&
                        ref.target_activity_id === 'calculate' &&
                        ref.exchange_name === 'Kill count'
                    );
                    return {assignment: exchange?.communication_assignment, staleRef};
                }"""
            )
            assert persisted == {"assignment": "none", "staleRef": False}
            assert not pseudo_window.is_closed()
            assert not diagram_window.is_closed()
        finally:
            browser.close()
