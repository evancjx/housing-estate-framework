#!/usr/bin/env python3
"""Add transparent cost scenarios and official rental context to research cohorts.

This is research arithmetic, not a valuation or an estate Value model. The
synthetic scenario combines the cohort's median price and median area; those
medians need not describe the same sale. Rental yields use the separately
observed median sale PSF, not that synthetic unit's price/area ratio.

The current-rate purchase illustration assumes the purchase price equals the
dutiable market value. An actual purchase uses the higher value. All exits are
conditional on being legally permitted and outside the applicable SSD period
and any EC minimum occupation period. No holding date is inferred from a
month-only transaction record.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RENTAL_CSV = ROOT / "data/raw/ura/rental/pmi_api_rental_median_2q26.csv"
SOURCE_VERIFIED_ON = "2026-09-20"
BSD_SOURCE = (
    "https://www.iras.gov.sg/taxes/stamp-duty/for-property/buying-or-acquiring-property/"
    "buyer%27s-stamp-duty-%28bsd%29"
)
ABSD_SOURCE = (
    "https://www.iras.gov.sg/taxes/stamp-duty/for-property/buying-or-acquiring-property/"
    "additional-buyer%27s-stamp-duty-%28absd%29"
)
SSD_SOURCE = (
    "https://www.iras.gov.sg/taxes/stamp-duty/for-property/selling-or-disposing-property/"
    "seller%27s-stamp-duty-%28ssd%29-for-residential-property"
)
RENTAL_SOURCE = "https://eservice.ura.gov.sg/maps/api/"
COHORT_COLUMNS = {
    "project_name", "ec_origin", "tenure", "sale_type", "n",
    "median_price", "median_psf", "median_sqft",
}
RENTAL_COLUMNS = {"project_name", "ref_quarter", "median_psf_pm", "psf25", "psf75"}
QUARTER_RE = re.compile(r"^(\d{4})Q([1-4])$")


def _decimal(value: object, name: str, *, allow_zero: bool = False) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not number.is_finite() or number < 0 or (number == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be a finite {qualifier} number")
    return number


def bsd_residential(dutiable_value: float) -> int:
    """Residential BSD at rates effective 15 February 2023, floored to S$1.

    The argument is the higher of purchase price and market value. This helper
    deliberately does not apply the current schedule to historical purchases.
    """
    remaining = _decimal(dutiable_value, "dutiable_value")
    duty = Decimal(0)
    for width, rate in (
        (180_000, "0.01"), (180_000, "0.02"), (640_000, "0.03"),
        (500_000, "0.04"), (1_500_000, "0.05"),
    ):
        chargeable = min(remaining, Decimal(width))
        duty += chargeable * Decimal(rate)
        remaining -= chargeable
    duty += remaining * Decimal("0.06")
    return max(1, int(duty.to_integral_value(rounding=ROUND_FLOOR)))


def capital_only_scenarios(
    entry_price: float,
    area_sqft: float,
    *,
    legal_allowance: float = 5_000,
    selling_rate: float = 0.025,
) -> dict:
    """Return SSD-free hypothetical exits before finance, holding costs and rent.

    Percentage price changes are total exit-price changes, not annual growth.
    S$500,000 is an illustrative capital-only profit hurdle, not an objective
    attributed to the buyer. The extra ABSD result is a tax-only SC second-home
    sensitivity with no remission; it is not a purchase-eligibility decision.
    """
    entry = _decimal(entry_price, "entry_price")
    area = _decimal(area_sqft, "area_sqft")
    legal = _decimal(legal_allowance, "legal_allowance", allow_zero=True)
    selling = _decimal(selling_rate, "selling_rate", allow_zero=True)
    if selling >= 1:
        raise ValueError("selling_rate must be less than 1")
    bsd = Decimal(bsd_residential(float(entry)))
    acquisition = entry + bsd + legal
    retain = Decimal(1) - selling
    break_even = acquisition / retain
    target = (acquisition + Decimal(500_000)) / retain
    absd = max(1, int((entry * Decimal("0.20")).to_integral_value(rounding=ROUND_FLOOR)))
    second_break_even = (acquisition + Decimal(absd)) / retain
    return {
        "scenario_entry_price": float(entry),
        "scenario_area_sqft": float(area),
        "scenario_entry_psf": float(entry / area),
        "scenario_bsd": int(bsd),
        "scenario_legal_allowance": float(legal),
        "scenario_selling_rate": float(selling),
        "scenario_acquisition_cost": float(acquisition),
        "break_even_sale": float(break_even),
        "break_even_psf": float(break_even / area),
        "break_even_uplift_pct": float((break_even / entry - 1) * 100),
        "target_500k_sale": float(target),
        "target_500k_psf": float(target / area),
        "profit_down_10": float(entry * Decimal("0.90") * retain - acquisition),
        "profit_flat": float(entry * retain - acquisition),
        "profit_up_10": float(entry * Decimal("1.10") * retain - acquisition),
        "sc_second_property_absd": absd,
        "sc_second_property_break_even_sale": float(second_break_even),
        "sc_second_property_break_even_psf": float(second_break_even / area),
    }


def normalise_project_name(value: object) -> str:
    """Match case/whitespace only, without speculative aliases or fuzzy joins."""
    if pd.isna(value):
        return ""
    return " ".join(unicodedata.normalize("NFKC", str(value)).upper().split())


def _require_columns(frame: pd.DataFrame, required: set[str], label: str) -> None:
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{label} missing columns: {', '.join(sorted(missing))}")
    if frame.columns.duplicated().any():
        raise ValueError(f"{label} contains duplicate column names")


def _quarter_parts(quarter: str) -> tuple[int, int]:
    match = QUARTER_RE.fullmatch(quarter)
    if not match:
        raise ValueError(f"Invalid rental quarter: {quarter!r}; expected YYYYQ1–YYYYQ4")
    return int(match[1]), int(match[2])


def _numeric_column(frame: pd.DataFrame, column: str, *, missing_ok: bool = False) -> pd.Series:
    values = pd.to_numeric(frame[column], errors="raise")
    invalid = (~np.isfinite(values) | (values <= 0)) & ~(values.isna() & missing_ok)
    if invalid.any():
        raise ValueError(f"{column} must contain finite positive values")
    return values


def rental_lens(
    cohorts: pd.DataFrame,
    rental_records: pd.DataFrame,
    *,
    quarter: str = "2026Q2",
) -> pd.DataFrame:
    """Add same-project quarterly rent context without mutating either input.

    A missing requested quarter stays missing even if older observations exist.
    Yield percentages are 1,200 * monthly project rent PSF / cohort median sale
    PSF. They are ratios of separate aggregates, not matched-unit rental yields.
    """
    _require_columns(cohorts, {"project_name", "median_psf"}, "Cohorts")
    _require_columns(rental_records, RENTAL_COLUMNS, "Rental records")
    year, quarter_number = _quarter_parts(quarter)
    prior_quarter = f"{year - 1}Q{quarter_number}"
    result = cohorts.copy(deep=True)
    sale_psf = _numeric_column(cohorts, "median_psf")
    keys = result["project_name"].map(normalise_project_name)
    if keys.eq("").any():
        raise ValueError("Cohorts contain a missing project name")
    rent = rental_records.copy(deep=True)
    rent["_project_key"] = rent["project_name"].map(normalise_project_name)
    rent = rent.loc[rent["_project_key"].isin(keys)].copy()
    for value in rent["ref_quarter"]:
        _quarter_parts(str(value))
    used_quarters = rent.loc[rent["ref_quarter"].isin([quarter, prior_quarter])]
    if used_quarters.duplicated(["_project_key", "ref_quarter"]).any():
        raise ValueError("Ambiguous rental rows: repeated normalized project and quarter")
    for column in ("median_psf_pm", "psf25", "psf75"):
        rent[column] = _numeric_column(rent, column, missing_ok=True)
    if ((rent["psf25"] > rent["median_psf_pm"]) | (rent["median_psf_pm"] > rent["psf75"])).any():
        raise ValueError("Rental quartiles must bracket the median")

    current = rent.loc[rent["ref_quarter"].eq(quarter)].set_index("_project_key")
    previous = rent.loc[rent["ref_quarter"].eq(prior_quarter)].set_index("_project_key")
    historical = rent.loc[rent["ref_quarter"].le(quarter)]
    latest = historical.groupby("_project_key")["ref_quarter"].max()

    result["rent_requested_quarter"] = quarter
    result["rent_prior_year_quarter"] = prior_quarter
    result["rent_latest_available_quarter"] = keys.map(latest)
    for field, source in (("median_psf_pm", "median_psf_pm"), ("p25_psf_pm", "psf25"), ("p75_psf_pm", "psf75")):
        result[f"rent_current_{field}"] = keys.map(current[source])
    result["rent_prior_year_median_psf_pm"] = keys.map(previous["median_psf_pm"])
    result["rent_current_source_project_name"] = keys.map(current["project_name"])
    result["rent_match_status"] = np.where(
        result["rent_current_median_psf_pm"].notna(),
        "current_quarter_project_aggregate",
        np.where(keys.isin(current.index), "current_quarter_median_missing", "requested_quarter_missing"),
    )
    result["rent_median_yoy_change_pct"] = (
        result["rent_current_median_psf_pm"] / result["rent_prior_year_median_psf_pm"] - 1
    ) * 100
    for label, source in (("p25", "p25_psf_pm"), ("median", "median_psf_pm"), ("p75", "p75_psf_pm")):
        result[f"gross_yield_{label}_pct"] = result[f"rent_current_{source}"] * 1200 / sale_psf
    return result


def _ec_flag(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if str(value).strip().lower() in {"1", "true"}:
        return True
    if str(value).strip().lower() in {"0", "false"}:
        return False
    raise ValueError(f"ec_origin must be a boolean, got {value!r}")


def economics_provenance(rental_csv: Path, *, quarter: str) -> dict:
    """Return a serializable source and assumption register for exported results."""
    return {
        "source_verified_on": SOURCE_VERIFIED_ON,
        "rental_csv": str(rental_csv.resolve().relative_to(ROOT)) if rental_csv.resolve().is_relative_to(ROOT) else str(rental_csv),
        "rental_sha256": hashlib.sha256(rental_csv.read_bytes()).hexdigest(),
        "rental_service": "PMI_Resi_Rental_Median",
        "rental_source_url": RENTAL_SOURCE,
        "rental_quarter": quarter,
        "bsd_source_url": BSD_SOURCE,
        "absd_source_url": ABSD_SOURCE,
        "ssd_source_url": SSD_SOURCE,
        "bsd_effective_from": "2023-02-15",
        "buyer_scenario": "Singapore citizen first residential property; no ABSD",
        "entry_basis": "Synthetic cohort anchor: independent median price and median sqft; not an actual unit or live ask",
        "tax_base_assumption": "Illustrative entry price equals market value; actual duty uses the higher of price and market value",
        "legal_allowance_sgd": 5000,
        "selling_allowance_fraction": 0.025,
        "ssd_and_eligibility": "Exit only after the applicable SSD period and any EC MOP; no calendar exit date or eligibility certification",
        "excluded": ["financing", "CPF obligations", "maintenance", "property tax", "renovation", "rental income", "vacancy", "other holding expenses"],
        "exit_changes": "-10%, 0%, +10% total price changes; no time horizon or annual growth forecast",
        "second_property_sensitivity": "20% ABSD, SC second residential property, no remission; omitted for EC-origin New Sale cohorts; tax arithmetic does not establish eligibility",
        "rental_match": "NFKC Unicode normalization, uppercase and whitespace; exact normalized project name; no fuzzy aliases or older-quarter fallback",
        "rental_yield": "12 * monthly project rental PSF / cohort median sale PSF; percentage output; separate aggregate lens, not matched-unit rent or net yield",
        "missing_evidence": "Missing quarterly rental evidence remains missing, never zero or silently stale",
    }


def enrich_cohorts(
    cohorts: pd.DataFrame,
    rental_csv: Path | str = DEFAULT_RENTAL_CSV,
    *,
    quarter: str = "2026Q2",
) -> pd.DataFrame:
    """Preserve cohort rows and segment keys; add scenarios, rents and provenance."""
    _require_columns(cohorts, COHORT_COLUMNS, "Cohorts")
    for column in ("n", "median_price", "median_psf", "median_sqft"):
        values = _numeric_column(cohorts, column)
        if column == "n" and values.mod(1).ne(0).any():
            raise ValueError("n must contain positive integer sample counts")
    ec_flags = cohorts["ec_origin"].map(_ec_flag)
    rental_path = Path(rental_csv)
    if not rental_path.is_file():
        raise FileNotFoundError(f"Rental source not found: {rental_path}")
    result = rental_lens(cohorts, pd.read_csv(rental_path), quarter=quarter)
    scenario_columns = list(capital_only_scenarios(1_000_000, 1_000))
    scenarios = pd.DataFrame(
        [capital_only_scenarios(row.median_price, row.median_sqft) for row in cohorts.itertuples()],
        index=cohorts.index,
        columns=scenario_columns,
    )
    for column in scenario_columns:
        result[column] = scenarios[column]
    result["scenario_anchor_basis"] = "synthetic_independent_cohort_medians_not_actual_unit"
    result["scenario_exit_condition"] = "after_applicable_ssd_and_ec_mop_if_any"
    excluded_second_property = ec_flags & cohorts["sale_type"].eq("New Sale")
    second_columns = [column for column in scenario_columns if column.startswith("sc_second_property_")]
    result.loc[excluded_second_property, second_columns] = np.nan
    result["sc_second_property_sensitivity_status"] = np.where(
        excluded_second_property,
        "omitted_ec_developer_purchase_requires_separate_eligibility_review",
        "tax_only_no_remission_does_not_establish_eligibility",
    )
    result.attrs["economics_provenance"] = economics_provenance(rental_path, quarter=quarter)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohorts", required=True, type=Path)
    parser.add_argument("--rental-csv", type=Path, default=DEFAULT_RENTAL_CSV)
    parser.add_argument("--quarter", default="2026Q2")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = enrich_cohorts(pd.read_csv(args.cohorts), args.rental_csv, quarter=args.quarter)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    provenance = result.attrs["economics_provenance"] | {
        "cohorts_csv": str(args.cohorts),
        "cohorts_sha256": hashlib.sha256(args.cohorts.read_bytes()).hexdigest(),
        "output_rows": len(result),
        "rental_matched_rows": int(result["rent_current_median_psf_pm"].notna().sum()),
    }
    args.output.with_suffix(".provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(result):,} cohort illustrations to {args.output}")


if __name__ == "__main__":
    main()
