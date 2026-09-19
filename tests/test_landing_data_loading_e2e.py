"""Real-browser coverage for the landing project-index fallback and retry."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import threading
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads(
    (ROOT / "site" / "assets" / "project-identity-registry" / "manifest.json").read_text(
        encoding="utf-8"
    )
)
REGISTRY_PATH = (
    "/assets/project-identity-registry/"
    f"{REGISTRY['registry_revision']}/registry.json"
)


class _CatalogHandler(SimpleHTTPRequestHandler):
    catalog_attempts = 0

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != REGISTRY_PATH:
            super().do_GET()
            return
        type(self).catalog_attempts += 1
        time.sleep(0.15)
        if type(self).catalog_attempts == 1:
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":"temporary"}')
            return
        body = json.dumps(REGISTRY).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_landing_catalog_failure_falls_back_and_retry_renders_typed_query(
    tmp_path: Path,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")

        shutil.copy2(ROOT / "index.html", tmp_path / "index.html")
        assets = tmp_path / "assets"
        assets.mkdir()
        for name in ("data-loader.js", "research-shell.css", "research-shell.js"):
            shutil.copy2(ROOT / "site" / "assets" / name, assets / name)

        _CatalogHandler.catalog_attempts = 0
        handler = partial(_CatalogHandler, directory=str(tmp_path))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        page = browser.new_page(viewport={"width": 1100, "height": 850})
        try:
            page.goto(
                f"http://127.0.0.1:{server.server_port}/index.html",
                wait_until="domcontentloaded",
            )
            playwright_api.expect(page.locator("#project-catalog-status")).to_have_attribute(
                "data-state", "loading"
            )
            playwright_api.expect(page.locator("#project-catalog-status")).to_have_attribute(
                "data-state", "error"
            )
            playwright_api.expect(page.locator("#project-catalog-status-copy")).to_contain_text(
                "limited to the three examples"
            )
            playwright_api.expect(page.locator("#project-catalog-retry")).to_be_visible()

            page.locator("#condo-search").fill("1 KING ALBERT PARK")
            playwright_api.expect(page.locator("#condo-suggestions")).to_be_hidden()
            page.locator("#project-catalog-retry").click()
            playwright_api.expect(page.locator("#project-catalog-status")).to_have_attribute(
                "data-state", "ready"
            )
            playwright_api.expect(page.locator("#condo-suggestions")).to_be_visible()
            playwright_api.expect(page.locator("#condo-suggestions")).to_contain_text(
                "1 KING ALBERT PARK"
            )
            assert _CatalogHandler.catalog_attempts == 2
        finally:
            page.close()
            browser.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
