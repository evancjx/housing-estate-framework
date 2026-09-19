"""Real-browser coverage for unreadable embedded report payloads."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import shutil
import threading

import pytest


ROOT = Path(__file__).resolve().parents[1]

REPORT_CASES = [
    {
        "name": "buyer-profile-data",
        "page": "buyer_profile_table.html",
        "script_id": "buyer-profile-data",
        "alert": "#view-caveat[role='alert']",
        "table_wrap": ".tbl-wrap",
    },
    {
        "name": "buyer-profile-summary",
        "page": "buyer_profile_table.html",
        "script_id": "buyer-profile-summary",
        "alert": "#view-caveat[role='alert']",
        "table_wrap": ".tbl-wrap",
    },
    {
        "name": "estate-comparison",
        "page": "comparison_table.html",
        "script_id": "estate-comparison-data",
        "alert": "#view-caveat[role='alert']",
        "table_wrap": ".tbl-wrap",
    },
    {
        "name": "mrt-comparison-data",
        "page": "mrt_comparison_table.html",
        "script_id": "mrt-comparison-data",
        "alert": "#view-caveat[role='alert']",
        "table_wrap": ".tbl-wrap",
    },
    {
        "name": "mrt-line-summary",
        "page": "mrt_comparison_table.html",
        "script_id": "mrt-line-summary",
        "alert": "#view-caveat[role='alert']",
        "table_wrap": ".tbl-wrap",
    },
    {
        "name": "mrt-comparison-config",
        "page": "mrt_comparison_table.html",
        "script_id": "mrt-comparison-config",
        "alert": "#view-caveat[role='alert']",
        "table_wrap": ".tbl-wrap",
    },
    {
        "name": "private-project-comparison-data",
        "page": "private_project_comparison_table.html",
        "script_id": "private-project-comparison-data",
        "alert": "#project-data-status[role='alert']",
        "table_wrap": "#table-wrap",
    },
    {
        "name": "private-project-comparison-config",
        "page": "private_project_comparison_table.html",
        "script_id": "private-project-comparison-config",
        "alert": "#project-data-status[role='alert']",
        "table_wrap": "#table-wrap",
    },
]


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def _corrupt_embedded_payload(source: str, script_id: str) -> str:
    pattern = re.compile(
        rf'(<script id="{re.escape(script_id)}" type="application/json">).*?(</script>)',
        flags=re.DOTALL,
    )
    corrupted, replacements = pattern.subn(
        lambda match: f"{match.group(1)}{{not-valid-json{match.group(2)}",
        source,
        count=1,
    )
    assert replacements == 1, f"embedded payload {script_id!r} is missing"
    return corrupted


@pytest.fixture(scope="module")
def malformed_report_server(tmp_path_factory):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")

        preview = tmp_path_factory.mktemp("malformed-report-preview")
        assets = preview / "assets"
        assets.mkdir()
        for asset_name in (
            "buyer-profile.css",
            "buyer-profile.js",
            "data-loader.js",
            "estate-comparison.js",
            "estate-explorer.css",
            "mrt-comparison.css",
            "mrt-comparison.js",
            "private-project-comparison.css",
            "private-project-comparison.js",
            "research-shell.css",
            "research-shell.js",
        ):
            shutil.copy2(ROOT / "site" / "assets" / asset_name, assets / asset_name)

        for case in REPORT_CASES:
            source = (ROOT / case["page"]).read_text(encoding="utf-8")
            malformed = _corrupt_embedded_payload(source, case["script_id"])
            (preview / f"{case['name']}.html").write_text(malformed, encoding="utf-8")

        handler = partial(_QuietHandler, directory=str(preview))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield browser, f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            browser.close()


@pytest.mark.parametrize("case", REPORT_CASES, ids=lambda case: case["name"])
def test_corrupt_embedded_json_settles_in_actionable_accessible_error(
    malformed_report_server,
    case: dict[str, str],
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    browser, base_url = malformed_report_server
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    try:
        page.goto(f"{base_url}/{case['name']}.html", wait_until="load")
        alert = page.locator(case["alert"])
        table_wrap = page.locator(case["table_wrap"])

        playwright_api.expect(alert).to_be_visible()
        playwright_api.expect(alert).to_have_attribute("aria-live", "assertive")
        alert_copy = alert.inner_text().lower()
        assert "reload" in alert_copy
        assert "regenerate" in alert_copy

        playwright_api.expect(table_wrap).to_have_attribute("aria-busy", "false")
        playwright_api.expect(table_wrap).to_be_hidden()
        assert page_errors == []
    finally:
        page.close()
