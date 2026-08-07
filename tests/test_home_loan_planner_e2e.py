"""Real-browser smoke coverage for the interactive home-loan planner."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import threading

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "home_loan_planner.html"


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
        preview = tmp_path_factory.mktemp("home-loan-browser-preview")
        assets = preview / "assets"
        assets.mkdir()
        shutil.copy2(PAGE, preview / PAGE.name)
        for name in ("home-loan-planner.js", "research-shell.js", "research-shell.css"):
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


def test_complete_calculator_flow_in_a_real_browser(chromium_page) -> None:
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

    page.goto(url, wait_until="load")

    assert page_errors == []
    assert console_errors == []
    assert "2051" in page.locator("#new-summary-copy").inner_text()
    assert page.locator("#schedule-payoff").inner_text() == "Jul 2051"
    assert page.locator("#schedule-principal").inner_text() == "S$750,000"
    assert page.locator("#schedule-interest").inner_text() == "S$394,585"

    loan_amount = page.locator("#new-loan-amount")
    loan_amount.fill("$1,207,404.00")
    assert page.locator("#calculator-errors").is_hidden()
    assert page.locator("#schedule-principal").inner_text() == "S$1,207,404"
    loan_amount.blur()
    assert loan_amount.input_value() == "1,207,404.00"
    page.locator("#construction-toggle").check()
    assert loan_amount.input_value() == "1,207,404.00"
    assert page.locator("#schedule-principal").inner_text() == "S$1,207,404"
    page.locator("#construction-toggle").uncheck()
    loan_amount.fill("750000")
    loan_amount.blur()
    assert loan_amount.input_value() == "750,000"

    page.locator("#loan-tab-existing").click()
    assert page.locator("#current-monthly").inner_text() == "S$5,098"
    assert page.locator("#package-monthly").inner_text() == "S$4,980"
    assert page.locator("#monthly-reduction").inner_text() == "S$118"
    assert page.locator("#first-year-saving").inner_text() == "S$2,424"
    assert page.locator("#lifetime-saving").inner_text() == "S$14,217"

    page.locator("#package-interest-rate").fill("3.00")
    assert page.locator("#package-monthly").inner_text() == "S$4,828"

    page.locator("#loan-tab-new").click()
    page.locator("#construction-toggle").check()
    assert page.locator("#progressive-card").is_visible()
    loan_amount.fill("1207404")
    assert loan_amount.input_value() == "1207404"
    assert page.locator("#schedule-principal").inner_text() == "S$1,207,404"
    loan_amount.blur()
    assert loan_amount.input_value() == "1,207,404"
    loan_amount.fill("750000")
    loan_amount.blur()
    assert page.locator("#schedule-interest").inner_text() == "S$364,723"
    assert page.locator("#progressive-timeline .timeline-row output").all_inner_texts() == [
        "S$254/mo",
        "S$769/mo",
        "S$1,030/mo",
        "S$1,293/mo",
        "S$1,557/mo",
        "S$1,823/mo",
        "S$3,163/mo",
        "S$3,991/mo",
    ]

    page.locator("#schedule-body .year-toggle").first.click()
    assert page.locator("#schedule-body .month-details tbody tr").count() == 5

    page.locator("#construction-toggle").uncheck()
    page.locator("#partial-details summary").click()
    page.locator("#partial-amount").fill("50000")
    assert page.locator("#calculator-errors").is_hidden()
    assert page.locator("#schedule-payoff").inner_text() == "Jul 2051"

    page.locator("#partial-mode").select_option("target-term")
    assert page.locator("#partial-term-fields").is_visible()
    page.locator("#partial-new-years").fill("15")
    page.locator("#partial-new-months").fill("0")
    assert page.locator("#calculator-errors").is_hidden()
    assert page.locator("#schedule-payoff").inner_text() == "Aug 2042"

    page.locator("#partial-mode").select_option("target-payment")
    assert page.locator("#partial-payment-fields").is_visible()
    page.locator("#partial-new-payment").fill("4000")
    assert page.locator("#calculator-errors").is_hidden()
    assert page.locator("#schedule-payoff").inner_text() == "Aug 2047"

    assert page_errors == []
    assert console_errors == []


def test_mobile_page_does_not_overflow_viewport(chromium_page) -> None:
    page, url = chromium_page
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(url, wait_until="load")

    assert page.evaluate(
        "document.documentElement.scrollWidth === document.documentElement.clientWidth"
    )
    assert page.locator(".table-scroll").evaluate(
        "element => element.scrollWidth > element.clientWidth"
    )
