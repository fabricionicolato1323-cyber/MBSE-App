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
def web_server_oa_help():
    env = os.environ.copy()
    env["MBSE_WEB_SECRET"] = "ci-oa-help-secret"
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


@pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="Playwright E2E tests run in the dedicated CI job.",
)
def test_operational_analysis_help_uses_progressive_disclosure_and_official_sources(
    web_server_oa_help,
):
    from playwright.sync_api import expect, sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded")
            expect(page.locator("#statusLine")).to_have_text("Ready", timeout=20_000)

            page.get_by_role("button", name="About Operational Analysis", exact=True).click()
            help_dialog = page.get_by_role("dialog", name="Operational Analysis help", exact=True)
            expect(help_dialog).to_be_visible()
            expect(
                help_dialog.get_by_text(
                    "Understand the operational need before defining the solution.",
                    exact=True,
                )
            ).to_be_visible(timeout=10_000)
            expect(help_dialog.get_by_text("Who is involved", exact=True)).to_be_visible()
            expect(help_dialog.get_by_text("Conditions and limits", exact=True)).to_be_visible()

            help_dialog.get_by_text("Learn more about this Arcadia viewpoint", exact=True).click()
            expect(help_dialog.get_by_role("heading", name="Purpose", exact=True)).to_be_visible()
            expect(help_dialog.get_by_role("heading", name="What to capture", exact=True)).to_be_visible()
            expect(help_dialog.get_by_role("heading", name="What not to do yet", exact=True)).to_be_visible()
            expect(help_dialog.get_by_role("heading", name="Arcadia perspective path", exact=True)).to_be_visible()
            expect(help_dialog.get_by_text("System Analysis", exact=True)).to_be_visible()
            expect(help_dialog.get_by_text("Logical Architecture", exact=True)).to_be_visible()
            expect(help_dialog.get_by_text("Physical Architecture", exact=True)).to_be_visible()

            overview = help_dialog.get_by_role("link", name="Official Arcadia overview", exact=True)
            reference = help_dialog.get_by_role("link", name="Arcadia reference documents", exact=True)
            qna = help_dialog.get_by_role("link", name="Arcadia Questions & Answers", exact=True)
            expect(overview).to_have_attribute("href", "https://mbse-capella.org/arcadia.html")
            expect(reference).to_have_attribute("href", "https://mbse-capella.org/arcadia-reference.html")
            expect(qna).to_have_attribute("href", "https://mbse-capella.org/arcadia-qna.html")

            page.keyboard.press("Escape")
            expect(help_dialog).to_be_hidden()
            expect(page.get_by_text("What is the main goal?", exact=True)).to_be_visible()
        finally:
            browser.close()
