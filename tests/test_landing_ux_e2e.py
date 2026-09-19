"""Real-browser UX and accessibility coverage for the research landing page."""

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
def landing_site(tmp_path_factory):
    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")

        preview = tmp_path_factory.mktemp("landing-ux-preview")
        site_root = preview / "nested" / "repo"
        site_root.mkdir(parents=True)
        assets = site_root / "assets"
        assets.mkdir()
        shutil.copy2(ROOT / "index.html", site_root / "index.html")
        for name in ("data-loader.js", "research-shell.css", "research-shell.js"):
            shutil.copy2(ROOT / "site" / "assets" / name, assets / name)
        shutil.copytree(
            ROOT / "site" / "assets" / "project-identity-registry",
            assets / "project-identity-registry",
        )

        handler = partial(_QuietHandler, directory=str(preview))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/nested/repo/index.html"
        try:
            yield browser, url
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            browser.close()


def _open_landing(landing_site, *, width: int = 1100, height: int = 850):
    playwright_api = pytest.importorskip("playwright.sync_api")
    browser, url = landing_site
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto(url, wait_until="load")
    playwright_api.expect(page.locator("#project-catalog-status")).to_have_attribute(
        "data-state", "ready"
    )
    return page


def test_research_tabs_use_roving_focus_and_arrow_home_end_keys(landing_site) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page = _open_landing(landing_site)
    try:
        condo = page.locator("#condo-tab")
        district = page.locator("#district-tab")

        playwright_api.expect(condo).to_have_attribute("tabindex", "0")
        playwright_api.expect(district).to_have_attribute("tabindex", "-1")
        condo.focus()
        condo.press("ArrowRight")
        playwright_api.expect(district).to_be_focused()
        playwright_api.expect(district).to_have_attribute("aria-selected", "true")
        playwright_api.expect(condo).to_have_attribute("tabindex", "-1")
        playwright_api.expect(page.locator("#district-panel")).to_be_visible()
        playwright_api.expect(page.locator("#condo-panel")).to_be_hidden()

        district.press("Home")
        playwright_api.expect(condo).to_be_focused()
        playwright_api.expect(condo).to_have_attribute("aria-selected", "true")
        condo.press("End")
        playwright_api.expect(district).to_be_focused()
        district.press("ArrowLeft")
        playwright_api.expect(condo).to_be_focused()
        condo.press("ArrowDown")
        playwright_api.expect(district).to_be_focused()
        district.press("ArrowUp")
        playwright_api.expect(condo).to_be_focused()
        playwright_api.expect(condo).to_have_attribute("tabindex", "0")
        playwright_api.expect(district).to_have_attribute("tabindex", "-1")
    finally:
        page.close()


def test_combobox_tracks_active_option_and_closes_on_enter_and_escape(landing_site) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page = _open_landing(landing_site)
    try:
        search = page.locator("#condo-search")
        options = page.locator("#condo-suggestions [role='option']")
        search.fill("EASTERN LAGOON")
        playwright_api.expect(page.locator("#condo-suggestions")).to_be_visible()
        playwright_api.expect(search).to_have_attribute("aria-expanded", "true")
        assert search.get_attribute("aria-activedescendant") is None
        assert options.count() == 3
        assert len(set(options.evaluate_all(
            "items => items.map(item => item.dataset.projectId)"
        ))) == 3

        search.press("ArrowDown")
        first_id = options.nth(0).get_attribute("id")
        playwright_api.expect(search).to_have_attribute("aria-activedescendant", first_id)
        playwright_api.expect(options.nth(0)).to_have_attribute("aria-selected", "true")
        search.press("ArrowDown")
        second_id = options.nth(1).get_attribute("id")
        second_label = options.nth(1).inner_text().splitlines()[0]
        playwright_api.expect(search).to_have_attribute("aria-activedescendant", second_id)
        playwright_api.expect(options.nth(1)).to_have_attribute("aria-selected", "true")
        search.press("Enter")

        playwright_api.expect(search).to_have_value(second_label)
        playwright_api.expect(search).to_be_focused()
        playwright_api.expect(search).to_have_attribute("aria-expanded", "false")
        playwright_api.expect(page.locator("#condo-suggestions")).to_be_hidden()
        assert search.get_attribute("aria-activedescendant") is None

        search.fill("EASTERN LAGOON")
        search.press("ArrowDown")
        assert search.get_attribute("aria-activedescendant") is not None
        search.press("Escape")
        playwright_api.expect(search).to_have_attribute("aria-expanded", "false")
        playwright_api.expect(page.locator("#condo-suggestions")).to_be_hidden()
        assert search.get_attribute("aria-activedescendant") is None
    finally:
        page.close()


def test_duplicate_free_text_requires_id_selection_and_name_only_is_honest(
    landing_site,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page = _open_landing(landing_site)
    try:
        search = page.locator("#condo-search")
        route = page.locator("#condo-route")

        search.fill("EASTERN LAGOON")
        page.locator("#condo-form .primary-btn").click()
        playwright_api.expect(route).to_contain_text(
            "Multiple identities share that name"
        )
        assert page.url.endswith("/index.html")

        search.fill("2B COMPLEX")
        options = page.locator("#condo-suggestions [role='option']")
        playwright_api.expect(options).to_have_count(1)
        options.first.click()
        playwright_api.expect(route).to_contain_text(
            "no reviewed achieved-project identity"
        )
        page.locator("#condo-form .primary-btn").click()
        assert page.url.endswith("/index.html")
    finally:
        page.close()


def test_report_preview_expands_and_filter_query_counts_stay_truthful(landing_site) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page = _open_landing(landing_site)
    try:
        cards = page.locator("#report-grid .report-card")
        status = page.locator("#report-results-status")
        toggle = page.locator("#report-toggle")
        total = cards.count()
        assert total == 52
        category_values = page.locator("#report-category-filter option").evaluate_all(
            "options => options.map(option => option.value)"
        )
        assert len(category_values) == len(set(category_values))
        assert set(category_values) == {
            "all",
            *cards.evaluate_all("items => items.map(item => item.dataset.category)"),
        }

        playwright_api.expect(status).to_have_text(
            f"Showing 12 of {total} matching report groups · 13 of 54 matching report links."
        )
        assert cards.evaluate_all("items => items.filter(item => !item.hidden).length") == 12
        playwright_api.expect(toggle).to_have_text(f"Show all {total} reports")
        playwright_api.expect(toggle).to_have_attribute("aria-expanded", "false")
        toggle.click()
        playwright_api.expect(status).to_have_text(
            f"Showing {total} of {total} matching report groups · 54 of 54 matching report links."
        )
        assert cards.evaluate_all("items => items.filter(item => !item.hidden).length") == total
        playwright_api.expect(toggle).to_have_attribute("aria-expanded", "true")
        playwright_api.expect(cards.nth(12).locator(".report-primary-link")).to_be_focused()

        page.locator("#report-category-filter").select_option("property-analysis")
        playwright_api.expect(status).to_have_text(
            "Showing 26 of 26 matching report groups · 28 of 28 matching report links."
        )
        assert cards.evaluate_all("items => items.filter(item => !item.hidden).length") == 26
        playwright_api.expect(toggle).to_be_hidden()

        page.locator("#report-search").fill("Canberra Crescent")
        playwright_api.expect(status).to_have_text(
            "Showing 1 of 1 matching report groups · 2 of 2 matching report links."
        )
        assert cards.evaluate_all("items => items.filter(item => !item.hidden).length") == 1
        playwright_api.expect(page.locator("#report-grid .report-card:not([hidden])")).to_have_attribute(
            "data-project-slug", "canberra-crescent-residences"
        )
    finally:
        page.close()


def test_report_filters_use_exact_metadata_and_url_back_forward_state(landing_site) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    browser, url = landing_site
    page = browser.new_page(viewport={"width": 1100, "height": 850})
    try:
        page.goto(
            f"{url}?keep=1&q=canberra&category=property-analysis&freshness=dated"
            "&evidence=market_research#reports",
            wait_until="load",
        )
        playwright_api.expect(page.locator("#report-search")).to_have_value("canberra")
        playwright_api.expect(page.locator("#report-category-filter")).to_have_value(
            "property-analysis"
        )
        playwright_api.expect(page.locator("#report-freshness-filter")).to_have_value(
            "dated"
        )
        playwright_api.expect(page.locator("#report-evidence-filter")).to_have_value(
            "market_research"
        )
        playwright_api.expect(page.locator("#report-results-status")).to_have_text(
            "Showing 1 of 1 matching report groups · 2 of 2 matching report links."
        )

        page.locator("#report-search").fill("lakegarden")
        playwright_api.expect(page.locator("#report-results-status")).to_have_text(
            "Showing 1 of 1 matching report groups · 2 of 2 matching report links."
        )
        assert "keep=1" in page.url and page.url.endswith("#reports")
        page.go_back()
        playwright_api.expect(page.locator("#report-search")).to_have_value("canberra")
        playwright_api.expect(page.locator("#report-results-status")).to_have_text(
            "Showing 1 of 1 matching report groups · 2 of 2 matching report links."
        )
        page.go_forward()
        playwright_api.expect(page.locator("#report-search")).to_have_value("lakegarden")

        page.locator("#report-freshness-filter").select_option("unknown")
        playwright_api.expect(page.locator("#report-results-status")).to_have_text(
            "No matching reports."
        )
        playwright_api.expect(page.locator("#report-empty")).to_be_visible()
        page.go_back()
        playwright_api.expect(page.locator("#report-freshness-filter")).to_have_value(
            "dated"
        )
        playwright_api.expect(page.locator("#report-search")).to_have_value("lakegarden")
    finally:
        page.close()


def test_invalid_report_query_is_canonical_and_special_characters_round_trip(
    landing_site,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    browser, url = landing_site
    page = browser.new_page(viewport={"width": 1100, "height": 850})
    try:
        page.goto(
            f"{url}?keep=yes&category=invalid&category=property-analysis"
            "&freshness=invalid&evidence=invalid&q=%20%20Canberra%20%20%26%20Lake%2B%23%25#reports",
            wait_until="load",
        )
        playwright_api.expect(page.locator("#report-search")).to_have_value(
            "Canberra & Lake+#%"
        )
        for selector in (
            "#report-category-filter",
            "#report-freshness-filter",
            "#report-evidence-filter",
        ):
            playwright_api.expect(page.locator(selector)).to_have_value("all")
        assert "keep=yes" in page.url
        assert "category=" not in page.url
        assert "freshness=" not in page.url
        assert "evidence=" not in page.url
        assert page.url.endswith("#reports")
        assert page.evaluate("new URL(location.href).searchParams.get('q')") == "Canberra & Lake+#%"
    finally:
        page.close()


def test_grouped_history_links_are_reachable_and_latest_capture_is_primary(
    landing_site,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page = _open_landing(landing_site)
    try:
        canberra = page.locator(
            ".report-card[data-project-slug='canberra-crescent-residences']"
        )
        playwright_api.expect(canberra).to_have_count(1)
        primary = canberra.locator(".report-primary-link")
        history = canberra.locator(".report-history-link")
        assert primary.get_attribute("href") == (
            "property-analysis-2026-08-08-canberra-crescent-residences.html"
        )
        playwright_api.expect(history).to_have_count(1)
        assert history.get_attribute("href") == (
            "property-analysis-2026-08-03-canberra-crescent-residences.html"
        )
        details = canberra.locator("details")
        details.locator("summary").focus()
        details.locator("summary").press("Enter")
        playwright_api.expect(details).to_have_attribute("open", "")
        history.focus()
        playwright_api.expect(history).to_be_focused()

        page.locator("#report-search").fill(
            "property-analysis-2026-08-03-canberra-crescent-residences.html"
        )
        playwright_api.expect(page.locator("#report-results-status")).to_have_text(
            "Showing 1 of 1 matching report groups · 1 of 1 matching report links."
        )
        playwright_api.expect(canberra.locator("details")).to_have_attribute("open", "")
        playwright_api.expect(history).to_be_visible()

        page.locator("#report-search").fill("")
        page.locator("#condo-search").fill("CANBERRA CRESCENT RESIDENCES")
        page.locator("#condo-suggestions [role='option']").first.click()
        route = page.locator("#condo-route a").first
        assert route.get_attribute("href") == primary.get_attribute("href")
    finally:
        page.close()


def test_report_library_is_static_and_every_catalog_link_is_unique(landing_site) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    browser, url = landing_site
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    try:
        page.goto(url, wait_until="load")
        primary = page.locator("#report-grid .report-primary-link")
        history = page.locator("#report-grid .report-history-link")
        assert primary.count() == 52
        assert history.count() == 2
        paths = primary.evaluate_all(
            "links => links.map(link => link.closest('.report-card').dataset.reportPath)"
        )
        paths += history.evaluate_all("links => links.map(link => link.dataset.reportPath)")
        assert len(paths) == 54
        assert len(set(paths)) == 54
        assert all(paths)
    finally:
        page.close()
        context.close()


def test_report_filters_work_from_file_url_without_runtime_catalog_fetch(
    tmp_path: Path,
    landing_site,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    site_root = tmp_path / "local preview"
    assets = site_root / "assets"
    assets.mkdir(parents=True)
    shutil.copy2(ROOT / "index.html", site_root / "index.html")
    for name in ("data-loader.js", "research-shell.css", "research-shell.js"):
        shutil.copy2(ROOT / "site" / "assets" / name, assets / name)

    browser, _ = landing_site
    page = browser.new_page(viewport={"width": 1100, "height": 850})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto((site_root / "index.html").as_uri(), wait_until="load")
        page.locator("#report-search").fill("Canberra Crescent")
        playwright_api.expect(page.locator("#report-results-status")).to_have_text(
            "Showing 3 of 3 matching report groups · 4 of 4 matching report links."
        )
        page.locator("#report-category-filter").select_option("property-analysis")
        playwright_api.expect(page.locator("#report-results-status")).to_have_text(
            "Showing 1 of 1 matching report groups · 2 of 2 matching report links."
        )
        assert page.url.startswith("file://")
        assert "category=property-analysis" in page.url
        href = page.locator(".report-card:not([hidden]) .report-primary-link").get_attribute(
            "href"
        )
        assert href == "property-analysis-2026-08-08-canberra-crescent-residences.html"
        assert errors == []
    finally:
        page.close()


def test_mobile_landing_has_no_horizontal_page_overflow(landing_site) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page = _open_landing(landing_site, width=390, height=844)
    try:
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        page.locator("#report-toggle").click()
        playwright_api.expect(page.locator("#report-toggle")).to_have_attribute(
            "aria-expanded", "true"
        )
        page.locator("#condo-search").fill("EASTERN LAGOON")
        playwright_api.expect(page.locator("#condo-suggestions")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    finally:
        page.close()
