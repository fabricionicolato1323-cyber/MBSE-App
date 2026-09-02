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
BASE_URL = "http://127.0.0.1:5001"


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
def web_server():
    env = os.environ.copy()
    env["MBSE_WEB_SECRET"] = "ci-loaded-resume-secret"
    env["FLASK_RUN_PORT"] = "5001"
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", "import web_app; web_app.app.run(host='127.0.0.1', port=5001, debug=False, threaded=True)"],
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
def test_loaded_model_new_action_continues_to_relationship_question(web_server, tmp_path):
    from playwright.sync_api import expect, sync_playwright

    model = {
        "directed": True,
        "multigraph": True,
        "graph": {"model": "Arcadia Operational Analysis", "model_name": "Loaded relation model"},
        "nodes": [
            {"id": "goal", "type": "OperationalCapability", "name": "Protect perimeter"},
            {
                "id": "operator",
                "type": "OperationalActor",
                "name": "Security operator",
                "nature": "human_individual",
                "expects_activity": True,
            },
            {"id": "action", "type": "OperationalActivity", "name": "Monitor perimeter"},
        ],
        "edges": [
            {"source": "operator", "target": "action", "key": 0, "type": "PERFORMS"},
            {"source": "action", "target": "goal", "key": 0, "type": "SUPPORTS_CAPABILITY"},
        ],
    }
    model_file = tmp_path / "loaded-relation-model.json"
    model_file.write_text(json.dumps(model), encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            page.locator("#loadModelInput").set_input_files(str(model_file))

            expect(
                page.get_by_text("What would you like to do with the loaded model?", exact=True)
            ).to_be_visible(timeout=20_000)
            expect(
                page.get_by_text(
                    "The loaded model has no obvious mandatory gaps. Would you like to edit or refine something?",
                    exact=True,
                )
            ).to_have_count(0)

            page.get_by_role("button", name="Add something new", exact=True).click()
            expect(page.get_by_text("Which part of the model?", exact=True)).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="Activities", exact=True).click()

            expect(page.get_by_text("What is the new action?", exact=True)).to_be_visible(timeout=20_000)
            composer = page.locator("#messageInput")
            composer.fill("Respond to alert")
            composer.press("Enter")

            expect(page.get_by_text("Who performs this action?", exact=True)).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="Security operator", exact=True).click()

            expect(
                page.get_by_text("Which goal does 'Respond to alert' contribute to?", exact=True)
            ).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="Protect perimeter", exact=True).click()

            expect(
                page.get_by_text("Does 'Respond to alert' contribute to another goal?", exact=True)
            ).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="No", exact=True).click()

            expect(
                page.get_by_text(
                    "Would you like to connect 'Respond to alert' to another action through an interaction?",
                    exact=True,
                )
            ).to_be_visible(timeout=20_000)
        finally:
            browser.close()


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_loaded_participant_can_be_placed_in_existing_operational_area(web_server, tmp_path):
    from playwright.sync_api import expect, sync_playwright

    model = {
        "directed": True,
        "multigraph": True,
        "graph": {"model": "Arcadia Operational Analysis", "model_name": "Loaded placement model"},
        "nodes": [
            {"id": "goal", "type": "OperationalCapability", "name": "Maintain safe area"},
            {
                "id": "soldier",
                "type": "OperationalActor",
                "name": "Soldier",
                "nature": "human_individual",
                "expects_activity": True,
            },
            {
                "id": "battlefield",
                "type": "OperationalEntity",
                "name": "Battlefield",
                "nature": "unspecified",
                "expects_activity": False,
            },
            {"id": "engage", "type": "OperationalActivity", "name": "Engage threats"},
        ],
        "edges": [
            {"source": "soldier", "target": "engage", "key": 0, "type": "PERFORMS"},
            {"source": "engage", "target": "goal", "key": 0, "type": "SUPPORTS_CAPABILITY"},
        ],
    }
    model_file = tmp_path / "loaded-placement-model.json"
    model_file.write_text(json.dumps(model), encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            page.locator("#loadModelInput").set_input_files(str(model_file))

            expect(
                page.get_by_text("What would you like to do with the loaded model?", exact=True)
            ).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="Change something that already exists", exact=True).click()
            expect(page.get_by_text("Which part of the model?", exact=True)).to_be_visible(timeout=20_000)
            page.get_by_role(
                "button",
                name="People, organizations, places, or systems involved",
                exact=True,
            ).click()

            expect(
                page.get_by_text(
                    "Which person, organization, place, system, or other participant would you like to modify?",
                    exact=True,
                )
            ).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="Soldier", exact=True).click()

            expect(
                page.get_by_text("What would you like to refine for 'Soldier'?", exact=True)
            ).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="Location / operational area", exact=True).click()

            expect(page.get_by_text("Where does Soldier operate?", exact=True)).to_be_visible(
                timeout=20_000
            )
            page.get_by_role("button", name="Battlefield", exact=True).click()

            expect(
                page.get_by_text("What would you like to refine for 'Soldier'?", exact=True)
            ).to_be_visible(timeout=20_000)

            located = page.evaluate(
                """async () => {
                    const state = await fetch('/api/state').then(response => response.json());
                    return state.model.edges.some(edge =>
                        edge.source === 'soldier' &&
                        edge.target === 'battlefield' &&
                        edge.type === 'LOCATED_IN'
                    );
                }"""
            )
            assert located is True
        finally:
            browser.close()
