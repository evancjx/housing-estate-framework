"""Real-browser coverage for partial multi-condo transaction-source failure."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import threading
from urllib.parse import parse_qs, urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "multi_condo_framework_comparison.html"
PROJECT_IDS = (
    "the-poiz-residences",
    "park-place-residences-at-plq",
    "treasure-at-tampines",
)
MANIFEST = json.loads(
    (ROOT / "site" / "assets" / "condo-transactions" / "manifest.json").read_text(
        encoding="utf-8"
    )
)
DATASET_REVISION = MANIFEST["dataset_revision"]
SHARD_PATHS = tuple(
    Path(MANIFEST["projects"][project_id]["transaction_shard"])
    for project_id in PROJECT_IDS
)
SHARDS = tuple(path.name for path in SHARD_PATHS)
ALL_FAILED_PROJECT_IDS = ("3-orchard-by-the-park", "aston-lodge")


class _PartialFailureHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0].endswith(f"/{SHARDS[1]}"):
            body = b'{"error":"temporary source failure"}'
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


class _RevisionMismatchHandler(SimpleHTTPRequestHandler):
    requested_urls: list[str] = []

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    def do_GET(self) -> None:  # noqa: N802
        self.requested_urls.append(self.path)
        if self.path.split("?", 1)[0].endswith(f"/{SHARDS[1]}"):
            shard = json.loads(
                (ROOT / "site" / SHARD_PATHS[1]).read_text(encoding="utf-8")
            )
            shard["dataset_revision"] = (
                "0" * 64 if DATASET_REVISION != "0" * 64 else "1" * 64
            )
            body = json.dumps(shard, separators=(",", ":")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def test_failed_middle_shard_preserves_letters_and_successful_evidence(
    tmp_path: Path,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")

        shutil.copy2(PAGE, tmp_path / PAGE.name)
        assets = tmp_path / "assets"
        transaction_assets = assets / "condo-transactions"
        transaction_assets.mkdir(parents=True)
        for name in ("data-loader.js", "research-shell.css", "research-shell.js"):
            shutil.copy2(ROOT / "site" / "assets" / name, assets / name)
        shutil.copytree(
            ROOT / "site" / "assets" / "project-catalog",
            assets / "project-catalog",
        )
        for shard_path in (SHARD_PATHS[0], SHARD_PATHS[2]):
            destination = tmp_path / shard_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "site" / shard_path, destination)

        handler = partial(_PartialFailureHandler, directory=str(tmp_path))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page_errors: list[str] = []
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        query = "&".join(f"p={project_id}" for project_id in PROJECT_IDS)
        url = (
            f"http://127.0.0.1:{server.server_port}/{PAGE.name}?{query}"
        )
        try:
            page.goto(url, wait_until="load")
            playwright_api.expect(page.locator("#tx-status")).to_contain_text(
                "1 project source unavailable", timeout=20_000
            )
            playwright_api.expect(page.locator("#tx-status")).to_contain_text(
                "2 available projects"
            )
            playwright_api.expect(
                page.locator("#transaction-research")
            ).to_have_attribute("aria-busy", "false")
            playwright_api.expect(
                page.locator("#retry-transaction-data")
            ).to_be_visible()

            headers = page.locator("#tx-snapshot thead th").all_inner_texts()
            assert headers[1].startswith("A · THE POIZ RESIDENCES")
            assert headers[2].startswith("B · PARK PLACE RESIDENCES AT PLQ")
            assert headers[3].startswith("C · TREASURE AT TAMPINES")

            snapshot_rows = page.locator("#tx-snapshot tbody tr")
            assert snapshot_rows.count() > 0
            assert page.locator(
                "#tx-snapshot tbody td[data-state='unavailable']"
            ).count() == snapshot_rows.count()
            first_snapshot_cells = snapshot_rows.first.locator("td")
            assert "Unavailable" not in first_snapshot_cells.nth(0).inner_text()
            failed_cell_text = first_snapshot_cells.nth(1).inner_text()
            assert "Unavailable" in failed_cell_text
            assert "n=0" not in failed_cell_text
            assert "S$0" not in failed_cell_text
            assert "Unavailable" not in first_snapshot_cells.nth(2).inner_text()

            trend_rows = page.locator("#tx-trend tbody tr")
            assert trend_rows.count() > 0
            assert page.locator(
                "#tx-trend tbody td[data-state='unavailable']"
            ).count() == trend_rows.count()

            analysis_cards = page.locator("#tx-analysis .tx-analysis-card")
            assert analysis_cards.count() == 3
            assert analysis_cards.nth(0).get_attribute("data-state") is None
            assert analysis_cards.nth(1).get_attribute("data-state") == "unavailable"
            assert "Transaction evidence unavailable" in analysis_cards.nth(1).inner_text()
            assert analysis_cards.nth(2).get_attribute("data-state") is None

            ledgers = page.locator("#tx-ledgers .tx-ledger")
            assert ledgers.count() == 3
            assert ledgers.nth(1).get_attribute("data-state") == "unavailable"
            failed_summary = ledgers.nth(1).locator("summary").inner_text()
            assert failed_summary.startswith("B · ")
            assert "park place residences at plq" in failed_summary.lower()

            download = page.locator("#download-transactions")
            playwright_api.expect(download).to_be_enabled()
            assert "includes 2 available projects" in (download.get_attribute("title") or "")
            assert "excludes 1 unavailable source" in (
                download.get_attribute("title") or ""
            )

            all_failed_query = "&".join(
                f"p={project_id}" for project_id in ALL_FAILED_PROJECT_IDS
            )
            page.goto(
                f"http://127.0.0.1:{server.server_port}/{PAGE.name}"
                f"?{all_failed_query}",
                wait_until="load",
            )
            playwright_api.expect(page.locator("#tx-status")).to_contain_text(
                "No transaction histories are available", timeout=20_000
            )
            playwright_api.expect(page.locator("#tx-status")).to_contain_text(
                "2 project sources unavailable"
            )
            playwright_api.expect(page.locator("#download-transactions")).to_be_disabled()
            playwright_api.expect(
                page.locator("#transaction-research")
            ).to_have_attribute("aria-busy", "false")
            playwright_api.expect(
                page.locator("#retry-transaction-data")
            ).to_be_visible()
            assert page.locator(
                "#tx-analysis .tx-analysis-card[data-state='unavailable']"
            ).count() == 2
            assert page.locator(
                "#tx-ledgers .tx-ledger[data-state='unavailable']"
            ).count() == 2
            assert page_errors == []
        finally:
            page.close()
            browser.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_revision_mismatch_withholds_all_transaction_results(
    tmp_path: Path,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")

        shutil.copy2(PAGE, tmp_path / PAGE.name)
        assets = tmp_path / "assets"
        assets.mkdir(exist_ok=True)
        for name in ("data-loader.js", "research-shell.css", "research-shell.js"):
            shutil.copy2(ROOT / "site" / "assets" / name, assets / name)
        shutil.copytree(
            ROOT / "site" / "assets" / "project-catalog",
            assets / "project-catalog",
        )
        for shard_path in (SHARD_PATHS[0], SHARD_PATHS[2]):
            destination = tmp_path / shard_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / "site" / shard_path, destination)

        _RevisionMismatchHandler.requested_urls = []
        handler = partial(_RevisionMismatchHandler, directory=str(tmp_path))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        query = "&".join(f"p={project_id}" for project_id in PROJECT_IDS)
        url = f"http://127.0.0.1:{server.server_port}/{PAGE.name}?{query}"
        try:
            page.goto(url, wait_until="load")
            playwright_api.expect(page.locator("#tx-status")).to_contain_text(
                "Reload this page before using transaction evidence", timeout=20_000
            )
            playwright_api.expect(page.locator("#reload-transaction-data")).to_be_visible()
            playwright_api.expect(
                page.locator("#transaction-research")
            ).to_have_attribute("aria-busy", "false")
            playwright_api.expect(
                page.locator("#retry-transaction-data")
            ).to_be_hidden()
            assert page.locator("#tx-snapshot table").count() == 0
            assert page.locator("#tx-trend table").count() == 0
            assert page.locator("#tx-analysis .tx-analysis-card").count() == 0
            assert page.locator("#tx-ledgers .tx-ledger").count() == 0
            playwright_api.expect(page.locator("#download-transactions")).to_be_disabled()
            shard_requests = [
                request_url
                for request_url in _RevisionMismatchHandler.requested_urls
                if "shard-" in request_url
            ]
            assert shard_requests
            assert all(
                parse_qs(urlparse(request_url).query).get("v")
                == [DATASET_REVISION]
                for request_url in shard_requests
            )
        finally:
            page.close()
            browser.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
