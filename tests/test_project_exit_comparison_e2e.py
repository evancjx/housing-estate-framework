"""Real-browser coverage for the project exit comparison decision lab."""

from __future__ import annotations

from datetime import date
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import shutil
import subprocess
import threading
from urllib.parse import parse_qs, urlparse

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "project_exit_comparison.html"
DEFAULT_PROJECTS = [
    "the-poiz-residences",
    "parc-esta",
    "treasure-at-tampines",
]
DEFAULT_PROJECT_LABELS = [
    "THE POIZ RESIDENCES",
    "PARC ESTA",
    "TREASURE AT TAMPINES",
]
DISAMBIGUATED_PROJECT_ID = "eastern-lagoon-d15-upper-east-coast-road"
DISAMBIGUATED_PROJECT_LABEL = "EASTERN LAGOON · D15 / UPPER EAST COAST ROAD"
SECOND_DISAMBIGUATED_PROJECT_ID = "eastern-lagoon-d16-upper-east-coast-road"
SECOND_DISAMBIGUATED_PROJECT_LABEL = "EASTERN LAGOON · D16 / UPPER EAST COAST ROAD"
FUNDING_SCRIPT = ROOT / "site" / "assets" / "condo-loan-timeline-funding-v3.js"


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

        preview = tmp_path_factory.mktemp("project-exit-comparison-preview")
        assets = preview / "assets"
        assets.mkdir()
        shutil.copy2(PAGE, preview / PAGE.name)
        for name in (
            "project-exit-comparison.css",
            "project-exit-comparison.js",
            "research-shell.css",
            "research-shell.js",
        ):
            shutil.copy2(ROOT / "site" / "assets" / name, assets / name)
        shutil.copytree(
            ROOT / "site" / "assets" / "condo-transactions",
            assets / "condo-transactions",
        )

        handler = partial(_QuietHandler, directory=str(preview))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
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
    page_errors: list[str] = []
    console_errors: list[str] = []
    page_error_handler = lambda error: page_errors.append(str(error))
    console_handler = lambda message: (
        console_errors.append(message.text) if message.type == "error" else None
    )
    page.on("pageerror", page_error_handler)
    page.on("console", console_handler)
    page.goto(url, wait_until="load")
    try:
        page.locator("#comparison-results .evidence-card").first.wait_for(
            state="visible", timeout=20_000
        )
    except Exception as error:
        status = page.locator("#status-message").inner_text()
        form_error = page.locator("#form-error").inner_text()
        results = page.locator("#comparison-results").inner_text()
        raise AssertionError(
            f"decision lab did not render; status={status!r}, "
            f"form_error={form_error!r}, results={results[:500]!r}, "
            f"page_errors={page_errors!r}, console_errors={console_errors!r}"
        ) from error
    finally:
        page.remove_listener("pageerror", page_error_handler)
        page.remove_listener("console", console_handler)
    page.wait_for_function(
        "document.querySelector('#decision-lab').getAttribute('aria-busy') === 'false'"
    )


def _metric_values(page, label: str) -> list[str]:
    return page.locator(".evidence-card").evaluate_all(
        r"""(cards, label) => cards.map(card => {
          const row = [...card.querySelectorAll('.evidence-metrics > div')]
            .find(item => item.querySelector('dt')?.textContent.trim() === label);
          return row?.textContent.replace(/\s+/g, ' ').trim() || '';
        })""",
        label,
    )


def _money(text: str) -> int:
    match = re.search(r"S\$([\d,]+)", text)
    assert match, text
    return int(match.group(1).replace(",", ""))


def _parse_planner_handoff(search: str) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is unavailable; planner handoff parsing is skipped")
    program = (
        f"const funding=require({json.dumps(str(FUNDING_SCRIPT))});"
        f"const value=funding.parseDecisionLabHandoff({json.dumps(search)});"
        "process.stdout.write(JSON.stringify(value));"
    )
    completed = subprocess.run(
        [node, "-e", program],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def _wait_until_idle(page) -> None:
    page.wait_for_function(
        "document.querySelector('#decision-lab').getAttribute('aria-busy') === 'false'"
    )


def _set_project(page, index: int, label: str) -> None:
    page.locator("[data-role='project']").nth(index).evaluate(
        """(element, value) => {
          element.value = value;
          element.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        label,
    )
    _wait_until_idle(page)


def test_default_comparison_uses_preferred_projects_percent_band_and_resale_activity(
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
    assert page.locator("[data-role='project']").evaluate_all(
        "elements => elements.map(element => element.value)"
    ) == DEFAULT_PROJECT_LABELS
    playwright_api.expect(page.locator("#form-error")).to_be_hidden()
    playwright_api.expect(page.locator("#status-message")).to_contain_text(
        "Comparison updated for 3 candidates"
    )

    area_cells = page.locator(
        ".ledger-table tbody tr td:nth-child(3)"
    ).all_text_contents()
    areas = []
    for value in area_cells:
        match = re.fullmatch(r"\s*([\d,]+)\s+sqft\s*", value)
        assert match, f"unexpected ledger area cell: {value!r}"
        areas.append(int(match.group(1).replace(",", "")))
    assert areas
    assert all(810 <= area <= 990 for area in areas)
    assert any(area < 890 or area > 910 for area in areas)

    assert "Unknown" not in _metric_values(page, "Access evidence")[0]
    assert "Unknown" not in _metric_values(page, "Primary-school radius")[0]
    resale_flow = _metric_values(page, "Recorded resale flow")
    resale_cadence = _metric_values(page, "Recorded resale cadence")
    assert len(resale_flow) == len(DEFAULT_PROJECTS)
    assert len(resale_cadence) == len(DEFAULT_PROJECTS)
    assert all(resale_flow)
    assert all(resale_cadence)

    page.locator("#sale-state").select_option("New Sale")
    page.wait_for_function(
        """() => new URL(location.href).searchParams.get('saleState') === 'New Sale'
          && document.querySelector('#decision-lab').getAttribute('aria-busy') === 'false'"""
    )
    assert _metric_values(page, "Recorded resale flow") == resale_flow
    assert _metric_values(page, "Recorded resale cadence") == resale_cadence
    assert page_errors == []
    assert console_errors == []


def test_scenario_math_and_per_project_entry_round_trip_through_url(
    chromium_page,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load(page, url)

    _set_project(page, 0, DISAMBIGUATED_PROJECT_LABEL)
    _set_project(page, 1, SECOND_DISAMBIGUATED_PROJECT_LABEL)
    page.locator("#purchase-date").fill("2023-08")
    page.locator("#planned-sale-date").fill("2026-08")
    page.locator("#annual-growth").fill("3")
    page.locator("#selling-rate").fill("2.18")
    page.locator("#sale-costs").fill("3000")
    page.locator("[data-role='entry-price']").first.fill("1000000")
    page.locator("#decision-form button[type='submit']").click()
    page.wait_for_function(
        """() => new URL(location.href).searchParams.get('purchaseDate') === '2023-08'
          && document.querySelector('#decision-lab').getAttribute('aria-busy') === 'false'"""
    )

    days = (date(2026, 8, 1) - date(2023, 8, 1)).days
    hold_years = days / 365.2425
    projected = 1_000_000 * (1 + 0.03) ** hold_years
    allowance = projected * 0.0218
    net_before_financing_cpf = projected - allowance - 3_000

    outcome_rows = page.locator("#comparison-results .comparison-matrix").first.locator(
        "tbody tr"
    )
    projected_row = outcome_rows.filter(has_text="Projected sale price")
    net_row = outcome_rows.filter(
        has_text="Scenario proceeds before financing / CPF / SSD"
    )
    assert _money(projected_row.locator("td").first.inner_text()) == round(projected)
    assert _money(net_row.locator("td").first.inner_text()) == round(
        net_before_financing_cpf
    )

    query = parse_qs(urlparse(page.url).query, keep_blank_values=True)
    assert query["p"] == [
        DISAMBIGUATED_PROJECT_ID,
        SECOND_DISAMBIGUATED_PROJECT_ID,
        DEFAULT_PROJECTS[2],
    ]
    assert query["price"][0] == "1000000"
    assert query["purchaseDate"] == ["2023-08"]
    assert query["saleDate"] == ["2026-08"]
    assert query["annualGrowth"] == ["3"]
    assert query["sellingRate"] == ["2.18"]
    assert query["saleCosts"] == ["3000"]

    expected_duplicate_labels = [
        DISAMBIGUATED_PROJECT_LABEL,
        SECOND_DISAMBIGUATED_PROJECT_LABEL,
    ]
    assert page.locator(".evidence-card h3").all_inner_texts()[:2] == (
        expected_duplicate_labels
    )
    assert page.locator(
        ".comparison-matrix"
    ).first.locator("thead th").all_inner_texts()[1:3] == expected_duplicate_labels
    assert page.locator(".ledger-card summary strong").all_inner_texts()[:2] == (
        expected_duplicate_labels
    )

    planner_link = page.locator(".evidence-card").first.locator(
        "a.planner-link"
    ).get_attribute("href")
    assert planner_link
    planner_url = urlparse(planner_link)
    planner_query = parse_qs(planner_url.query)
    assert planner_url.path.endswith("/condo_loan_timeline_planner.html")
    assert planner_query == {
        "from": ["project-exit"],
        "project": [DISAMBIGUATED_PROJECT_LABEL],
        "purchasePrice": ["1000000"],
        "purchaseDate": ["2023-08-01"],
        "saleDate": ["2026-08-01"],
        "datePrecision": ["month"],
        "annualGrowth": ["3"],
        "sellingRate": ["2.18"],
        "saleCosts": ["3000"],
        "areaSqft": ["900"],
    }
    assert _parse_planner_handoff(planner_url.query) == {
        "project": DISAMBIGUATED_PROJECT_LABEL,
        "purchasePrice": 1_000_000,
        "purchaseDate": "2023-08-01",
        "saleDate": "2026-08-01",
        "datePrecision": "month",
        "annualGrowth": 3,
        "sellingRate": 2.18,
        "saleCosts": 3_000,
        "areaSqft": 900,
    }

    page.reload(wait_until="load")
    page.locator("#comparison-results .evidence-card").first.wait_for(state="visible")
    playwright_api.expect(page.locator("#purchase-date")).to_have_value("2023-08")
    playwright_api.expect(page.locator("#planned-sale-date")).to_have_value("2026-08")
    playwright_api.expect(page.locator("[data-role='entry-price']").first).to_have_value(
        "1000000"
    )


def test_invalid_bounds_and_project_inputs_fail_visibly_without_non_finite_output(
    chromium_page,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load(page, url)
    error = page.locator("#form-error")

    page.locator("#target-area").fill("199")
    page.locator("#decision-form button[type='submit']").click()
    playwright_api.expect(error).to_be_visible()
    playwright_api.expect(error).to_contain_text("between 200 and 10,000 sqft")

    page.locator("#target-area").fill("900")
    page.locator("#area-tolerance").fill("51")
    page.locator("#decision-form button[type='submit']").click()
    playwright_api.expect(error).to_contain_text("between 0% and 50%")

    page.locator("#area-tolerance").fill("10")
    page.locator("#purchase-date").fill("2031-08")
    page.locator("#planned-sale-date").fill("2030-08")
    page.locator("#decision-form button[type='submit']").click()
    playwright_api.expect(error).to_contain_text("must be after the purchase date")

    page.locator("#purchase-date").fill("2026-08")
    page.locator("#planned-sale-date").fill("2031-08")
    page.locator("#annual-growth").fill("21")
    page.locator("#decision-form button[type='submit']").click()
    playwright_api.expect(error).to_contain_text("between −20% and 20%")

    page.locator("#annual-growth").fill("3")
    page.locator("#selling-rate").fill("11")
    page.locator("#decision-form button[type='submit']").click()
    playwright_api.expect(error).to_contain_text("between 0% and 10%")

    page.locator("#selling-rate").fill("2.18")
    page.locator("#decision-form button[type='submit']").click()
    _wait_until_idle(page)
    playwright_api.expect(error).to_be_hidden()
    first_label = page.locator("[data-role='project']").first.input_value()
    _set_project(page, 1, first_label)
    playwright_api.expect(error).to_be_visible()
    playwright_api.expect(error).to_contain_text("different project")

    _set_project(page, 1, "NOT A RECOGNIZED PROJECT")
    playwright_api.expect(error).to_be_visible()
    playwright_api.expect(error).to_contain_text("recognized project")
    results_text = page.locator("#comparison-results").inner_text()
    assert not re.search(r"\b(?:NaN|Infinity|undefined)\b", results_text)

    page.locator("#reset-view").click()
    _wait_until_idle(page)
    playwright_api.expect(error).to_be_hidden()
    reset_query = parse_qs(urlparse(page.url).query, keep_blank_values=True)
    assert reset_query["p"] == DEFAULT_PROJECTS
    assert reset_query["price"] == ["", "", ""]
    assert reset_query["areaSqft"] == ["900"]
    assert reset_query["tolerancePct"] == ["10"]
    assert reset_query["saleState"] == ["Resale"]


def test_mobile_contains_wide_matrices_and_ledgers_inside_scroll_regions(
    chromium_page,
) -> None:
    page, url = chromium_page
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        _load(page, url)
        page.locator("details.ledger-card").first.locator("summary").click()
        page.locator(".ledger-scroll").first.wait_for(state="visible")
        dimensions = page.evaluate(
            """() => {
              const matrix = document.querySelector('.comparison-scroll');
              const ledger = document.querySelector('.ledger-scroll');
              return {
                body: document.documentElement.scrollWidth,
                viewport: window.innerWidth,
                matrixClient: matrix.clientWidth,
                matrixScroll: matrix.scrollWidth,
                ledgerClient: ledger.clientWidth,
                ledgerScroll: ledger.scrollWidth,
              };
            }"""
        )
        assert dimensions["body"] <= dimensions["viewport"] + 1
        assert dimensions["matrixScroll"] > dimensions["matrixClient"]
        assert dimensions["ledgerScroll"] > dimensions["ledgerClient"]
    finally:
        page.set_viewport_size({"width": 1440, "height": 1000})
