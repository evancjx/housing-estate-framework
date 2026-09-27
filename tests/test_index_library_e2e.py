"""Real-browser checks for the tiered research library on the landing page."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import threading

import pytest


ROOT = Path(__file__).resolve().parents[1]


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


@pytest.fixture(scope="module")
def landing_page(tmp_path_factory):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")
        preview = tmp_path_factory.mktemp("landing-preview")
        (preview / "assets").mkdir()
        shutil.copy2(ROOT / "index.html", preview / "index.html")
        for name in ("research-shell.js", "research-shell.css"):
            shutil.copy2(ROOT / "site" / "assets" / name, preview / "assets" / name)
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(_QuietHandler, directory=str(preview))
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            yield page, f"http://127.0.0.1:{server.server_port}/index.html"
        finally:
            page.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            browser.close()


def _visible_tiers(page) -> list[str]:
    return page.eval_on_selector_all(
        "#report-grid .library-tier",
        "tiers => tiers.filter(t => !t.hidden).map(t => t.dataset.tier)",
    )


def test_filters_hide_tiers_left_without_cards(landing_page) -> None:
    page, url = landing_page
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url, wait_until="load")
    assert _visible_tiers(page) == ["tools", "explorers", "case-studies", "method"]

    page.locator(".filter-chip[data-filter='tool']").click()
    assert _visible_tiers(page) == ["tools"]

    page.locator(".filter-chip[data-filter='all']").click()
    page.locator("#report-search").fill("canberra")
    assert _visible_tiers(page) == ["case-studies", "method"]

    page.locator("#report-search").fill("zzzz-no-such-report")
    assert _visible_tiers(page) == []
    assert page.locator("#report-empty").is_visible()

    page.locator("#report-search").fill("")
    assert _visible_tiers(page) == ["tools", "explorers", "case-studies", "method"]
    assert errors == []
