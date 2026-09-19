"""Real-browser coverage for the MRT and LRT context explorer."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import threading

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "mrt_comparison_table.html"
SOURCE = pd.read_csv(ROOT / "data" / "inputs" / "mrt_layer.csv")
TOTAL_ROWS = len(SOURCE)
FUTURE_ROWS = int((SOURCE["operational"] == 0).sum())
LRT_ROWS = int(SOURCE["line"].str.contains("LRT", case=False, na=False).sum())
EWL_ROWS = int(SOURCE["stn_code"].astype(str).str.match(r"^EW\d+$").sum())
JRL_ROWS = int((SOURCE["line"] == "Jurong Region Line").sum())


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

        preview = tmp_path_factory.mktemp("mrt-comparison-preview")
        assets = preview / "assets"
        assets.mkdir()
        shutil.copy2(PAGE, preview / PAGE.name)
        for name in (
            "mrt-comparison.css",
            "mrt-comparison.js",
            "estate-explorer.css",
            "research-shell.css",
            "research-shell.js",
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
    page.locator("#mrt-comparison-table-body tr").first.wait_for(state="visible")


def test_filters_views_empty_state_and_reset_intersect_without_errors(chromium_page) -> None:
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
    playwright_api.expect(page.locator("#visible-count")).to_have_text(str(TOTAL_ROWS))
    assert page.locator("#mrt-comparison-table-body tr").count() == TOTAL_ROWS
    assert page.locator("#mrt-comparison-table-body th[scope='row']").count() == TOTAL_ROWS
    playwright_api.expect(page.locator(".research-shell-nav")).to_be_visible()

    page.locator("[data-view='rail']").click()
    playwright_api.expect(page.locator("thead th[data-column-key='coordinates']")).to_be_visible()
    assert page.locator("thead th[data-column-key='provision']").count() == 0

    page.locator("button[data-status='future']").click()
    playwright_api.expect(page.locator("#visible-count")).to_have_text(str(FUTURE_ROWS))
    assert set(page.locator("#mrt-comparison-table-body tr").evaluate_all(
        "items => items.map(item => item.dataset.status)"
    )) == {"future"}

    page.locator("button[data-mode='mrt']").click()
    page.locator("button[data-line='jurong-region-line']").click()
    assert page.locator("#mrt-comparison-table-body tr").count() == JRL_ROWS
    assert "Tengah" in page.locator("#mrt-comparison-table-body").inner_text()

    page.locator("#station-search").fill("no such station")
    playwright_api.expect(page.locator("#empty-state")).to_be_visible()
    playwright_api.expect(page.locator(".tbl-wrap")).to_be_hidden()

    page.locator("#empty-reset").click()
    playwright_api.expect(page.locator("#visible-count")).to_have_text(str(TOTAL_ROWS))
    playwright_api.expect(page.locator("[data-view='overview']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("button[data-status='all']")).to_have_attribute("aria-pressed", "true")
    assert page.locator("#station-search").input_value() == ""
    assert page_errors == []
    assert console_errors == []


def test_context_gates_and_value_proxies_are_visible(chromium_page) -> None:
    page, url = chromium_page
    _load(page, url)

    page.locator("[data-view='household']").click()
    page.locator("#station-search").fill("Outram Park")
    row = page.locator("#mrt-comparison-table-body tr")
    assert row.count() == 3
    assert set(row.evaluate_all("items => items.map(item => item.dataset.context)")) == {"not_residential"}
    assert "N/R" in row.first.locator("td[data-column-key='provision']").inner_text()
    assert "4.26" not in row.first.inner_text()

    page.locator("#station-search").fill("Tuas Link")
    row = page.locator("#mrt-comparison-table-body tr")
    assert row.get_attribute("data-context") == "out_of_range"
    assert "beyond 1.4 km" in row.locator("td[data-column-key='provision']").inner_text()

    page.locator("#station-search").fill("Canberra")
    page.locator("[data-view='value']").click()
    row = page.locator("#mrt-comparison-table-body tr")
    assert row.count() == 1
    assert "Proxy · Sembawang" in row.locator("td[data-column-key='hdb_value']").inner_text()
    assert "Proxy · Sembawang" in row.locator("td[data-column-key='private_value']").inner_text()
    assert row.locator("td[data-column-key='hdb_value']").inner_text() != row.locator("td[data-column-key='private_value']").inner_text()

    page.locator("#station-search").fill("CC21")
    row = page.locator("#mrt-comparison-table-body tr")
    assert row.count() == 1
    assert "Not covered" in row.locator("td[data-column-key='hdb_value']").inner_text()
    assert "No HDB Segment" in row.locator("td[data-column-key='hdb_value']").inner_text()
    assert row.locator("td[data-column-key='private_value']").inner_text() == "Not covered"


def test_selecting_a_line_synchronises_its_mode_and_round_trips(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load(page, url)

    page.locator("button[data-mode='lrt']").click()
    playwright_api.expect(page.locator("#visible-count")).to_have_text(str(LRT_ROWS))
    page.locator("button[data-line='east-west-line']").click()
    playwright_api.expect(page.locator("button[data-mode='mrt']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("button[data-line='east-west-line']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("#visible-count")).to_have_text(str(EWL_ROWS))
    assert "mode=mrt" in page.url
    assert "line=east-west-line" in page.url

    page.reload(wait_until="load")
    playwright_api.expect(page.locator("button[data-mode='mrt']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("button[data-line='east-west-line']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("#visible-count")).to_have_text(str(EWL_ROWS))


def test_keyboard_sort_and_filter_state_survive_reload(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load(page, url)

    page.locator("[data-view='proximity']").click()
    distance_button = page.locator("[data-sort='distance']")
    distance_button.focus()
    distance_button.press("Enter")
    playwright_api.expect(page.locator("[data-sort='distance']")).to_be_focused()
    heading = page.locator("th[data-column-key='distance']")
    playwright_api.expect(heading).to_have_attribute("aria-sort", "ascending")
    ascending = [
        int(text.split()[0].replace(",", ""))
        for text in page.locator("td[data-column-key='distance']").all_inner_texts()
    ]
    assert ascending == sorted(ascending)

    page.locator("[data-sort='distance']").press("Enter")
    playwright_api.expect(heading).to_have_attribute("aria-sort", "descending")
    descending = [
        int(text.split()[0].replace(",", ""))
        for text in page.locator("td[data-column-key='distance']").all_inner_texts()
    ]
    assert descending == sorted(descending, reverse=True)

    page.locator("button[data-status='future']").click()
    page.locator("button[data-mode='mrt']").click()
    page.locator("button[data-line='jurong-region-line']").click()
    page.locator("#station-search").fill("JS3")
    page.wait_for_function(
        "() => new URLSearchParams(location.search).get('q') === 'JS3'"
    )
    assert "view=proximity" in page.url
    assert "status=future" in page.url
    assert "mode=mrt" in page.url
    assert "line=jurong-region-line" in page.url
    assert "sort=distance" in page.url
    assert "dir=desc" in page.url

    page.reload(wait_until="load")
    playwright_api.expect(page.locator("#station-search")).to_have_value("JS3")
    playwright_api.expect(page.locator("[data-view='proximity']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("button[data-status='future']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("button[data-mode='mrt']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("button[data-line='jurong-region-line']")).to_have_attribute("aria-pressed", "true")
    assert page.locator("#mrt-comparison-table-body tr").count() == 1

    page.goto(
        f"{url}?view=missing&status=missing&mode=missing&line=missing&sort=missing&dir=desc",
        wait_until="load",
    )
    playwright_api.expect(page.locator("[data-view='overview']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("thead th[data-column-key='station']")).to_have_attribute("aria-sort", "ascending")
    assert page.url == url


def test_station_descending_sort_and_visible_column_help_survive_reload(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load(page, url)

    station_button = page.locator("[data-sort='station']")
    station_button.press("Enter")
    playwright_api.expect(page.locator("thead th[data-column-key='station']")).to_have_attribute("aria-sort", "descending")
    assert "sort=station" in page.url
    assert "dir=desc" in page.url
    page.reload(wait_until="load")
    playwright_api.expect(page.locator("thead th[data-column-key='station']")).to_have_attribute("aria-sort", "descending")

    page.locator(".column-guide summary").click()
    guide = page.locator("#column-guide-list")
    playwright_api.expect(guide).to_contain_text("Station")
    playwright_api.expect(guide).to_contain_text("Open, under-construction, deferred or planned")


def test_unavailable_samples_sort_after_available_evidence(chromium_page) -> None:
    page, url = chromium_page
    _load(page, url)

    page.locator("[data-view='value']").click()
    page.locator("[data-sort='hdb_sample']").click()
    samples = page.locator("td[data-column-key='hdb_sample']").all_inner_texts()
    available_indexes = [index for index, value in enumerate(samples) if "n=" in value]
    unavailable_indexes = [index for index, value in enumerate(samples) if "n=" not in value]

    assert available_indexes
    assert unavailable_indexes
    assert max(available_indexes) < min(unavailable_indexes)


def test_mobile_contains_wide_evidence_and_keeps_station_identity_sticky(chromium_page) -> None:
    page, url = chromium_page
    page.set_viewport_size({"width": 390, "height": 844})
    _load(page, url)
    page.locator("[data-view='all']").click()

    dimensions = page.evaluate(
        """() => {
          const wrapper = document.querySelector('.tbl-wrap');
          const station = document.querySelector('.station-cell');
          const header = document.querySelector('.station-column');
          return {
            body: document.documentElement.scrollWidth,
            viewport: window.innerWidth,
            wrapperClient: wrapper.clientWidth,
            wrapperScroll: wrapper.scrollWidth,
            stationPosition: getComputedStyle(station).position,
            headerPosition: getComputedStyle(header).position,
          };
        }"""
    )
    assert dimensions["body"] <= dimensions["viewport"] + 1
    assert dimensions["wrapperScroll"] > dimensions["wrapperClient"]
    assert dimensions["stationPosition"] == "sticky"
    assert dimensions["headerPosition"] == "sticky"
