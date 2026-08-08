"""Real-browser coverage for the buyer-profile explorer."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import threading

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "buyer_profile_table.html"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def _embedded_rows() -> list[dict]:
    match = re.search(
        r'<script id="buyer-profile-data" type="application/json">(.*?)</script>',
        PAGE.read_text(encoding="utf-8"),
        flags=re.DOTALL,
    )
    assert match
    return json.loads(match.group(1))


@pytest.fixture(scope="module")
def chromium_page(tmp_path_factory):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")

        preview = tmp_path_factory.mktemp("buyer-profile-preview")
        assets = preview / "assets"
        assets.mkdir()
        shutil.copy2(PAGE, preview / PAGE.name)
        source = PAGE.read_text(encoding="utf-8")
        canonical_rows = _embedded_rows()
        hdb = dict(next(row for row in canonical_rows if row["tenure"] == "hdb" and row["rank"] == 1))
        condo = dict(next(row for row in canonical_rows if row["tenure"] == "condo" and row["rank"] == 1))
        for row in (hdb, condo):
            row["profile_id"] = "multi-tenure-test"
            row["eligible"] = True
            row["rank"] = 1
            row["score_reporting"] = "available"
        multi_summary = [{
            "profile_id": "multi-tenure-test",
            "label": "Multi-tenure test",
            "description": "Synthetic browser fixture for tenure isolation.",
            "rows": 2,
            "eligible": 2,
            "ranked": 2,
            "persona": "YoungFam",
            "horizon": "T5",
            "life_path": "forming_family",
            "tenures": ["hdb", "condo"],
            "hard_filters": {"exclude_archetypes": ["X"]},
            "soft_weights": {"liveability": 0.5, "value": 0.25},
            "partial_coverage": 0,
            "band_only_value": 0,
        }]
        source = re.sub(
            r'(<script id="buyer-profile-data" type="application/json">).*?(</script>)',
            lambda match: match.group(1) + json.dumps([hdb, condo]) + match.group(2),
            source,
            flags=re.DOTALL,
        )
        source = re.sub(
            r'(<script id="buyer-profile-summary" type="application/json">).*?(</script>)',
            lambda match: match.group(1) + json.dumps(multi_summary) + match.group(2),
            source,
            flags=re.DOTALL,
        )
        (preview / "buyer_profile_multi.html").write_text(source, encoding="utf-8")
        for name in (
            "buyer-profile.css",
            "buyer-profile.js",
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
        multi_url = f"http://127.0.0.1:{server.server_port}/buyer_profile_multi.html"
        try:
            yield page, url, multi_url
        finally:
            page.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            browser.close()


def _load(page, url: str) -> None:
    page.goto(url, wait_until="load")
    page.locator("#buyer-profile-table-body tr").first.wait_for(state="visible")


def test_profile_status_views_and_reset_intersect_without_console_errors(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url, _ = chromium_page
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
    playwright_api.expect(page.locator("#visible-count")).to_have_text("21")
    assert page.locator("#buyer-profile-table-body tr").count() == 21
    assert page.locator("#buyer-profile-table-body th[scope='row']").count() == 21
    playwright_api.expect(page.locator(".research-shell-nav")).to_be_visible()
    assert "Forming family · HDB" in page.locator("#scenario-detail").inner_text()

    profile_button = page.locator("[data-profile='single-pro-condo-commute-value']")
    profile_button.focus()
    profile_button.press("Enter")
    playwright_api.expect(profile_button).to_be_focused()
    playwright_api.expect(page.locator("#visible-count")).to_have_text("7")
    assert page.locator("#buyer-profile-table-body tr").count() == 7
    assert set(page.locator("#buyer-profile-table-body .segment-badge").all_inner_texts()) == {"CONDO"}
    assert "T0 · current" in page.locator("#scenario-detail").inner_text()

    page.locator("[data-view='value']").click()
    playwright_api.expect(page.locator("[data-group='value']")).to_be_visible()
    playwright_api.expect(page.locator("[data-group='household']")).to_be_hidden()

    page.locator("#scenario-detail .scenario-copy").evaluate(
        "element => { element.dataset.stable = 'yes'; }"
    )
    page.locator("[data-status='filtered']").click()
    playwright_api.expect(page.locator("#visible-count")).to_have_text("28")
    assert page.locator("#sort-status").inner_text().startswith("Estate")
    assert "shown alphabetically" in page.locator("#table-guidance").inner_text()
    playwright_api.expect(page.locator("thead th[data-column-key='estate']")).to_have_attribute("aria-sort", "ascending")
    page.locator("#estate-search").fill("Canberra")
    playwright_api.expect(page.locator("#visible-count")).to_have_text("1")
    assert "Filtered" in page.locator("#buyer-profile-table-body").inner_text()
    playwright_api.expect(page.locator("#scenario-detail .scenario-copy")).to_have_attribute("data-stable", "yes")

    page.locator("#reset-view").click()
    playwright_api.expect(page.locator("#visible-count")).to_have_text("21")
    playwright_api.expect(page.locator("[data-profile='forming-family-hdb-balanced']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("[data-view='overview']")).to_have_attribute("aria-pressed", "true")
    assert page.locator("#estate-search").input_value() == ""
    assert page_errors == []
    assert console_errors == []


def test_sort_is_keyboard_operable_and_url_state_survives_reload(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url, _ = chromium_page
    _load(page, url)

    score_button = page.locator("[data-sort='score']")
    score_button.focus()
    score_button.press("Enter")
    playwright_api.expect(score_button).to_be_focused()
    score_heading = page.locator("th[data-column-key='score']")
    playwright_api.expect(score_heading).to_have_attribute("aria-sort", "descending")
    descending = [float(value) for value in page.locator("td[data-column-key='score'] .profile-score").all_inner_texts()]
    assert descending == sorted(descending, reverse=True)

    score_button.press("Enter")
    playwright_api.expect(score_button).to_be_focused()
    playwright_api.expect(score_heading).to_have_attribute("aria-sort", "ascending")
    ascending = [float(value) for value in page.locator("td[data-column-key='score'] .profile-score").all_inner_texts()]
    assert ascending == sorted(ascending)

    page.locator("[data-profile='landed-family-amenity-upside']").click()
    page.locator("[data-view='value']").click()
    page.locator("[data-status='all']").click()
    page.locator("#estate-search").fill("Tampines")
    page.wait_for_function(
        "() => new URLSearchParams(window.location.search).get('q') === 'Tampines'"
    )
    assert "profile=landed-family-amenity-upside" in page.url
    assert "view=value" in page.url
    assert "status=all" in page.url
    assert "q=Tampines" in page.url

    page.reload(wait_until="load")
    playwright_api.expect(page.locator("#estate-search")).to_have_value("Tampines")
    playwright_api.expect(page.locator("[data-profile='landed-family-amenity-upside']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("[data-view='value']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("[data-status='all']")).to_have_attribute("aria-pressed", "true")

    page.goto(f"{url}?profile=missing&view=missing&sort=reasons&dir=desc", wait_until="load")
    playwright_api.expect(page.locator("[data-profile='forming-family-hdb-balanced']")).to_have_attribute("aria-pressed", "true")
    playwright_api.expect(page.locator("th[data-column-key='rank']")).to_have_attribute("aria-sort", "ascending")
    assert "profile=missing" not in page.url
    assert "view=missing" not in page.url
    assert "sort=reasons" not in page.url
    assert "dir=desc" not in page.url


def test_non_residential_and_thin_value_evidence_are_not_published_as_scores(chromium_page) -> None:
    page, url, _ = chromium_page
    _load(page, url)

    page.locator("[data-status='filtered']").click()
    page.locator("[data-view='all']").click()
    page.locator("#estate-search").fill("Central Area")
    row = page.locator("#buyer-profile-table-body tr")
    assert row.count() == 1
    assert row.locator("td[data-column-key='score']").inner_text() == "N/R"
    assert row.locator("td[data-column-key='provision']").inner_text() == "N/R"
    assert "Not a residential construct" in row.inner_text()
    assert "4.26" not in row.inner_text()

    thin = next(
        row
        for row in _embedded_rows()
        if row["profile_id"] == "landed-family-amenity-upside"
        and row["eligible"]
        and row["value_reporting"] == "band_only"
    )
    page.goto(
        f"{url}?profile=landed-family-amenity-upside&view=all&q={thin['estate'].replace(' ', '+')}",
        wait_until="load",
    )
    page.locator("#buyer-profile-table-body tr").first.wait_for(state="visible")
    thin_row = page.locator("#buyer-profile-table-body tr")
    assert thin_row.count() == 1
    assert "band only" in thin_row.locator("td[data-column-key='value']").inner_text().lower()
    assert f"n={round(thin['value_n']):,}" in thin_row.locator("td[data-column-key='value_sample']").inner_text()
    assert "Withheld" in thin_row.locator("td[data-column-key='rank']").inner_text()
    assert "Withheld" in thin_row.locator("td[data-column-key='score']").inner_text()

    no_segment = next(
        row
        for row in _embedded_rows()
        if row["tenure"] != "hdb" and row["value_basis"] == "no_hdb_segment"
    )
    page.goto(
        f"{url}?profile={no_segment['profile_id']}&status=all&view=value&q={no_segment['estate'].replace(' ', '+')}",
        wait_until="load",
    )
    page.locator("#buyer-profile-table-body tr").first.wait_for(state="visible")
    basis = page.locator("td[data-column-key='value_basis']").inner_text()
    assert basis == "No matching tenure-segment evidence"
    assert "HDB segment" not in basis


def test_mobile_keeps_wide_evidence_inside_the_scroll_region(chromium_page) -> None:
    page, url, _ = chromium_page
    page.set_viewport_size({"width": 390, "height": 844})
    _load(page, url)
    page.locator("[data-view='all']").click()

    dimensions = page.evaluate(
        """() => {
          const wrapper = document.querySelector('.tbl-wrap');
          return {
            body: document.documentElement.scrollWidth,
            viewport: window.innerWidth,
            wrapperClient: wrapper.clientWidth,
            wrapperScroll: wrapper.scrollWidth,
            profileClient: document.querySelector('.profile-choice-list').clientWidth,
            profileScroll: document.querySelector('.profile-choice-list').scrollWidth,
          };
        }"""
    )
    assert dimensions["body"] <= dimensions["viewport"] + 1
    assert dimensions["wrapperScroll"] > dimensions["wrapperClient"]
    assert dimensions["profileScroll"] > dimensions["profileClient"]


def test_multi_tenure_profile_requires_one_segment_before_showing_rank(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, _, multi_url = chromium_page
    page.set_viewport_size({"width": 1280, "height": 900})
    _load(page, multi_url)

    assert page.locator("th[data-column-key='rank']").count() == 0
    assert page.locator("th[data-column-key='score']").count() == 0
    assert "Choose one tenure segment" in page.locator("#view-caveat").inner_text()
    assert page.locator("#sort-status").inner_text().startswith("Estate")
    assert "shown alphabetically" in page.locator("#table-guidance").inner_text()

    hdb_button = page.locator("[data-segment='hdb']")
    hdb_button.focus()
    hdb_button.press("Enter")
    playwright_api.expect(hdb_button).to_be_focused()
    playwright_api.expect(page.locator("th[data-column-key='rank']")).to_be_visible()
    playwright_api.expect(page.locator("th[data-column-key='score']")).to_be_visible()
    assert page.locator("#buyer-profile-table-body tr").count() == 1
    assert page.locator("#buyer-profile-table-body .segment-badge").inner_text() == "HDB"
