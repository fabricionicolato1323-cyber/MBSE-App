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
def web_server():
    env = os.environ.copy()
    env["MBSE_WEB_SECRET"] = "ci-e2e-secret"
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


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_ai_off_goal_to_participant_flow(web_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")

            expect(page.get_by_text("Arcadia viewpoint", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="Save model", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="Load model", exact=True)).to_be_visible()
            expect(page.locator("#aiStatusText")).to_have_text("AI Off")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            expect(page.get_by_text("What is the main goal?", exact=True)).to_be_visible()

            page.get_by_role("button", name="Save model", exact=True).click()
            expect(page.get_by_role("dialog", name="Save Operational Analysis model")).to_be_visible()
            expect(page.get_by_label("Model name")).to_be_visible()
            page.get_by_role("button", name="Cancel", exact=True).click()

            goal = "Allow an authorized visitor to enter a facility safely"
            composer = page.locator("#messageInput")
            expect(composer).to_be_visible()
            composer.fill(goal)
            composer.press("Enter")

            expect(
                page.get_by_text("Is there another important goal?", exact=True)
            ).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="No", exact=True).click()

            expect(
                page.get_by_text(
                    "Would you like to add a participant or context element?",
                    exact=True,
                )
            ).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="Yes", exact=True).click()

            expect(page.get_by_text("Who or what is involved?", exact=True)).to_be_visible(
                timeout=20_000
            )
            expect(page.locator("#statusLine")).to_have_text("Ready")
            expect(page.get_by_role("button", name="Use suggested classification")).to_have_count(0)
            expect(page.locator("#modelTextual")).to_contain_text(goal, timeout=10_000)
        finally:
            browser.close()


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_searchable_model_picker_opens_and_filters(web_server):
    from playwright.sync_api import expect, sync_playwright

    choices = [
        {"label": "Action: Detect threats", "value": "1"},
        {"label": "Action: Engage threats", "value": "2"},
        {"label": "Action: Report threat engagement", "value": "3"},
        {"label": "Participant: Soldier", "value": "4"},
        {"label": "Participant / context: Threat detection system", "value": "5"},
        {"label": "Goal: Protect target area", "value": "6"},
        {"label": "Interaction: Threat report", "value": "7"},
        {"label": "Communication mean: Radio link", "value": "8"},
        {"label": "Action: Track threats", "value": "9"},
        {"label": "Participant / context: Target area", "value": "10"},
    ]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            page.evaluate(
                "choices => renderRevisionInteraction({mode: 'choice', choices}, true, {locked: false})",
                choices,
            )
            toggle = page.get_by_role("button", name="Select from 10 model items")
            expect(toggle).to_be_visible()
            toggle.click()
            search = page.get_by_role("searchbox", name="Search model items")
            expect(search).to_be_visible()
            expect(page.get_by_text("Actions (4)", exact=True)).to_be_visible()
            expect(page.get_by_text("Participants / Context (3)", exact=True)).to_be_visible()
            search.fill("engage")
            expect(page.get_by_role("button", name="Engage threats", exact=True)).to_be_visible()
            expect(page.get_by_role("button", name="Detect threats", exact=True)).to_be_hidden()
        finally:
            browser.close()


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_load_saved_model_populates_preview_and_opens_continuation_menu(web_server, tmp_path):
    from playwright.sync_api import expect, sync_playwright

    model = {
        "directed": True,
        "multigraph": True,
        "graph": {"model": "Arcadia Operational Analysis", "model_name": "Loaded perimeter model"},
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
    model_file = tmp_path / "loaded-model.json"
    model_file.write_text(json.dumps(model), encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            page.locator("#loadModelInput").set_input_files(str(model_file))

            expect(page.locator("#modelTextual")).to_contain_text("Protect perimeter", timeout=20_000)
            expect(page.locator("#modelTextual")).to_contain_text("Monitor perimeter")
            expect(page.locator("#modelFileName")).to_have_text("Loaded perimeter model")
            expect(
                page.get_by_text("What would you like to do with the loaded model?", exact=True)
            ).to_be_visible(timeout=20_000)
            expect(
                page.get_by_role("button", name="Change something that already exists", exact=True)
            ).to_be_visible()
            expect(page.get_by_role("button", name="Add something new", exact=True)).to_be_visible()

            page.get_by_role("button", name="Change something that already exists", exact=True).click()
            expect(page.get_by_text("Which part of the model?", exact=True)).to_be_visible(timeout=20_000)
            for label in [
                "Goals",
                "People, organizations, places, or systems involved",
                "Activities",
                "Information or material exchanged",
                "Means of communication",
                "Characteristics and limits",
            ]:
                expect(page.get_by_role("button", name=label, exact=True)).to_be_visible()

            expect(
                page.get_by_text(
                    "The loaded model has no obvious mandatory gaps. Would you like to edit or refine something?",
                    exact=True,
                )
            ).to_have_count(0)
        finally:
            browser.close()


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_unified_output_sidebar_splits_views_only_when_undocked(web_server):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            expect(page.locator("#modelPanel")).to_be_visible()
            expect(page.locator("#sysmlPanel")).to_have_count(0)
            expect(page.get_by_role("tab", name="Pseudo-code", exact=True)).to_be_visible()
            expect(page.get_by_role("tab", name="SysML V2", exact=True)).to_be_visible()
            expect(page.get_by_role("tab", name="Diagram", exact=True)).to_be_visible()
            expect(page.get_by_role("tab", name="Details", exact=True)).to_be_visible()
            expect(page.locator("#utilityTextView")).to_be_visible()

            with page.expect_popup() as text_popup_info:
                page.locator("#modelPanel [data-panel-action='dock']").click()
            text_popup = text_popup_info.value
            text_popup.wait_for_load_state("domcontentloaded")
            assert "detachedPanel=text" in text_popup.url
            expect(text_popup.locator("#modelPanel")).to_be_visible()
            expect(text_popup.locator("#utilityTextView")).to_be_visible()
            expect(text_popup.locator("#utilitySysmlView")).to_be_hidden()
            expect(page.locator("#modelPanel")).to_be_visible()
            expect(page.locator("#utilitySysmlView")).to_be_visible()

            with page.expect_popup() as sysml_popup_info:
                page.locator("#modelPanel [data-panel-action='dock']").click()
            sysml_popup = sysml_popup_info.value
            sysml_popup.wait_for_load_state("domcontentloaded")
            assert "detachedPanel=sysml" in sysml_popup.url
            expect(sysml_popup.locator("#utilitySysmlView")).to_be_visible()
            expect(sysml_popup.locator("#utilityTextView")).to_be_hidden()
            expect(page.locator("#modelPanel")).to_be_visible()
            expect(page.locator("#diagramTab")).to_be_visible()

            page.get_by_role("button", name="Model output", exact=True).click()
            expect(page.locator("#modelPanel")).to_be_hidden()
            assert not text_popup.is_closed()
            assert not sysml_popup.is_closed()

            text_popup.locator("#modelPanel [data-panel-action='dock']").click()
            expect(page.locator("#modelPanel")).to_be_visible(timeout=5_000)
            expect(page.locator("#utilityTextView")).to_be_visible(timeout=5_000)
            assert not sysml_popup.is_closed()
        finally:
            browser.close()
