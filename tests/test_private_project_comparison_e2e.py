"""Real-browser coverage for the private-project evidence explorer."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import threading
from collections import Counter

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "private_project_comparison_table.html"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def _embedded_rows() -> list[dict]:
    match = re.search(
        r'<script id="private-project-comparison-data" type="application/json">(.*?)</script>',
        PAGE.read_text(encoding="utf-8"),
        flags=re.DOTALL,
    )
    assert match, "generated private-project data is missing"
    return json.loads(match.group(1))


ROWS = _embedded_rows()
TOTAL_ROWS = len(ROWS)
PAGE_SIZE = 100
SOURCE_COUNTS = {
    value: sum(row["location_source"] == value for row in ROWS)
    for value in ("project_geocode", "centroid_proxy")
}
PRIMARY_COUNTS = {
    "has": sum(row.get("has_primary_1km") is True for row in ROWS),
    "ranked": sum(row.get("has_ranked_primary_1km") is True for row in ROWS),
    "none": sum(
        row.get("school_metrics_source") == "project_geocode"
        and row.get("has_primary_1km") is False
        for row in ROWS
    ),
    "missing": sum(row.get("school_metrics_source") != "project_geocode" for row in ROWS),
}
DISTRICT_COUNTS = Counter(row["district"] for row in ROWS)
FINAL_BATCH_DISTRICT, FINAL_BATCH_COUNT = next(
    (district, count)
    for district, count in sorted(DISTRICT_COUNTS.items())
    if PAGE_SIZE < count < PAGE_SIZE * 2
)


@pytest.fixture(scope="module")
def chromium_page(tmp_path_factory):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")

        preview = tmp_path_factory.mktemp("private-project-comparison-preview")
        assets = preview / "assets"
        assets.mkdir()
        shutil.copy2(PAGE, preview / PAGE.name)
        for name in (
            "private-project-comparison.css",
            "private-project-comparison.js",
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
    page.locator("#private-project-table-body tr").first.wait_for(state="visible")


def _count_text(value: int) -> str:
    return f"{value:,}"


def test_views_filters_empty_state_and_reset_work_without_browser_errors(
    chromium_page,
) -> None:
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
    playwright_api.expect(page.locator("#visible-count")).to_have_text(
        _count_text(TOTAL_ROWS)
    )
    assert page.locator("#private-project-table-body tr").count() == PAGE_SIZE
    assert page.locator("#private-project-table-body th[scope='row']").count() == PAGE_SIZE
    playwright_api.expect(page.locator(".research-shell-nav")).to_be_visible()

    for view in ("access", "schools", "price", "transactions", "context"):
        page.locator(f"[data-view='{view}']").click()
        playwright_api.expect(page.locator(f"[data-view='{view}']")).to_have_attribute(
            "aria-pressed", "true"
        )
        playwright_api.expect(
            page.locator(f"#private-project-table-head [data-group='{view}']").first
        ).to_be_visible()
        assert f"view={view}" in page.url

    page.locator("#project-search").fill("no such private project")
    playwright_api.expect(page.locator("#empty-state")).to_be_visible()
    playwright_api.expect(page.locator("#table-wrap")).to_be_hidden()

    page.locator("#empty-reset").click()
    playwright_api.expect(page.locator("#visible-count")).to_have_text(
        _count_text(TOTAL_ROWS)
    )
    playwright_api.expect(page.locator("[data-view='overview']")).to_have_attribute(
        "aria-pressed", "true"
    )
    assert page.locator("#project-search").input_value() == ""
    assert page.locator("#private-project-table-body tr").count() == PAGE_SIZE
    assert page_errors == []
    assert console_errors == []


def test_search_district_and_all_filters_round_trip_through_the_url(
    chromium_page,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load(page, url)

    target = next(row for row in ROWS if row["project"] == "THE POIZ RESIDENCES")
    assert target["location_source"] == "project_geocode"
    assert target["has_primary_1km"] is True
    assert "Resale" in target["sale_mix"]

    page.locator("[data-view='access']").click()
    page.locator("#district-filter").select_option(target["district"])
    page.locator("#station-filter").select_option(target["station_key"])
    page.locator("#sale-filter").select_option("Resale")
    page.locator("#source-filter").select_option("project_geocode")
    page.locator("#primary-filter").select_option("has")
    page.locator("#project-search").fill(target["project"])
    page.wait_for_function(
        "() => new URLSearchParams(location.search).get('q') === 'THE POIZ RESIDENCES'"
    )

    playwright_api.expect(page.locator("#visible-count")).to_have_text("1")
    assert target["project"].title() in page.locator(
        "#private-project-table-body"
    ).inner_text().title()
    assert "view=access" in page.url
    assert f"district={target['district']}" in page.url
    assert f"station={target['station_key']}" in page.url
    assert "sale=Resale" in page.url
    assert "source=project_geocode" in page.url
    assert "primary=has" in page.url

    page.reload(wait_until="load")
    page.locator("#private-project-table-body tr").first.wait_for(state="visible")
    playwright_api.expect(page.locator("#project-search")).to_have_value(target["project"])
    playwright_api.expect(page.locator("#district-filter")).to_have_value(target["district"])
    playwright_api.expect(page.locator("#station-filter")).to_have_value(target["station_key"])
    playwright_api.expect(page.locator("#sale-filter")).to_have_value("Resale")
    playwright_api.expect(page.locator("#source-filter")).to_have_value("project_geocode")
    playwright_api.expect(page.locator("#primary-filter")).to_have_value("has")
    playwright_api.expect(page.locator("[data-view='access']")).to_have_attribute(
        "aria-pressed", "true"
    )
    playwright_api.expect(page.locator("#visible-count")).to_have_text("1")


def test_source_and_primary_filters_report_full_matching_populations(
    chromium_page,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load(page, url)

    for source, expected in SOURCE_COUNTS.items():
        page.locator("#source-filter").select_option(source)
        playwright_api.expect(page.locator("#visible-count")).to_have_text(
            _count_text(expected)
        )
        assert page.locator("#private-project-table-body tr").count() == min(
            PAGE_SIZE, expected
        )

    page.locator("#reset-view").click()
    for primary, expected in PRIMARY_COUNTS.items():
        page.locator("#primary-filter").select_option(primary)
        playwright_api.expect(page.locator("#visible-count")).to_have_text(
            _count_text(expected)
        )
        assert page.locator("#private-project-table-body tr").count() == min(
            PAGE_SIZE, expected
        )

    page.locator("[data-view='schools']").click()
    page.locator("#primary-filter").select_option("none")
    playwright_api.expect(
        page.locator(
            "#private-project-table-body [data-column-key='primary_1km_schools']"
        ).first
    ).to_contain_text("None found")


def test_keyboard_sort_exposes_aria_state_and_survives_reload(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load(page, url)

    project_sort = page.locator("[data-sort='project']")
    project_sort.click()
    playwright_api.expect(
        page.locator("th[data-column-key='project']")
    ).to_have_attribute("aria-sort", "descending")
    assert "sort=project" in page.url
    assert "dir=desc" in page.url
    page.reload(wait_until="load")
    page.locator("#private-project-table-body tr").first.wait_for(state="visible")
    playwright_api.expect(
        page.locator("th[data-column-key='project']")
    ).to_have_attribute("aria-sort", "descending")

    page.locator("[data-view='price']").click()
    sort_button = page.locator("[data-sort='median_psm']")
    sort_button.focus()
    sort_button.press("Enter")
    playwright_api.expect(sort_button).to_be_focused()
    heading = page.locator("th[data-column-key='median_psm']")
    playwright_api.expect(heading).to_have_attribute("aria-sort", "ascending")
    assert "sort=median_psm" in page.url

    sort_button.press("Enter")
    playwright_api.expect(heading).to_have_attribute("aria-sort", "descending")
    assert "dir=desc" in page.url

    page.reload(wait_until="load")
    page.locator("#private-project-table-body tr").first.wait_for(state="visible")
    playwright_api.expect(page.locator("[data-view='price']")).to_have_attribute(
        "aria-pressed", "true"
    )
    playwright_api.expect(
        page.locator("th[data-column-key='median_psm']")
    ).to_have_attribute("aria-sort", "descending")

    page.goto(
        f"{url}?view=missing&sort=missing&dir=desc&source=missing&primary=unknown",
        wait_until="load",
    )
    page.locator("#private-project-table-body tr").first.wait_for(state="visible")
    playwright_api.expect(page.locator("[data-view='overview']")).to_have_attribute(
        "aria-pressed", "true"
    )
    playwright_api.expect(
        page.locator("#private-project-table-head th[data-column-key='project']")
    ).to_have_attribute("aria-sort", "ascending")
    assert page.url == url


def test_show_more_progressively_renders_filtered_rows(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load(page, url)

    assert page.locator("#private-project-table-body tr").count() == PAGE_SIZE
    playwright_api.expect(page.locator("#show-more")).to_be_visible()
    playwright_api.expect(page.locator("#rendered-copy")).to_contain_text("100")

    page.locator("#show-more").click()
    playwright_api.expect(page.locator("#private-project-table-body tr")).to_have_count(
        PAGE_SIZE * 2
    )
    playwright_api.expect(page.locator("#rendered-copy")).to_contain_text("200")

    page.locator("#project-search").fill("THE POIZ RESIDENCES")
    playwright_api.expect(page.locator("#visible-count")).to_have_text("1")
    playwright_api.expect(page.locator("#private-project-table-body tr")).to_have_count(1)
    playwright_api.expect(page.locator("#show-more")).to_be_hidden()

    page.locator("#reset-view").click()
    playwright_api.expect(page.locator("#private-project-table-body tr")).to_have_count(
        PAGE_SIZE
    )
    playwright_api.expect(page.locator("#show-more")).to_be_visible()

    page.locator("#district-filter").select_option(FINAL_BATCH_DISTRICT)
    playwright_api.expect(page.locator("#visible-count")).to_have_text(
        _count_text(FINAL_BATCH_COUNT)
    )
    page.locator("#show-more").click()
    playwright_api.expect(page.locator("#show-more")).to_be_hidden()
    playwright_api.expect(page.locator("#table-wrap")).to_be_focused()


def test_mobile_keeps_wide_evidence_inside_the_table_region(chromium_page) -> None:
    page, url = chromium_page
    page.set_viewport_size({"width": 390, "height": 844})
    _load(page, url)
    page.locator("[data-view='schools']").click()

    dimensions = page.evaluate(
        """() => {
          const wrapper = document.querySelector('#table-wrap');
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
