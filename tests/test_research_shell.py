"""Focused browser coverage for the shared report navigation shell."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import threading

import pytest


ROOT = Path(__file__).resolve().parents[1]


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


@pytest.fixture(scope="module")
def shell_page(tmp_path_factory):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")

        preview = tmp_path_factory.mktemp("research-shell-preview")
        assets = preview / "assets"
        assets.mkdir()
        for name in ("research-shell.css", "research-shell.js"):
            shutil.copy2(ROOT / "site" / "assets" / name, assets / name)
        status_payload = {
            "schema_version": 1,
            "report_path": "comparison_table.html",
            "data_families": ["estate_model", "private_transactions"],
            "families": {
                "estate_model": {
                    "label": "Estate model",
                    "status": "complete",
                    "data_through": None,
                    "last_checked": None,
                    "generated_at": "2026-08-07T23:45:00+00:00",
                    "note": "Sources have different coverage periods.",
                },
                "private_transactions": {
                    "label": "Private transactions",
                    "status": "partial_latest_period",
                    "data_through": "2026-06",
                    "last_checked": None,
                    "generated_at": None,
                    "note": "2026-07 is partial; Data through uses the last complete month.",
                },
            },
            "generated_at": "2026-08-09",
        }
        shell_html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sample estate context report</title>
<link rel="stylesheet" href="assets/research-shell.css">
</head><body><main><h1>Sample report</h1><button id="outside" type="button">Outside</button></main>
<script type="application/json" id="research-report-status">{json.dumps(status_payload)}</script>
<script src="assets/research-shell.js"></script></body></html>"""
        (preview / "comparison_table.html").write_text(shell_html, encoding="utf-8")
        (preview / "generic_report.html").write_text(
            shell_html.replace(
                '<script type="application/json" id="research-report-status">'
                + json.dumps(status_payload)
                + "</script>\n",
                "",
            ),
            encoding="utf-8",
        )

        handler = partial(_QuietHandler, directory=str(preview))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        url = f"http://127.0.0.1:{server.server_port}/comparison_table.html"
        try:
            yield page, url, (preview / "comparison_table.html").as_uri()
        finally:
            page.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            browser.close()


def test_desktop_keeps_primary_navigation_and_marks_current_page(shell_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url, _ = shell_page
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(url, wait_until="load")

    playwright_api.expect(page.locator(".research-shell-menu-toggle")).to_be_hidden()
    playwright_api.expect(page.locator(".research-shell-links")).to_be_visible()
    playwright_api.expect(page.locator(".research-shell-current-title")).to_have_text(
        "Sample estate context report"
    )
    assert page.locator(".research-shell-links a").count() == 4
    assert page.locator(".research-shell-links a").evaluate_all(
        "links => links.map(link => ["
        "link.getAttribute('href'), link.getAttribute('aria-current')])"
    ) == [
        [url.replace("comparison_table.html", "index.html#reports"), None],
        [
            url.replace(
                "comparison_table.html", "private_project_comparison_table.html"
            ),
            None,
        ],
        [url, "page"],
        [url.replace("comparison_table.html", "home_loan_planner.html"), None],
    ]


def test_mobile_menu_exposes_every_destination_and_closes_safely(shell_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url, _ = shell_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(url, wait_until="load")

    toggle = page.locator(".research-shell-menu-toggle")
    links = page.locator(".research-shell-links")
    playwright_api.expect(toggle).to_be_visible()
    playwright_api.expect(toggle).to_have_attribute("aria-expanded", "false")
    playwright_api.expect(links).to_be_hidden()

    toggle.click()
    playwright_api.expect(toggle).to_have_attribute("aria-expanded", "true")
    for destination in page.locator(".research-shell-links a").all():
        playwright_api.expect(destination).to_be_visible()
    playwright_api.expect(page.locator(".research-shell-copy")).to_be_visible()

    page.locator(".research-shell-links a").first.focus()
    page.keyboard.press("Escape")
    playwright_api.expect(links).to_be_hidden()
    playwright_api.expect(toggle).to_be_focused()

    toggle.click()
    page.locator("#outside").click()
    playwright_api.expect(toggle).to_have_attribute("aria-expanded", "false")
    playwright_api.expect(links).to_be_hidden()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def test_unlisted_report_marks_its_visible_context_as_current(shell_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url, _ = shell_page
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(url.replace("comparison_table.html", "generic_report.html"), wait_until="load")

    playwright_api.expect(page.locator(".research-shell-current")).to_have_attribute(
        "aria-current", "page"
    )
    assert page.locator(".research-shell-links a[aria-current='page']").count() == 0


def test_reduced_motion_disables_smooth_shell_scrolling(shell_page) -> None:
    page, url, _ = shell_page
    page.emulate_media(reduced_motion="reduce")
    page.goto(url, wait_until="load")

    assert page.locator("html").evaluate(
        "element => getComputedStyle(element).scrollBehavior"
    ) == "auto"
    page.emulate_media(reduced_motion="no-preference")


def test_embedded_status_keeps_each_date_role_distinct(shell_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url, _ = shell_page
    page.goto(url, wait_until="load")

    panel = page.locator(".research-shell-freshness")
    playwright_api.expect(panel).to_have_attribute("aria-busy", "false")
    cards = panel.locator(".research-shell-freshness-family")
    assert cards.count() == 2
    assert panel.locator("h2").count() == 0

    estate = cards.filter(has_text="Estate model")
    private = cards.filter(has_text="Private transactions")
    playwright_api.expect(estate.locator("dd").nth(0)).to_have_text("Unknown")
    playwright_api.expect(estate.locator("dd").nth(2)).to_have_text("9 Aug 2026")
    playwright_api.expect(private.locator("dd").nth(0)).to_have_text("Jun 2026")
    playwright_api.expect(private.locator("dd").nth(1)).to_have_text("Unknown")
    playwright_api.expect(private.locator("dd").nth(2)).to_have_text("9 Aug 2026")
    playwright_api.expect(private.locator("dd").nth(0).locator("time")).to_have_attribute(
        "datetime", "2026-06"
    )
    assert private.locator("dd").nth(1).locator("time").count() == 0
    playwright_api.expect(
        private.locator(".research-shell-freshness-family-title")
    ).to_have_attribute("href", url.replace("comparison_table.html", "data-status.json#private_transactions"))


def test_file_preview_uses_embedded_status_without_fetching(shell_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, _, file_url = shell_page
    page.goto(file_url, wait_until="load")

    panel = page.locator(".research-shell-freshness")
    playwright_api.expect(panel).to_have_attribute("aria-busy", "false")
    playwright_api.expect(
        panel.locator(".research-shell-freshness-family").filter(
            has_text="Private transactions"
        ).locator("dd").nth(0)
    ).to_have_text("Jun 2026")
    assert "cannot load" not in panel.inner_text().lower()
