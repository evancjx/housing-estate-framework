#!/usr/bin/env python3
"""
Generate a Canberra Crescent Residences versus District 27 deep analysis.

This is a private-project diagnostic on the Liveability/Value side of the
framework. It does not create a unified condo ranking or feed project facts
into estate-level Provision scores.

Reads:
  data/raw/ura/pmi_d27_2021-2026.csv
      Official URA PMI apartment/condominium rows. Raw multiplicity is
      intentionally retained because distinct launch units can share the same
      month, price, area and floor band.
  data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv
      Secondary bedroom labels matched conservatively to official rows.
  data/outputs/private_project_locations.csv
      project_name,lat,lon
  data/outputs/private_project_school_metrics.csv
      project_name,primary_1km_count,primary_1km_schools
  data/inputs/mrt_layer.csv
      name,stn_code,line,lat,lon,operational

Writes:
  canberra_crescent_d27_deep_analysis.html

Method:
  - Apartment and condominium transactions only; Executive Condominiums and
    landed homes are outside this project comparison universe.
  - Headline comparison uses the latest 18 complete months.
  - A current partial month is disclosed and retained in the transaction
    ledger but excluded from headline medians.
  - New Sale, Sub Sale and Resale states remain visible and are never presented
    as one appreciation series.
  - Every transaction is benchmarked against its District 27 calendar-year,
    sale-state and bedroom cohort. Cohorts with one project are explicitly
    labelled launch-position evidence rather than a market comparison.
  - Exact apartment numbers are unavailable in URA PMI; no repeat-sale
    identity or apartment-level growth is claimed.
"""

from __future__ import annotations

import argparse
import html
import math
import pathlib
import re
from datetime import date
from typing import Any

import pandas as pd

from build_private_bedrooms import (
    SQM_TO_SQFT,
    band_of,
    build_name_mapping,
    load_edgeprop,
    normalise_project_name,
    tier1_exact,
    tier2_band_labels,
)

ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_RAW = ROOT / "data/raw/ura/pmi_d27_2021-2026.csv"
DEFAULT_EDGEPROP = (
    ROOT
    / "data/raw/edgeprop/"
    "edgeprop_condo_apartment_transactions_playwright_not_clean.csv"
)
DEFAULT_LOCATIONS = ROOT / "data/outputs/private_project_locations.csv"
DEFAULT_SCHOOLS = ROOT / "data/outputs/private_project_school_metrics.csv"
DEFAULT_MRT = ROOT / "data/inputs/mrt_layer.csv"
DEFAULT_OUT = ROOT / "canberra_crescent_d27_deep_analysis.html"

SUBJECT = "CANBERRA CRESCENT RESIDENCES"
SUBJECT_UNITS = 376
# Reviewed against the LTA MRT-station-exit dataset and OneMap on 2026-08-03.
# The legacy geocoded input places NS12 beside the subject instead of at
# 11 Canberra Link, reversing the closest-project comparison. Keep this
# correction local to the Canberra private-project diagnostics so an
# estate-level input refresh remains a separately reviewed pipeline change.
MRT_COORDINATE_OVERRIDES = {"NS12": (1.4432, 103.8296)}
MIN_DELTA_SAMPLE = 3
TAB_KEYS = ("all", "1", "2", "3", "4")
TAB_LABELS = {
    "all": "All unit types",
    "1": "1 bedroom",
    "2": "2 bedrooms",
    "3": "3 bedrooms",
    "4": "4 bedrooms",
}
PRIMARY_PROJECTS = (
    SUBJECT,
    "THE WATERGARDENS AT CANBERRA",
    "THE COMMODORE",
    "CANBERRA RESIDENCES",
    "NORTH PARK RESIDENCES",
    "THE WISTERIA",
    "NINE RESIDENCES",
)
PROJECT_ROLES = {
    SUBJECT: "Subject · New Sale",
    "THE WATERGARDENS AT CANBERRA": "Closest completed precinct control",
    "THE COMMODORE": "Closest newer precinct control",
    "CANBERRA RESIDENCES": "Older same-precinct resale control",
    "NORTH PARK RESIDENCES": "Integrated town-centre control",
    "THE WISTERIA": "Mixed-use Yishun control",
    "NINE RESIDENCES": "Mixed-use Yishun control",
}
RAW_COLUMNS = {
    "Project Name",
    "Transacted Price ($)",
    "Sale Date",
    "Street Name",
    "Type of Sale",
    "Area (SQM)",
    "Property Type",
    "Tenure",
    "Postal District",
    "Floor Level",
}


def normalise_district(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value))
    return digits.zfill(2) if digits else ""


def clean_text(value: Any, default: str = "—") -> str:
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none"} else default


def _parse_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace(",", "", regex=False).str.replace("-", "", regex=False),
        errors="coerce",
    )


def load_district_transactions(
    raw_path: pathlib.Path,
    edgeprop_path: pathlib.Path,
) -> pd.DataFrame:
    raw = pd.read_csv(raw_path, low_memory=False)
    missing = sorted(RAW_COLUMNS - set(raw.columns))
    if missing:
        raise SystemExit(f"{raw_path} missing required columns: {missing}")

    txns = pd.DataFrame(
        {
            "project_name": raw["Project Name"].astype(str).str.strip().str.upper(),
            "street_name": raw["Street Name"],
            "postal_district": raw["Postal District"].map(normalise_district),
            "property_type": raw["Property Type"],
            "tenure": raw["Tenure"],
            "sale_period": pd.to_datetime(
                raw["Sale Date"],
                format="%b-%y",
                errors="coerce",
            ).dt.to_period("M"),
            "type_of_sale": raw["Type of Sale"].astype(str).str.strip(),
            "price": _parse_number(raw["Transacted Price ($)"]),
            "area_sqm": _parse_number(raw["Area (SQM)"]),
            "floor_level": raw["Floor Level"],
        }
    )
    txns = txns[
        txns["property_type"].astype(str).str.strip().isin({"Apartment", "Condominium"})
    ].copy()
    txns = txns.dropna(subset=["sale_period", "price", "area_sqm"])
    txns = txns[
        txns["postal_district"].eq("27")
        & txns["project_name"].ne("")
        & txns["price"].gt(0)
        & txns["area_sqm"].gt(0)
    ].copy()
    txns["price"] = txns["price"].round().astype("Int64")
    txns["sale_month"] = txns["sale_period"].astype(str)
    txns["sqft"] = txns["area_sqm"] * SQM_TO_SQFT
    txns["psf"] = txns["price"] / txns["sqft"]
    txns["district"] = "27"
    txns["name_norm"] = txns["project_name"].map(normalise_project_name)
    txns["price_int"] = txns["price"]

    edgeprop = load_edgeprop(edgeprop_path)
    edgeprop = edgeprop[edgeprop["district"].eq("27")].copy()
    mapping = build_name_mapping(txns, edgeprop)
    txns["match_name"] = [
        mapping.get((name, district))
        for name, district in zip(txns["name_norm"], txns["district"])
    ]
    txns["bedrooms"] = pd.array([pd.NA] * len(txns), dtype="Float64")
    txns["bedroom_source"] = "unknown"
    n_input = len(txns)

    def apply_matches(matched: pd.Series, source: str) -> None:
        if matched.empty:
            return
        txns.loc[matched.index, "bedrooms"] = matched.astype("Float64")
        txns.loc[matched.index, "bedroom_source"] = source

    pool = edgeprop[edgeprop["bedrooms"].notna()]
    apply_matches(tier1_exact(txns, pool, month_shift=0), "edgeprop_exact")
    for shift in (-1, 1):
        apply_matches(tier1_exact(txns, pool, month_shift=shift), "edgeprop_exact")

    labels = tier2_band_labels(edgeprop)
    unmatched = txns["bedrooms"].isna() & txns["match_name"].notna()
    keys = list(
        zip(
            txns.loc[unmatched, "match_name"],
            txns.loc[unmatched, "district"],
            txns.loc[unmatched, "area_sqm"].map(band_of),
        )
    )
    band_values = pd.Series(
        [labels.get(key) for key in keys],
        index=txns.index[unmatched],
        dtype="Float64",
    ).dropna()
    apply_matches(band_values, "edgeprop_band_label")
    assert len(txns) == n_input, "official rows fanned out during bedroom matching"

    txns["bedrooms"] = txns["bedrooms"].round().astype("Int64")
    txns["unit_key"] = txns["bedrooms"].map(
        lambda value: str(int(value)) if pd.notna(value) else "unknown"
    )
    txns["year"] = txns["sale_period"].dt.year.astype(int)
    txns["size_band_low"] = (txns["sqft"] // 100 * 100).astype(int)
    txns["floor_mid"] = txns["floor_level"].map(floor_midpoint)
    return txns.reset_index(drop=True)


def floor_midpoint(value: Any) -> float | None:
    match = re.match(r"^\s*(\d{2})\s+to\s+(\d{2})\s*$", str(value), re.I)
    if not match:
        return None
    return (int(match.group(1)) + int(match.group(2))) / 2.0


def comparison_window(
    txns: pd.DataFrame,
    as_of: date,
) -> dict[str, pd.Period | None]:
    latest = txns["sale_period"].max()
    current = pd.Period(as_of.strftime("%Y-%m"), freq="M")
    full_end = current - 1 if latest >= current else latest
    return {
        "current_start": full_end - 17,
        "full_end": full_end,
        "partial": latest if latest > full_end else None,
    }


def add_transaction_diagnostics(txns: pd.DataFrame) -> pd.DataFrame:
    out = txns.copy()
    cohort_cols = ["year", "type_of_sale", "unit_key"]
    cohort = out.groupby(cohort_cols, dropna=False)["psf"]
    out["cohort_n"] = cohort.transform("size").astype(int)
    out["cohort_median_psf"] = cohort.transform("median")
    out["cohort_percentile"] = cohort.rank(method="average", pct=True) * 100.0
    out["cohort_project_n"] = (
        out.groupby(cohort_cols, dropna=False)["project_name"]
        .transform("nunique")
        .astype(int)
    )
    out["cohort_delta_pct"] = (
        out["psf"] / out["cohort_median_psf"] - 1.0
    ) * 100.0

    project_cols = ["project_name", "year", "unit_key"]
    project = out.groupby(project_cols, dropna=False)["psf"]
    out["project_cohort_n"] = project.transform("size").astype(int)
    out["project_median_psf"] = project.transform("median")
    out["project_delta_pct"] = (
        out["psf"] / out["project_median_psf"] - 1.0
    ) * 100.0

    size_cols = ["year", "type_of_sale", "size_band_low"]
    size_cohort = out.groupby(size_cols, dropna=False)["psf"]
    out["size_cohort_n"] = size_cohort.transform("size").astype(int)
    out["size_cohort_median_psf"] = size_cohort.transform("median")
    out["size_delta_pct"] = (
        out["psf"] / out["size_cohort_median_psf"] - 1.0
    ) * 100.0
    out["position"] = out["cohort_percentile"].map(percentile_position)
    out["analysis"] = out.apply(transaction_analysis, axis=1)
    return out


def percentile_position(value: float) -> str:
    if value >= 90:
        return "Upper decile"
    if value >= 75:
        return "Upper quartile"
    if value <= 10:
        return "Lower decile"
    if value <= 25:
        return "Lower quartile"
    return "Middle range"


def transaction_analysis(row: pd.Series) -> str:
    unit = unit_label(row["unit_key"], short=True)
    scope = f"{row['year']} {row['type_of_sale']} {unit}"
    if row["cohort_project_n"] == 1:
        breadth = "single-project cohort; launch-position signal only"
    else:
        breadth = f"{row['cohort_project_n']} projects in cohort"
    text = (
        f"{row['position']} of {scope}; {row['cohort_delta_pct']:+.1f}% versus "
        f"cohort median (n={row['cohort_n']}, {breadth}). "
        f"{row['project_delta_pct']:+.1f}% versus its project-year {unit} median."
    )
    if row["size_cohort_n"] >= MIN_DELTA_SAMPLE:
        low = row["size_band_low"]
        text += (
            f" {row['size_delta_pct']:+.1f}% versus the {low:,}–{low + 99:,} sqft "
            f"{row['type_of_sale'].lower()} size cohort (n={row['size_cohort_n']})."
        )
    if abs(row["cohort_delta_pct"]) >= 15:
        text += " Large deviation: check floor, view, layout and transaction particulars."
    if row["bedroom_source"] == "unknown":
        text += " Bedroom is unavailable, so bedroom-cohort precision is limited."
    return text


def load_lookup(path: pathlib.Path) -> dict[str, dict[str, Any]]:
    frame = pd.read_csv(path)
    frame["project"] = frame["project_name"].map(
        lambda value: re.sub(r"\s+", " ", str(value).strip()).upper()
    )
    return frame.drop_duplicates("project").set_index("project").to_dict("index")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def nearest_station(
    project: str,
    locations: dict[str, dict[str, Any]],
    mrt: pd.DataFrame,
) -> dict[str, Any]:
    location = locations.get(project)
    if not location:
        return {"station": "—", "station_distance_m": None}
    stations = mrt.copy()
    codes = stations.get(
        "stn_code", pd.Series("", index=stations.index)
    ).astype(str).str.strip().str.upper()
    for code, (reviewed_lat, reviewed_lon) in MRT_COORDINATE_OVERRIDES.items():
        mask = codes.eq(code)
        stations.loc[mask, ["lat", "lon"]] = (reviewed_lat, reviewed_lon)
    stations["lat"] = pd.to_numeric(stations["lat"], errors="coerce")
    stations["lon"] = pd.to_numeric(stations["lon"], errors="coerce")
    stations["operational"] = pd.to_numeric(
        stations["operational"],
        errors="coerce",
    ).fillna(1)
    stations = stations[
        stations["lat"].notna()
        & stations["lon"].notna()
        & stations["operational"].eq(1)
    ].copy()
    lat = float(location["lat"])
    lon = float(location["lon"])
    stations["distance_m"] = stations.apply(
        lambda row: haversine_m(lat, lon, float(row["lat"]), float(row["lon"])),
        axis=1,
    )
    row = stations.nsmallest(1, "distance_m").iloc[0]
    code = clean_text(row.get("stn_code"), "")
    name = clean_text(row.get("name"))
    return {
        "station": f"{name} ({code})" if code else name,
        "station_distance_m": int(round(float(row["distance_m"]))),
    }


def sale_state(group: pd.DataFrame) -> str:
    counts = group["type_of_sale"].value_counts()
    return " / ".join(f"{name} {count}" for name, count in counts.items())


def describe(group: pd.DataFrame) -> dict[str, Any]:
    if group.empty:
        return {
            "n": 0,
            "median_price": None,
            "price_p10": None,
            "price_p90": None,
            "median_psf": None,
            "psf_p10": None,
            "psf_p90": None,
            "median_sqft": None,
        }
    return {
        "n": int(len(group)),
        "median_price": float(group["price"].median()),
        "price_p10": float(group["price"].quantile(0.10)),
        "price_p90": float(group["price"].quantile(0.90)),
        "median_psf": float(group["psf"].median()),
        "psf_p10": float(group["psf"].quantile(0.10)),
        "psf_p90": float(group["psf"].quantile(0.90)),
        "median_sqft": float(group["sqft"].median()),
    }


def pct_delta(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or base <= 0:
        return None
    return (value / base - 1.0) * 100.0


def build_project_rows(
    txns: pd.DataFrame,
    window: dict[str, pd.Period | None],
    locations: dict[str, dict[str, Any]],
    schools: dict[str, dict[str, Any]],
    mrt: pd.DataFrame,
) -> list[dict[str, Any]]:
    complete = txns[txns["sale_period"].le(window["full_end"])]
    current = complete[
        complete["sale_period"].between(window["current_start"], window["full_end"])
    ]
    rows = []
    for project, history in complete.groupby("project_name", sort=False):
        recent = current[current["project_name"].eq(project)]
        evidence = recent if not recent.empty else history
        school = schools.get(project, {})
        primary_count = pd.to_numeric(
            pd.Series([school.get("primary_1km_count")]),
            errors="coerce",
        ).iloc[0]
        role = PROJECT_ROLES.get(project, "District context")
        station = nearest_station(project, locations, mrt)
        rows.append(
            {
                "project": project,
                "role": role,
                "history_n": int(len(history)),
                "recent_n": int(len(recent)),
                "evidence_state": sale_state(evidence),
                "tenure": clean_text(history["tenure"].mode().iloc[0]),
                "first_month": str(history["sale_period"].min()),
                "last_month": str(history["sale_period"].max()),
                "stats": describe(evidence),
                "primary_1km_count": int(primary_count) if pd.notna(primary_count) else None,
                **station,
            }
        )
    priority = {project: index for index, project in enumerate(PRIMARY_PROJECTS)}
    return sorted(
        rows,
        key=lambda row: (
            priority.get(row["project"], len(priority)),
            -row["recent_n"],
            row["project"],
        ),
    )


def build_matched_rows(
    txns: pd.DataFrame,
    window: dict[str, pd.Period | None],
    project_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    complete = txns[
        txns["sale_period"].between(window["current_start"], window["full_end"])
        & txns["project_name"].isin(PRIMARY_PROJECTS)
    ]
    spatial = {row["project"]: row for row in project_rows}
    rows = []
    for project in PRIMARY_PROJECTS:
        group = complete[complete["project_name"].eq(project)]
        if group.empty:
            continue
        stats = {"all": describe(group)}
        for key in TAB_KEYS[1:]:
            stats[key] = describe(group[group["unit_key"].eq(key)])
        rows.append(
            {
                "project": project,
                "role": PROJECT_ROLES[project],
                "sale_state": sale_state(group),
                "stats": stats,
                "station": spatial[project]["station"],
                "station_distance_m": spatial[project]["station_distance_m"],
            }
        )
    subject = next(row for row in rows if row["project"] == SUBJECT)
    for row in rows:
        for key in TAB_KEYS:
            stat = row["stats"][key]
            base = subject["stats"][key]
            stat["subject_psf_delta_pct"] = (
                pct_delta(stat["median_psf"], base["median_psf"])
                if stat["n"] >= MIN_DELTA_SAMPLE and base["n"] >= MIN_DELTA_SAMPLE
                else None
            )
            stat["subject_price_delta_pct"] = (
                pct_delta(stat["median_price"], base["median_price"])
                if stat["n"] >= MIN_DELTA_SAMPLE and base["n"] >= MIN_DELTA_SAMPLE
                else None
            )
    return rows


def build_subject(
    txns: pd.DataFrame,
    window: dict[str, pd.Period | None],
) -> dict[str, Any]:
    group = txns[txns["project_name"].eq(SUBJECT)].copy()
    complete = group[group["sale_period"].le(window["full_end"])]
    partial = group[group["sale_period"].gt(window["full_end"])]
    stats = {"all": describe(complete)}
    for key in ("1", "2", "3", "4", "unknown"):
        stats[key] = describe(complete[complete["unit_key"].eq(key)])

    months = []
    for period, month in group.groupby("sale_period"):
        month_stats = describe(month)
        months.append(
            {
                "month": str(period),
                "partial": bool(period > window["full_end"]),
                "stats": month_stats,
                "sale_state": sale_state(month),
            }
        )

    floor_rows = []
    floor_order = ["01 to 05", "06 to 10", "11 to 15"]
    for floor in floor_order:
        floor_group = complete[
            complete["floor_level"].astype(str).str.strip().eq(floor)
        ]
        cells = {"all": describe(floor_group)}
        for key in TAB_KEYS[1:]:
            cells[key] = describe(floor_group[floor_group["unit_key"].eq(key)])
        floor_rows.append({"floor": floor, "cells": cells})

    return {
        "complete_n": int(len(complete)),
        "partial_n": int(len(partial)),
        "all_n": int(len(group)),
        "stats": stats,
        "months": months,
        "floor_rows": floor_rows,
        "caveat_stock_pct": len(group) / SUBJECT_UNITS * 100.0,
        "bedroom_known_pct": group["bedrooms"].notna().mean() * 100.0,
    }


def unit_label(key: str, short: bool = False) -> str:
    if key == "all":
        return "All units" if short else "All unit types"
    if key == "unknown":
        return "BR unknown" if short else "Bedroom unknown"
    return f"{key}BR" if short else f"{key} bedroom{'s' if key != '1' else ''}"


def slugify(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _money(value: float | None) -> str:
    if value is None:
        return "—"
    if value >= 1_000_000:
        return f"S${value / 1_000_000:.3g}m"
    return f"S${value / 1_000:.0f}k"


def _num(
    value: float | None,
    prefix: str = "",
    suffix: str = "",
    digits: int = 0,
) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{prefix}{value:,.{digits}f}{suffix}"


def _delta(value: float | None) -> str:
    if value is None:
        return "<span class='na'>insufficient</span>"
    css = "premium" if value > 0.5 else "discount" if value < -0.5 else "flat"
    return f"<span class='delta {css}'>{value:+.1f}%</span>"


def _range(low: float | None, high: float | None, formatter) -> str:
    if low is None or high is None:
        return "—"
    return f"{formatter(low)}–{formatter(high)}"


def _strategy_cards() -> str:
    strategies = [
        (
            "01",
            "Micro-location first",
            "Anchor on The Watergardens and The Commodore. They test recent 99-year "
            "Canberra precinct pricing with the least location drift.",
            "canberra_strategy_1_micro_location.html",
        ),
        (
            "02",
            "Control for newness",
            "Use Canberra Residences as the older same-precinct control. Its lower PSF "
            "can come with larger layouts and a shorter remaining lease.",
            "canberra_strategy_2_newness.html",
        ),
        (
            "03",
            "Price integration separately",
            "North Park, The Wisteria and Nine Residences test the value of direct "
            "retail and transport integration, not just distance to rail.",
            "canberra_strategy_3_integration.html",
        ),
        (
            "04",
            "Match bedroom and size",
            "Compare bedroom type, floor area and floor band together. PSF alone can "
            "make compact launch units look more expensive without showing quantum.",
            "canberra_strategy_4_unit_matching.html",
        ),
        (
            "05",
            "Keep sale states apart",
            "Canberra Crescent is New Sale evidence. Sub Sale and Resale controls "
            "include different completion, condition, financing and seller effects.",
            "canberra_strategy_5_sale_state.html",
        ),
        (
            "06",
            "Treat plans as context",
            "North-South Corridor and Northern Gateway plans support the area thesis, "
            "but are not added to achieved prices or presented as guaranteed uplift.",
            "canberra_strategy_6_planning_context.html",
        ),
    ]
    return "".join(
        "<article class='strategy'>"
        f"<span>{number}</span><h3>{_esc(title)}</h3><p>{_esc(text)}</p>"
        f"<p><a href='{_esc(filename)}'>Open strategy workbook →</a></p></article>"
        for number, title, text, filename in strategies
    )


def _finding_cards(
    subject: dict[str, Any],
    matched_rows: list[dict[str, Any]],
    txns: pd.DataFrame,
) -> str:
    by_project = {row["project"]: row for row in matched_rows}
    subject_psf = subject["stats"]["all"]["median_psf"]
    water = by_project["THE WATERGARDENS AT CANBERRA"]["stats"]["all"]
    commodore = by_project["THE COMMODORE"]["stats"]["all"]
    north_park = by_project["NORTH PARK RESIDENCES"]["stats"]["all"]
    recent = txns[txns["sale_period"].ge(pd.Period("2025-01", freq="M"))]
    district_state = recent["type_of_sale"].value_counts()
    findings = [
        (
            "Launch evidence is deep",
            f"{subject['all_n']} official caveats equal {subject['caveat_stock_pct']:.1f}% "
            f"of {SUBJECT_UNITS} project units. This is caveat-to-stock evidence—not "
            "developer-confirmed sales or unique buyers.",
        ),
        (
            "The launch premium is visible",
            f"Canberra Crescent's {_num(subject_psf, prefix='S$', digits=0)} median PSF "
            f"is {_num(abs(pct_delta(water['median_psf'], subject_psf) or 0), suffix='%', digits=1)} "
            "away from Watergardens' recent non-New-Sale evidence. Sale state and "
            "completion explain part of the gap.",
        ),
        (
            "Closest peers are not identical",
            f"Watergardens contributes {water['n']} current-window transactions; "
            f"The Commodore contributes {commodore['n']}. Bedroom, size and floor "
            "tabs are more reliable than their all-unit medians.",
        ),
        (
            "Integration offers a different trade",
            f"North Park's current-window median is {_num(north_park['median_psf'], prefix='S$', digits=0)} "
            "PSF. Buyers trade a more established integrated town centre against an "
            "older lease clock and Yishun rather than Canberra positioning.",
        ),
        (
            "Launch path is not appreciation",
            "Monthly Canberra Crescent medians reflect the sequence of released and "
            "booked units. Changes across launch months cannot verify capital growth "
            "before a resale market exists.",
        ),
        (
            "District liquidity is mostly resale",
            f"Since 2025 the district ledger contains {int(district_state.get('Resale', 0))} "
            f"Resale, {int(district_state.get('Sub Sale', 0))} Sub Sale and "
            f"{int(district_state.get('New Sale', 0))} New Sale caveats. Exit evidence "
            "must be read separately from launch absorption.",
        ),
    ]
    return "".join(
        "<article class='finding'>"
        f"<span>{index:02d}</span><h3>{_esc(title)}</h3><p>{_esc(text)}</p></article>"
        for index, (title, text) in enumerate(findings, 1)
    )


def _subject_bedroom_table(subject: dict[str, Any]) -> str:
    rows = []
    for key in ("1", "2", "3", "4", "unknown"):
        stat = subject["stats"][key]
        if stat["n"] == 0:
            continue
        rows.append(
            "<tr>"
            f"<td><b>{_esc(unit_label(key))}</b></td>"
            f"<td class='num'>{stat['n']}</td>"
            f"<td class='num'>{_money(stat['median_price'])}<small>"
            f"{_range(stat['price_p10'], stat['price_p90'], _money)}</small></td>"
            f"<td class='num'>{_num(stat['median_psf'], prefix='S$', digits=0)}<small>"
            f"{_range(stat['psf_p10'], stat['psf_p90'], lambda value: _num(value, prefix='S$', digits=0))}</small></td>"
            f"<td class='num'>{_num(stat['median_sqft'], suffix=' sqft', digits=0)}</td>"
            "</tr>"
        )
    return (
        "<div class='table-wrap'><table class='subject-table'><thead><tr>"
        "<th>Bedroom / unit type</th><th class='num'>Caveats</th>"
        "<th class='num'>Median quantum<small>P10–P90</small></th>"
        "<th class='num'>Median PSF<small>P10–P90</small></th>"
        f"<th class='num'>Median size</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _subject_month_table(subject: dict[str, Any]) -> str:
    rows = []
    first_psf = subject["months"][0]["stats"]["median_psf"]
    for month in subject["months"]:
        stat = month["stats"]
        change = pct_delta(stat["median_psf"], first_psf)
        status = "<span class='partial'>partial</span>" if month["partial"] else ""
        rows.append(
            "<tr>"
            f"<td><b>{month['month']}</b>{status}</td>"
            f"<td class='num'>{stat['n']}</td>"
            f"<td class='num'>{_money(stat['median_price'])}</td>"
            f"<td class='num'>{_num(stat['median_psf'], prefix='S$', digits=0)}</td>"
            f"<td class='num'>{_delta(change)}</td>"
            f"<td class='num'>{_num(stat['median_sqft'], suffix=' sqft', digits=0)}</td>"
            "</tr>"
        )
    return (
        "<div class='table-wrap'><table class='month-table'><thead><tr>"
        "<th>Launch month</th><th class='num'>Caveats</th>"
        "<th class='num'>Median quantum</th><th class='num'>Median PSF</th>"
        "<th class='num'>PSF vs first month</th><th class='num'>Median size</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _subject_floor_table(subject: dict[str, Any]) -> str:
    headings = "".join(
        f"<th class='num'>{_esc(TAB_LABELS[key])}</th>"
        for key in TAB_KEYS
    )
    rows = []
    for floor in subject["floor_rows"]:
        cells = []
        for key in TAB_KEYS:
            stat = floor["cells"][key]
            cells.append(
                "<td class='num'>"
                f"{_num(stat['median_psf'], prefix='S$', digits=0)}"
                f"<small>{stat['n']} caveat{'s' if stat['n'] != 1 else ''}</small>"
                "</td>"
            )
        rows.append(
            f"<tr><td><b>{_esc(floor['floor'])}</b></td>{''.join(cells)}</tr>"
        )
    return (
        "<div class='table-wrap'><table class='floor-table'><thead><tr>"
        f"<th>Floor band</th>{headings}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _matched_section(
    key: str,
    rows: list[dict[str, Any]],
    active: bool,
) -> str:
    body = []
    for row in rows:
        stat = row["stats"][key]
        body.append(
            "<tr>"
            f"<td><b>{_esc(row['project'])}</b><small>{_esc(row['role'])}</small></td>"
            f"<td>{_esc(row['sale_state'])}</td>"
            f"<td class='num'>{stat['n']}</td>"
            f"<td class='num'>{_money(stat['median_price'])}<small>"
            f"{_range(stat['price_p10'], stat['price_p90'], _money)}</small></td>"
            f"<td class='num'>{_num(stat['median_psf'], prefix='S$', digits=0)}</td>"
            f"<td class='num'>{_delta(stat['subject_psf_delta_pct'])}</td>"
            f"<td class='num'>{_num(stat['median_sqft'], suffix=' sqft', digits=0)}</td>"
            f"<td>{_esc(row['station'])}<small>"
            f"{_num(row['station_distance_m'], suffix='m')}</small></td>"
            "</tr>"
        )
    active_class = " active" if active else ""
    return (
        f"<section id='matched-{_esc(key)}' class='matched-section{active_class}'>"
        "<div class='table-wrap'><table class='matched-table'><thead><tr>"
        "<th>Project / role</th><th>Evidence state</th><th class='num'>n</th>"
        "<th class='num'>Median quantum<small>P10–P90</small></th>"
        "<th class='num'>Median PSF</th><th class='num'>PSF vs subject</th>"
        "<th class='num'>Median size</th><th>Nearest open MRT<small>straight-line</small></th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table></div></section>"
    )


def _project_table(rows: list[dict[str, Any]]) -> str:
    body = []
    for row in rows:
        subject_class = " class='subject-row'" if row["project"] == SUBJECT else ""
        body.append(
            f"<tr{subject_class}>"
            f"<td><b>{_esc(row['project'])}</b><small>{_esc(row['role'])}</small></td>"
            f"<td>{_esc(row['evidence_state'])}</td>"
            f"<td class='num'>{row['recent_n']}<small>{row['history_n']} in raw history</small></td>"
            f"<td class='num'>{_money(row['stats']['median_price'])}</td>"
            f"<td class='num'>{_num(row['stats']['median_psf'], prefix='S$', digits=0)}</td>"
            f"<td class='num'>{_num(row['stats']['median_sqft'], suffix=' sqft', digits=0)}</td>"
            f"<td>{_esc(row['tenure'])}</td>"
            f"<td>{_esc(row['station'])}<small>{_num(row['station_distance_m'], suffix='m')}</small></td>"
            f"<td class='num'>{row['primary_1km_count'] if row['primary_1km_count'] is not None else '—'}</td>"
            f"<td>{row['first_month']}–{row['last_month']}</td>"
            "</tr>"
        )
    return (
        "<div class='table-wrap'><table class='project-table'><thead><tr>"
        "<th>Project / comparison role</th><th>Recent evidence state</th>"
        "<th class='num'>Current-window txns<small>raw history</small></th>"
        "<th class='num'>Median quantum</th><th class='num'>Median PSF</th>"
        "<th class='num'>Median size</th><th>Observed tenure</th>"
        "<th>Nearest open MRT<small>straight-line</small></th>"
        "<th class='num'>Primary ≤1km</th><th>Observed period</th>"
        f"</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def _planning_table() -> str:
    plans = [
        (
            "Canberra MRT / Canberra Plaza",
            "Delivered",
            "Current amenity and access evidence; no future uplift is added.",
            "https://www.lta.gov.sg/content/ltagov/en/getting_around/public_transport/rail_network/north_south_line.html",
            "LTA",
        ),
        (
            "North-South Corridor",
            "Viaduct targeted 2027; tunnel targeted 2029",
            "Supports road, bus, cycling and public-realm context. It is not direct MRT integration or guaranteed price growth.",
            "https://www.lta.gov.sg/content/ltagov/en/upcoming_projects/road_commuter_facilities/north_south_corridor.html/",
            "LTA",
        ),
        (
            "Woodlands Regional Centre / RTS",
            "RTS targeted end-2026; broader hub multi-stage",
            "Northern employment and cross-border context. Canberra Crescent is not at the RTS station.",
            "https://www.ura.gov.sg/land-planning/master-plan/master-plan-2025/regional-plans/north/powering-industry-and-work-spaces--enhancing-the-rustic-region-and-its-past/",
            "URA",
        ),
        (
            "Sembawang Shipyard",
            "Operations wind down from 2028; concepts long-dated",
            "Potential future waterfront district, but currently a planning concept rather than near-term project evidence.",
            "https://www.ura.gov.sg/land-planning/master-plan/master-plan-2025/regional-plans/north/sembawang-shipyard/",
            "URA",
        ),
        (
            "Additional North-region housing",
            "Progressive",
            "Adds amenities and household base while also increasing future private and public housing competition.",
            "https://www.ura.gov.sg/land-planning/master-plan/master-plan-2025/regional-plans/north/home-for-all--nearby-to-nature/",
            "URA",
        ),
    ]
    body = "".join(
        "<tr>"
        f"<td><b>{_esc(plan)}</b></td><td>{_esc(horizon)}</td>"
        f"<td>{_esc(treatment)}</td><td><a href='{_esc(url)}'>{_esc(label)} source</a></td>"
        "</tr>"
        for plan, horizon, treatment, url, label in plans
    )
    return (
        "<div class='table-wrap'><table class='planning-table'><thead><tr>"
        "<th>Plan / amenity</th><th>Evidence horizon</th>"
        f"<th>How this report treats it</th><th>Primary source</th></tr></thead><tbody>{body}</tbody></table></div>"
    )


def _position_key(value: str) -> str:
    return slugify(value)


def _transaction_ledger(
    txns: pd.DataFrame,
    window: dict[str, pd.Period | None],
) -> str:
    rows = []
    ordered = txns.sort_values(
        ["sale_period", "project_name", "price", "area_sqm"],
        ascending=[False, True, False, False],
        kind="stable",
    )
    for number, row in enumerate(ordered.to_dict("records"), 1):
        period = str(row["sale_period"])
        partial = (
            "<span class='partial'>partial month</span>"
            if row["sale_period"] > window["full_end"]
            else ""
        )
        unit = (
            f"{unit_label(row['unit_key'], short=True)} · "
            f"{_num(row['sqft'], suffix=' sqft', digits=0)}"
        )
        cohort_scope = (
            f"{row['year']} {_esc(row['type_of_sale'])} "
            f"{_esc(unit_label(row['unit_key'], short=True))}"
        )
        if row["cohort_project_n"] == 1:
            cohort_scope += " · single project"
        search = (
            f"{period} {row['project_name']} {row['type_of_sale']} {unit} "
            f"{clean_text(row['floor_level'])} {float(row['price']):.0f} "
            f"{row['psf']:.0f} {row['analysis']}"
        ).lower()
        rows.append(
            f"<tr data-project='{_esc(slugify(row['project_name']))}' "
            f"data-sale='{_esc(slugify(row['type_of_sale']))}' "
            f"data-unit='{_esc(row['unit_key'])}' data-year='{row['year']}' "
            f"data-position='{_esc(_position_key(row['position']))}' "
            f"data-search='{_esc(search)}'>"
            f"<td><b>{period}</b>{partial}<small>record {number:04d}</small></td>"
            f"<td><b>{_esc(row['project_name'])}</b></td>"
            f"<td>{_esc(row['type_of_sale'])}</td>"
            f"<td><b>{_esc(unit)}</b><small>{_esc(clean_text(row['floor_level'], 'floor unavailable'))}</small></td>"
            f"<td class='num'>{_money(float(row['price']))}</td>"
            f"<td class='num'>{_num(row['psf'], prefix='S$', digits=0)}</td>"
            f"<td class='num'>{_num(row['cohort_median_psf'], prefix='S$', digits=0)}"
            f"<small>{_esc(cohort_scope)} · n={row['cohort_n']}</small></td>"
            f"<td class='num'>{_delta(row['cohort_delta_pct'])}"
            f"<small>{row['cohort_percentile']:.0f}th percentile</small></td>"
            f"<td class='num'>{_delta(row['project_delta_pct'])}"
            f"<small>project-year type · n={row['project_cohort_n']}</small></td>"
            f"<td class='analysis-cell'>{_esc(row['analysis'])}</td>"
            f"<td>{_esc(row['bedroom_source'].replace('_', ' ').title())}</td>"
            "</tr>"
        )

    projects = sorted(txns["project_name"].unique().tolist())
    project_options = "".join(
        f"<option value='{_esc(slugify(project))}'>{_esc(project)}</option>"
        for project in projects
        if project != SUBJECT
    )
    years = sorted(txns["year"].unique().tolist(), reverse=True)
    year_options = "".join(
        f"<option value='{year}'>{year}</option>"
        for year in years
    )
    position_options = "".join(
        f"<option value='{_esc(_position_key(position))}'>{_esc(position)}</option>"
        for position in (
            "Upper decile",
            "Upper quartile",
            "Middle range",
            "Lower quartile",
            "Lower decile",
        )
    )
    return (
        "<div class='ledger-controls'>"
        "<label>Project<select id='ledger-project'><option value='all'>All projects</option>"
        f"<option value='{slugify(SUBJECT)}'>CANBERRA CRESCENT ONLY</option>"
        f"{project_options}</select></label>"
        "<label>Sale state<select id='ledger-sale'><option value='all'>All states</option>"
        "<option value='new-sale'>New Sale</option><option value='sub-sale'>Sub Sale</option>"
        "<option value='resale'>Resale</option></select></label>"
        "<label>Bedroom<select id='ledger-unit'><option value='all'>All types</option>"
        "<option value='1'>1BR</option><option value='2'>2BR</option>"
        "<option value='3'>3BR</option><option value='4'>4BR</option>"
        "<option value='5'>5BR</option><option value='unknown'>Unknown</option>"
        "</select></label>"
        "<label>Year<select id='ledger-year'><option value='all'>All years</option>"
        f"{year_options}</select></label>"
        "<label>Position<select id='ledger-position'><option value='all'>All positions</option>"
        f"{position_options}</select></label>"
        "<label class='search-label'>Search<input id='ledger-search' type='search' "
        "placeholder='project, month, floor, price, PSF or diagnostic'></label>"
        f"<span id='ledger-count'>{len(txns):,} records shown</span>"
        "</div>"
        "<div class='table-wrap ledger-wrap'><table class='ledger-table'><thead><tr>"
        "<th>Sale month</th><th>Project</th><th>Sale state</th><th>Unit profile / floor</th>"
        "<th class='num'>Price</th><th class='num'>PSF</th>"
        "<th class='num'>D27 peer median<small>year · state · bedroom</small></th>"
        "<th class='num'>Peer position</th><th class='num'>Vs project</th>"
        "<th>Transaction diagnostic</th><th>Bedroom evidence</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _source_register(window: dict[str, pd.Period | None]) -> str:
    return (
        "<div class='source-grid'>"
        "<article><h3>Transaction evidence</h3><ul>"
        "<li><a href='https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch'>URA Property Market Information</a>: official District 27 caveats.</li>"
        "<li><a href='https://eservice.ura.gov.sg/reis/coverageandMethodology'>URA REALIS methodology</a>: caveat coverage limitations.</li>"
        f"<li>Headline window: {_esc(window['current_start'])}–{_esc(window['full_end'])}; "
        f"partial {_esc(window['partial'])} retained only in the ledger.</li>"
        "<li>Raw official row multiplicity is retained; identical public attributes can represent distinct units.</li>"
        "</ul></article>"
        "<article><h3>Project and spatial facts</h3><ul>"
        "<li><a href='https://links.sgx.com/1.0.0/corporate-announcements/ZM405N4QV5HI1RWJ/855144_PXL_Business%20Update%20for%201H2025.pdf'>SGX-filed PropNex update</a>: 376 units and 2 August 2025 launch.</li>"
        "<li><a href='https://www.ura.gov.sg/-/media/Corporate/Media-Room/2024/Apr/pr24-14a.pdf'>URA GLS parcel details</a>: 99-year site and planning parameters.</li>"
        "<li><a href='https://www.onemap.gov.sg/home/'>OneMap</a>: reviewed project coordinates.</li>"
        "<li><a href='https://www.lta.gov.sg/content/ltagov/en/map/train.html'>LTA rail map</a>: operational MRT network.</li>"
        "<li><a href='https://www.moe.gov.sg/schoolfinder?journey=Primary+school'>MOE SchoolFinder</a>: final address-specific school checks.</li>"
        "</ul></article>"
        "<article><h3>Calculation register</h3><ul>"
        "<li>Peer cohort: calendar year × sale state × bedroom count.</li>"
        "<li>Project reference: project × calendar year × bedroom count.</li>"
        "<li>Size cohort: calendar year × sale state × 100-sqft band.</li>"
        "<li>Percentiles use average rank and include the subject row.</li>"
        "<li>Bedroom labels are secondary EdgeProp matches; source is shown per row.</li>"
        "</ul></article>"
        "</div>"
    )


def render_html(
    txns: pd.DataFrame,
    window: dict[str, pd.Period | None],
    project_rows: list[dict[str, Any]],
    matched_rows: list[dict[str, Any]],
    subject: dict[str, Any],
    as_of: date,
) -> str:
    subject_row = next(row for row in project_rows if row["project"] == SUBJECT)
    tabs = "".join(
        f"<button class='matched-tab{' active' if key == 'all' else ''}' "
        f"data-tab='{_esc(key)}'>{_esc(TAB_LABELS[key])}</button>"
        for key in TAB_KEYS
    )
    matched_sections = "".join(
        _matched_section(key, matched_rows, key == "all")
        for key in TAB_KEYS
    )
    partial_total = int(txns["sale_period"].gt(window["full_end"]).sum())
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Canberra Crescent Residences · District 27 Deep Analysis</title>
<style>
  :root {{
    --ink:#17212b; --muted:#617080; --line:#d9e1e8; --paper:#f4f7f8;
    --card:#fff; --accent:#0f766e; --accent-soft:#dff4f0;
    --premium:#b4412f; --premium-soft:#fae7e3;
    --discount:#0b7a42; --discount-soft:#dff4e9; --warm:#9a5b13;
  }}
  * {{ box-sizing:border-box; }}
  html {{ scroll-behavior:smooth; }}
  body {{ margin:0; background:var(--paper); color:var(--ink);
    font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
  main {{ max-width:1540px; margin:0 auto; padding:44px 28px 76px; }}
  a {{ color:inherit; text-decoration-color:#70afa7; text-underline-offset:3px; }}
  .eyebrow {{ color:var(--accent); font-size:11px; font-weight:850;
    letter-spacing:.14em; text-transform:uppercase; }}
  h1 {{ max-width:1050px; margin:9px 0 12px; font-size:clamp(32px,4.8vw,58px);
    line-height:1.01; letter-spacing:-.045em; }}
  .lede {{ max-width:1000px; margin:0; color:var(--muted); font-size:16px; line-height:1.6; }}
  .nav-links {{ display:flex; gap:16px; flex-wrap:wrap; margin-top:14px; }}
  .nav-links a {{ color:var(--accent); font-size:12px; font-weight:800; }}
  .headline-grid {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:11px; margin:28px 0 18px; }}
  .headline-grid article {{ min-height:110px; padding:17px; border-radius:14px; background:var(--ink); color:white; }}
  .headline-grid b {{ display:block; margin-bottom:6px; font-size:22px; }}
  .headline-grid span {{ color:#cbd5df; font-size:10px; line-height:1.5; }}
  .verdict {{ padding:18px 20px; border:1px solid #a7dacf; border-radius:14px;
    background:var(--accent-soft); font-size:13px; line-height:1.6; }}
  .verdict b {{ color:var(--accent); }}
  h2 {{ margin:40px 0 13px; font-size:23px; letter-spacing:-.025em; }}
  h3.subhead {{ margin:28px 0 7px; font-size:17px; }}
  .section-note {{ margin:0 0 11px; color:var(--muted); font-size:11px; line-height:1.55; }}
  .strategies,.findings {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }}
  .strategy,.finding {{ min-height:145px; padding:18px; border-radius:14px; }}
  .strategy {{ background:white; border:1px solid var(--line); }}
  .finding {{ background:var(--ink); color:white; }}
  .strategy span,.finding span {{ color:var(--accent); font-size:9px; font-weight:900; letter-spacing:.1em; }}
  .finding span {{ color:#79d5c9; }}
  .strategy h3,.finding h3 {{ margin:9px 0 7px; font-size:15px; }}
  .strategy p,.finding p {{ margin:0; color:var(--muted); font-size:11px; line-height:1.55; }}
  .finding p {{ color:#cdd7df; }}
  .subject-metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:11px; }}
  .subject-metrics article {{ padding:16px; border:1px solid var(--line); border-radius:13px; background:white; }}
  .subject-metrics span {{ display:block; min-height:27px; color:var(--muted); font-size:9px;
    text-transform:uppercase; letter-spacing:.04em; }}
  .subject-metrics b {{ display:block; margin-top:5px; font-size:20px; }}
  .two-column {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:14px; }}
  .table-wrap {{ overflow:auto; border:1px solid var(--line); border-radius:14px; background:white; }}
  table {{ width:100%; border-collapse:collapse; font-size:11px; }}
  th,td {{ padding:10px 9px; border-bottom:1px solid #e8edf1; text-align:left; vertical-align:top; }}
  th {{ position:sticky; top:0; z-index:2; background:#edf2f4; color:#52616e;
    font-size:9px; text-transform:uppercase; letter-spacing:.04em; }}
  th small,td small {{ display:block; margin-top:3px; color:#7a8895; font-size:9px;
    font-weight:500; text-transform:none; letter-spacing:0; }}
  th.num,td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  tbody tr:hover {{ background:#f7faf9; }}
  .subject-table,.month-table,.floor-table {{ min-width:620px; }}
  .matched-table {{ min-width:1080px; }} .project-table {{ min-width:1480px; }}
  .planning-table {{ min-width:1050px; }} .ledger-table {{ min-width:2050px; }}
  .subject-row {{ background:#eefaf7; }}
  .tabs {{ display:flex; gap:7px; flex-wrap:wrap; margin:11px 0; }}
  .matched-tab {{ border:1px solid var(--line); border-radius:9px; padding:9px 12px;
    background:white; color:var(--ink); cursor:pointer; font-size:10px; font-weight:800; }}
  .matched-tab.active {{ border-color:var(--ink); background:var(--ink); color:white; }}
  .matched-section {{ display:none; }} .matched-section.active {{ display:block; }}
  .delta {{ display:inline-flex; border-radius:99px; padding:4px 8px; font-weight:850; }}
  .delta.premium {{ color:var(--premium); background:var(--premium-soft); }}
  .delta.discount {{ color:var(--discount); background:var(--discount-soft); }}
  .delta.flat {{ color:var(--muted); background:#eef1f3; }}
  .na {{ color:#84909a; font-size:9px; font-weight:650; }}
  .partial {{ display:block; width:max-content; margin-top:4px; border-radius:99px;
    padding:2px 5px; color:var(--warm); background:#fff1d6; font-size:8px; font-weight:850; }}
  .ledger-controls {{ display:flex; align-items:flex-end; gap:8px; flex-wrap:wrap; margin:11px 0; }}
  .ledger-controls label {{ display:flex; flex-direction:column; gap:4px; color:var(--muted);
    font-size:9px; font-weight:800; text-transform:uppercase; letter-spacing:.04em; }}
  select,input {{ min-width:145px; border:1px solid var(--line); border-radius:9px; background:white;
    color:var(--ink); padding:9px 10px; font:inherit; font-size:10px; }}
  #ledger-project {{ min-width:230px; }} .search-label {{ flex:1; }}
  .search-label input {{ width:100%; min-width:240px; }}
  #ledger-count {{ margin-left:auto; padding:9px 0; color:var(--muted); font-size:10px; }}
  .ledger-wrap {{ max-height:720px; }} .analysis-cell {{ min-width:390px; max-width:520px; line-height:1.5; }}
  .source-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
  .source-grid article {{ padding:17px; border:1px solid var(--line); border-radius:14px; background:white; }}
  .source-grid h3 {{ margin:0 0 9px; font-size:14px; }}
  .source-grid ul {{ margin:0; padding-left:18px; }}
  .source-grid li {{ margin:5px 0; color:#4e5e6b; font-size:11px; line-height:1.5; }}
  .caveat {{ margin-top:25px; padding:16px 18px; border-left:4px solid var(--warm);
    background:white; color:var(--muted); font-size:11px; line-height:1.65; }}
  @media(max-width:1050px) {{
    .headline-grid {{ grid-template-columns:repeat(3,1fr); }}
    .strategies,.findings {{ grid-template-columns:repeat(2,1fr); }}
    .two-column {{ grid-template-columns:minmax(0,1fr); }}
  }}
  @media(max-width:720px) {{
    main {{ padding:30px 15px 55px; }}
    .headline-grid,.subject-metrics,.strategies,.findings {{ grid-template-columns:1fr; }}
    .source-grid {{ grid-template-columns:1fr; }}
    #ledger-count {{ width:100%; margin:0; }}
    .ledger-controls label,.search-label {{ width:100%; }}
    select,input,#ledger-project,.search-label input {{ width:100%; min-width:0; min-height:40px; }}
  }}
</style>
</head>
<body><main>
<div class="eyebrow">Private-project diagnostic · District 27 · generated {_esc(as_of.isoformat())}</div>
<h1>Canberra Crescent Residences: launch evidence versus District 27</h1>
<p class="lede">A sale-state-aware comparison of the 376-unit launch against Canberra, Sembawang and Yishun condominiums, followed by a diagnostic for every official district transaction in the current URA extract.</p>
<div class="nav-links">
  <a href="index.html">← All research reports</a>
  <a href="poiz_east_resale_comparison.html">Poiz versus East comparison</a>
</div>
<div class="headline-grid">
  <article><b>{subject['all_n']}</b><span>official Canberra Crescent caveats through {_esc(subject['months'][-1]['month'])}; {subject['partial_n']} in the partial month</span></article>
  <article><b>{subject['caveat_stock_pct']:.1f}%</b><span>caveats divided by {SUBJECT_UNITS} units—not confirmed sales or unique buyers</span></article>
  <article><b>{_num(subject['stats']['all']['median_psf'], prefix='S$', digits=0)}</b><span>subject median achieved PSF through the latest complete month</span></article>
  <article><b>{len(txns):,}</b><span>official District 27 apartment/condominium records analysed row by row</span></article>
  <article><b>{subject_row['station_distance_m']}m</b><span>straight-line subject diagnostic to {_esc(subject_row['station'])}; not a walking route</span></article>
</div>
<div class="verdict"><b>Decision read:</b> Start with The Watergardens and The Commodore for micro-location and newer-lease context, then Canberra Residences for the age/space discount. Use North Park, The Wisteria and Nine Residences only to test the separate value of established mixed-use integration. Never present the subject’s launch-month price path as resale appreciation.</div>

<h2>Recommended comparison strategy</h2>
<div class="strategies">{_strategy_cards()}</div>

<h2>Research findings</h2>
<div class="findings">{_finding_cards(subject, matched_rows, txns)}</div>

<h2>Canberra Crescent launch audit</h2>
<div class="subject-metrics">
  <article><span>Complete-month caveats</span><b>{subject['complete_n']}</b></article>
  <article><span>Partial-month caveats</span><b>{subject['partial_n']}</b></article>
  <article><span>Median achieved quantum</span><b>{_money(subject['stats']['all']['median_price'])}</b></article>
  <article><span>Bedroom attribution</span><b>{subject['bedroom_known_pct']:.1f}%</b></article>
</div>
<div class="two-column">
  <div>
    <h3 class="subhead">Launch evidence by bedroom type</h3>
    <p class="section-note">P10–P90 preserves dispersion rather than implying a single representative unit.</p>
    {_subject_bedroom_table(subject)}
  </div>
  <div>
    <h3 class="subhead">Launch-month price path</h3>
    <p class="section-note">Movement versus the first month remains release- and mix-sensitive, not appreciation.</p>
    {_subject_month_table(subject)}
  </div>
</div>
<h3 class="subhead">Floor-band achieved PSF</h3>
<p class="section-note">Bedroom columns help separate floor effects from unit-mix effects; thin cells should not be generalised.</p>
{_subject_floor_table(subject)}

<h2>Bedroom-matched primary comparisons</h2>
<p class="section-note">Window {_esc(window['current_start'])}–{_esc(window['full_end'])}. The subject is New Sale; peer evidence states remain explicit. Subject deltas require at least three transactions on both sides.</p>
<div class="tabs">{tabs}</div>
{matched_sections}

<h2>All District 27 condominium projects</h2>
<p class="section-note">All projects in the official five-year apartment/condominium extract. Current-window medians use the latest 18 complete months; projects without current evidence fall back to their raw history and remain labelled by observed period.</p>
{_project_table(project_rows)}

<h2>Planning and delivery context</h2>
<p class="section-note">Delivered amenities and future plans are separated so announcements do not masquerade as present-day achieved value.</p>
{_planning_table()}

<h2>Every District 27 transaction analysed</h2>
<p class="section-note">Each row is benchmarked against calendar year × sale state × bedroom peers, its own project-year bedroom median and a 100-sqft size cohort. {partial_total} partial-month records are retained and flagged.</p>
{_transaction_ledger(txns, window)}

<h2>Sources and calculation register</h2>
{_source_register(window)}
<div class="caveat"><b>Read before deciding.</b> URA caveats are voluntary and not exhaustive. Identical public rows can represent distinct apartment transactions, so official multiplicity is preserved. Exact unit numbers, view, facing, condition, discounts and purchaser identity are unavailable. Bedroom labels are secondary EdgeProp row matches because URA does not publish bedrooms. New Sale, Sub Sale and Resale prices reflect different asset states. Straight-line MRT and school diagnostics are not routed walking distances or official Primary 1 home-school measurements. NS12 uses the reviewed 11 Canberra Link location because the legacy input row is invalid. This is descriptive research, not a valuation or financial recommendation.</div>
</main>
<script>
document.querySelectorAll(".matched-tab").forEach(function(button) {{
  button.addEventListener("click", function() {{
    document.querySelectorAll(".matched-tab").forEach(function(item) {{
      item.classList.remove("active");
    }});
    document.querySelectorAll(".matched-section").forEach(function(item) {{
      item.classList.remove("active");
    }});
    button.classList.add("active");
    document.getElementById("matched-" + button.dataset.tab).classList.add("active");
  }});
}});

function applyLedgerFilters() {{
  var project = document.getElementById("ledger-project").value;
  var sale = document.getElementById("ledger-sale").value;
  var unit = document.getElementById("ledger-unit").value;
  var year = document.getElementById("ledger-year").value;
  var position = document.getElementById("ledger-position").value;
  var search = document.getElementById("ledger-search").value.trim().toLowerCase();
  var visible = 0;
  document.querySelectorAll(".ledger-table tbody tr").forEach(function(row) {{
    var show = (project === "all" || row.dataset.project === project) &&
      (sale === "all" || row.dataset.sale === sale) &&
      (unit === "all" || row.dataset.unit === unit) &&
      (year === "all" || row.dataset.year === year) &&
      (position === "all" || row.dataset.position === position) &&
      (!search || row.dataset.search.indexOf(search) !== -1);
    row.hidden = !show;
    if (show) visible += 1;
  }});
  document.getElementById("ledger-count").textContent =
    visible.toLocaleString() + " record" + (visible === 1 ? "" : "s") + " shown";
}}

document.querySelectorAll("#ledger-project,#ledger-sale,#ledger-unit,#ledger-year,#ledger-position").forEach(function(control) {{
  control.addEventListener("change", applyLedgerFilters);
}});
document.getElementById("ledger-search").addEventListener("input", applyLedgerFilters);
</script>
</body></html>"""


def generate(
    raw_path: pathlib.Path = DEFAULT_RAW,
    edgeprop_path: pathlib.Path = DEFAULT_EDGEPROP,
    locations_path: pathlib.Path = DEFAULT_LOCATIONS,
    schools_path: pathlib.Path = DEFAULT_SCHOOLS,
    mrt_path: pathlib.Path = DEFAULT_MRT,
    out_path: pathlib.Path = DEFAULT_OUT,
    as_of: date | None = None,
) -> tuple[pathlib.Path, pd.DataFrame, dict[str, pd.Period | None]]:
    as_of = as_of or date.today()
    txns = load_district_transactions(raw_path, edgeprop_path)
    if SUBJECT not in set(txns["project_name"]):
        raise SystemExit(f"{raw_path} has no {SUBJECT} transactions")
    window = comparison_window(txns, as_of)
    txns = add_transaction_diagnostics(txns)
    locations = load_lookup(locations_path)
    schools = load_lookup(schools_path)
    mrt = pd.read_csv(mrt_path)
    project_rows = build_project_rows(txns, window, locations, schools, mrt)
    matched_rows = build_matched_rows(txns, window, project_rows)
    subject = build_subject(txns, window)
    out_path.write_text(
        render_html(
            txns,
            window,
            project_rows,
            matched_rows,
            subject,
            as_of,
        ),
        encoding="utf-8",
    )
    return out_path, txns, window


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Canberra Crescent versus District 27 deep analysis"
    )
    parser.add_argument("--raw", default=str(DEFAULT_RAW))
    parser.add_argument("--edgeprop", default=str(DEFAULT_EDGEPROP))
    parser.add_argument("--locations", default=str(DEFAULT_LOCATIONS))
    parser.add_argument("--schools", default=str(DEFAULT_SCHOOLS))
    parser.add_argument("--mrt", default=str(DEFAULT_MRT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    out_path, txns, window = generate(
        pathlib.Path(args.raw),
        pathlib.Path(args.edgeprop),
        pathlib.Path(args.locations),
        pathlib.Path(args.schools),
        pathlib.Path(args.mrt),
        pathlib.Path(args.out),
    )
    print(
        f"Written: {out_path} ({len(txns):,} official D27 transactions, "
        f"{txns['project_name'].nunique()} projects, "
        f"headlines through {window['full_end']})"
    )


if __name__ == "__main__":
    main()
