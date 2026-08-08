"""Real-browser checks for the exact co-owner funding ledger in planner V3."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import threading

import pytest


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "condo_loan_timeline_planner.html"
STORAGE_KEY = "housing-estate-framework.condo-loan-timeline-planner-v3.draft.v1"


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
        preview = tmp_path_factory.mktemp("condo-funding-v3-preview")
        assets = preview / "assets"
        assets.mkdir()
        shutil.copy2(PAGE, preview / PAGE.name)
        for name in (
            "condo-loan-timeline-planner.js",
            "condo-loan-timeline-funding-v3.js",
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


def _fill_and_blur(locator, value: str) -> None:
    locator.fill(value)
    locator.blur()


def _set_ledger_amount(page, row_key: str, field: str, value: str) -> None:
    _fill_and_blur(
        page.locator(
            f"#funding-ledger-body [data-row-key='{row_key}'][data-field='{field}']"
        ),
        value,
    )


def _load_clean(page, url: str) -> None:
    page.goto(url, wait_until="load")
    page.locator("#reset-plan").click()
    page.wait_for_function(
        "key => localStorage.getItem(key) === null", arg=STORAGE_KEY
    )
    page.reload(wait_until="load")


def _open_details(page, selector: str) -> None:
    details = page.locator(selector)
    if not details.evaluate("element => element.open"):
        details.locator(":scope > summary").click()


def _money_number(locator) -> float:
    return float(locator.input_value().replace(",", ""))


def _apply_couple_setup(
    page,
    *,
    borrower: str = "joint",
    primary_name: str | None = None,
    partner_name: str | None = None,
    amounts: dict[str, float] | None = None,
) -> None:
    dialog = page.locator("#couple-funding-dialog")
    dialog.wait_for(state="visible")
    page.locator(f"#loan-borrower-{borrower}").check()
    if primary_name is not None:
        page.locator("#couple-primary-name").fill(primary_name)
    if partner_name is not None:
        page.locator("#couple-partner-name").fill(partner_name)
    for field, value in (amounts or {}).items():
        page.locator(f"#couple-{field.replace('_', '-')}").fill(str(value))
    page.locator("#couple-dialog-apply").click()
    dialog.wait_for(state="hidden")
    page.locator("#funding-ledger-card").wait_for(state="visible")


def _wait_for_saved_dialog_draft(
    page,
    *,
    borrower: str,
    values: dict[str, str],
    open_state: bool = True,
) -> None:
    page.wait_for_function(
        """
        ({ key, borrower, values, openState }) => {
          try {
            const saved = JSON.parse(localStorage.getItem(key));
            const dialogDraft = saved && saved.coupleDialogDraft;
            return dialogDraft
              && dialogDraft.borrower === borrower
              && dialogDraft.open === openState
              && Object.entries(values).every(
                ([id, value]) => dialogDraft.values[id] === value
              );
          } catch {
            return false;
          }
        }
        """,
        arg={
            "key": STORAGE_KEY,
            "borrower": borrower,
            "values": values,
            "openState": open_state,
        },
    )


def _set_owner_allocations(page, row_key: str, **amounts: float) -> None:
    for field in ("primaryCash", "primaryCpf", "partnerCash", "partnerCpf"):
        _set_ledger_amount(page, row_key, field, str(amounts.get(field, 0)))


def test_default_form_uses_progressive_disclosure(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    page.set_viewport_size({"width": 1280, "height": 900})
    _load_clean(page, url)

    for selector in (
        "#purchase-price",
        "#loan-amount",
        "#acquisition-date",
        "#buc-top-date",
        "#annual-growth",
        "#sale-date",
        "label[for='partner-enabled']",
    ):
        playwright_api.expect(page.locator(selector)).to_be_visible()

    property_details = page.locator("#property-loan-details")
    partner_details = page.locator("#partner-settings")
    advanced_details = page.locator("#advanced-cost-details")
    assert property_details.evaluate("element => !element.open")
    assert advanced_details.evaluate("element => !element.open")
    assert partner_details.is_hidden()
    assert page.locator("#project-name").is_hidden()
    assert page.locator("#area-sqft").is_hidden()
    assert page.locator("#loan-rate").is_hidden()
    assert page.locator("#purchase-legal").is_hidden()
    assert page.locator("#selling-cost-percent").is_hidden()

    _open_details(page, "#property-loan-details")
    playwright_api.expect(page.locator("#project-name")).to_be_visible()
    playwright_api.expect(page.locator("#loan-rate")).to_be_visible()

    page.locator("#partner-enabled").check()
    playwright_api.expect(partner_details).to_be_visible()
    assert partner_details.evaluate("element => !element.open")
    playwright_api.expect(page.locator("#couple-funding-dialog")).to_be_visible()
    assert page.locator("#funding-ledger-card").is_hidden()
    assert page.locator("#couple-required-funding").inner_text() == (
        page.locator("#couple-entered-funding").inner_text()
    )
    assert page.locator("#couple-funding-difference").inner_text() == "S$0 · matched"
    _apply_couple_setup(page)
    _open_details(page, "#partner-settings")
    playwright_api.expect(page.locator("#partner-ownership-share")).to_be_visible()
    playwright_api.expect(page.locator("#edit-couple-funding")).to_be_visible()

    _open_details(page, "#advanced-cost-details")
    playwright_api.expect(page.locator("#purchase-legal")).to_be_visible()
    playwright_api.expect(page.locator("#selling-cost-percent")).to_be_visible()


def test_holding_scenario_follows_desktop_scroll_only(chromium_page) -> None:
    page, url = chromium_page
    page.set_viewport_size({"width": 1280, "height": 900})
    _load_clean(page, url)

    result_card = page.locator("#results-panel")
    assert result_card.evaluate("element => getComputedStyle(element).position") == "sticky"
    page.locator("#partner-enabled").check()
    _apply_couple_setup(page)
    page.locator("#funding-ledger-title").scroll_into_view_if_needed()
    page.wait_for_timeout(100)
    assert result_card.evaluate(
        "element => Math.round(element.getBoundingClientRect().top)"
    ) == 12
    assert result_card.evaluate(
        "element => element.getBoundingClientRect().right"
    ) < page.locator("#funding-ledger-card").evaluate(
        "element => element.getBoundingClientRect().left"
    )

    page.locator("#schedule-title").scroll_into_view_if_needed()
    page.wait_for_timeout(100)
    assert result_card.evaluate(
        "element => Math.round(element.getBoundingClientRect().top)"
    ) == 12

    page.set_viewport_size({"width": 900, "height": 900})
    assert result_card.evaluate("element => getComputedStyle(element).position") == "static"


def test_first_enable_cancel_close_and_escape_all_turn_partner_back_off(
    chromium_page,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    for dismissal in ("cancel", "close", "escape"):
        _load_clean(page, url)
        page.locator("#partner-enabled").check()
        playwright_api.expect(page.locator("#couple-funding-dialog")).to_be_visible()
        assert page.locator("#funding-ledger-card").is_hidden()
        if dismissal == "cancel":
            page.locator("#couple-dialog-cancel").click()
        elif dismissal == "close":
            page.locator("#couple-dialog-close").click()
        else:
            page.keyboard.press("Escape")
        playwright_api.expect(page.locator("#couple-funding-dialog")).to_be_hidden()
        playwright_api.expect(page.locator("#partner-enabled")).not_to_be_checked()
        assert page.locator("#partner-settings").is_hidden()
        assert page.locator("#funding-ledger-card").is_hidden()


def test_unapplied_couple_dialog_draft_survives_autosave_refresh(
    chromium_page,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load_clean(page, url)

    page.locator("#partner-enabled").check()
    dialog = page.locator("#couple-funding-dialog")
    playwright_api.expect(dialog).to_be_visible()
    assert page.locator("#funding-ledger-card").is_hidden()

    borrower = "partner"
    values = {
        "couple-primary-name": "Evan Draft",
        "couple-partner-name": "Mandy Draft",
        "couple-primary-cash": "86,296.25",
        "couple-primary-cpf": "141,500.50",
        "couple-partner-cash": "224,315.75",
        "couple-partner-cpf": "987.50",
    }
    page.locator(f"#loan-borrower-{borrower}").check()
    for field_id, raw_value in values.items():
        page.locator(f"#{field_id}").fill(raw_value)

    reconciliation = {
        output_id: page.locator(f"#{output_id}").inner_text()
        for output_id in (
            "couple-required-funding",
            "couple-entered-funding",
            "couple-funding-difference",
        )
    }
    assert reconciliation["couple-entered-funding"] == "S$453,100"
    assert reconciliation["couple-funding-difference"] == "S$0 · matched"

    _wait_for_saved_dialog_draft(page, borrower=borrower, values=values)
    playwright_api.expect(page.locator("#draft-save-status")).to_contain_text(
        "Saved automatically"
    )

    page.reload(wait_until="load")

    playwright_api.expect(page.locator("#partner-enabled")).to_be_checked()
    playwright_api.expect(dialog).to_be_visible()
    assert page.locator("#funding-ledger-card").is_hidden()
    playwright_api.expect(page.locator(f"#loan-borrower-{borrower}")).to_be_checked()
    for field_id, raw_value in values.items():
        assert page.locator(f"#{field_id}").input_value() == raw_value
    for output_id, expected_text in reconciliation.items():
        assert page.locator(f"#{output_id}").inner_text() == expected_text
    page.locator("#couple-dialog-cancel").click()
    playwright_api.expect(dialog).to_be_hidden()


def test_unapplied_edit_of_complete_setup_reopens_after_refresh(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load_clean(page, url)

    page.locator("#partner-enabled").check()
    _apply_couple_setup(
        page,
        borrower="primary",
        primary_name="Applied Evan",
        partner_name="Applied Mandy",
    )
    assert page.locator("#ledger-loan-heading").inner_text() == (
        "Applied Evan bank loan"
    )

    _open_details(page, "#partner-settings")
    page.locator("#edit-couple-funding").click()
    dialog = page.locator("#couple-funding-dialog")
    playwright_api.expect(dialog).to_be_visible()
    borrower = "partner"
    values = {
        "couple-primary-name": "Draft Evan",
        "couple-partner-name": "Draft Mandy",
        "couple-primary-cash": "1,234.50",
        "couple-primary-cpf": "2,345.60",
        "couple-partner-cash": "3,456.70",
        "couple-partner-cpf": "446,063.20",
    }
    page.locator(f"#loan-borrower-{borrower}").check()
    for field_id, raw_value in values.items():
        page.locator(f"#{field_id}").fill(raw_value)
    _wait_for_saved_dialog_draft(page, borrower=borrower, values=values)

    page.reload(wait_until="load")

    playwright_api.expect(page.locator("#partner-enabled")).to_be_checked()
    playwright_api.expect(page.locator("#funding-ledger-card")).to_be_visible()
    playwright_api.expect(dialog).to_be_visible()
    playwright_api.expect(page.locator(f"#loan-borrower-{borrower}")).to_be_checked()
    for field_id, raw_value in values.items():
        assert page.locator(f"#{field_id}").input_value() == raw_value
    assert page.locator("#primary-owner-name").input_value() == "Applied Evan"
    assert page.locator("#partner-owner-name").input_value() == "Applied Mandy"
    assert page.locator("#ledger-loan-heading").inner_text() == (
        "Applied Evan bank loan"
    )

    page.locator("#couple-dialog-cancel").click()
    playwright_api.expect(dialog).to_be_hidden()
    playwright_api.expect(page.locator("#partner-enabled")).to_be_checked()
    playwright_api.expect(page.locator("#funding-ledger-card")).to_be_visible()


def test_sample_allocations_reconcile_and_variance_is_visible(chromium_page) -> None:
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
    _load_clean(page, url)

    assert page.locator("#partner-settings").is_hidden()
    assert page.locator("#funding-ledger-card").is_hidden()
    _fill_and_blur(page.locator("#purchase-price"), "1610000")
    _fill_and_blur(page.locator("#loan-amount"), "1207404")
    _open_details(page, "#advanced-cost-details")
    _fill_and_blur(page.locator("#purchase-legal"), "2800")
    page.locator("#acquisition-date").fill("2025-10-25")
    page.locator("#buc-top-date").fill("2028-07-06")
    page.locator("#sale-date").fill("2031-10-25")
    playwright_api.expect(page.locator("#planner-errors")).to_be_hidden()

    page.locator("#partner-enabled").check()
    playwright_api.expect(page.locator("#partner-settings")).to_be_visible()
    playwright_api.expect(page.locator("#couple-funding-dialog")).to_be_visible()
    assert page.locator("#funding-ledger-card").is_hidden()
    assert page.locator("#couple-required-funding").inner_text() == "S$455,996"
    _apply_couple_setup(
        page,
        borrower="primary",
        primary_name="Evan",
        partner_name="Mandy",
        amounts={
            "primary_cash": 86_796,
            "primary_cpf": 141_500,
            "partner_cash": 227_700,
            "partner_cpf": 0,
        },
    )
    assert page.locator("#ledger-loan-heading").inner_text() == "Evan bank loan"
    assert page.locator("#ledger-loan-column-heading").inner_text() == "Evan bank loan"
    playwright_api.expect(page.locator("#ledger-overall-status")).to_have_text(
        "All rows and totals reconcile"
    )
    assert page.locator("#ledger-purchase-reconciliation").inner_text() == (
        "S$1,610,000 · reconciled"
    )
    assert page.locator("#ledger-loan-reconciliation").inner_text() == (
        "S$1,207,404 · reconciled"
    )
    assert page.locator("#ledger-equity-reconciliation").inner_text() == (
        "S$402,596 · reconciled"
    )
    assert page.locator("#ledger-cost-reconciliation").inner_text() == (
        "S$53,400 · reconciled"
    )

    foundation = page.locator(
        "#funding-ledger-body [data-row-key='stage-2'][data-field='action']"
    ).locator("xpath=ancestor::tr")
    assert foundation.locator("[data-field='paymentAmount']").input_value() == "161,000"
    assert foundation.locator("[data-field='loan']").input_value() == "80,404"
    mortgage = page.locator(
        "#funding-ledger-body [data-row-key='cost-mortgage-duty'][data-field='action']"
    ).locator("xpath=ancestor::tr")
    assert mortgage.locator("[data-field='action']").input_value() == "Mortgage duty"
    assert mortgage.locator("[data-field='paymentAmount']").input_value() == "500"

    _set_owner_allocations(page, "stage-0", partnerCash=80_500)
    _set_owner_allocations(page, "cost-purchase-legal", partnerCash=2_800)
    _set_owner_allocations(page, "cost-bsd", partnerCash=50_100)
    _set_owner_allocations(
        page,
        "stage-1",
        primaryCash=86_296,
        primaryCpf=60_904,
        partnerCash=94_300,
    )
    _set_owner_allocations(page, "stage-2", primaryCpf=80_596)
    page.locator("[data-remove-row='cost-mortgage-duty']").click()

    playwright_api.expect(page.locator("#ledger-overall-status")).to_have_text(
        "Ledger needs reconciliation"
    )
    assert page.locator("#ledger-cost-reconciliation").inner_text() == (
        "S$53,400 target · S$52,900 ledger · −S$500"
    )
    assert page.locator("#ledger-primary-cash-footer").inner_text() == "S$86,296"
    assert page.locator("#ledger-primary-cpf-footer").inner_text() == "S$141,500"
    assert page.locator("#ledger-partner-cash-footer").inner_text() == "S$227,700"
    assert page.locator("#ledger-partner-cpf-footer").inner_text() == "S$0"
    assert page.locator("#ledger-loan-footer").inner_text() == "S$1,207,404"
    assert page.locator("#ledger-payment-total").inner_text() == "S$1,662,900"
    assert page.locator("#ledger-allocated-footer").inner_text() == "S$1,662,900"
    assert page.locator("#ledger-difference-footer").inner_text() == "S$0"
    assert page.locator("#funding-ledger-body .ledger-status-bad").count() == 0

    _set_ledger_amount(page, "stage-0", "partnerCash", "80400")
    playwright_api.expect(page.locator("#ledger-overall-status")).to_have_text(
        "Ledger needs reconciliation"
    )
    booking = page.locator(
        "#funding-ledger-body [data-row-key='stage-0'][data-field='action']"
    ).locator("xpath=ancestor::tr")
    playwright_api.expect(booking.locator(".ledger-status-bad")).to_contain_text(
        "short S$100"
    )
    assert page.locator("#ledger-difference-footer").inner_text() == "+S$100"

    _set_ledger_amount(page, "stage-0", "partnerCash", "80500")
    playwright_api.expect(page.locator("#ledger-difference-footer")).to_have_text("S$0")
    assert page.locator("#funding-ledger-body .ledger-status-bad").count() == 0
    funding_totals = page.locator(
        "#ledger-primary-cash-footer, #ledger-primary-cpf-footer, "
        "#ledger-partner-cash-footer, #ledger-partner-cpf-footer"
    ).all_inner_texts()
    _open_details(page, "#partner-settings")
    page.locator("#partner-ownership-share").fill("25")
    playwright_api.expect(page.locator("#ledger-partner-outcome")).to_contain_text("25%")
    assert page.locator(
        "#ledger-primary-cash-footer, #ledger-primary-cpf-footer, "
        "#ledger-partner-cash-footer, #ledger-partner-cpf-footer"
    ).all_inner_texts() == funding_totals

    _fill_and_blur(page.locator("#loan-amount"), "1207304")
    playwright_api.expect(page.locator("#ledger-stale")).to_be_visible()
    assert page.locator(
        "#funding-ledger-body [data-row-key='stage-0'][data-field='partnerCash']"
    ).input_value() == "80,500"
    playwright_api.expect(page.locator("#ledger-loan-reconciliation")).to_contain_text(
        "S$1,207,304 target · S$1,207,404 ledger"
    )
    page.locator("#regenerate-funding-ledger").click()
    playwright_api.expect(page.locator("#ledger-stale")).to_be_hidden()
    playwright_api.expect(page.locator("#ledger-overall-status")).to_have_text(
        "Ledger needs reconciliation"
    )
    playwright_api.expect(page.locator("#couple-plan-status")).to_contain_text(
        "Saved setup: S$100 shortfall"
    )
    assert page.locator(
        "#funding-ledger-body [data-row-key='stage-0'][data-field='partnerCash']"
    ).input_value() == "0"

    page.locator("#partner-enabled").uncheck()
    assert page.locator("#partner-settings").is_hidden()
    assert page.locator("#funding-ledger-card").is_hidden()
    assert page_errors == []
    assert console_errors == []


def test_modal_shortage_and_excess_remain_visible_after_apply(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load_clean(page, url)
    page.locator("#partner-enabled").check()
    playwright_api.expect(page.locator("#couple-funding-dialog")).to_be_visible()
    assert page.locator("#couple-required-funding").inner_text() == "S$453,100"

    _apply_couple_setup(
        page,
        amounts={
            "primary_cash": 0,
            "primary_cpf": 0,
            "partner_cash": 0,
            "partner_cpf": 0,
        },
    )
    _open_details(page, "#partner-settings")
    playwright_api.expect(page.locator("#couple-plan-status")).to_contain_text(
        "Saved setup: S$453,100 shortfall"
    )
    playwright_api.expect(page.locator("#ledger-overall-status")).to_have_text(
        "Ledger needs reconciliation"
    )

    page.locator("#edit-couple-funding").click()
    playwright_api.expect(page.locator("#couple-funding-dialog")).to_be_visible()
    page.locator("#couple-primary-cash").fill("453200")
    playwright_api.expect(page.locator("#couple-entered-funding")).to_have_text(
        "S$453,200"
    )
    playwright_api.expect(page.locator("#couple-funding-difference")).to_have_text(
        "S$100 excess"
    )
    _apply_couple_setup(
        page,
        borrower="partner",
        primary_name="Alex",
        partner_name="Jamie",
    )
    assert page.locator("#ledger-loan-heading").inner_text() == "Jamie bank loan"
    assert page.locator("#ledger-loan-column-heading").inner_text() == "Jamie bank loan"
    playwright_api.expect(page.locator("#couple-plan-status")).to_contain_text(
        "Saved setup: S$100 remains unallocated"
    )
    playwright_api.expect(page.locator("#ledger-overall-status")).to_have_text(
        "All rows and totals reconcile"
    )


def test_browser_draft_survives_reload_and_reset_restores_html_defaults(
    chromium_page,
) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    page.set_viewport_size({"width": 1280, "height": 900})
    _load_clean(page, url)

    page.locator("#route-resale").check()
    _open_details(page, "#property-loan-details")
    page.locator("#project-name").fill("Persisted couple condo")
    page.locator("#area-sqft").fill("850")
    page.locator("#loan-rate").fill("2.75")
    page.locator("#loan-years").fill("25")
    _fill_and_blur(page.locator("#purchase-price"), "1610000")
    _fill_and_blur(page.locator("#loan-amount"), "1207404")
    page.locator("#acquisition-date").fill("2025-10-25")
    page.locator("#resale-completion-date").fill("2025-12-25")
    page.locator("#sale-date").fill("2031-10-25")

    _open_details(page, "#advanced-cost-details")
    _fill_and_blur(page.locator("#purchase-legal"), "2800")
    page.locator("#selling-cost-percent").fill("1.75")

    page.locator("#partner-enabled").check()
    seeded_primary_cash = _money_number(page.locator("#couple-primary-cash"))
    seeded_partner_cash = _money_number(page.locator("#couple-partner-cash"))
    _apply_couple_setup(
        page,
        borrower="partner",
        primary_name="Evan",
        partner_name="Mandy",
        amounts={
            "primary_cash": seeded_primary_cash - 12_345,
            "primary_cpf": 12_345,
            "partner_cash": seeded_partner_cash,
            "partner_cpf": 0,
        },
    )
    _open_details(page, "#partner-settings")
    page.locator("#partner-ownership-share").fill("40")

    partner_cash = page.locator(
        "#funding-ledger-body [data-row-key='resale-completion']"
        "[data-field='partnerCash']"
    )
    current_partner_cash = _money_number(partner_cash)
    _set_ledger_amount(
        page,
        "resale-completion",
        "partnerCash",
        f"{current_partner_cash - 100:.2f}",
    )
    _set_ledger_amount(page, "resale-completion", "partnerCpf", "100")
    playwright_api.expect(page.locator("#ledger-overall-status")).to_have_text(
        "All rows and totals reconcile"
    )
    expected_partner_cash_text = page.locator(
        "#funding-ledger-body [data-row-key='resale-completion']"
        "[data-field='partnerCash']"
    ).input_value()
    expected_partner_cpf_text = page.locator(
        "#funding-ledger-body [data-row-key='resale-completion']"
        "[data-field='partnerCpf']"
    ).input_value()

    page.wait_for_function(
        "key => localStorage.getItem(key) !== null",
        arg=STORAGE_KEY,
    )
    assert page.locator("#draft-save-status").inner_text().strip()
    page.reload(wait_until="load")

    playwright_api.expect(page.locator("#route-resale")).to_be_checked()
    playwright_api.expect(page.locator("#partner-enabled")).to_be_checked()
    playwright_api.expect(page.locator("#funding-ledger-card")).to_be_visible()
    playwright_api.expect(page.locator("#couple-funding-dialog")).to_be_hidden()
    assert page.locator("#project-name").input_value() == "Persisted couple condo"
    assert page.locator("#area-sqft").input_value() == "850"
    assert page.locator("#loan-rate").input_value() == "2.75"
    assert page.locator("#loan-years").input_value() == "25"
    assert page.locator("#purchase-price").input_value().replace(",", "") == "1610000"
    assert page.locator("#loan-amount").input_value().replace(",", "") == "1207404"
    assert page.locator("#purchase-legal").input_value().replace(",", "") == "2800"
    assert page.locator("#selling-cost-percent").input_value() == "1.75"
    assert page.locator("#primary-owner-name").input_value() == "Evan"
    assert page.locator("#partner-owner-name").input_value() == "Mandy"
    assert page.locator("#partner-ownership-share").input_value() == "40"
    assert page.locator("#ledger-loan-heading").inner_text() == "Mandy bank loan"
    assert page.locator(
        "#funding-ledger-body [data-row-key='resale-completion']"
        "[data-field='partnerCash']"
    ).input_value() == expected_partner_cash_text
    assert page.locator(
        "#funding-ledger-body [data-row-key='resale-completion']"
        "[data-field='partnerCpf']"
    ).input_value() == expected_partner_cpf_text
    playwright_api.expect(page.locator("#ledger-overall-status")).to_have_text(
        "All rows and totals reconcile"
    )

    _open_details(page, "#property-loan-details")
    _open_details(page, "#partner-settings")
    _open_details(page, "#advanced-cost-details")
    page.locator("#edit-couple-funding").click()
    playwright_api.expect(page.locator("#couple-funding-dialog")).to_be_visible()
    playwright_api.expect(page.locator("#loan-borrower-partner")).to_be_checked()
    assert page.locator("#couple-primary-name").input_value() == "Evan"
    assert page.locator("#couple-partner-name").input_value() == "Mandy"
    assert _money_number(page.locator("#couple-primary-cash")) == pytest.approx(
        seeded_primary_cash - 12_345
    )
    assert _money_number(page.locator("#couple-primary-cpf")) == 12_345
    _apply_couple_setup(page, borrower="partner")
    assert page.locator(
        "#funding-ledger-body [data-row-key='resale-completion']"
        "[data-field='partnerCash']"
    ).input_value() == expected_partner_cash_text
    assert page.locator(
        "#funding-ledger-body [data-row-key='resale-completion']"
        "[data-field='partnerCpf']"
    ).input_value() == expected_partner_cpf_text

    page.locator("#reset-plan").click()
    page.wait_for_function(
        "key => localStorage.getItem(key) === null",
        arg=STORAGE_KEY,
    )
    playwright_api.expect(page.locator("#route-buc")).to_be_checked()
    assert page.locator("#project-name").input_value() == "My condominium"
    assert page.locator("#area-sqft").input_value() == "700"
    assert page.locator("#loan-rate").input_value() == "3.00"
    assert page.locator("#loan-years").input_value() == "30"
    assert page.locator("#purchase-price").input_value() == "1,600,000"
    assert page.locator("#loan-amount").input_value() == "1,200,000"
    assert page.locator("#purchase-legal").input_value() == "3,000"
    assert page.locator("#selling-cost-percent").input_value() == "2.18"
    playwright_api.expect(page.locator("#partner-enabled")).not_to_be_checked()
    assert page.locator("#primary-owner-name").input_value() == "Owner 1"
    assert page.locator("#partner-owner-name").input_value() == "Partner"
    assert page.locator("#partner-ownership-share").input_value() == "50"
    assert page.locator("#default-partner-payment-share").input_value() == "50"
    assert page.locator("#couple-funding-dialog").is_hidden()
    assert page.locator("#partner-settings").is_hidden()
    assert page.locator("#funding-ledger-card").is_hidden()
    assert page.locator("#property-loan-details").evaluate("element => !element.open")
    assert page.locator("#partner-settings").evaluate("element => !element.open")
    assert page.locator("#advanced-cost-details").evaluate("element => !element.open")

    page.reload(wait_until="load")
    assert page.evaluate("key => localStorage.getItem(key)", STORAGE_KEY) is None
    playwright_api.expect(page.locator("#route-buc")).to_be_checked()
    playwright_api.expect(page.locator("#partner-enabled")).not_to_be_checked()
    assert page.locator("#purchase-price").input_value() == "1,600,000"
    assert page.locator("#project-name").input_value() == "My condominium"


def test_route_switch_custom_row_and_mobile_table_scroll(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    page.set_viewport_size({"width": 390, "height": 844})
    _load_clean(page, url)
    page.locator("#partner-enabled").check()
    _apply_couple_setup(page)

    initial_count = page.locator("#funding-ledger-body tr").count()
    page.locator("#add-funding-row").click()
    playwright_api.expect(page.locator("#funding-ledger-body tr")).to_have_count(
        initial_count + 1
    )
    assert page.locator(
        "#funding-ledger-body [data-row-key='custom-1'][data-field='action']"
    ).input_value() == "New payment or timeline action"

    page.locator("#route-resale").check()
    playwright_api.expect(page.locator("#ledger-route-copy")).to_contain_text(
        "Completed-property funding ledger"
    )
    assert page.locator(
        "#funding-ledger-body [data-row-key='resale-completion'][data-field='action']"
    ).input_value() == "Completion / property payment"
    page.locator("#route-buc").check()
    playwright_api.expect(page.locator("#ledger-route-copy")).to_contain_text(
        "BUC funding ledger"
    )
    assert page.locator(
        "#funding-ledger-body [data-row-key='custom-1'][data-field='action']"
    ).input_value() == "New payment or timeline action"

    assert page.evaluate(
        "document.documentElement.scrollWidth === document.documentElement.clientWidth"
    )
    assert page.locator("#funding-ledger-card .ledger-table-wrap").evaluate(
        "element => element.scrollWidth > element.clientWidth"
    )
