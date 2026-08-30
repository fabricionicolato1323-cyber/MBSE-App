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
def impact_web_server():
    env = os.environ.copy()
    env["MBSE_WEB_SECRET"] = "ci-impact-e2e-secret"
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
def test_loaded_activity_rename_is_red_and_direct_impacts_are_orange(
    impact_web_server,
    tmp_path,
):
    from playwright.sync_api import expect, sync_playwright

    model = {
        "directed": True,
        "multigraph": True,
        "graph": {
            "model": "Arcadia Operational Analysis",
            "model_name": "Threat protection impact test",
        },
        "nodes": [
            {
                "id": "goal",
                "type": "OperationalCapability",
                "name": "Protect target area",
                "status": "confirmed",
            },
            {
                "id": "operator",
                "type": "OperationalActor",
                "name": "Threat detection system",
                "nature": "human_individual",
                "expects_activity": True,
                "status": "confirmed",
            },
            {
                "id": "action",
                "type": "OperationalActivity",
                "name": "Detect incoming threats",
                "status": "confirmed",
            },
        ],
        "edges": [
            {
                "source": "operator",
                "target": "action",
                "key": 0,
                "type": "PERFORMS",
            },
            {
                "source": "action",
                "target": "goal",
                "key": 0,
                "type": "SUPPORTS_CAPABILITY",
            },
        ],
    }
    model_file = tmp_path / "impact-model.json"
    model_file.write_text(json.dumps(model), encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            page.locator("#loadModelInput").set_input_files(str(model_file))

            expect(
                page.get_by_text("What would you like to do with the loaded model?", exact=True)
            ).to_be_visible(timeout=20_000)
            page.get_by_role(
                "button", name="Change something that already exists", exact=True
            ).click()

            expect(page.get_by_text("Which part of the model?", exact=True)).to_be_visible(
                timeout=20_000
            )
            page.get_by_role("button", name="Activities", exact=True).click()

            expect(
                page.get_by_text("Which activity would you like to modify?", exact=True)
            ).to_be_visible(timeout=20_000)
            page.get_by_role("button", name="Detect incoming threats", exact=True).click()

            expect(page.get_by_role("button", name="Rename this action", exact=True)).to_be_visible(
                timeout=20_000
            )
            expect(page.get_by_role("button", name="Delete this action", exact=True)).to_be_visible()
            page.get_by_role("button", name="Rename this action", exact=True).click()

            expect(
                page.get_by_text(
                    "What should 'Detect incoming threats' be called?",
                    exact=True,
                )
            ).to_be_visible(timeout=20_000)
            composer = page.locator("#messageInput")
            expect(composer).to_be_visible()
            composer.fill("Detect incoming threats updated")
            composer.press("Enter")

            expect(page.locator("#modelTextual .mbse-change-modified")).to_contain_text(
                "Detect incoming threats updated",
                timeout=20_000,
            )
            expect(page.locator("#modelTextual .mbse-change-impacted").first).to_be_visible(
                timeout=20_000
            )

            page.get_by_role("tab", name="Diagram", exact=True).click()
            expect(
                page.locator('[data-node-id="action"].mbse-change-modified')
            ).to_be_visible(timeout=20_000)
            expect(
                page.locator('[data-node-id="operator"].mbse-change-impacted')
            ).to_be_visible(timeout=20_000)

            page.get_by_role("tab", name="SysML V2", exact=True).click()
            expect(
                page.locator("#utilitySysmlView code .mbse-change-modified").first
            ).to_contain_text("Detect incoming threats updated", timeout=20_000)
            expect(
                page.locator("#utilitySysmlView code .mbse-change-impacted").first
            ).to_be_visible(timeout=20_000)
        finally:
            browser.close()
