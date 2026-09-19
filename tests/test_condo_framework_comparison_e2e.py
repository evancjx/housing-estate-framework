"""Browser coverage for the external catalog in the two-project comparison."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import threading
from urllib.parse import parse_qs, urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "condo_framework_comparison.html"
CATALOG = json.loads(
    (ROOT / "site/assets/project-catalog/manifest.json").read_text(encoding="utf-8")
)
CATALOG_URL_RE = re.compile(
    r"/assets/project-catalog/[0-9a-f]{64}/catalog\.json(?:\?.*)?$"
)
NONDEFAULT_IDS = (
    "eastern-lagoon-d15-upper-east-coast-road",
    "eastern-lagoon-d16-upper-east-coast-road",
)
NONDEFAULT_LABELS = (
    "EASTERN LAGOON · D15 / UPPER EAST COAST ROAD",
    "EASTERN LAGOON · D16 / UPPER EAST COAST ROAD",
)


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


@pytest.fixture(scope="module")
def chromium_page(tmp_path_factory):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")

        preview = tmp_path_factory.mktemp("condo-framework-preview")
        assets = preview / "assets"
        assets.mkdir()
        shutil.copy2(PAGE, preview / PAGE.name)
        for name in ("data-loader.js", "research-shell.css", "research-shell.js"):
            shutil.copy2(ROOT / "site/assets" / name, assets / name)
        shutil.copytree(ROOT / "site/assets/project-catalog", assets / "project-catalog")

        handler = partial(_QuietHandler, directory=str(preview))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        url = f"http://127.0.0.1:{server.server_port}/{PAGE.name}"
        try:
            yield page, url
        finally:
            page.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            browser.close()


def test_catalog_failure_keeps_two_defaults_usable_and_retry_hydrates(
    chromium_page,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    requests: list[str] = []

    def fail_catalog(route, request) -> None:
        requests.append(request.url)
        route.fulfill(
            status=503,
            content_type="application/json",
            body='{"error":"catalog unavailable"}',
        )

    page.route(CATALOG_URL_RE, fail_catalog)
    page.goto(url, wait_until="load")
    try:
        playwright_api.expect(page.locator("#project-catalog-status")).to_contain_text(
            "example projects remain usable", timeout=20_000
        )
        playwright_api.expect(page.locator("#project-catalog-status")).to_have_attribute(
            "role", "alert"
        )
        playwright_api.expect(page.locator("#retry-project-catalog")).to_be_visible()
        playwright_api.expect(page.locator("#comparison-result")).to_be_visible()
        assert page.locator("#subject-grid .subject").count() == 2
        assert page.locator("#project-options option").count() == 2
        assert requests
        assert parse_qs(urlparse(requests[-1]).query).get("v") == [
            CATALOG["catalog_revision"]
        ]
    finally:
        page.unroute(CATALOG_URL_RE, fail_catalog)

    page.locator("#retry-project-catalog").click()
    playwright_api.expect(page.locator("#project-catalog-status")).to_contain_text(
        "projects ready", timeout=20_000
    )
    playwright_api.expect(page.locator("#retry-project-catalog")).to_be_hidden()
    assert page.locator("#project-options option").count() == CATALOG["counts"][
        "comparison"
    ]
    assert page.locator("#subject-grid .subject").count() == 2


def test_nondefault_url_restores_after_catalog_hydration(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    page.goto(
        f"{url}?a={NONDEFAULT_IDS[0]}&b={NONDEFAULT_IDS[1]}", wait_until="load"
    )

    playwright_api.expect(page.locator("#project-catalog-status")).to_contain_text(
        "projects ready", timeout=20_000
    )
    playwright_api.expect(page.locator("#project-a")).to_have_value(
        NONDEFAULT_LABELS[0]
    )
    playwright_api.expect(page.locator("#project-b")).to_have_value(
        NONDEFAULT_LABELS[1]
    )
    assert page.locator("#subject-grid h3").all_inner_texts() == [
        "Eastern Lagoon",
        "Eastern Lagoon",
    ]
    query = parse_qs(urlparse(page.url).query)
    assert query == {"a": [NONDEFAULT_IDS[0]], "b": [NONDEFAULT_IDS[1]]}

