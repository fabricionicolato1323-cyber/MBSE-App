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
def diagram_web_server_v4():
    env = os.environ.copy()
    env["MBSE_WEB_SECRET"] = "ci-diagram-v4-e2e-secret"
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
    return {
        "nodes": [
            {"id": "battlefield", "type": "OperationalEntity", "name": "Battle field", "status": "confirmed"},
            {"id": "soldier", "type": "OperationalActor", "name": "Soldier", "status": "confirmed"},
            {"id": "detector", "type": "OperationalEntity", "name": "Threat detection system", "status": "confirmed"},
            {"id": "engage", "type": "OperationalActivity", "name": "Engage threats", "status": "confirmed"},
            {"id": "report", "type": "OperationalActivity", "name": "Report threat engagement", "status": "confirmed"},
            {"id": "detect", "type": "OperationalActivity", "name": "Detect incoming threats", "status": "confirmed"},
            {"id": "rate", "type": "OperationalActivity", "name": "Calculate rate of kill", "status": "confirmed"},
        ],
        "drafts": [],
        "edges": [
            {"source": "soldier", "target": "engage", "type": "PERFORMS"},
            {"source": "soldier", "target": "report", "type": "PERFORMS"},
            {"source": "detector", "target": "detect", "type": "PERFORMS"},
            {"source": "detector", "target": "rate", "type": "PERFORMS"},
            {"source": "soldier", "target": "battlefield", "type": "LOCATED_IN"},
            {"source": "detector", "target": "battlefield", "type": "LOCATED_IN"},
            # Legacy loaded interaction: it predates exchange_refs but there is
            # exactly one Communication Mean between the two performers.
            {"source": "detect", "target": "engage", "type": "OPERATIONAL_EXCHANGE", "name": "Threat location"},
            # New interaction explicitly associated with the existing Radio link.
            {"source": "report", "target": "rate", "type": "OPERATIONAL_EXCHANGE", "name": "Kill count", "communication_assignment": "assigned"},
            {
                "source": "detector",
                "target": "soldier",
                "type": "COMMUNICATION_MEAN",
                "name": "Radio link",
                "exchange_refs": [
                    {
                        "source_activity_id": "report",
                        "target_activity_id": "rate",
                        "exchange_name": "Kill count",
                    }
                ],
            },
        ],
    }


def _drag(page, selector: str, dx: float, dy: float, button: str = "left") -> None:
    target = page.locator(selector)
    box = target.bounding_box()
    assert box is not None
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down(button=button)
    page.mouse.move(x + dx, y + dy, steps=10)
    page.mouse.up(button=button)
    page.wait_for_timeout(160)


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_scroll_area_zoom_fullscreen_four_direction_growth_and_movable_ports(diagram_web_server_v4):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        try:
            page.goto(BASE_URL, wait_until="load")
            page.wait_for_function("() => !!window.oaDiagram", timeout=20_000)
            page.wait_for_function(
                "() => document.getElementById('oaDiagramViewport')?.dataset.portDragInstalled === 'true'",
                timeout=20_000,
            )
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            page.route("**/api/state", lambda route: route.abort())
            page.evaluate("() => { window.applyState = function () {}; }")
            page.get_by_role("tab", name="Diagram").click()
            page.evaluate("model => window.oaDiagram.render(model, 'diagram-v4-e2e')", _diagram_model())
            page.evaluate("() => window.oaDiagram.resetLayout()")
            page.wait_for_timeout(350)

            # The old Threat location interaction and the newer Kill count
            # interaction must both route through the sole Radio link. There
            # must be no direct Activity-to-Activity exchange in this legacy
            # compatibility case.
            expect(page.locator("#oaDiagramEdges .direct-exchange")).to_have_count(0)
            expect(page.locator("#oaDiagramEdges .source-segment")).to_have_count(2)
            expect(page.locator("#oaDiagramEdges .target-segment")).to_have_count(2)
            expect(page.locator("#oaDiagramEdges .communication-mean")).to_have_count(1)

            communication_label = page.locator("#oaDiagramEdges .communication-label")
            expect(communication_label).to_contain_text("Radio link")
            expect(communication_label).to_contain_text("Threat location")
            expect(communication_label).to_contain_text("Kill count")

            # Arrow tips are exactly half of their previous marker dimensions.
            marker_sizes = page.evaluate(
                """() => ({
                    interaction: [
                        document.getElementById('oaInteractionArrow')?.getAttribute('markerWidth'),
                        document.getElementById('oaInteractionArrow')?.getAttribute('markerHeight')
                    ],
                    relation: [
                        document.getElementById('oaRelationArrow')?.getAttribute('markerWidth'),
                        document.getElementById('oaRelationArrow')?.getAttribute('markerHeight')
                    ]
                })"""
            )
            assert marker_sizes["interaction"] == ["4.5", "4.5"]
            assert marker_sizes["relation"] == ["4", "4"]

            # Communication ports P slide vertically on the participant border.
            first_port = page.locator(".oa-diagram-port").first
            port_before = first_port.bounding_box()
            assert port_before is not None
            _drag(page, ".oa-diagram-port", 0, 85)
            port_after = page.locator(".oa-diagram-port").first.bounding_box()
            assert port_after is not None
            assert port_after["y"] > port_before["y"] + 25
            assert abs(port_after["x"] - port_before["x"]) < 8
            saved_ports = page.evaluate(
                """() => Object.keys(localStorage)
                    .filter(key => key.startsWith('oa-diagram-ports:v1:'))
                    .map(key => JSON.parse(localStorage.getItem(key) || '{}'))"""
            )
            assert saved_ports and any(saved_ports[0].values())

            # Native scrollbars support both axes. Artificially enlarge the scene
            # here so the browser must expose real horizontal and vertical scroll.
            overflow = page.evaluate("() => getComputedStyle(document.getElementById('oaDiagramViewport')).overflow")
            assert overflow == "auto"
            scroll = page.evaluate(
                """() => {
                    const viewport = document.getElementById('oaDiagramViewport');
                    const scene = document.getElementById('oaDiagramScene');
                    scene.style.width = '2200px'; scene.style.height = '1600px';
                    viewport.scrollLeft = 180; viewport.scrollTop = 140;
                    return {left: viewport.scrollLeft, top: viewport.scrollTop};
                }"""
            )
            assert scroll["left"] > 0
            assert scroll["top"] > 0
            page.evaluate("() => window.oaDiagram.resetLayout()")
            page.wait_for_timeout(250)

            def box(node_id: str) -> dict:
                result = page.locator(f'[data-node-id="{node_id}"]').bounding_box()
                assert result is not None
                return result

            # Move an internal activity far enough left/up to cross its current
            # parent padding. The activity must keep the requested position and
            # the Soldier container must expand by moving its left/top boundaries.
            report_before = box("report")
            soldier_before = box("soldier")
            battlefield_before = box("battlefield")
            _drag(page, '[data-node-id="report"]', -105, -135)
            report_after = box("report")
            soldier_after = box("soldier")
            battlefield_after = box("battlefield")

            assert report_after["x"] < report_before["x"] - 35
            assert report_after["y"] < report_before["y"] - 35
            assert soldier_after["x"] < soldier_before["x"] - 20
            assert soldier_after["y"] < soldier_before["y"] - 10
            assert soldier_after["width"] > soldier_before["width"] + 15
            assert soldier_after["height"] > soldier_before["height"] + 8
            assert battlefield_after["x"] <= battlefield_before["x"]
            assert battlefield_after["y"] <= battlefield_before["y"]
            assert battlefield_after["width"] >= battlefield_before["width"]
            assert battlefield_after["height"] >= battlefield_before["height"]

            # Right-button drag selects an area and zooms it to the viewport.
            page.evaluate("() => window.oaDiagram.resetLayout()")
            page.wait_for_timeout(250)
            zoom_before = page.evaluate("() => window.oaDiagram.getView().zoom")
            viewport_box = page.locator("#oaDiagramViewport").bounding_box()
            assert viewport_box is not None
            x = viewport_box["x"] + viewport_box["width"] * 0.25
            y = viewport_box["y"] + viewport_box["height"] * 0.25
            page.mouse.move(x, y)
            page.mouse.down(button="right")
            page.mouse.move(
                x + viewport_box["width"] * 0.35,
                y + viewport_box["height"] * 0.35,
                steps=8,
            )
            expect(page.locator("#oaDiagramZoomRect")).to_be_visible()
            page.mouse.up(button="right")
            page.wait_for_timeout(120)
            expect(page.locator("#oaDiagramZoomRect")).to_be_hidden()
            zoom_after = page.evaluate("() => window.oaDiagram.getView().zoom")
            assert zoom_after > zoom_before

            # Test the deterministic fullscreen fallback rather than depending on
            # browser fullscreen permissions in a headless CI environment.
            page.evaluate(
                """() => Object.defineProperty(Element.prototype, 'requestFullscreen', {
                    configurable: true, value: undefined
                })"""
            )
            fullscreen = page.locator("#oaDiagramFullscreen")
            expect(fullscreen).to_be_visible()
            fullscreen.click()
            expect(page.locator("#diagramTab")).to_have_class("tab-content active oa-diagram-fullscreen-fallback")
            expect(fullscreen).to_have_attribute("aria-pressed", "true")
            fullscreen.click()
            expect(fullscreen).to_have_attribute("aria-pressed", "false")
        finally:
            browser.close()
