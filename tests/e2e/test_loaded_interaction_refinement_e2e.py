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
BASE_URL = "http://127.0.0.1:5002"


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
def web_server_loaded_interactions():
    env = os.environ.copy()
    env["MBSE_WEB_SECRET"] = "ci-loaded-interaction-secret"
    env["FLASK_RUN_PORT"] = "5002"
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            "import web_app; web_app.app.run(host='127.0.0.1', port=5002, debug=False, threaded=True)",
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


def _loaded_interaction_model() -> dict:
    return {
        "directed": True,
        "multigraph": True,
        "graph": {
            "model": "Arcadia Operational Analysis",
            "model_name": "Loaded interaction refinement model",
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
            {
                "source": "soldier",
                "target": "report",
                "key": 0,
                "type": "PERFORMS",
            },
            {
                "source": "detector",
                "target": "calculate",
                "key": 0,
                "type": "PERFORMS",
            },
            {
                "source": "report",
                "target": "goal",
                "key": 0,
                "type": "SUPPORTS_CAPABILITY",
            },
            {
                "source": "calculate",
                "target": "goal",
                "key": 0,
                "type": "SUPPORTS_CAPABILITY",
            },
            {
                "source": "report",
                "target": "calculate",
                "key": 0,
                "type": "OPERATIONAL_EXCHANGE",
                "name": "Kill info",
            },
            {
                "source": "soldier",
                "target": "detector",
                "key": 0,
                "type": "COMMUNICATION_MEAN",
                "name": "Radio link",
            },
        ],
    }


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_loaded_interaction_refinement_requires_target_and_explicit_communication(
    web_server_loaded_interactions,
    tmp_path,
):
    from playwright.sync_api import expect, sync_playwright

    model_file = tmp_path / "loaded-interaction-refinement.json"
    model_file.write_text(json.dumps(_loaded_interaction_model()), encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1500, "height": 1050})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            page.locator("#loadModelInput").set_input_files(str(model_file))

            expect(page.get_by_role("button", name="Operational Exchange", exact=True)).to_be_visible(
                timeout=20_000
            )

            # Existing interaction: concept -> Modify existing -> explicit exchange.
            page.get_by_role("button", name="Operational Exchange", exact=True).click()
            expect(page.get_by_text("What would you like to do?", exact=True)).to_be_visible(
                timeout=20_000
            )
            page.get_by_role("button", name="Modify existing", exact=True).click()
            expect(
                page.get_by_text("Which Operational Exchange would you like to work on?", exact=True)
            ).to_be_visible(timeout=20_000)
            page.get_by_role(
                "button",
                name=re.compile(r"^Interaction: Kill info"),
            ).click()

            expect(
                page.get_by_text("What would you like to refine for 'Kill info'?", exact=True)
            ).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="Communication method", exact=True).click()

            expect(
                page.get_by_text(
                    "How should 'Kill info' be carried between Soldier and Threat detection system?",
                    exact=True,
                )
            ).to_be_visible(timeout=20_000)
            expect(page.get_by_role("button", name="Radio link", exact=True)).to_be_visible()
            expect(
                page.get_by_role("button", name="+ Add new communication method", exact=True)
            ).to_be_visible()
            page.get_by_role("button", name="Radio link", exact=True).click()

            associated = page.evaluate(
                """async () => {
                    const state = await fetch('/api/state').then(response => response.json());
                    const edge = state.model.edges.find(item =>
                        item.type === 'COMMUNICATION_MEAN' && item.name === 'Radio link'
                    );
                    return !!edge && Array.isArray(edge.exchange_refs) && edge.exchange_refs.some(ref =>
                        ref.source_activity_id === 'report' &&
                        ref.target_activity_id === 'calculate' &&
                        ref.exchange_name === 'Kill info'
                    );
                }"""
            )
            assert associated is True

            # Return from the existing exchange refinement to the concept menu.
            page.get_by_role("button", name="Back to the interaction list", exact=True).click()
            expect(page.get_by_role("button", name="Operational Exchange", exact=True)).to_be_visible(
                timeout=20_000
            )

            # New interaction: concept -> Add new, then normal source/target flow.
            page.get_by_role("button", name="Operational Exchange", exact=True).click()
            expect(page.get_by_text("What would you like to do?", exact=True)).to_be_visible(
                timeout=20_000
            )
            page.get_by_role("button", name="Add new", exact=True).click()
            expect(
                page.get_by_text("Which action should the interaction start from?", exact=True)
            ).to_be_visible(timeout=20_000)
            page.get_by_role(
                "button",
                name=re.compile(r"^Action: Report threat engagement"),
            ).click()

            expect(
                page.get_by_text("Which action should receive the interaction?", exact=True)
            ).to_be_visible(timeout=20_000)
            expect(
                page.get_by_text(
                    "Would you like to add another interaction from 'Report threat engagement — Soldier'?",
                    exact=True,
                )
            ).to_have_count(0)
            page.get_by_role(
                "button",
                name=re.compile(r"^Calculate rate of kill"),
            ).click()

            expect(page.get_by_text("What is exchanged?", exact=True)).to_be_visible(timeout=20_000)
            composer = page.locator("#messageInput")
            composer.fill("Engagement status")
            composer.press("Enter")

            expect(
                page.get_by_text(
                    "How should 'Engagement status' be carried between Soldier and Threat detection system?",
                    exact=True,
                )
            ).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="+ Add new communication method", exact=True).click()

            expect(page.get_by_text("How do they communicate?", exact=True)).to_be_visible(
                timeout=20_000
            )
            composer.fill("Backup radio")
            composer.press("Enter")

            expect(
                page.get_by_text(
                    "Would you like to add another interaction from 'Report threat engagement — Soldier'?",
                    exact=True,
                )
            ).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="No", exact=True).click()

            persisted = page.evaluate(
                """async () => {
                    const state = await fetch('/api/state').then(response => response.json());
                    const exchange = state.model.edges.find(item =>
                        item.type === 'OPERATIONAL_EXCHANGE' &&
                        item.source === 'report' &&
                        item.target === 'calculate' &&
                        item.name === 'Engagement status'
                    );
                    const medium = state.model.edges.find(item =>
                        item.type === 'COMMUNICATION_MEAN' && item.name === 'Backup radio'
                    );
                    const linked = !!medium && Array.isArray(medium.exchange_refs) &&
                        medium.exchange_refs.some(ref =>
                            ref.source_activity_id === 'report' &&
                            ref.target_activity_id === 'calculate' &&
                            ref.exchange_name === 'Engagement status'
                        );
                    return {exchange: !!exchange, medium: !!medium, linked};
                }"""
            )
            assert persisted == {"exchange": True, "medium": True, "linked": True}
        finally:
            browser.close()
