"""Real-browser coverage for the estate-context explorer interactions."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import threading

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "comparison_table.html"


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

        preview = tmp_path_factory.mktemp("estate-comparison-preview")
        assets = preview / "assets"
        assets.mkdir()
        shutil.copy2(PAGE, preview / PAGE.name)
        for name in (
            "estate-comparison.js",
            "estate-explorer.css",
            "research-shell.js",
            "research-shell.css",
        ):
            shutil.copy2(ROOT / "site" / "assets" / name, assets / name)

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


def _load(page, url: str) -> None:
    page.goto(url, wait_until="load")
    page.locator("#estate-table-body tr").first.wait_for(state="visible")


def test_filters_views_and_reset_intersect_without_console_errors(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    page_errors: list[str] = []
    console_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )

    _load(page, url)
    playwright_api.expect(page.locator("#visible-count")).to_have_text("35")
    assert page.locator("#estate-table-body tr").count() == 35
    assert page.locator("#estate-table-body th[scope='row']").count() == 35
    playwright_api.expect(page.locator(".research-shell-nav")).to_be_visible()

    page.locator("[data-view='value']").click()
    playwright_api.expect(page.locator("[data-group='hdb']")).to_be_visible()
    playwright_api.expect(page.locator("[data-group='private']")).to_be_visible()
    playwright_api.expect(page.locator("[data-group='provision']")).to_be_hidden()

    page.locator("button[data-arch='B']").click()
    assert page.locator("#estate-table-body tr").count() > 1
    assert set(page.locator("#estate-table-body tr").evaluate_all(
        "rows => rows.map(row => row.dataset.arch)"
    )) == {"B"}

    page.locator("#estate-search").fill("Canberra")
    playwright_api.expect(page.locator("#visible-count")).to_have_text("1")
    assert "Canberra" in page.locator("#estate-table-body").inner_text()
    assert "Proxy · Sembawang" in page.locator("#estate-table-body").inner_text()

    page.locator("#reset-view").click()
    playwright_api.expect(page.locator("#visible-count")).to_have_text("35")
    playwright_api.expect(page.locator("[data-view='overview']")).to_have_attribute(
        "aria-pressed", "true"
    )
    assert page.locator("#estate-search").input_value() == ""
    assert page_errors == []
    assert console_errors == []


def test_sort_is_keyboard_operable_and_state_survives_reload(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load(page, url)

    page.locator("[data-view='provision']").click()
    score_button = page.locator("[data-sort='score']")
    score_button.focus()
    score_button.press("Enter")
    score_heading = page.locator("th[data-column-key='score']")
    playwright_api.expect(score_heading).to_have_attribute("aria-sort", "ascending")
    assert "view=provision" in page.url
    assert "sort=score" in page.url
    ascending = [
        float(value.replace("≈", ""))
        for value in page.locator("td[data-column-key='score']").all_inner_texts()
        if value != "N/R"
    ]
    assert ascending == sorted(ascending)

    score_button.press("Enter")
    playwright_api.expect(score_heading).to_have_attribute("aria-sort", "descending")
    assert "dir=desc" in page.url
    descending = [
        float(value.replace("≈", ""))
        for value in page.locator("td[data-column-key='score']").all_inner_texts()
        if value != "N/R"
    ]
    assert descending == sorted(descending, reverse=True)

    page.locator("[data-view='value']").click()
    playwright_api.expect(page.locator("thead th[data-column-key='estate']")).to_have_attribute(
        "aria-sort", "ascending"
    )
    assert "sort=score" not in page.url
    page.locator("[data-view='provision']").click()
    score_button = page.locator("[data-sort='score']")
    score_button.press("Enter")
    score_button.press("Enter")

    page.locator("#estate-search").fill("Tampines")
    page.reload(wait_until="load")
    playwright_api.expect(page.locator("#estate-search")).to_have_value("Tampines")
    playwright_api.expect(page.locator("[data-view='provision']")).to_have_attribute(
        "aria-pressed", "true"
    )
    playwright_api.expect(page.locator("th[data-column-key='score']")).to_have_attribute(
        "aria-sort", "descending"
    )

    page.goto(f"{url}?view=value&sort=score&dir=desc", wait_until="load")
    playwright_api.expect(page.locator("thead th[data-column-key='estate']")).to_have_attribute(
        "aria-sort", "ascending"
    )
    assert "sort=score" not in page.url
    assert "dir=desc" not in page.url


def test_dead_band_and_non_residential_gate_are_visible(chromium_page) -> None:
    page, url = chromium_page
    _load(page, url)

    page.locator("[data-view='liveability']").click()
    page.locator("#estate-search").fill("Pasir Ris")
    gap_text = page.locator("td[data-column-key='gap_yf']").inner_text()
    assert "+0.22" in gap_text
    assert "matched" in gap_text
    assert "punches above" not in gap_text

    page.locator("#reset-view").click()
    page.locator("[data-view='all']").click()
    page.locator("button[data-arch='X']").click()
    assert page.locator("#estate-table-body tr").count() == 1
    row = page.locator("#estate-table-body tr")
    assert "Central Area" in row.inner_text()
    assert row.locator("td[data-column-key='score']").inner_text() == "N/R"
    assert "4.26" not in row.inner_text()
    assert "Not a residential construct" in row.inner_text()


def test_mobile_keeps_horizontal_overflow_inside_the_table_region(chromium_page) -> None:
    page, url = chromium_page
    page.set_viewport_size({"width": 390, "height": 844})
    _load(page, url)

    dimensions = page.evaluate(
        """() => {
          const wrapper = document.querySelector('.tbl-wrap');
          return {
            body: document.documentElement.scrollWidth,
            viewport: window.innerWidth,
            wrapperClient: wrapper.clientWidth,
            wrapperScroll: wrapper.scrollWidth,
          };
        }"""
    )
    assert dimensions["body"] <= dimensions["viewport"] + 1
    assert dimensions["wrapperScroll"] > dimensions["wrapperClient"]

    page.locator("[data-view='all']").click()
    all_evidence = page.evaluate(
        """() => {
          const wrapper = document.querySelector('.tbl-wrap');
          return {
            body: document.documentElement.scrollWidth,
            viewport: window.innerWidth,
            wrapperClient: wrapper.clientWidth,
            wrapperScroll: wrapper.scrollWidth,
          };
        }"""
    )
    assert all_evidence["body"] <= all_evidence["viewport"] + 1
    assert all_evidence["wrapperScroll"] > all_evidence["wrapperClient"]
