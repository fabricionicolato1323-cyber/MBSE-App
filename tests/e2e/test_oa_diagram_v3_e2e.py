from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


PROJECT_DIR = Path(__file__).resolve().parents[2]
BASE_URL = "http://127.0.0.1:5000"


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
def diagram_web_server():
    env = os.environ.copy()
    env["MBSE_WEB_SECRET"] = "ci-diagram-e2e-secret"
    process = subprocess.Popen(
        [sys.executable, "-u", "web_app.py"],
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


def _diagram_model() -> dict:
    nodes = [
        {"id": "capability", "type": "OperationalCapability", "name": "Keep engagement area safe", "status": "confirmed"},
        {"id": "battlefield", "type": "OperationalEntity", "name": "Battle field", "status": "confirmed"},
        {"id": "soldier", "type": "OperationalActor", "name": "Soldier", "status": "confirmed"},
        {"id": "detector", "type": "OperationalEntity", "name": "Threat detection system", "status": "confirmed"},
        {"id": "engage", "type": "OperationalActivity", "name": "Engage threats", "status": "confirmed"},
        {"id": "report", "type": "OperationalActivity", "name": "Report threat engagement", "status": "confirmed"},
        {"id": "detect", "type": "OperationalActivity", "name": "Detect incoming threats", "status": "confirmed"},
        {"id": "rate", "type": "OperationalActivity", "name": "Calculate rate of kill", "status": "confirmed"},
    ]
    edges = [
        {"source": "soldier", "target": "engage", "type": "PERFORMS"},
        {"source": "soldier", "target": "report", "type": "PERFORMS"},
        {"source": "detector", "target": "detect", "type": "PERFORMS"},
        {"source": "detector", "target": "rate", "type": "PERFORMS"},
        {"source": "soldier", "target": "battlefield", "type": "LOCATED_IN"},
        {"source": "detector", "target": "battlefield", "type": "LOCATED_IN"},
        {"source": "engage", "target": "capability", "type": "SUPPORTS_CAPABILITY"},
        {"source": "report", "target": "capability", "type": "SUPPORTS_CAPABILITY"},
        {"source": "detect", "target": "capability", "type": "SUPPORTS_CAPABILITY"},
        {"source": "rate", "target": "capability", "type": "SUPPORTS_CAPABILITY"},
        {
            "source": "detect",
            "target": "report",
            "type": "OPERATIONAL_EXCHANGE",
            "name": "Threat report",
        },
        {
            "source": "detector",
            "target": "soldier",
            "type": "COMMUNICATION_MEAN",
            "name": "Radio link",
            "exchange_refs": [
                {
                    "source_activity_id": "detect",
                    "target_activity_id": "report",
                    "exchange_name": "Threat report",
                }
            ],
        },
    ]
    return {"nodes": nodes, "drafts": [], "edges": edges}


def _contains(parent: dict, child: dict, tolerance: float = 2.0) -> bool:
    return (
        child["x"] >= parent["x"] - tolerance
        and child["y"] >= parent["y"] - tolerance
        and child["x"] + child["width"] <= parent["x"] + parent["width"] + tolerance
        and child["y"] + child["height"] <= parent["y"] + parent["height"] + tolerance
    )


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_nested_containment_drag_capability_toggle_and_communication_routing(diagram_web_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        try:
            page.goto(BASE_URL, wait_until="load")
            page.wait_for_function("() => !!window.oaDiagram", timeout=20_000)
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)

            # Stop background state refresh from replacing the synthetic diagram model.
            page.route("**/api/state", lambda route: route.abort())
            page.evaluate("() => { window.applyState = function () {}; }")
            page.get_by_role("tab", name="Diagram").click()
            page.evaluate("model => window.oaDiagram.render(model, 'diagram-v3-e2e')", _diagram_model())
            page.evaluate("() => window.oaDiagram.resetLayout()")
            page.wait_for_timeout(250)

            def box(node_id: str) -> dict:
                result = page.locator(f'[data-node-id="{node_id}"]').bounding_box()
                assert result is not None
                return result

            battlefield = box("battlefield")
            soldier = box("soldier")
            detector = box("detector")
            engage = box("engage")
            report = box("report")
            detect = box("detect")
            rate = box("rate")

            assert _contains(battlefield, soldier)
            assert _contains(battlefield, detector)
            assert _contains(soldier, engage)
            assert _contains(soldier, report)
            assert _contains(detector, detect)
            assert _contains(detector, rate)

            expect(page.locator(".oa-diagram-edge.communication-mean")).to_have_count(1)
            expect(page.locator(".oa-diagram-edge.routed-segment")).to_have_count(2)
            expect(page.locator(".oa-diagram-edge.direct-exchange")).to_have_count(0)
            expect(page.locator(".oa-diagram-port")).to_have_count(2)

            toggle = page.locator("#oaDiagramCapabilitiesToggle")
            expect(toggle).to_have_attribute("aria-pressed", "false")
            expect(page.locator('[data-node-id="capability"]')).to_have_count(0)
            expect(page.locator('.oa-diagram-edge[data-edge-type="SUPPORTS_CAPABILITY"]')).to_have_count(0)

            toggle.click()
            expect(toggle).to_have_attribute("aria-pressed", "true")
            expect(page.locator('[data-node-id="capability"]')).to_have_count(1)

            toggle.click()
            expect(toggle).to_have_attribute("aria-pressed", "false")
            expect(page.locator('[data-node-id="capability"]')).to_have_count(0)

            soldier_before = box("soldier")
            report_before = box("report")
            drag_handle = page.locator('[data-node-id="soldier"] .oa-diagram-node-header')
            handle_box = drag_handle.bounding_box()
            assert handle_box is not None
            start_x = handle_box["x"] + handle_box["width"] / 2
            start_y = handle_box["y"] + handle_box["height"] / 2
            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x + 90, start_y + 55, steps=8)
            page.mouse.up()
            page.wait_for_timeout(100)

            soldier_after = box("soldier")
            report_after = box("report")
            soldier_dx = soldier_after["x"] - soldier_before["x"]
            soldier_dy = soldier_after["y"] - soldier_before["y"]
            report_dx = report_after["x"] - report_before["x"]
            report_dy = report_after["y"] - report_before["y"]
            assert soldier_dx > 20
            assert soldier_dy > 10
            assert abs(report_dx - soldier_dx) < 4
            assert abs(report_dy - soldier_dy) < 4
        finally:
            browser.close()