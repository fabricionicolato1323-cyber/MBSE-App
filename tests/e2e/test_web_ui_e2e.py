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

            expect(page.locator("#aiStatusText")).to_have_text("AI Off")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)
            expect(page.get_by_text("What is the main goal?", exact=True)).to_be_visible()

            goal = "Allow an authorized visitor to enter a facility safely"
            composer = page.locator("#messageInput")
            expect(composer).to_be_visible()
            composer.fill(goal)
            composer.press("Enter")

            expect(
                page.get_by_text("Is there another important goal?", exact=True)
            ).to_be_visible(timeout=20_000)
            no_button = page.get_by_role("button", name="No", exact=True)
            expect(no_button).to_be_enabled()
            no_button.click()

            expect(
                page.get_by_text(
                    "Would you like to add a participant or context element?",
                    exact=True,
                )
            ).to_be_visible(timeout=20_000)
            yes_button = page.get_by_role("button", name="Yes", exact=True)
            expect(yes_button).to_be_enabled()
            yes_button.click()

            expect(page.get_by_text("Who or what is involved?", exact=True)).to_be_visible(
                timeout=20_000
            )
            expect(page.locator("#statusLine")).to_have_text("Ready")
            expect(page.get_by_role("button", name="Use suggested classification")).to_have_count(0)

            live_model = page.locator("#modelTextual")
            expect(live_model).to_contain_text(goal, timeout=10_000)
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
