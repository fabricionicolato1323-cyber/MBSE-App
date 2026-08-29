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
def diagram_scroll_server():
    env = os.environ.copy()
    env["MBSE_WEB_SECRET"] = "ci-diagram-scroll-origin-secret"
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
            {"source": "detect", "target": "engage", "type": "OPERATIONAL_EXCHANGE", "name": "Threat location"},
            {"source": "report", "target": "rate", "type": "OPERATIONAL_EXCHANGE", "name": "Kill count"},
            {"source": "detector", "target": "soldier", "type": "COMMUNICATION_MEAN", "name": "Radio link"},
        ],
    }


def _drag(page, selector: str, dx: float, dy: float) -> None:
    target = page.locator(selector)
    box = target.bounding_box()
    assert box is not None
    x = box["x"] + box["width"] / 2
    y = box["y"] + box["height"] / 2
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + dx, y + dy, steps=12)
    page.mouse.up()
    page.wait_for_timeout(300)


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_leftmost_diagram_content_remains_reachable_by_horizontal_scrollbar(diagram_scroll_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        try:
            page.goto(BASE_URL, wait_until="load")
            page.wait_for_function("() => !!window.oaDiagram", timeout=20_000)
            page.wait_for_function(
                "() => document.getElementById('oaDiagramViewport')?.dataset.scrollOriginInstalled === 'true'",
                timeout=20_000,
            )
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            page.route("**/api/state", lambda route: route.abort())
            page.evaluate("() => { window.applyState = function () {}; }")
            page.get_by_role("tab", name="Diagram").click()
            page.evaluate("model => window.oaDiagram.render(model, 'scroll-origin-e2e')", _diagram_model())
            page.evaluate("() => window.oaDiagram.resetLayout()")
            page.wait_for_timeout(400)

            # Reproduce the reported failure: move a child far enough left that
            # its actor and enclosing entity would previously grow into x < 0.
            _drag(page, '[data-node-id="report"]', -520, 0)

            metrics = page.evaluate(
                """() => {
                    const viewport = document.getElementById('oaDiagramViewport');
                    const outer = document.querySelector('[data-node-id="battlefield"]');
                    const vr = viewport.getBoundingClientRect();
                    const nr = outer.getBoundingClientRect();
                    return {
                        scrollLeft: viewport.scrollLeft,
                        scrollWidth: viewport.scrollWidth,
                        clientWidth: viewport.clientWidth,
                        leftInsideViewport: nr.left - vr.left,
                        view: window.oaDiagram.getView(),
                    };
                }"""
            )
            assert metrics["scrollLeft"] == 0
            assert metrics["leftInsideViewport"] >= 0
            assert metrics["view"]["x"] >= 0
            assert metrics["scrollWidth"] > metrics["clientWidth"]

            # The native scrollbar must travel to the right and then all the way
            # back to zero, where the complete left edge is still visible.
            scroll = page.evaluate(
                """() => {
                    const viewport = document.getElementById('oaDiagramViewport');
                    viewport.scrollLeft = viewport.scrollWidth;
                    const right = viewport.scrollLeft;
                    viewport.scrollLeft = 0;
                    const outer = document.querySelector('[data-node-id="battlefield"]');
                    const vr = viewport.getBoundingClientRect();
                    const nr = outer.getBoundingClientRect();
                    return {right, left: viewport.scrollLeft, leftInsideViewport: nr.left - vr.left};
                }"""
            )
            assert scroll["right"] > 0
            assert scroll["left"] == 0
            assert scroll["leftInsideViewport"] >= 0

            # A background pan to the left used to create a negative CSS
            # translation and reintroduce the same unreachable area. After the
            # gesture completes, the translation is normalized as well.
            viewport_box = page.locator("#oaDiagramViewport").bounding_box()
            assert viewport_box is not None
            x = viewport_box["x"] + viewport_box["width"] * 0.55
            y = viewport_box["y"] + 120
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x - 260, y, steps=10)
            page.mouse.up()
            page.wait_for_timeout(300)
            view_after_pan = page.evaluate("() => window.oaDiagram.getView()")
            assert view_after_pan["x"] >= 0
        finally:
            browser.close()
