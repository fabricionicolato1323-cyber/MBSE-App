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
BASE_URL = "http://127.0.0.1:5003"


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
def web_server_loaded_characteristics():
    env = os.environ.copy()
    env["MBSE_WEB_SECRET"] = "ci-loaded-characteristics-secret"
    env["FLASK_RUN_PORT"] = "5003"
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            "import web_app; web_app.app.run(host='127.0.0.1', port=5003, debug=False, threaded=True)",
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
def test_loaded_characteristics_can_be_changed_and_added_without_parallel_model_logic(
    web_server_loaded_characteristics,
    tmp_path,
):
    from playwright.sync_api import expect, sync_playwright

    model = {
        "directed": True,
        "multigraph": True,
        "graph": {"model": "Arcadia Operational Analysis", "model_name": "Loaded limits model"},
        "nodes": [
            {
                "id": "goal",
                "type": "OperationalCapability",
                "name": "Maintain service",
                "characteristics": [
                    {"name": "Operating condition", "value_type": "text", "value": "Day"}
                ],
            },
            {
                "id": "operator",
                "type": "OperationalActor",
                "name": "Operator",
                "nature": "human_individual",
                "expects_activity": True,
            },
            {"id": "action", "type": "OperationalActivity", "name": "Monitor service"},
        ],
        "edges": [
            {"source": "operator", "target": "action", "key": 0, "type": "PERFORMS"},
            {"source": "action", "target": "goal", "key": 0, "type": "SUPPORTS_CAPABILITY"},
        ],
    }
    model_file = tmp_path / "loaded-characteristics.json"
    model_file.write_text(json.dumps(model), encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1050})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            page.locator("#loadModelInput").set_input_files(str(model_file))

            # Change an existing characteristic using the standard characteristic builder.
            page.get_by_role("button", name="Change something that already exists", exact=True).click()
            page.get_by_role("button", name="Characteristics and limits", exact=True).click()
            expect(
                page.get_by_text("Which characteristic or limit would you like to change?", exact=True)
            ).to_be_visible(timeout=20_000)
            page.get_by_role(
                "button",
                name="Goal: Maintain service — Operating condition: Day",
                exact=True,
            ).click()

            composer = page.locator("#messageInput")
            expect(page.get_by_text("What is the characteristic name?", exact=True)).to_be_visible(
                timeout=20_000
            )
            composer.fill("Operating condition")
            composer.press("Enter")
            expect(page.get_by_text("What kind of value does it have?", exact=True)).to_be_visible(
                timeout=20_000
            )
            page.get_by_role("button", name="Text value", exact=True).click()
            expect(page.get_by_text("What is the text value?", exact=True)).to_be_visible(timeout=20_000)
            composer.fill("Night")
            composer.press("Enter")

            expect(
                page.get_by_text("What would you like to do with the loaded model?", exact=True)
            ).to_be_visible(timeout=20_000)

            changed = page.evaluate(
                """async () => {
                    const state = await fetch('/api/state').then(response => response.json());
                    const goal = state.model.nodes.find(node => node.id === 'goal');
                    return goal?.characteristics || [];
                }"""
            )
            assert changed == [
                {"name": "Operating condition", "value_type": "text", "value": "Night"}
            ]

            # Add another characteristic through the same existing builder/storage path.
            page.get_by_role("button", name="Add something new", exact=True).click()
            page.get_by_role("button", name="Characteristics and limits", exact=True).click()
            expect(
                page.get_by_text("Which model item should receive the characteristic or limit?", exact=True)
            ).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="Goal: Maintain service", exact=True).click()

            expect(page.get_by_text("What is the characteristic name?", exact=True)).to_be_visible(
                timeout=20_000
            )
            composer.fill("Priority")
            composer.press("Enter")
            page.get_by_role("button", name="Text value", exact=True).click()
            expect(page.get_by_text("What is the text value?", exact=True)).to_be_visible(timeout=20_000)
            composer.fill("High")
            composer.press("Enter")

            expect(
                page.get_by_text("What would you like to do with the loaded model?", exact=True)
            ).to_be_visible(timeout=20_000)
            updated = page.evaluate(
                """async () => {
                    const state = await fetch('/api/state').then(response => response.json());
                    const goal = state.model.nodes.find(node => node.id === 'goal');
                    return goal?.characteristics || [];
                }"""
            )
            assert [item["name"] for item in updated] == ["Operating condition", "Priority"]
            assert updated[1]["value"] == "High"
        finally:
            browser.close()
