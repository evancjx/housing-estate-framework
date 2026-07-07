#!/usr/bin/env python3
"""
Generate landed_growth_dashboard.html from EdgeProp public landed transactions.

Reads:
  data/edgeprop_landed_transactions_playwright_not_clean.csv

Writes:
  landed_growth_dashboard.html

Run:
  python3 models/gen_landed_growth_dashboard_html.py

Notes:
  The source file is public rendered EdgeProp data and is marked not_clean.
  Projections are simple trend extrapolations from annual median psf, not
  investment forecasts. Current partial-year rows are shown in recent metrics
  but excluded from the annual trend fit.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_INPUT = ROOT / "data/edgeprop_landed_transactions_playwright_not_clean.csv"
DEFAULT_OUTPUT = ROOT / "landed_growth_dashboard.html"

START_YEAR = 2019
RECENT_DAYS = 365
PROJECT_RATE_FLOOR = -0.10
PROJECT_RATE_CEIL = 0.18
DISTRICT_MIN_ANNUAL_N = 5
PROJECT_MIN_ANNUAL_N = 2


def normalise_text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, float) and math.isnan(value):
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "not_covered", "n/a"}:
        return default
    return text


def normalise_district(value: Any) -> str:
    text = normalise_text(value, "?")
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(2) if text.isdigit() else text


def pct(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value * 100.0, 1)


def safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den <= 0:
        return None
    return num / den


def median_or_none(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    return float(clean.median())


def mode_text(series: pd.Series, default: str = "-") -> str:
    values = series.dropna().astype(str).str.strip()
    values = values[values.ne("") & values.str.lower().ne("nan")]
    if values.empty:
        return default
    return str(values.value_counts().index[0])


def period_share(group: pd.DataFrame, column: str, matcher: str | set[str]) -> float | None:
    if group.empty or column not in group:
        return None
    values = group[column].dropna().astype(str).str.strip()
    if values.empty:
        return None
    if isinstance(matcher, str):
        mask = values.str.contains(matcher, case=False, regex=False)
    else:
        mask = values.isin(matcher)
    return float(mask.mean())


def load_landed_transactions(path: pathlib.Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    required = {
        "Project",
        "planning_area",
        "Postal District",
        "Date of Sale",
        "Unit Price ($psf)",
        "Price ($)",
        "Area (sqft)",
        "Type",
        "Tenure",
        "Sale Type",
        "source_quality",
        "source_url",
    }
    missing = sorted(required - set(data.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")

    data = data.copy()
    data["sale_date"] = pd.to_datetime(data["Date of Sale"], errors="coerce")
    data["year"] = data["sale_date"].dt.year
    data["psf"] = pd.to_numeric(data["Unit Price ($psf)"], errors="coerce")
    data["price"] = pd.to_numeric(data["Price ($)"], errors="coerce")
    data["area_sqft"] = pd.to_numeric(data["Area (sqft)"], errors="coerce")
    data["district"] = data["Postal District"].apply(normalise_district)
    data["planning_area"] = data["planning_area"].apply(lambda value: normalise_text(value).upper())
    data["project"] = data["Project"].apply(normalise_text)
    data["source_quality"] = data["source_quality"].apply(lambda value: normalise_text(value, "unknown"))

    data = data[
        (data["sale_date"].notna())
        & (data["year"] >= START_YEAR)
        & (data["psf"] > 0)
        & (data["price"] > 0)
        & (data["area_sqft"] > 0)
        & data["district"].ne("?")
        & data["project"].ne("-")
    ].copy()
    return data


def annual_stats(group: pd.DataFrame) -> list[dict[str, Any]]:
    annual = (
        group.groupby("year", as_index=False)
        .agg(
            median_psf=("psf", "median"),
            n=("psf", "size"),
            median_price=("price", "median"),
            median_area=("area_sqft", "median"),
        )
        .sort_values("year")
    )
    out: list[dict[str, Any]] = []
    for row in annual.to_dict("records"):
        out.append(
            {
                "year": int(row["year"]),
                "median_psf": round(float(row["median_psf"]), 0),
                "n": int(row["n"]),
                "median_price": round(float(row["median_price"]), 0),
                "median_area": round(float(row["median_area"]), 0),
            }
        )
    return out


def log_trend_rate(annual: list[dict[str, Any]], max_trend_year: int, min_annual_n: int) -> float | None:
    eligible = [
        row
        for row in annual
        if row["year"] <= max_trend_year
        and row["n"] >= min_annual_n
        and row["median_psf"] > 0
    ]
    if len(eligible) < 2:
        return None

    x = np.array([row["year"] for row in eligible], dtype=float)
    y = np.log(np.array([row["median_psf"] for row in eligible], dtype=float))
    w = np.sqrt(np.array([row["n"] for row in eligible], dtype=float))
    try:
        slope = float(np.polyfit(x - x.min(), y, 1, w=w)[0])
    except (ValueError, np.linalg.LinAlgError):
        return None
    return math.exp(slope) - 1.0


def first_eligible_annual(
    annual: list[dict[str, Any]],
    max_trend_year: int,
    min_annual_n: int,
) -> dict[str, Any] | None:
    for row in annual:
        if row["year"] <= max_trend_year and row["n"] >= min_annual_n and row["median_psf"] > 0:
            return row
    return None


def last_eligible_annual(
    annual: list[dict[str, Any]],
    max_trend_year: int,
    min_annual_n: int,
) -> dict[str, Any] | None:
    for row in reversed(annual):
        if row["year"] <= max_trend_year and row["n"] >= min_annual_n and row["median_psf"] > 0:
            return row
    return None


def confidence_label(level: str, total_n: int, active_years: int, trend_years: int, recent_n: int) -> str:
    if level == "district":
        if total_n >= 150 and active_years >= 5 and trend_years >= 5:
            return "High"
        if total_n >= 40 and active_years >= 3 and trend_years >= 3:
            return "Medium"
        return "Low"

    if total_n >= 25 and active_years >= 5 and trend_years >= 4 and recent_n >= 3:
        return "High"
    if total_n >= 10 and active_years >= 3 and trend_years >= 2:
        return "Medium"
    return "Low"


def cap_projection_rate(rate: float | None) -> tuple[float | None, bool]:
    if rate is None or not math.isfinite(rate):
        return None, False
    capped = min(max(rate, PROJECT_RATE_FLOOR), PROJECT_RATE_CEIL)
    return capped, capped != rate


def base_summary(
    group: pd.DataFrame,
    *,
    level: str,
    key: str,
    label: str,
    district: str,
    max_date: pd.Timestamp,
    max_trend_year: int,
) -> dict[str, Any]:
    min_annual_n = DISTRICT_MIN_ANNUAL_N if level == "district" else PROJECT_MIN_ANNUAL_N
    annual = annual_stats(group)
    eligible = [
        row for row in annual if row["year"] <= max_trend_year and row["n"] >= min_annual_n
    ]
    first = first_eligible_annual(annual, max_trend_year, min_annual_n)
    latest = last_eligible_annual(annual, max_trend_year, min_annual_n)
    trend_raw = log_trend_rate(annual, max_trend_year, min_annual_n)

    recent_start = max_date - pd.Timedelta(days=RECENT_DAYS)
    recent = group[group["sale_date"] >= recent_start]
    early = group[group["year"].isin([START_YEAR, START_YEAR + 1])]
    if early.empty and first is not None:
        early = group[group["year"].eq(first["year"])]

    total_n = int(len(group))
    recent_n = int(len(recent))
    active_years = int(group["year"].nunique())
    trend_years = len(eligible)
    confidence = confidence_label(level, total_n, active_years, trend_years, recent_n)

    baseline_psf = float(first["median_psf"]) if first else None
    latest_psf = float(latest["median_psf"]) if latest else None
    recent_psf = median_or_none(recent["psf"]) if not recent.empty else latest_psf
    growth = safe_div(latest_psf, baseline_psf)
    recent_growth = safe_div(recent_psf, baseline_psf)

    early_area = median_or_none(early["area_sqft"]) if not early.empty else None
    recent_area = median_or_none(recent["area_sqft"]) if not recent.empty else None
    area_shift = None
    if early_area and recent_area:
        area_shift = recent_area / early_area - 1.0

    recent_new_share = period_share(recent, "Sale Type", "New Sale") or 0.0
    row = {
        "level": level,
        "key": key,
        "label": label,
        "district": district,
        "planning_area": mode_text(group["planning_area"]),
        "project": label if level == "project" else "",
        "total_n": total_n,
        "recent_n": recent_n,
        "active_years": active_years,
        "trend_years": trend_years,
        "baseline_year": int(first["year"]) if first else None,
        "baseline_psf": round(baseline_psf, 0) if baseline_psf else None,
        "latest_full_year": int(latest["year"]) if latest else None,
        "latest_full_psf": round(latest_psf, 0) if latest_psf else None,
        "recent_psf": round(float(recent_psf), 0) if recent_psf else None,
        "median_price_mil": round(float(group["price"].median()) / 1_000_000, 2),
        "median_area_sqft": round(float(group["area_sqft"].median()), 0),
        "growth_pct": pct(growth - 1.0) if growth else None,
        "recent_growth_pct": pct(recent_growth - 1.0) if recent_growth else None,
        "trend_rate_raw": trend_raw,
        "trend_rate_pct": pct(trend_raw),
        "confidence": confidence,
        "freehold_share_pct": pct(period_share(group, "Tenure", "Freehold") or 0.0),
        "new_sale_share_pct": pct(period_share(group, "Sale Type", "New Sale") or 0.0),
        "recent_new_sale_share_pct": pct(recent_new_share),
        "premium_type_share_pct": pct(
            period_share(group, "Type", {"Detached House", "Semi-Detached House", "GCB"}) or 0.0
        ),
        "area_shift_pct": pct(area_shift) if area_shift is not None else None,
        "main_type": mode_text(group["Type"]),
        "main_tenure": mode_text(group["Tenure"]),
        "sale_mix": mode_text(group["Sale Type"]),
        "first_sale": group["sale_date"].min().strftime("%Y-%m-%d"),
        "last_sale": group["sale_date"].max().strftime("%Y-%m-%d"),
        "annual": annual,
        "projection_source": "own trend",
        "projection_rate": None,
        "projection_rate_pct": None,
        "projection_capped": False,
        "projection_years": [],
        "trend_delta_pp": None,
        "why": [],
    }
    return row


def blend_rate(row: dict[str, Any], fallback: dict[str, Any] | None) -> tuple[float | None, str]:
    own = row.get("trend_rate_raw")
    fallback_rate = None
    if fallback:
        fallback_rate = fallback.get("projection_rate")
        if fallback_rate is None:
            fallback_rate = fallback.get("trend_rate_raw")

    if row["level"] == "district":
        if own is not None:
            return own, "district trend"
        return fallback_rate, "market fallback"

    if own is None:
        return fallback_rate, "district fallback"
    if fallback_rate is None:
        return own, "own trend"
    if row["confidence"] == "High":
        return own * 0.70 + fallback_rate * 0.30, "project/district blend"
    if row["confidence"] == "Medium":
        return own * 0.50 + fallback_rate * 0.50, "project/district blend"
    return fallback_rate, "district fallback"


def build_explanations(
    row: dict[str, Any],
    fallback: dict[str, Any] | None,
    market_rate: float | None,
) -> list[str]:
    reasons: list[str] = []
    compare_label = "district" if row["level"] == "project" else "market"
    compare_rate = None
    if fallback:
        compare_rate = fallback.get("projection_rate")
    if compare_rate is None:
        compare_rate = market_rate

    rate = row.get("projection_rate")
    if rate is not None and compare_rate is not None:
        delta_pp = (rate - compare_rate) * 100.0
        row["trend_delta_pp"] = round(delta_pp, 1)
        if delta_pp >= 2.0:
            reasons.append(f"Trend is {delta_pp:.1f} pp faster than the {compare_label} baseline.")
        elif delta_pp <= -2.0:
            reasons.append(f"Trend is {abs(delta_pp):.1f} pp slower than the {compare_label} baseline.")
        else:
            reasons.append(f"Trend is close to the {compare_label} baseline.")

    if row.get("recent_growth_pct") is not None:
        recent_growth = float(row["recent_growth_pct"])
        if recent_growth >= 25:
            reasons.append(f"Recent median psf is {recent_growth:.1f}% above the baseline year.")
        elif recent_growth <= -10:
            reasons.append(f"Recent median psf is {abs(recent_growth):.1f}% below the baseline year.")

    if row.get("freehold_share_pct") is not None and row["freehold_share_pct"] >= 70:
        reasons.append("Mostly freehold transactions; scarcity can support stronger land psf.")
    if row.get("recent_new_sale_share_pct") is not None and row["recent_new_sale_share_pct"] >= 15:
        reasons.append("Recent new-sale mix is material and can reset psf above resale comparables.")
    if row.get("area_shift_pct") is not None:
        if row["area_shift_pct"] <= -10:
            reasons.append("Recent transactions are on smaller plots, which can mechanically lift psf.")
        elif row["area_shift_pct"] >= 10:
            reasons.append("Recent transactions are on larger plots, which can dampen psf growth.")
    if row["confidence"] == "Low":
        reasons.append("Thin public sample; projection leans on the broader district/market trend.")
    elif row["confidence"] == "Medium":
        reasons.append("Moderate sample; read the projection as directional.")
    if row.get("projection_capped"):
        reasons.append("Extreme fitted trend was capped for dashboard projection.")

    if not reasons:
        reasons.append("No strong mix signal; movement mainly follows observed median psf trend.")
    return reasons[:5]


def finalise_row(
    row: dict[str, Any],
    *,
    fallback: dict[str, Any] | None,
    market_rate: float | None,
    projection_years: list[int],
) -> dict[str, Any]:
    raw_rate, source = blend_rate(row, fallback)
    rate, capped = cap_projection_rate(raw_rate)
    row["projection_rate"] = rate
    row["projection_rate_pct"] = pct(rate)
    row["projection_capped"] = capped
    row["projection_source"] = source

    anchor = row.get("recent_psf") or row.get("latest_full_psf")
    row["projection_years"] = []
    if rate is not None and anchor:
        for offset, year in enumerate(projection_years, 1):
            row["projection_years"].append(
                {"year": year, "psf": round(float(anchor) * ((1.0 + rate) ** offset), 0)}
            )
    row["why"] = build_explanations(row, fallback, market_rate)
    return row


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_ready(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return round(value, 6)
    return value


def prepare_dashboard_payload(
    data: pd.DataFrame,
    *,
    generated_on: date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if data.empty:
        raise SystemExit("No landed transactions available after cleaning/filtering.")

    generated_on = generated_on or date.today()
    max_date = pd.Timestamp(data["sale_date"].max())
    trend_end_year = int(max_date.year)
    if max_date.month < 12:
        trend_end_year -= 1
    projection_years = [int(max_date.year + 1), int(max_date.year + 3), int(max_date.year + 5)]

    market = base_summary(
        data,
        level="market",
        key="market",
        label="All public landed rows",
        district="ALL",
        max_date=max_date,
        max_trend_year=trend_end_year,
    )
    market_rate, market_capped = cap_projection_rate(market.get("trend_rate_raw"))
    market["projection_rate"] = market_rate
    market["projection_rate_pct"] = pct(market_rate)
    market["projection_capped"] = market_capped

    district_rows: list[dict[str, Any]] = []
    for district, group in data.groupby("district", sort=True):
        row = base_summary(
            group,
            level="district",
            key=f"D{district}",
            label=f"D{district}",
            district=district,
            max_date=max_date,
            max_trend_year=trend_end_year,
        )
        finalise_row(row, fallback=market, market_rate=market_rate, projection_years=projection_years)
        district_rows.append(row)

    district_lookup = {row["district"]: row for row in district_rows}
    project_rows: list[dict[str, Any]] = []
    for (district, project), group in data.groupby(["district", "project"], sort=True):
        row = base_summary(
            group,
            level="project",
            key=f"D{district}:{project}",
            label=project,
            district=district,
            max_date=max_date,
            max_trend_year=trend_end_year,
        )
        finalise_row(
            row,
            fallback=district_lookup.get(district) or market,
            market_rate=market_rate,
            projection_years=projection_years,
        )
        project_rows.append(row)

    rows = district_rows + project_rows
    rows.sort(key=lambda item: (item["level"], item["district"], item["label"]))

    metadata = {
        "generated_on": generated_on.isoformat(),
        "source_file": str(DEFAULT_INPUT.relative_to(ROOT)),
        "source_quality": ", ".join(sorted(data["source_quality"].dropna().unique())),
        "source_note": "EdgeProp public rendered landed-house pages; public table labels source as URA.",
        "row_count_2019_plus": int(len(data)),
        "project_count": int(data["project"].nunique()),
        "district_count": int(data["district"].nunique()),
        "date_min": data["sale_date"].min().strftime("%Y-%m-%d"),
        "date_max": data["sale_date"].max().strftime("%Y-%m-%d"),
        "trend_start_year": START_YEAR,
        "trend_end_year": trend_end_year,
        "partial_year_note": f"{max_date.year} is partial and excluded from the annual trend fit.",
        "projection_years": projection_years,
        "market_projection_rate_pct": pct(market_rate),
        "market_recent_psf": market.get("recent_psf"),
        "market_total_n": market.get("total_n"),
    }
    return json_ready(rows), json_ready(metadata)


def render_html(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> str:
    data_json = json.dumps(rows, ensure_ascii=True, allow_nan=False)
    meta_json = json.dumps(metadata, ensure_ascii=True, allow_nan=False)
    template = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Singapore Landed PSF Growth Dashboard</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
    background: #f6f7f9;
    color: #18212f;
    font-size: 13px;
  }
  header {
    padding: 18px 24px 14px;
    border-bottom: 1px solid #d9dee8;
    background: #ffffff;
  }
  h1 {
    margin: 0 0 6px;
    font-size: 22px;
    font-weight: 720;
    letter-spacing: 0;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 8px 18px;
    color: #5b6678;
    line-height: 1.45;
  }
  main { padding: 18px 24px 28px; }
  .metrics {
    display: grid;
    grid-template-columns: repeat(5, minmax(150px, 1fr));
    gap: 10px;
    margin-bottom: 14px;
  }
  .metric {
    background: #ffffff;
    border: 1px solid #dce2ec;
    border-radius: 7px;
    padding: 10px 12px;
    min-height: 72px;
  }
  .metric span {
    display: block;
    color: #687386;
    font-size: 11px;
    margin-bottom: 7px;
  }
  .metric strong {
    display: block;
    color: #111827;
    font-size: 20px;
    line-height: 1.1;
  }
  .metric em {
    display: block;
    color: #7d8797;
    font-style: normal;
    font-size: 11px;
    margin-top: 5px;
  }
  .toolbar {
    display: grid;
    grid-template-columns: minmax(220px, 1.2fr) repeat(4, minmax(130px, 0.8fr)) minmax(180px, 1fr);
    gap: 10px;
    align-items: end;
    margin: 14px 0;
  }
  label {
    display: grid;
    gap: 5px;
    color: #5b6678;
    font-size: 11px;
  }
  input, select, button {
    font: inherit;
  }
  input[type="search"], input[type="range"], select {
    width: 100%;
  }
  input[type="search"], select {
    border: 1px solid #cfd6e3;
    border-radius: 6px;
    background: #ffffff;
    color: #1f2937;
    min-height: 34px;
    padding: 7px 9px;
  }
  input[type="range"] { accent-color: #0f766e; }
  .segments {
    display: grid;
    grid-template-columns: 1fr 1fr;
    border: 1px solid #cfd6e3;
    border-radius: 6px;
    overflow: hidden;
    background: #ffffff;
  }
  .segments button {
    border: 0;
    border-right: 1px solid #cfd6e3;
    background: #ffffff;
    color: #374151;
    min-height: 34px;
    cursor: pointer;
  }
  .segments button:last-child { border-right: 0; }
  .segments button.active {
    background: #0f766e;
    color: #ffffff;
    font-weight: 650;
  }
  .workspace {
    display: grid;
    grid-template-columns: minmax(420px, 1.25fr) minmax(300px, 0.75fr);
    gap: 12px;
    margin-bottom: 12px;
  }
  .panel {
    background: #ffffff;
    border: 1px solid #dce2ec;
    border-radius: 7px;
    min-width: 0;
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 11px 13px;
    border-bottom: 1px solid #e2e7f0;
  }
  .panel-title {
    font-weight: 700;
    color: #111827;
  }
  .panel-subtitle {
    color: #687386;
    font-size: 11px;
    margin-top: 2px;
  }
  #chart { width: 100%; min-height: 290px; padding: 8px 10px 12px; }
  #chart svg { width: 100%; height: 290px; display: block; }
  .selected-detail {
    padding: 12px 13px 14px;
  }
  .detail-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 12px;
  }
  .detail-grid div {
    border: 1px solid #e3e8f1;
    border-radius: 6px;
    padding: 8px;
    background: #fafbfc;
  }
  .detail-grid span {
    display: block;
    color: #6b7280;
    font-size: 11px;
    margin-bottom: 4px;
  }
  .detail-grid strong {
    color: #111827;
    font-size: 15px;
  }
  .why-list {
    display: grid;
    gap: 7px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .why-list li {
    border-left: 3px solid #0f766e;
    background: #f3faf8;
    padding: 7px 9px;
    color: #263241;
    line-height: 1.35;
  }
  .top-list {
    display: grid;
    gap: 8px;
    padding: 12px 13px 14px;
  }
  .bar-row {
    display: grid;
    grid-template-columns: minmax(110px, 1fr) minmax(120px, 1.6fr) 52px;
    gap: 8px;
    align-items: center;
    cursor: pointer;
  }
  .bar-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: #263241;
  }
  .bar-track {
    height: 9px;
    border-radius: 999px;
    background: #e5eaf2;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    border-radius: 999px;
    background: #2563eb;
  }
  .bar-value {
    color: #4b5563;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .table-wrap {
    border: 1px solid #dce2ec;
    border-radius: 7px;
    background: #ffffff;
    overflow: auto;
    max-height: 62vh;
  }
  table {
    width: 100%;
    min-width: 1260px;
    border-collapse: collapse;
  }
  th, td {
    padding: 8px 10px;
    border-bottom: 1px solid #edf0f5;
    text-align: right;
    font-variant-numeric: tabular-nums;
    vertical-align: top;
  }
  th {
    position: sticky;
    top: 0;
    z-index: 2;
    background: #f8fafc;
    color: #526071;
    font-size: 11px;
    font-weight: 700;
    border-bottom: 1px solid #dce2ec;
    cursor: pointer;
  }
  td:first-child, th:first-child,
  td:nth-child(2), th:nth-child(2),
  td:nth-child(3), th:nth-child(3),
  td:last-child, th:last-child {
    text-align: left;
  }
  tbody tr {
    cursor: pointer;
  }
  tbody tr:hover {
    background: #f8fafc;
  }
  tbody tr.active {
    background: #ecfdf5;
  }
  .project-cell {
    max-width: 240px;
    white-space: normal;
    line-height: 1.25;
  }
  .why-cell {
    max-width: 360px;
    white-space: normal;
    line-height: 1.3;
    color: #374151;
  }
  .pill {
    display: inline-flex;
    align-items: center;
    min-height: 22px;
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 650;
  }
  .pill-high { background: #dcfce7; color: #166534; }
  .pill-medium { background: #fef3c7; color: #92400e; }
  .pill-low { background: #fee2e2; color: #991b1b; }
  .pos { color: #047857; }
  .neg { color: #b91c1c; }
  .muted { color: #7d8797; }
  @media (max-width: 980px) {
    main, header { padding-left: 14px; padding-right: 14px; }
    .metrics { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
    .toolbar { grid-template-columns: 1fr 1fr; }
    .workspace { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<header>
  <h1>Singapore Landed PSF Growth Dashboard</h1>
  <div class="meta">
    <span>Generated <strong id="generatedOn"></strong></span>
    <span>Source quality <strong id="sourceQuality"></strong></span>
    <span>Trend fit <strong id="trendWindow"></strong></span>
    <span id="partialYearNote"></span>
  </div>
</header>
<main>
  <section class="metrics">
    <div class="metric"><span>Transactions since 2019</span><strong id="metricRows"></strong><em>public visible rows</em></div>
    <div class="metric"><span>Projects</span><strong id="metricProjects"></strong><em>with 2019+ rows</em></div>
    <div class="metric"><span>Districts</span><strong id="metricDistricts"></strong><em>postal districts</em></div>
    <div class="metric"><span>Market recent median</span><strong id="metricMarketPsf"></strong><em>last 12 months</em></div>
    <div class="metric"><span>Market projection rate</span><strong id="metricMarketRate"></strong><em>annualized capped trend</em></div>
  </section>

  <section class="toolbar">
    <label>Search
      <input id="searchBox" type="search" placeholder="District, project, planning area">
    </label>
    <label>View
      <div class="segments">
        <button id="districtMode" class="active" type="button">District</button>
        <button id="projectMode" type="button">Project</button>
      </div>
    </label>
    <label>District
      <select id="districtFilter"></select>
    </label>
    <label>Confidence
      <select id="confidenceFilter">
        <option value="all">All</option>
        <option value="High">High</option>
        <option value="Medium">Medium</option>
        <option value="Low">Low</option>
      </select>
    </label>
    <label>Sort
      <select id="sortSelect">
        <option value="projection_rate_pct">Projection rate</option>
        <option value="recent_growth_pct">Recent growth</option>
        <option value="total_n">Transaction count</option>
        <option value="recent_psf">Recent psf</option>
        <option value="trend_delta_pp">Peer delta</option>
      </select>
    </label>
    <label>Minimum transactions <span id="minTxnLabel">10</span>
      <input id="minTxn" type="range" min="0" max="80" step="1" value="10">
    </label>
  </section>

  <section class="workspace">
    <div class="panel">
      <div class="panel-head">
        <div>
          <div class="panel-title" id="chartTitle">District trend</div>
          <div class="panel-subtitle" id="chartSubtitle"></div>
        </div>
        <div class="muted" id="visibleCount"></div>
      </div>
      <div id="chart"></div>
    </div>
    <div class="panel">
      <div class="panel-head">
        <div>
          <div class="panel-title" id="detailTitle">Selected row</div>
          <div class="panel-subtitle" id="detailSubtitle"></div>
        </div>
      </div>
      <div class="selected-detail">
        <div class="detail-grid">
          <div><span>Recent median psf</span><strong id="detailRecent"></strong></div>
          <div><span>Projection rate</span><strong id="detailRate"></strong></div>
          <div><span>Transactions</span><strong id="detailTxn"></strong></div>
          <div><span>Confidence</span><strong id="detailConfidence"></strong></div>
        </div>
        <ul class="why-list" id="detailWhy"></ul>
      </div>
    </div>
  </section>

  <section class="panel" style="margin-bottom: 12px;">
    <div class="panel-head">
      <div>
        <div class="panel-title">Fastest projected movers</div>
        <div class="panel-subtitle">Filtered rows, annualized projection rate</div>
      </div>
    </div>
    <div class="top-list" id="topMovers"></div>
  </section>

  <section class="table-wrap">
    <table>
      <thead>
        <tr>
          <th data-sort="level">View</th>
          <th data-sort="district">District</th>
          <th data-sort="label">Project / Area</th>
          <th data-sort="total_n">Txn</th>
          <th data-sort="active_years">Yrs</th>
          <th data-sort="baseline_psf">Base psf</th>
          <th data-sort="recent_psf">Recent psf</th>
          <th data-sort="recent_growth_pct">Recent growth</th>
          <th data-sort="projection_rate_pct">Proj rate</th>
          <th id="projH1"></th>
          <th id="projH2"></th>
          <th id="projH3"></th>
          <th data-sort="confidence">Confidence</th>
          <th data-sort="trend_delta_pp">Peer delta</th>
          <th>Why</th>
        </tr>
      </thead>
      <tbody id="tableBody"></tbody>
    </table>
  </section>
</main>

<script>
const DATA = __DATA_JSON__;
const META = __META_JSON__;

let state = {
  level: "district",
  search: "",
  district: "all",
  confidence: "all",
  minTxn: 10,
  sortKey: "projection_rate_pct",
  sortDir: -1,
  selectedKey: null,
};

function fmtInt(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toLocaleString();
}
function fmtPsf(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return "$" + Math.round(Number(value)).toLocaleString();
}
function fmtPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const num = Number(value);
  const sign = num > 0 ? "+" : "";
  return sign + num.toFixed(1) + "%";
}
function clsPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "";
  return Number(value) >= 0 ? "pos" : "neg";
}
function escapeHtml(value) {
  const escapes = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"};
  return String(value ?? "").replace(/[&<>"']/g, char => escapes[char]);
}
function confidencePill(value) {
  const key = String(value || "Low").toLowerCase();
  return `<span class="pill pill-${key}">${escapeHtml(value || "Low")}</span>`;
}
function projectionValue(row, index) {
  return row.projection_years && row.projection_years[index] ? row.projection_years[index].psf : null;
}
function selectedRows() {
  const needle = state.search.trim().toLowerCase();
  return DATA.filter(row => {
    if (row.level !== state.level) return false;
    if (state.district !== "all" && row.district !== state.district) return false;
    if (state.confidence !== "all" && row.confidence !== state.confidence) return false;
    if (Number(row.total_n || 0) < state.minTxn) return false;
    if (needle) {
      const haystack = `${row.label} ${row.project} ${row.planning_area} D${row.district}`.toLowerCase();
      if (!haystack.includes(needle)) return false;
    }
    return true;
  }).sort((a, b) => {
    const key = state.sortKey;
    const av = a[key] ?? (typeof a[key] === "string" ? "" : -Infinity);
    const bv = b[key] ?? (typeof b[key] === "string" ? "" : -Infinity);
    if (typeof av === "string" || typeof bv === "string") {
      return String(av).localeCompare(String(bv)) * state.sortDir;
    }
    return (Number(av) - Number(bv)) * state.sortDir;
  });
}
function populateDistricts() {
  const districts = [...new Set(DATA.filter(row => row.level === "district").map(row => row.district))].sort();
  document.getElementById("districtFilter").innerHTML = [
    '<option value="all">All districts</option>',
    ...districts.map(d => `<option value="${escapeHtml(d)}">D${escapeHtml(d)}</option>`)
  ].join("");
}
function renderMetrics() {
  document.getElementById("generatedOn").textContent = META.generated_on;
  document.getElementById("sourceQuality").textContent = META.source_quality;
  document.getElementById("trendWindow").textContent = `${META.trend_start_year}-${META.trend_end_year}`;
  document.getElementById("partialYearNote").textContent = META.partial_year_note;
  document.getElementById("metricRows").textContent = fmtInt(META.row_count_2019_plus);
  document.getElementById("metricProjects").textContent = fmtInt(META.project_count);
  document.getElementById("metricDistricts").textContent = fmtInt(META.district_count);
  document.getElementById("metricMarketPsf").textContent = fmtPsf(META.market_recent_psf);
  document.getElementById("metricMarketRate").textContent = fmtPct(META.market_projection_rate_pct);
  document.getElementById("projH1").textContent = String(META.projection_years[0]);
  document.getElementById("projH2").textContent = String(META.projection_years[1]);
  document.getElementById("projH3").textContent = String(META.projection_years[2]);
}
function renderTable(rows) {
  const activeKey = state.selectedKey;
  document.getElementById("tableBody").innerHTML = rows.map(row => {
    const firstWhy = row.why && row.why.length ? row.why[0] : "";
    return `<tr data-key="${escapeHtml(row.key)}" class="${row.key === activeKey ? "active" : ""}">
      <td>${escapeHtml(row.level)}</td>
      <td>D${escapeHtml(row.district)}</td>
      <td class="project-cell"><strong>${escapeHtml(row.label)}</strong><br><span class="muted">${escapeHtml(row.planning_area || "")}</span></td>
      <td>${fmtInt(row.total_n)}</td>
      <td>${fmtInt(row.active_years)}</td>
      <td>${fmtPsf(row.baseline_psf)}<br><span class="muted">${row.baseline_year || ""}</span></td>
      <td>${fmtPsf(row.recent_psf)}<br><span class="muted">${fmtInt(row.recent_n)} recent</span></td>
      <td class="${clsPct(row.recent_growth_pct)}">${fmtPct(row.recent_growth_pct)}</td>
      <td class="${clsPct(row.projection_rate_pct)}">${fmtPct(row.projection_rate_pct)}<br><span class="muted">${escapeHtml(row.projection_source)}</span></td>
      <td>${fmtPsf(projectionValue(row, 0))}</td>
      <td>${fmtPsf(projectionValue(row, 1))}</td>
      <td>${fmtPsf(projectionValue(row, 2))}</td>
      <td>${confidencePill(row.confidence)}</td>
      <td class="${clsPct(row.trend_delta_pp)}">${fmtPct(row.trend_delta_pp)}</td>
      <td class="why-cell">${escapeHtml(firstWhy)}</td>
    </tr>`;
  }).join("");
  document.querySelectorAll("tbody tr").forEach(tr => {
    tr.addEventListener("click", () => {
      state.selectedKey = tr.dataset.key;
      render();
    });
  });
}
function drawChart(row) {
  const host = document.getElementById("chart");
  if (!row) {
    host.innerHTML = "<div class='muted' style='padding:18px;'>No matching rows.</div>";
    return;
  }
  const annual = (row.annual || []).map(item => ({year: item.year, psf: item.median_psf, n: item.n, projected: false}));
  const projected = (row.projection_years || []).map(item => ({year: item.year, psf: item.psf, n: null, projected: true}));
  const points = annual.concat(projected).filter(item => item.psf !== null && item.psf !== undefined);
  if (!points.length) {
    host.innerHTML = "<div class='muted' style='padding:18px;'>No chartable psf values.</div>";
    return;
  }
  const width = 760, height = 290, pad = {l: 58, r: 24, t: 18, b: 42};
  const years = points.map(p => p.year);
  const values = points.map(p => Number(p.psf));
  const minYear = Math.min(...years), maxYear = Math.max(...years);
  const minVal = Math.min(...values) * 0.92;
  const maxVal = Math.max(...values) * 1.08;
  const x = year => pad.l + ((year - minYear) / Math.max(1, maxYear - minYear)) * (width - pad.l - pad.r);
  const y = value => pad.t + (1 - ((value - minVal) / Math.max(1, maxVal - minVal))) * (height - pad.t - pad.b);
  const annualPath = annual.map((p, i) => `${i ? "L" : "M"}${x(p.year).toFixed(1)},${y(p.psf).toFixed(1)}`).join(" ");
  const projectionStart = annual.length ? annual[annual.length - 1] : projected[0];
  const projectionPath = [projectionStart].concat(projected).map((p, i) => `${i ? "L" : "M"}${x(p.year).toFixed(1)},${y(p.psf).toFixed(1)}`).join(" ");
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map(t => minVal + (maxVal - minVal) * t);
  const yearTicks = [...new Set(points.map(p => p.year))].filter((year, i) => i % Math.ceil(points.length / 7) === 0 || year === maxYear);
  host.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Annual median psf and projected psf">
    <rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff"></rect>
    ${yTicks.map(v => `<line x1="${pad.l}" x2="${width - pad.r}" y1="${y(v)}" y2="${y(v)}" stroke="#e5eaf2"></line><text x="${pad.l - 8}" y="${y(v) + 4}" text-anchor="end" fill="#6b7280" font-size="11">${fmtPsf(v)}</text>`).join("")}
    ${yearTicks.map(year => `<text x="${x(year)}" y="${height - 14}" text-anchor="middle" fill="#6b7280" font-size="11">${year}</text>`).join("")}
    <path d="${annualPath}" fill="none" stroke="#0f766e" stroke-width="3" stroke-linecap="round"></path>
    <path d="${projectionPath}" fill="none" stroke="#2563eb" stroke-width="3" stroke-dasharray="7 6" stroke-linecap="round"></path>
    ${annual.map(p => `<circle cx="${x(p.year)}" cy="${y(p.psf)}" r="4" fill="#0f766e"><title>${p.year}: ${fmtPsf(p.psf)} (${p.n} rows)</title></circle>`).join("")}
    ${projected.map(p => `<circle cx="${x(p.year)}" cy="${y(p.psf)}" r="4" fill="#2563eb"><title>${p.year} projection: ${fmtPsf(p.psf)}</title></circle>`).join("")}
    <text x="${pad.l}" y="16" fill="#0f766e" font-size="11">observed median psf</text>
    <text x="${pad.l + 148}" y="16" fill="#2563eb" font-size="11">projection</text>
  </svg>`;
}
function renderDetail(row) {
  if (!row) return;
  document.getElementById("chartTitle").textContent = `${row.level === "district" ? "District" : "Project"}: ${row.label}`;
  document.getElementById("chartSubtitle").textContent = `D${row.district} / ${row.planning_area} / ${row.first_sale} to ${row.last_sale}`;
  document.getElementById("detailTitle").textContent = row.label;
  document.getElementById("detailSubtitle").textContent = `D${row.district} / ${row.main_type} / ${row.main_tenure}`;
  document.getElementById("detailRecent").textContent = fmtPsf(row.recent_psf);
  document.getElementById("detailRate").textContent = fmtPct(row.projection_rate_pct);
  document.getElementById("detailTxn").textContent = `${fmtInt(row.total_n)} total, ${fmtInt(row.recent_n)} recent`;
  document.getElementById("detailConfidence").innerHTML = confidencePill(row.confidence);
  document.getElementById("detailWhy").innerHTML = (row.why || []).map(item => `<li>${escapeHtml(item)}</li>`).join("");
  drawChart(row);
}
function renderTopMovers(rows) {
  const ranked = rows.filter(row => row.projection_rate_pct !== null && row.projection_rate_pct !== undefined).slice(0, 10);
  const maxAbs = Math.max(1, ...ranked.map(row => Math.abs(Number(row.projection_rate_pct || 0))));
  document.getElementById("topMovers").innerHTML = ranked.map(row => {
    const value = Number(row.projection_rate_pct || 0);
    const width = Math.min(100, Math.abs(value) / maxAbs * 100);
    const color = value >= 0 ? "#2563eb" : "#b91c1c";
    return `<div class="bar-row" data-key="${escapeHtml(row.key)}">
      <div class="bar-name">D${escapeHtml(row.district)} ${escapeHtml(row.label)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${width}%; background:${color};"></div></div>
      <div class="bar-value ${clsPct(value)}">${fmtPct(value)}</div>
    </div>`;
  }).join("");
  document.querySelectorAll(".bar-row").forEach(item => {
    item.addEventListener("click", () => {
      state.selectedKey = item.dataset.key;
      render();
    });
  });
}
function render() {
  document.getElementById("districtMode").classList.toggle("active", state.level === "district");
  document.getElementById("projectMode").classList.toggle("active", state.level === "project");
  document.getElementById("minTxnLabel").textContent = String(state.minTxn);
  const rows = selectedRows();
  if (!state.selectedKey || !rows.some(row => row.key === state.selectedKey)) {
    state.selectedKey = rows.length ? rows[0].key : null;
  }
  const selected = rows.find(row => row.key === state.selectedKey) || rows[0] || null;
  document.getElementById("visibleCount").textContent = `${fmtInt(rows.length)} rows`;
  renderTable(rows);
  renderTopMovers(rows);
  renderDetail(selected);
}
function bindEvents() {
  document.getElementById("districtMode").addEventListener("click", () => { state.level = "district"; state.selectedKey = null; render(); });
  document.getElementById("projectMode").addEventListener("click", () => { state.level = "project"; state.selectedKey = null; render(); });
  document.getElementById("searchBox").addEventListener("input", event => { state.search = event.target.value; state.selectedKey = null; render(); });
  document.getElementById("districtFilter").addEventListener("change", event => { state.district = event.target.value; state.selectedKey = null; render(); });
  document.getElementById("confidenceFilter").addEventListener("change", event => { state.confidence = event.target.value; state.selectedKey = null; render(); });
  document.getElementById("sortSelect").addEventListener("change", event => { state.sortKey = event.target.value; render(); });
  document.getElementById("minTxn").addEventListener("input", event => { state.minTxn = Number(event.target.value); state.selectedKey = null; render(); });
  document.querySelectorAll("th[data-sort]").forEach(th => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) state.sortDir *= -1;
      else { state.sortKey = key; state.sortDir = -1; }
      document.getElementById("sortSelect").value = state.sortKey;
      render();
    });
  });
}
populateDistricts();
renderMetrics();
bindEvents();
render();
</script>
</body>
</html>
"""
    return template.replace("__DATA_JSON__", data_json).replace("__META_JSON__", meta_json)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate landed growth dashboard HTML")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="EdgeProp landed transaction CSV")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="Output HTML path")
    args = parser.parse_args()

    input_path = pathlib.Path(args.input)
    output_path = pathlib.Path(args.out)
    data = load_landed_transactions(input_path)
    rows, metadata = prepare_dashboard_payload(data)
    output_path.write_text(render_html(rows, metadata), encoding="utf-8")
    print(f"Wrote {len(rows)} dashboard rows to {output_path}")


if __name__ == "__main__":
    main()
