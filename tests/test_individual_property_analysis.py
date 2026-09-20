"""Evidence boundaries and publication identity for individual project reports."""

import math
import re

import pandas as pd
import pytest

from models.build_individual_property_analyses import (
    market_stage,
    maximum_entry,
    render_project,
    slugify,
)
from models.regional_research_economics import enrich_cohorts
from sg_estate.reporting.property_analysis import parse_property_analysis, render_property_analysis_page


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("The LakeGarden Residences", "the-lakegarden-residences"),
        ("  PARKTOWN   RESIDENCE  ", "parktown-residence"),
        ("77 @ EAST COAST", "77-east-coast"),
        ("J'DEN", "jden"),
    ],
)
def test_generated_project_slug_is_stable_and_safe(name, expected):
    slug = slugify(name)
    assert slug == expected
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug)


@pytest.mark.parametrize(
    ("exit_price", "entry"),
    [
        (191_589.7435897436, 180_000),
        (379_897.4358974359, 360_000),
        (1_056_000, 1_000_000),
        (1_589_333.3333333333, 1_500_000),
        (3_204_717.9487179486, 3_000_000),
        (4_291_897.435897436, 4_000_000),
    ],
)
def test_maximum_entry_inverts_residential_stamp_duty_at_bracket_boundaries(exit_price, entry):
    # Fixed independently calculated exit proceeds recover the purchase,
    # current residential BSD and S$5,000 allowance after 2.5% selling costs.
    assert maximum_entry(exit_price) == pytest.approx(entry, abs=0.02)


def test_target_gain_reduces_affordable_entry_instead_of_becoming_free_upside():
    exit_price = 1_568_820.5128205128
    assert maximum_entry(exit_price, target_gain=500_000) == pytest.approx(1_000_000, abs=0.02)
    assert maximum_entry(exit_price) > 1_000_000


def test_affordable_entry_removes_selling_and_acquisition_cost_assumptions_when_zero():
    # At S$1m, BSD is still S$24,600 even when the discretionary fees are zero.
    assert maximum_entry(1_024_600, legal_allowance=0, selling_rate=0) == pytest.approx(1_000_000, abs=0.02)


def test_unaffordable_exit_after_fixed_costs_returns_no_purchase_budget():
    assert maximum_entry(10_000, target_gain=5_000, legal_allowance=5_000) == 0


@pytest.mark.parametrize("exit_price", [0, -1, math.inf, math.nan])
def test_maximum_entry_rejects_invalid_exit_values(exit_price):
    with pytest.raises(ValueError):
        maximum_entry(exit_price)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_gain": -1}, {"target_gain": math.inf},
        {"legal_allowance": -1}, {"legal_allowance": math.nan},
        {"selling_rate": -0.1}, {"selling_rate": 1}, {"selling_rate": math.nan},
    ],
)
def test_maximum_entry_rejects_invalid_cost_or_gain_assumptions(kwargs):
    with pytest.raises(ValueError):
        maximum_entry(1_000_000, **kwargs)


def project_record(**overrides):
    return {
        "project_name": "SAMPLE PROJECT",
        "ec_origin": False,
        "region": "Bedok",
        "subregion": "Bedok planning area",
        "tenures": "99 yrs lease commencing from 2010",
        "latest_month": "2026-06",
        "coverage_note": "",
        "development_status": "Completion status not independently verified",
        "status_as_of": "",
        "scope_source": "https://example.com/project-geography",
    } | overrides


def transaction_records(*, sale_type="Resale", n=2, month="2026-06", eligible=True):
    # Different source occurrences deliberately expose the same public sale
    # signature. They cannot be deduplicated into one property transaction.
    return pd.DataFrame([
        {
            "record_id": f"source-occurrence-{index}",
            "metric_eligible": eligible,
            "sale_month": month,
            "street_name": "SAMPLE ROAD",
            "sale_type": sale_type,
            "tenure": "99 yrs lease commencing from 2010",
            "sqm": 80,
            "price": 1_000_000,
            "psf": 1_161,
        }
        for index in range(n)
    ])


def empty_rent():
    return pd.DataFrame(columns=["project_name", "ref_quarter", "median_psf_pm", "psf25", "psf75"])


def cohort_records(tmp_path, *, sale_type="Resale", ec_origin=False, n=2, rent=None):
    base = pd.DataFrame([{
        "project_name": "SAMPLE PROJECT",
        "ec_origin": ec_origin,
        "tenure": "99 yrs lease commencing from 2010",
        "sale_type": sale_type,
        "n": n,
        "median_price": 1_000_000,
        "median_psf": 1_161,
        "median_sqft": 861.1128,
        "size_band": ">70–100 sqm (753–1,076 sqft)",
        "q1_price": 1_000_000,
        "q3_price": 1_000_000,
        "min_sqft": 861.1128,
        "max_sqft": 861.1128,
        "active_months": 1,
        "median_psf_change_pct": float("nan"),
        "prior_n": 0,
        "prior_median_psf": float("nan"),
        "cohort_id": "sample-cohort",
    }])
    rental = empty_rent() if rent is None else rent
    path = tmp_path / "rental-source.csv"
    rental.to_csv(path, index=False)
    return enrich_cohorts(base, path)


def render_sample(*, project=None, transactions=None, cohorts=None, rental=None, developer=None, profile=None):
    return render_project(
        project_record() if project is None else project,
        pd.DataFrame() if transactions is None else transactions,
        pd.DataFrame() if cohorts is None else cohorts,
        pd.DataFrame(),
        empty_rent() if rental is None else rental,
        pd.DataFrame() if developer is None else developer,
        {} if profile is None else profile,
        {},
        slug="sample-project",
        display_name="Sample Project",
        captured_at="2026-09-20 18:00:00",
    )


def test_no_data_report_has_no_invented_price_or_default_resale_status(tmp_path):
    markdown = render_sample(project=project_record(latest_month=""))
    assert "Market stage: **unverified**" in markdown
    assert "No current entry-price recommendation is supported" in markdown
    assert "no eligible recent cohort" in markdown
    assert "no current observed price anchor" in markdown
    assert "No published subject rental observation" in markdown
    assert "Cost-only break-even |" not in markdown
    assert "S$0 psf" not in markdown
    path = tmp_path / "2026-09-20-sample-project.md"
    path.write_text(markdown)
    parsed = parse_property_analysis(path)
    page = render_property_analysis_page(parsed)
    assert 'href="assets/property-analysis.css"' in page
    assert '<h2 id="decision">Decision</h2>' in page


def test_historical_bulk_sale_is_not_presented_as_buyable_home():
    transactions = transaction_records(n=1, eligible=False).assign(
        number_of_units=100,
        exclusion_reason="Bulk disposal; excluded from individual-home metrics",
    )
    markdown = render_sample(
        project=project_record(coverage_note="Historical redevelopment predecessor; not current stock."),
        transactions=transactions,
    )
    assert "Market stage: **historical project**" in markdown
    assert "historical redevelopment predecessor" in markdown
    assert "| Total consideration |" in markdown
    assert "S$1,000,000" in markdown
    assert "not an individual apartment price" in markdown
    assert "not present a live buying opportunity" in markdown
    assert "## Purchase" not in markdown
    assert "## Rental" not in markdown
    assert "maximum entry" not in markdown.lower()


def test_thin_price_evidence_is_not_promoted_to_a_reliable_buying_band(tmp_path):
    markdown = render_sample(transactions=transaction_records(), cohorts=cohort_records(tmp_path))
    assert "not a reliable buying band" in markdown
    assert "thin evidence cell" in markdown
    assert "not a stable valuation interval" in markdown
    assert "There are 2 recent owner-sale records" in markdown
    assert "No owner comparison meets" in markdown
    assert "actual TOP" in markdown or "Actual TOP" in markdown


def test_new_sale_only_history_does_not_claim_observed_owner_exit_prices(tmp_path):
    markdown = render_sample(
        transactions=transaction_records(sale_type="New Sale"),
        cohorts=cohort_records(tmp_path, sale_type="New Sale"),
    )
    assert "There are 0 recent owner-sale records" in markdown
    assert "No subject owner exit-price evidence is demonstrated" in markdown
    assert "These records provide observed owner pricing" not in markdown


def test_masked_transaction_multiplicity_is_preserved_and_partial_month_excluded(tmp_path):
    transactions = pd.concat([
        transaction_records(),
        transaction_records(n=1, month="2026-09").assign(record_id="partial-month"),
    ], ignore_index=True)
    markdown = render_sample(transactions=transactions, cohorts=cohort_records(tmp_path))
    assert "3; repeated public row occurrences retained" in markdown
    assert "2 in Sep 2025–Aug 2026; 1 in partial Sep 2026" in markdown
    assert "| 2026-06 | 0 | 0 | 2 |" in markdown
    assert "There are 2 recent owner-sale records" in markdown
    assert "1 additional eligible records in September are excluded" in markdown


def test_old_rental_observation_does_not_become_current_yield(tmp_path):
    rent = pd.DataFrame([{
        "project_name": "SAMPLE PROJECT", "ref_quarter": "2025Q2",
        "median_psf_pm": 4.5, "psf25": 4.1, "psf75": 4.9,
    }])
    markdown = render_sample(
        transactions=transaction_records(),
        cohorts=cohort_records(tmp_path, rent=rent),
        rental=rent,
    )
    assert "The latest available subject statistic is 2025Q2" in markdown
    assert "not carried forward into a current yield" in markdown
    assert "| Unverified |" in markdown
    assert "aggregate gross-yield screen of about" not in markdown
    assert "| 2025Q2 | S$4.10 | S$4.50 | S$4.90 |" in markdown


def test_new_ec_report_keeps_eligibility_and_rental_constraints_visible(tmp_path):
    markdown = render_sample(
        project=project_record(ec_origin=True, development_status="under development"),
        transactions=transaction_records(sale_type="New Sale"),
        cohorts=cohort_records(tmp_path, sale_type="New Sale", ec_origin=True),
    )
    assert "Market stage: **new launch**" in markdown
    assert "Sample Project is EC-origin" in markdown
    assert "ten-year MOP instead of five years" in markdown
    assert "does not override MOP or whole-unit rental restrictions" in markdown
    assert "outside the applicable SSD period and any EC MOP" in markdown
    assert "second-property purchase with 20% ABSD" not in markdown


def test_short_lease_is_a_decision_constraint_not_just_an_identity_field(tmp_path):
    markdown = render_sample(
        project=project_record(tenures="60 yrs lease commencing from 2013"),
        transactions=transaction_records(),
        cohorts=cohort_records(tmp_path),
    )
    decision_text = markdown.split("## Decision", 1)[1].split("## Project identity", 1)[0]
    assert "60-year tenure is a defining constraint" in decision_text
    assert "shorter remaining lease" in decision_text
    assert "future buyer pool" in decision_text


def test_unpublished_developer_price_does_not_render_as_zero_psf():
    developer = pd.DataFrame([{
        "ref_month": "2026-08", "sold_to_date": 90, "units_avail": 100,
        "unsold_total": 10, "launched_unsold": 5, "unlaunched_units": 5,
        "sold_in_month": 0, "launched_to_date": 95, "median_psf": 0,
    }])
    markdown = render_sample(developer=developer)
    assert "| 2026-08 | 0 | 90 | 95 | 10 | Not published |" in markdown
    assert "S$0 psf" not in markdown
    assert "5 had been launched and 5 had not" in markdown


@pytest.mark.parametrize(
    ("project", "profile", "recent", "expected"),
    [
        (project_record(), {}, pd.DataFrame(), "unverified"),
        (project_record(coverage_note="Historical redevelopment predecessor"), {}, transaction_records(), "historical project"),
        (project_record(), {"status": {"value": "preview open; sale bookings have not started"}}, pd.DataFrame(), "future project"),
        (project_record(), {"status": {"value": "under construction"}}, pd.DataFrame(), "new launch"),
        (project_record(), {}, transaction_records(sale_type="New Sale"), "new launch"),
        (project_record(), {}, transaction_records(sale_type="Resale"), "resale"),
        (project_record(), {"status": {"value": "completed"}}, pd.DataFrame(), "resale"),
        (
            project_record(ec_origin=True),
            {"status": {"value": "completed"}, "actual_top": {"verified": True, "value": "2024-06-03"}},
            transaction_records(sale_type="Resale", n=1),
            "restricted ec",
        ),
        (
            project_record(ec_origin=True),
            {"status": {"value": "completed"}, "actual_top": {"verified": True, "value": "2020-05-04; 2022-05-02"}},
            transaction_records(sale_type="Resale", n=1),
            "restricted ec",
        ),
        (
            project_record(ec_origin=True),
            {"status": {"value": "completed"}, "actual_top": {"verified": True, "value": "2020-02-29"}},
            pd.DataFrame(),
            "resale",
        ),
    ],
)
def test_market_stage_preserves_project_evidence_and_history(project, profile, recent, expected):
    assert market_stage(project, profile, pd.DataFrame(), recent) == expected
