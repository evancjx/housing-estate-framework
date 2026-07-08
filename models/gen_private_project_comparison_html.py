#!/usr/bin/env python3
"""
Generate private_project_comparison_table.html from committed URA private data.

Reads:
  data/inputs/ura_private.csv      - URA private residential transactions
  data/outputs/private_project_locations.csv - optional OneMap-geocoded project points
  data/outputs/private_project_school_metrics.csv - optional project school diagnostics
  data/inputs/mrt_layer.csv        - station coordinates, line, operational flag
  data/inputs/estates.csv          - framework estate centroids
  data/outputs/master_output.csv    - estate-level model context

Writes:
  private_project_comparison_table.html

Run:
  python3 models/gen_private_project_comparison_html.py

Notes:
  URA private transaction rows do not include project coordinates. When
  data/outputs/private_project_locations.csv exists, MRT station assignment is computed
  from that project lat/lon layer. Rows without project coordinates fall back
  to the framework planning-area/estate centroid and are marked as proxy rows.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import pathlib
import re
from datetime import date
from typing import Any

import pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
DEFAULT_LOCATION_PATH = ROOT / "data/outputs/private_project_locations.csv"
DEFAULT_SCHOOL_METRICS_PATH = ROOT / "data/outputs/private_project_school_metrics.csv"

CONDO_TYPE_RE = re.compile(r"\b(?:apartment|condominium|executive condominium)\b", re.I)
SALE_TYPE_LABELS = {
    "1": "New Sale",
    "2": "Sub Sale",
    "3": "Resale",
}

# Planning areas in URA private transactions that are not framework estate rows.
# The target is used only for estate-level context and the MRT centroid proxy.
AREA_CONTEXT_PROXY = {
    "CHANGI": "PASIR RIS",
    "MACPHERSON": "GEYLANG",
    "NOVENA": "TOA PAYOH",
    "RIVER VALLEY": "CENTRAL AREA",
    "SELETAR": "ANG MO KIO",
}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-") or "unknown"


def short_line(line: str) -> str:
    words = str(line).replace("-", " ").split()
    ignore = {"line", "branch"}
    code = "".join(word[0].upper() for word in words if word.lower() not in ignore)
    return code or "MRT"


def normalise_name(value: Any, default: str = "-") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "not_covered", "n/a"}:
        return default
    return text


def normalise_district(value: Any) -> str:
    text = normalise_name(value, "?")
    if text == "?":
        return text
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(2) if text.isdigit() else text


def clean_sale_type(value: Any) -> str:
    text = normalise_name(value, "Unknown")
    return SALE_TYPE_LABELS.get(text, text)


def mode_text(series: pd.Series, default: str = "-") -> str:
    values = series.dropna().astype(str).str.strip()
    values = values[values.ne("") & values.str.lower().ne("nan")]
    if values.empty:
        return default
    return str(values.value_counts().index[0])


def month_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).strftime("%Y-%m")


def pct_delta(value: float | None, base: float | None) -> float | None:
    if value is None or base is None or base <= 0:
        return None
    return round((value / base - 1.0) * 100.0, 1)


def value_or_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if text in {"", "nan", "NaN", "None", "not_covered", "N/A", "N/R"}:
        return None
    return value


def int_or_none(value: Any) -> int | None:
    if value_or_none(value) is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def bool_or_none(value: Any) -> bool | None:
    if value_or_none(value) is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def project_location_key(project: Any, street: Any, district: Any, area: Any) -> tuple[str, str, str, str]:
    return (
        normalise_name(project).upper(),
        normalise_name(street).upper(),
        normalise_district(district),
        normalise_name(area).upper(),
    )


def load_private(path: pathlib.Path) -> pd.DataFrame:
    private = pd.read_csv(path)
    required = {"planning_area", "transacted_price", "area_sqm", "property_type", "project_name", "postal_district"}
    missing = sorted(required - set(private.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")

    private = private.copy()
    private["property_type"] = private["property_type"].apply(normalise_name)
    private = private[private["property_type"].str.contains(CONDO_TYPE_RE, na=False)]
    private = private[private["project_name"].notna()].copy()

    private["planning_area"] = private["planning_area"].apply(lambda v: normalise_name(v).upper())
    private["project_name"] = private["project_name"].apply(normalise_name)
    private["street_name"] = private.get("street_name", pd.Series(["-"] * len(private))).apply(normalise_name)
    private["district"] = private["postal_district"].apply(normalise_district)
    private["sale_type_norm"] = private.get("type_of_sale", pd.Series(["Unknown"] * len(private))).apply(clean_sale_type)

    private["transacted_price"] = pd.to_numeric(private["transacted_price"], errors="coerce")
    private["area_sqm"] = pd.to_numeric(private["area_sqm"], errors="coerce")
    if "unit_price_psm" in private.columns:
        private["unit_price_psm"] = pd.to_numeric(private["unit_price_psm"], errors="coerce")
    else:
        private["unit_price_psm"] = private["transacted_price"] / private["area_sqm"]
    missing_psm = private["unit_price_psm"].isna() | (private["unit_price_psm"] <= 0)
    private.loc[missing_psm, "unit_price_psm"] = (
        private.loc[missing_psm, "transacted_price"] / private.loc[missing_psm, "area_sqm"]
    )

    private["sale_month_dt"] = pd.to_datetime(private.get("sale_month"), errors="coerce")
    private = private[
        (private["transacted_price"] > 0)
        & (private["area_sqm"] > 0)
        & (private["unit_price_psm"] > 0)
    ].copy()
    return private


def load_project_locations(path: pathlib.Path) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    locations = pd.read_csv(path)
    required = {"project_name", "street_name", "postal_district", "planning_area", "lat", "lon"}
    missing = sorted(required - set(locations.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")

    locations = locations.copy()
    locations["lat"] = pd.to_numeric(locations["lat"], errors="coerce")
    locations["lon"] = pd.to_numeric(locations["lon"], errors="coerce")
    locations = locations[locations["lat"].notna() & locations["lon"].notna()]

    out: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for _, row in locations.iterrows():
        key = project_location_key(
            row["project_name"],
            row["street_name"],
            row["postal_district"],
            row["planning_area"],
        )
        out[key] = row.to_dict()
    return out


def load_school_metrics(path: pathlib.Path) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    metrics = pd.read_csv(path)
    required = {"project_name", "street_name", "postal_district", "planning_area"}
    missing = sorted(required - set(metrics.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")

    out: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for _, row in metrics.iterrows():
        key = project_location_key(
            row["project_name"],
            row["street_name"],
            row["postal_district"],
            row["planning_area"],
        )
        out[key] = row.to_dict()
    return out


def school_context(metrics: dict[str, Any] | None) -> dict[str, Any]:
    if not metrics:
        return {
            "school_metrics_source": "missing",
            "has_primary_1km": None,
            "has_ranked_primary_1km": None,
            "primary_1km_count": None,
            "primary_1km_schools": None,
            "primary_1km_ranked_count": None,
            "top_primary_1km_count": None,
            "best_primary_1km_school": None,
            "best_primary_1km_rank": None,
            "best_primary_1km_distance_m": None,
            "best_primary_1km_metric": None,
            "secondary_2km_count": None,
            "best_secondary_2km_school": None,
            "best_secondary_2km_rank": None,
            "best_secondary_2km_distance_m": None,
            "jc_5km_count": None,
            "best_jc_5km_school": None,
            "best_jc_5km_rank": None,
            "best_jc_5km_distance_m": None,
        }
    return {
        "school_metrics_source": "project_geocode",
        "has_primary_1km": bool_or_none(metrics.get("has_primary_1km")),
        "has_ranked_primary_1km": bool_or_none(metrics.get("has_ranked_primary_1km")),
        "primary_1km_count": int_or_none(metrics.get("primary_1km_count")),
        "primary_1km_schools": value_or_none(metrics.get("primary_1km_schools")),
        "primary_1km_ranked_count": int_or_none(metrics.get("primary_1km_ranked_count")),
        "top_primary_1km_count": int_or_none(metrics.get("top_primary_1km_count")),
        "best_primary_1km_school": value_or_none(metrics.get("best_primary_1km_school")),
        "best_primary_1km_rank": int_or_none(metrics.get("best_primary_1km_rank")),
        "best_primary_1km_distance_m": int_or_none(metrics.get("best_primary_1km_distance_m")),
        "best_primary_1km_metric": value_or_none(metrics.get("best_primary_1km_metric")),
        "secondary_2km_count": int_or_none(metrics.get("secondary_2km_count")),
        "best_secondary_2km_school": value_or_none(metrics.get("best_secondary_2km_school")),
        "best_secondary_2km_rank": int_or_none(metrics.get("best_secondary_2km_rank")),
        "best_secondary_2km_distance_m": int_or_none(metrics.get("best_secondary_2km_distance_m")),
        "jc_5km_count": int_or_none(metrics.get("jc_5km_count")),
        "best_jc_5km_school": value_or_none(metrics.get("best_jc_5km_school")),
        "best_jc_5km_rank": int_or_none(metrics.get("best_jc_5km_rank")),
        "best_jc_5km_distance_m": int_or_none(metrics.get("best_jc_5km_distance_m")),
    }


def nearest_station(lat: float, lon: float, stations: list[dict[str, Any]]) -> dict[str, Any]:
    nearest = min(
        stations,
        key=lambda station: haversine_m(lat, lon, float(station["lat"]), float(station["lon"])),
    )
    distance_m = haversine_m(lat, lon, float(nearest["lat"]), float(nearest["lon"]))
    station_name = normalise_name(nearest["name"])
    station_code = normalise_name(nearest["stn_code"])
    line = normalise_name(nearest["line"])
    return {
        "station": station_name,
        "station_code": station_code,
        "station_display": f"{station_name} ({station_code})",
        "station_key": slug(f"{station_name}-{station_code}"),
        "line": line,
        "line_short": short_line(line),
        "line_key": slug(line),
        "station_distance_m": int(round(distance_m)),
        "station_status": "Open" if int(nearest.get("operational", 1)) == 1 else "Future",
    }


def build_station_lookup(estates: pd.DataFrame, mrt: pd.DataFrame) -> dict[str, dict[str, Any]]:
    estate_rows = {
        str(row["estate"]).strip().upper(): row
        for _, row in estates.iterrows()
    }
    stations = list(mrt.to_dict("records"))
    lookup: dict[str, dict[str, Any]] = {}
    for area, estate_row in estate_rows.items():
        lat = float(estate_row["lat"])
        lon = float(estate_row["lon"])
        lookup[area] = nearest_station(lat, lon, stations)
    return lookup


def context_for_area(area: str) -> tuple[str, str]:
    context = AREA_CONTEXT_PROXY.get(area, area)
    basis = "direct" if context == area else f"proxy:{context}"
    return context, basis


def band_context(master: pd.DataFrame, context_area: str) -> dict[str, Any]:
    if context_area not in master.index:
        return {
            "provision_band": None,
            "provision_score": None,
            "private_value_band": None,
            "private_value_score": None,
            "private_value_n": None,
        }
    row = master.loc[context_area]
    private_n = value_or_none(row.get("value_private_n"))
    return {
        "provision_band": value_or_none(row.get("provision_band")),
        "provision_score": round(float(row["provision_score"]), 2)
        if value_or_none(row.get("provision_score")) is not None
        else None,
        "private_value_band": value_or_none(row.get("value_private_band")),
        "private_value_score": round(float(row["value_private_score"]), 2)
        if value_or_none(row.get("value_private_score")) is not None
        else None,
        "private_value_n": int(float(private_n)) if private_n is not None else None,
    }


def aggregate_projects(
    private: pd.DataFrame,
    estates: pd.DataFrame,
    mrt: pd.DataFrame,
    master: pd.DataFrame,
    project_locations: dict[tuple[str, str, str, str], dict[str, Any]],
    school_metrics: dict[tuple[str, str, str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    station_lookup = build_station_lookup(estates, mrt)
    stations = list(mrt.to_dict("records"))
    max_month = private["sale_month_dt"].max()
    recent_start = max_month - pd.DateOffset(months=11) if not pd.isna(max_month) else None

    district_median = private.groupby("district")["unit_price_psm"].median().to_dict()
    area_median = private.groupby("planning_area")["unit_price_psm"].median().to_dict()

    rows: list[dict[str, Any]] = []
    group_cols = ["project_name", "street_name", "district", "planning_area"]
    for (project, street, district, area), group in private.groupby(group_cols, dropna=False):
        area = normalise_name(area).upper()
        context_area, context_basis = context_for_area(area)
        location_key = project_location_key(project, street, district, area)
        location = project_locations.get(location_key)
        school = school_context((school_metrics or {}).get(location_key))
        if location:
            station = nearest_station(float(location["lat"]), float(location["lon"]), stations)
            location_source = "project_geocode"
            project_lat = round(float(location["lat"]), 6)
            project_lon = round(float(location["lon"]), 6)
            geocode_status = normalise_name(location.get("match_status"), "-")
            geocode_score = int(float(location.get("match_score"))) if value_or_none(location.get("match_score")) is not None else None
        else:
            station = station_lookup.get(context_area, {})
            location_source = "centroid_proxy"
            project_lat = None
            project_lon = None
            geocode_status = "missing"
            geocode_score = None
        model_context = band_context(master, context_area)

        median_psm = float(group["unit_price_psm"].median())
        recent = group[group["sale_month_dt"].ge(recent_start)] if recent_start is not None else group.iloc[0:0]
        recent_median_psm = float(recent["unit_price_psm"].median()) if not recent.empty else None
        sale_counts = group["sale_type_norm"].value_counts()
        sale_mix = " / ".join(
            f"{label}:{int(sale_counts[label])}"
            for label in ["New Sale", "Resale", "Sub Sale"]
            if label in sale_counts
        ) or mode_text(group["sale_type_norm"], "Unknown")

        rows.append(
            {
                "project": normalise_name(project),
                "street": normalise_name(street),
                "district": district,
                "district_key": slug(f"d-{district}"),
                "planning_area": area,
                "context_area": context_area,
                "context_basis": context_basis,
                "station": station.get("station", "-"),
                "station_code": station.get("station_code", "-"),
                "station_display": station.get("station_display", "-"),
                "station_key": station.get("station_key", "unknown"),
                "line": station.get("line", "-"),
                "line_short": station.get("line_short", "-"),
                "line_key": station.get("line_key", "unknown"),
                "station_status": station.get("station_status", "-"),
                "station_distance_m": station.get("station_distance_m"),
                "location_source": location_source,
                "project_lat": project_lat,
                "project_lon": project_lon,
                "geocode_status": geocode_status,
                "geocode_score": geocode_score,
                "n": int(len(group)),
                "recent_n": int(len(recent)),
                "median_psm": int(round(median_psm)),
                "recent_median_psm": int(round(recent_median_psm)) if recent_median_psm else None,
                "recent_delta_pct": pct_delta(recent_median_psm, median_psm),
                "district_delta_pct": pct_delta(median_psm, district_median.get(district)),
                "area_delta_pct": pct_delta(median_psm, area_median.get(area)),
                "median_price_mil": round(float(group["transacted_price"].median()) / 1_000_000.0, 2),
                "median_area_sqm": int(round(float(group["area_sqm"].median()))),
                "first_sale": month_text(group["sale_month_dt"].min()),
                "last_sale": month_text(group["sale_month_dt"].max()),
                "sale_mix": sale_mix,
                "property_type": mode_text(group["property_type"]),
                "tenure": mode_text(group.get("tenure", pd.Series(dtype=object))),
                "market_segment": mode_text(group.get("market_segment", pd.Series(dtype=object))),
                "provision_band": model_context["provision_band"],
                "provision_score": model_context["provision_score"],
                "private_value_band": model_context["private_value_band"],
                "private_value_score": model_context["private_value_score"],
                "private_value_n": model_context["private_value_n"],
                **school,
            }
        )

    rows.sort(key=lambda row: (row["district"], row["station"], row["project"], row["street"]))
    return rows


def option_html(value: str, label: str) -> str:
    return f'<option value="{html.escape(value)}">{html.escape(label)}</option>'


def render_html(rows: list[dict[str, Any]], latest_month: str | None) -> str:
    today = date.today().strftime("%Y-%m-%d")
    data_js = json.dumps(rows, indent=2)

    station_counts = pd.Series([row["station_key"] for row in rows]).value_counts().to_dict()
    station_labels = {
        row["station_key"]: row["station_display"]
        for row in rows
    }
    station_options = "\n".join(
        option_html(key, f"{station_labels[key]} ({station_counts[key]})")
        for key in sorted(station_labels, key=lambda item: station_labels[item])
    )

    district_counts = pd.Series([row["district"] for row in rows]).value_counts().to_dict()
    district_options = "\n".join(
        option_html(district, f"D{district} ({district_counts[district]})")
        for district in sorted(district_counts)
    )

    project_count = len(rows)
    transaction_count = sum(row["n"] for row in rows)
    district_count = len(district_counts)
    station_count = len(station_counts)
    geocoded_count = sum(1 for row in rows if row.get("location_source") == "project_geocode")
    centroid_count = project_count - geocoded_count
    school_metrics_count = sum(1 for row in rows if row.get("school_metrics_source") == "project_geocode")

    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SG Private Condo Project Comparison</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", monospace;
    background: #0b0d12;
    color: #cbd5e1;
    padding: 32px;
    font-size: 12px;
  }
  h1 { font-size: 17px; font-weight: 700; color: #f1f5f9; margin-bottom: 4px; }
  .meta { font-size: 11px; color: #64748b; margin-bottom: 18px; }
  .summary {
    display: grid;
    grid-template-columns: repeat(4, minmax(120px, 1fr));
    gap: 10px;
    margin-bottom: 16px;
  }
  .metric {
    border: 1px solid #1e293b;
    border-radius: 6px;
    background: #0d1117;
    padding: 9px 10px;
  }
  .metric b { display: block; color: #f1f5f9; font-size: 16px; margin-bottom: 2px; }
  .metric span { color: #64748b; font-size: 10px; }
  .help-note {
    display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
    margin-bottom: 16px; padding: 8px 10px;
    border: 1px solid #1e293b; border-radius: 6px;
    background: #0d1117; color: #64748b; font-size: 11px; line-height: 1.45;
  }
  .help-note strong { color: #cbd5e1; }
  .controls {
    display: grid;
    grid-template-columns: minmax(200px, 1.4fr) minmax(125px, 0.7fr) minmax(150px, 0.8fr) minmax(125px, 0.7fr) minmax(125px, 0.7fr) minmax(150px, 0.85fr) auto;
    gap: 8px;
    margin-bottom: 16px;
    align-items: start;
  }
  .search, select {
    padding: 6px 10px; border-radius: 5px; border: 1px solid #1e293b;
    background: #111827; color: #e2e8f0; font-size: 11px; outline: none;
    min-height: 30px;
  }
  select[multiple] {
    min-height: 92px;
    padding: 5px 8px;
  }
  select[multiple] option {
    padding: 2px 4px;
  }
  .search::placeholder { color: #475569; }
  .search:focus, select:focus { border-color: #38bdf8; }
  .count { color: #64748b; font-size: 11px; text-align: right; }
  .tbl-wrap { overflow-x: auto; border-radius: 8px; border: 1px solid #1e293b; }
  table { border-collapse: collapse; width: 100%; white-space: nowrap; }
  thead tr.group th {
    padding: 8px 10px 6px;
    font-size: 9px; font-weight: 700; letter-spacing: 1.1px; text-transform: uppercase;
    border-bottom: 1px solid #1e293b;
    text-align: center;
  }
  thead tr.cols th {
    padding: 6px 10px 8px;
    font-size: 10px; font-weight: 600; color: #64748b;
    border-bottom: 2px solid #1e293b;
    cursor: pointer; user-select: none;
    text-align: center;
  }
  thead tr.cols th:hover { color: #94a3b8; }
  thead tr.cols th.sorted { color: #bae6fd; }
  thead tr.cols th.sorted-asc::after { content: " asc"; }
  thead tr.cols th.sorted-desc::after { content: " desc"; }
  .tip {
    position: relative;
    display: inline-flex;
    align-items: center;
    border-bottom: 1px dotted #475569;
    cursor: help;
  }
  .tip::after {
    content: attr(data-tip);
    position: absolute;
    left: 50%;
    top: calc(100% + 8px);
    transform: translateX(-50%);
    z-index: 50;
    width: max-content;
    max-width: 260px;
    padding: 6px 8px;
    border: 1px solid #334155;
    border-radius: 5px;
    background: #020617;
    color: #cbd5e1;
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0;
    text-transform: none;
    line-height: 1.35;
    text-align: left;
    white-space: normal;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.12s ease;
  }
  .tip::before {
    content: "";
    position: absolute;
    left: 50%;
    top: calc(100% + 3px);
    transform: translateX(-50%);
    border: 5px solid transparent;
    border-bottom-color: #334155;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.12s ease;
  }
  .tip:hover::after,
  .tip:hover::before,
  .tip:focus-visible::after,
  .tip:focus-visible::before {
    opacity: 1;
  }
  .row-tip {
    position: relative;
    display: inline-flex;
    align-items: center;
  }
  .row-tip::after {
    content: attr(data-tip);
    position: absolute;
    left: 50%;
    top: calc(100% + 8px);
    transform: translateX(-50%);
    z-index: 60;
    width: max-content;
    max-width: 320px;
    padding: 7px 9px;
    border: 1px solid #334155;
    border-radius: 5px;
    background: #020617;
    color: #cbd5e1;
    font-size: 10px;
    font-weight: 500;
    line-height: 1.4;
    text-align: left;
    white-space: normal;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.12s ease;
  }
  .row-tip::before {
    content: "";
    position: absolute;
    left: 50%;
    top: calc(100% + 3px);
    transform: translateX(-50%);
    border: 5px solid transparent;
    border-bottom-color: #334155;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.12s ease;
  }
  .row-tip:hover::after,
  .row-tip:hover::before,
  .row-tip:focus-visible::after,
  .row-tip:focus-visible::before {
    opacity: 1;
  }
  .g-project { background:#0d1117; color:#38bdf8; }
  .g-location { background:#0d1117; color:#22c55e; }
  .g-school { background:#0d1117; color:#14b8a6; }
  .g-price { background:#0d1117; color:#f59e0b; }
  .g-txn { background:#0d1117; color:#a78bfa; }
  .g-model { background:#0d1117; color:#94a3b8; }
  tbody tr { border-bottom: 1px solid #111827; transition: background 0.1s; }
  tbody tr:hover { background: #111827; }
  td { padding: 7px 10px; text-align: center; }
  td.project-name { text-align: left; font-weight: 700; color: #e2e8f0; min-width: 210px; }
  td.street-name, td.context { text-align: left; color: #94a3b8; }
  .line-badge {
    display: inline-flex; min-width: 36px; height: 18px; align-items: center; justify-content: center;
    border-radius: 4px; padding: 0 6px; font-size: 10px; font-weight: 800;
    background: #172554; color: #bfdbfe;
  }
  .status { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; }
  .status-open { background:#052e16; color:#4ade80; }
  .status-future { background:#422006; color:#fbbf24; }
  .source { display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 700; }
  .source-geocode { background:#052e16; color:#4ade80; }
  .source-proxy { background:#422006; color:#fbbf24; }
  .school-yes { background:#052e16; color:#4ade80; }
  .school-no { background:#3f0909; color:#f87171; }
  .muted { color:#64748b; font-size: 10px; }
  .money { color:#f8fafc; font-weight: 700; }
  .delta-high { color:#f87171; font-weight:700; }
  .delta-mid { color:#fbbf24; }
  .delta-low { color:#4ade80; font-weight:700; }
  .delta-flat { color:#64748b; }
  .band {
    display: inline-block; padding: 1px 6px; border-radius: 4px;
    font-weight: 700; font-size: 11px; letter-spacing: 0.3px;
  }
  .b-A { background:#14532d; color:#4ade80; }
  .b-Bp { background:#1e3a5f; color:#60a5fa; }
  .b-B { background:#1e293b; color:#94a3b8; }
  .b-C { background:#292524; color:#a8a29e; }
  .b-D { background:#431407; color:#fb923c; }
  .b-F { background:#3f0909; color:#f87171; }
  .b-NR { background:transparent; color:#475569; }
  @media (max-width: 900px) {
    body { padding: 18px; }
    .summary { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
    .controls { grid-template-columns: 1fr; }
    .count { text-align: left; }
  }
</style>
</head>
<body>
<h1>SG Private Condo Project Comparison</h1>
<p class="meta">{{PROJECT_COUNT}} projects | {{TRANSACTION_COUNT}} apartment/condo transactions | {{DISTRICT_COUNT}} postal districts | {{STATION_COUNT}} MRT stations | {{GEOCODED_COUNT}} geocoded | {{CENTROID_COUNT}} centroid fallback | {{SCHOOL_METRICS_COUNT}} school-metric rows | latest transaction month {{LATEST_MONTH}} | generated {{TODAY}}</p>

<div class="summary">
  <div class="metric"><b>{{PROJECT_COUNT}}</b><span>projects</span></div>
  <div class="metric"><b>{{TRANSACTION_COUNT}}</b><span>transactions</span></div>
  <div class="metric"><b>{{GEOCODED_COUNT}}</b><span>project geocodes</span></div>
  <div class="metric"><b>{{SCHOOL_METRICS_COUNT}}</b><span>school metrics</span></div>
</div>

<div class="help-note">
  <strong>Scope:</strong>
  <span>Includes URA private Apartment, Condominium, and Executive Condominium rows where present; landed rows are excluded.</span>
  <span>MRT station uses data/outputs/private_project_locations.csv when available; otherwise the row is marked as a centroid fallback.</span>
  <span>School columns use data/outputs/private_project_school_metrics.csv when available; primary is checked within 1km, secondary within 2km, and JC within 5km.</span>
  <span>Provision and private value bands are estate-level context, not project-level model scores.</span>
</div>

<div class="controls">
  <input class="search" id="search" placeholder="Search project, street, district, station..." oninput="applyFilters()">
  <select id="districtFilter" multiple size="5" onchange="applyFilters()" aria-label="District filter">
    <option value="all" selected>All districts</option>
{{DISTRICT_OPTIONS}}
  </select>
  <select id="stationFilter" multiple size="5" onchange="applyFilters()" aria-label="MRT station filter">
    <option value="all" selected>All MRT stations</option>
{{STATION_OPTIONS}}
  </select>
  <select id="saleFilter" multiple size="5" onchange="applyFilters()" aria-label="Sale mix filter">
    <option value="all" selected>All sale mixes</option>
    <option value="New Sale">Has new sales</option>
    <option value="Resale">Has resale</option>
    <option value="Sub Sale">Has sub sales</option>
  </select>
  <select id="sourceFilter" multiple size="4" onchange="applyFilters()" aria-label="Location source filter">
    <option value="all" selected>All locations</option>
    <option value="project_geocode">Project geocode</option>
    <option value="centroid_proxy">Centroid fallback</option>
  </select>
  <select id="primaryFilter" multiple size="4" onchange="applyFilters()" aria-label="Primary access filter">
    <option value="all" selected>All primary access</option>
    <option value="has_primary_1km">Has primary <=1km</option>
    <option value="has_ranked_primary_1km">Has ranked primary <=1km</option>
    <option value="no_primary_1km">No primary <=1km</option>
  </select>
  <div class="count"><span id="visibleCount">{{PROJECT_COUNT}}</span> visible</div>
</div>

<div class="tbl-wrap">
<table>
<thead>
  <tr class="group">
    <th colspan="3" class="g-project"><span class="tip" data-tip="Project identity from URA private transaction records.">Project</span></th>
    <th colspan="7" class="g-location"><span class="tip" data-tip="Postal, planning-area, MRT, and coordinate-source fields used for filtering and spatial context.">Location Filters</span></th>
    <th colspan="8" class="g-school"><span class="tip" data-tip="Project-level school access diagnostics from matched geocodes and sourced selectivity proxies.">Schools</span></th>
    <th colspan="7" class="g-price"><span class="tip" data-tip="Project transaction prices compared with district and recent project medians.">Price Comparison</span></th>
    <th colspan="5" class="g-txn"><span class="tip" data-tip="Transaction sample depth, dates, sale types, tenure, and market segment.">Transaction Profile</span></th>
    <th colspan="4" class="g-model"><span class="tip" data-tip="Estate-level framework context joined to the private project row; not project-level scores.">Estate Context</span></th>
  </tr>
  <tr class="cols">
    <th data-sort="project" onclick="sortTable('project', this)"><span class="tip" data-tip="Private project name from URA transactions, grouped with street, district, and planning area.">Project</span></th>
    <th data-sort="street" onclick="sortTable('street', this)"><span class="tip" data-tip="Street name reported in the URA private transaction feed.">Street</span></th>
    <th data-sort="property_type" onclick="sortTable('property_type', this)"><span class="tip" data-tip="Dominant private property type in this project group.">Type</span></th>
    <th data-sort="district" onclick="sortTable('district', this)"><span class="tip" data-tip="Postal district from the private transaction record.">District</span></th>
    <th data-sort="planning_area" onclick="sortTable('planning_area', this)"><span class="tip" data-tip="Planning area used to join project rows to estate-level framework context.">Planning area</span></th>
    <th data-sort="station" onclick="sortTable('station', this)"><span class="tip" data-tip="Nearest MRT or LRT station from the project geocode, or from centroid fallback when no project geocode exists.">MRT station</span></th>
    <th data-sort="line" onclick="sortTable('line', this)"><span class="tip" data-tip="Line code for the nearest MRT or LRT station.">Line</span></th>
    <th data-sort="station_distance_m" onclick="sortTable('station_distance_m', this)"><span class="tip" data-tip="Straight-line distance in metres to the nearest MRT or LRT station.">MRT dist</span></th>
    <th data-sort="location_source" onclick="sortTable('location_source', this)"><span class="tip" data-tip="Whether spatial fields use a project OneMap geocode or a planning-area/estate centroid fallback.">Source</span></th>
    <th data-sort="geocode_score" onclick="sortTable('geocode_score', this)"><span class="tip" data-tip="OneMap match score for project geocodes; blank for centroid fallback rows.">Geocode</span></th>
    <th data-sort="primary_1km_count" onclick="sortTable('primary_1km_count', this)"><span class="tip" data-tip="Number of MOE primary schools within 1km of the matched project coordinate.">Primary 1km</span></th>
    <th data-sort="best_primary_1km_school" onclick="sortTable('best_primary_1km_school', this)"><span class="tip" data-tip="Best ranked primary school within 1km, using the sourced selectivity proxy when available.">Best primary</span></th>
    <th data-sort="best_primary_1km_rank" onclick="sortTable('best_primary_1km_rank', this)"><span class="tip" data-tip="Rank of the best primary proxy within 1km; lower rank is more selective.">P rank</span></th>
    <th data-sort="best_primary_1km_distance_m" onclick="sortTable('best_primary_1km_distance_m', this)"><span class="tip" data-tip="Distance in metres to the best ranked primary school within 1km.">P dist</span></th>
    <th data-sort="best_secondary_2km_school" onclick="sortTable('best_secondary_2km_school', this)"><span class="tip" data-tip="Best ranked secondary school within 2km, using the sourced selectivity proxy when available.">Best sec</span></th>
    <th data-sort="best_secondary_2km_rank" onclick="sortTable('best_secondary_2km_rank', this)"><span class="tip" data-tip="Rank of the best secondary proxy within 2km; lower rank is more selective.">S rank</span></th>
    <th data-sort="best_jc_5km_school" onclick="sortTable('best_jc_5km_school', this)"><span class="tip" data-tip="Best ranked junior college or Year 5 school within 5km, using the sourced selectivity proxy when available.">Best JC</span></th>
    <th data-sort="best_jc_5km_rank" onclick="sortTable('best_jc_5km_rank', this)"><span class="tip" data-tip="Rank of the best JC proxy within 5km; lower rank is more selective.">JC rank</span></th>
    <th data-sort="n" onclick="sortTable('n', this)"><span class="tip" data-tip="Total transaction count in the grouped project record.">n</span></th>
    <th data-sort="recent_n" onclick="sortTable('recent_n', this)"><span class="tip" data-tip="Transaction count from the recent comparison window.">Recent n</span></th>
    <th data-sort="median_psm" onclick="sortTable('median_psm', this)"><span class="tip" data-tip="Median transacted price per square metre across project transactions.">Median $psm</span></th>
    <th data-sort="recent_median_psm" onclick="sortTable('recent_median_psm', this)"><span class="tip" data-tip="Recent-window median transacted price per square metre for this project.">Recent $psm</span></th>
    <th data-sort="district_delta_pct" onclick="sortTable('district_delta_pct', this)"><span class="tip" data-tip="Project median price per square metre versus its postal-district median.">vs district</span></th>
    <th data-sort="recent_delta_pct" onclick="sortTable('recent_delta_pct', this)"><span class="tip" data-tip="Recent median price per square metre versus the full project median.">Recent move</span></th>
    <th data-sort="median_price_mil" onclick="sortTable('median_price_mil', this)"><span class="tip" data-tip="Median transacted price in Singapore dollars, shown in millions.">Median price</span></th>
    <th data-sort="median_area_sqm" onclick="sortTable('median_area_sqm', this)"><span class="tip" data-tip="Median transacted unit area in square metres.">Median sqm</span></th>
    <th data-sort="first_sale" onclick="sortTable('first_sale', this)"><span class="tip" data-tip="Earliest transaction month observed for this project group.">First sale</span></th>
    <th data-sort="last_sale" onclick="sortTable('last_sale', this)"><span class="tip" data-tip="Latest transaction month observed for this project group.">Last sale</span></th>
    <th data-sort="sale_mix" onclick="sortTable('sale_mix', this)"><span class="tip" data-tip="Sale types present in the project record, such as New Sale, Resale, or Sub Sale.">Sale mix</span></th>
    <th data-sort="tenure" onclick="sortTable('tenure', this)"><span class="tip" data-tip="Dominant tenure text reported for transactions in this project group.">Tenure</span></th>
    <th data-sort="market_segment" onclick="sortTable('market_segment', this)"><span class="tip" data-tip="URA market segment, such as CCR, RCR, or OCR.">Market</span></th>
    <th data-sort="context_area" onclick="sortTable('context_area', this)"><span class="tip" data-tip="Estate or planning-area context used for framework joins.">Context estate</span></th>
    <th data-sort="provision_band" onclick="sortTable('provision_band', this)"><span class="tip" data-tip="Estate-level Provision band. This is context for the project, not a project-level score.">Prov</span></th>
    <th data-sort="private_value_band" onclick="sortTable('private_value_band', this)"><span class="tip" data-tip="Estate-level private value band from the framework, kept separate from HDB value.">Private value</span></th>
    <th data-sort="private_value_n" onclick="sortTable('private_value_n', this)"><span class="tip" data-tip="Estate-level private value sample count used by the value model.">Value n</span></th>
  </tr>
</thead>
<tbody id="tbody"></tbody>
</table>
</div>

<script>
const DATA = {{DATA_JSON}};
const NUMERIC_FIELDS = new Set([
  "n", "recent_n", "median_psm", "recent_median_psm", "district_delta_pct",
  "recent_delta_pct", "median_price_mil", "median_area_sqm", "station_distance_m",
  "provision_score", "private_value_score", "private_value_n", "geocode_score",
  "primary_1km_count", "primary_1km_ranked_count", "top_primary_1km_count",
  "best_primary_1km_rank", "best_primary_1km_distance_m", "secondary_2km_count",
  "best_secondary_2km_rank", "best_secondary_2km_distance_m", "jc_5km_count",
  "best_jc_5km_rank", "best_jc_5km_distance_m"
]);
const BAND_ORDER = {A: 6, "B+": 5, B: 4, C: 3, D: 2, F: 1};

let filtered = DATA.slice();
let sortField = "district";
let sortAsc = true;

function escapeHTML(value) {
  return String(value ?? "-").replace(/[&<>"']/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[ch]));
}
function moneyPSM(value) {
  if (value === null || value === undefined) return '<span class="muted">-</span>';
  return `<span class="money">$${Number(value).toLocaleString()}</span>`;
}
function moneyMil(value) {
  if (value === null || value === undefined) return '<span class="muted">-</span>';
  return `<span class="money">$${Number(value).toFixed(2)}m</span>`;
}
function plain(value) {
  if (value === null || value === undefined || value === "") return '<span class="muted">-</span>';
  return escapeHTML(value);
}
function distance(value) {
  if (value === null || value === undefined) return '<span class="muted">-</span>';
  return `<span class="muted">${Number(value).toLocaleString()}m</span>`;
}
function deltaHTML(value) {
  if (value === null || value === undefined) return '<span class="muted">-</span>';
  const cls = value >= 10 ? "delta-high" : value <= -10 ? "delta-low" : Math.abs(value) >= 5 ? "delta-mid" : "delta-flat";
  const sign = value > 0 ? "+" : "";
  return `<span class="${cls}">${sign}${Number(value).toFixed(1)}%</span>`;
}
function bandHTML(value) {
  if (!value || value === "-") return '<span class="band b-NR">-</span>';
  const cls = value === "B+" ? "b-Bp" : `b-${value}`;
  return `<span class="band ${cls in document.documentElement.style ? "b-NR" : cls}">${escapeHTML(value)}</span>`;
}
function bandClass(value) {
  if (!value || value === "-") return "b-NR";
  return {A: "b-A", "B+": "b-Bp", B: "b-B", C: "b-C", D: "b-D", F: "b-F"}[value] || "b-NR";
}
function bandPill(value) {
  if (!value || value === "-") return '<span class="band b-NR">-</span>';
  return `<span class="band ${bandClass(value)}">${escapeHTML(value)}</span>`;
}
function statusHTML(row) {
  const cls = row.station_status === "Open" ? "status-open" : "status-future";
  return `<span class="status ${cls}">${escapeHTML(row.station_status)}</span>`;
}
function sourceHTML(row) {
  if (row.location_source === "project_geocode") return '<span class="source source-geocode">geocode</span>';
  return '<span class="source source-proxy">centroid</span>';
}
function geocodeHTML(row) {
  if (row.location_source !== "project_geocode") return '<span class="muted">missing</span>';
  const score = row.geocode_score === null || row.geocode_score === undefined ? "-" : row.geocode_score;
  return `<span class="muted">${escapeHTML(row.geocode_status)} ${escapeHTML(score)}</span>`;
}
function primaryHTML(row) {
  if (row.primary_1km_count === null || row.primary_1km_count === undefined) return '<span class="muted">-</span>';
  const cls = row.has_primary_1km ? "school-yes" : "school-no";
  const label = row.has_primary_1km ? "yes" : "no";
  const schools = row.primary_1km_schools ? row.primary_1km_schools : "No primary schools within 1km";
  return `<span class="row-tip" data-tip="${escapeHTML(schools)}"><span class="source ${cls}">${label}</span> <span class="muted">${Number(row.primary_1km_count).toLocaleString()}</span></span>`;
}
function schoolHTML(value) {
  if (!value) return '<span class="muted">-</span>';
  return escapeHTML(value);
}
function rankHTML(value) {
  if (value === null || value === undefined) return '<span class="muted">-</span>';
  return `<span class="money">#${Number(value).toLocaleString()}</span>`;
}
function contextHTML(row) {
  const proxy = row.context_basis && row.context_basis !== "direct" ? ` <span class="muted">(${escapeHTML(row.context_basis)})</span>` : "";
  return `${escapeHTML(row.context_area)}${proxy}`;
}
function renderRow(row) {
  return `<tr>
    <td class="project-name">${escapeHTML(row.project)}</td>
    <td class="street-name">${escapeHTML(row.street)}</td>
    <td>${plain(row.property_type)}</td>
    <td>D${escapeHTML(row.district)}</td>
    <td>${escapeHTML(row.planning_area)}</td>
    <td>${escapeHTML(row.station)} <span class="muted">${escapeHTML(row.station_code)}</span> ${statusHTML(row)}</td>
    <td><span class="line-badge">${escapeHTML(row.line_short)}</span></td>
    <td>${distance(row.station_distance_m)}</td>
    <td>${sourceHTML(row)}</td>
    <td>${geocodeHTML(row)}</td>
    <td>${primaryHTML(row)}</td>
    <td class="street-name">${schoolHTML(row.best_primary_1km_school)}</td>
    <td>${rankHTML(row.best_primary_1km_rank)}</td>
    <td>${distance(row.best_primary_1km_distance_m)}</td>
    <td class="street-name">${schoolHTML(row.best_secondary_2km_school)}</td>
    <td>${rankHTML(row.best_secondary_2km_rank)}</td>
    <td class="street-name">${schoolHTML(row.best_jc_5km_school)}</td>
    <td>${rankHTML(row.best_jc_5km_rank)}</td>
    <td>${Number(row.n).toLocaleString()}</td>
    <td>${Number(row.recent_n).toLocaleString()}</td>
    <td>${moneyPSM(row.median_psm)}</td>
    <td>${moneyPSM(row.recent_median_psm)}</td>
    <td>${deltaHTML(row.district_delta_pct)}</td>
    <td>${deltaHTML(row.recent_delta_pct)}</td>
    <td>${moneyMil(row.median_price_mil)}</td>
    <td>${Number(row.median_area_sqm).toLocaleString()}</td>
    <td class="muted">${plain(row.first_sale)}</td>
    <td class="muted">${plain(row.last_sale)}</td>
    <td class="muted">${escapeHTML(row.sale_mix)}</td>
    <td class="muted">${escapeHTML(row.tenure)}</td>
    <td class="muted">${escapeHTML(row.market_segment)}</td>
    <td class="context">${contextHTML(row)}</td>
    <td>${bandPill(row.provision_band)}</td>
    <td>${bandPill(row.private_value_band)}</td>
    <td class="muted">${row.private_value_n !== null && row.private_value_n !== undefined ? Number(row.private_value_n).toLocaleString() : "-"}</td>
  </tr>`;
}
function compareValues(a, b, field) {
  let av = a[field], bv = b[field];
  if (field === "provision_band" || field === "private_value_band") {
    av = BAND_ORDER[av] || 0;
    bv = BAND_ORDER[bv] || 0;
  } else if (NUMERIC_FIELDS.has(field)) {
    av = av === null || av === undefined ? -Infinity : Number(av);
    bv = bv === null || bv === undefined ? -Infinity : Number(bv);
  } else {
    av = String(av ?? "");
    bv = String(bv ?? "");
  }
  if (typeof av === "number" && typeof bv === "number") return av - bv;
  return av.localeCompare(bv);
}
function renderRows() {
  document.getElementById("tbody").innerHTML = filtered.map(renderRow).join("");
  document.getElementById("visibleCount").textContent = filtered.length.toLocaleString();
}
function selectedValues(id) {
  return Array.from(document.getElementById(id).selectedOptions)
    .map(option => option.value)
    .filter(value => value !== "all");
}
function matchesSelected(values, value) {
  return values.length === 0 || values.includes(String(value));
}
function matchesSale(values, saleMix) {
  return values.length === 0 || values.some(value => String(saleMix ?? "").includes(value));
}
function matchesPrimary(values, row) {
  if (values.length === 0) return true;
  return values.some(value =>
    (value === "has_primary_1km" && row.has_primary_1km === true) ||
    (value === "has_ranked_primary_1km" && row.has_ranked_primary_1km === true) ||
    (value === "no_primary_1km" && row.has_primary_1km === false)
  );
}
function applyFilters() {
  const search = document.getElementById("search").value.trim().toLowerCase();
  const districts = selectedValues("districtFilter");
  const stations = selectedValues("stationFilter");
  const sales = selectedValues("saleFilter");
  const sources = selectedValues("sourceFilter");
  const primaryValues = selectedValues("primaryFilter");
  filtered = DATA.filter(row => {
    const searchText = [
      row.project, row.street, row.district, row.planning_area, row.station, row.station_code,
      row.line, row.location_source, row.best_primary_1km_school, row.best_secondary_2km_school,
      row.best_jc_5km_school
    ].join(" ").toLowerCase();
    const searchOk = !search || searchText.includes(search);
    const districtOk = matchesSelected(districts, row.district);
    const stationOk = matchesSelected(stations, row.station_key);
    const saleOk = matchesSale(sales, row.sale_mix);
    const sourceOk = matchesSelected(sources, row.location_source);
    const primaryOk = matchesPrimary(primaryValues, row);
    return searchOk && districtOk && stationOk && saleOk && sourceOk && primaryOk;
  });
  filtered.sort((a, b) => {
    const cmp = compareValues(a, b, sortField);
    return sortAsc ? cmp : -cmp;
  });
  renderRows();
}
function sortTable(field, th) {
  document.querySelectorAll("thead tr.cols th").forEach(el => el.classList.remove("sorted", "sorted-asc", "sorted-desc"));
  if (sortField === field) sortAsc = !sortAsc;
  else { sortField = field; sortAsc = true; }
  th.classList.add("sorted", sortAsc ? "sorted-asc" : "sorted-desc");
  applyFilters();
}
applyFilters();
</script>
</body>
</html>
"""

    return (
        html_template
        .replace("{{DATA_JSON}}", data_js)
        .replace("{{STATION_OPTIONS}}", station_options)
        .replace("{{DISTRICT_OPTIONS}}", district_options)
        .replace("{{PROJECT_COUNT}}", f"{project_count:,}")
        .replace("{{TRANSACTION_COUNT}}", f"{transaction_count:,}")
        .replace("{{DISTRICT_COUNT}}", f"{district_count:,}")
        .replace("{{STATION_COUNT}}", f"{station_count:,}")
        .replace("{{GEOCODED_COUNT}}", f"{geocoded_count:,}")
        .replace("{{CENTROID_COUNT}}", f"{centroid_count:,}")
        .replace("{{SCHOOL_METRICS_COUNT}}", f"{school_metrics_count:,}")
        .replace("{{LATEST_MONTH}}", latest_month or "-")
        .replace("{{TODAY}}", today)
    )


def generate(
    private_path: pathlib.Path,
    location_path: pathlib.Path,
    school_metrics_path: pathlib.Path,
    out_path: pathlib.Path,
) -> tuple[pathlib.Path, int]:
    private = load_private(private_path)
    project_locations = load_project_locations(location_path)
    school_metrics = load_school_metrics(school_metrics_path)
    estates = pd.read_csv(ROOT / "data/inputs/estates.csv")
    mrt = pd.read_csv(ROOT / "data/inputs/mrt_layer.csv")
    master = pd.read_csv(ROOT / "data/outputs/master_output.csv").set_index("estate")

    rows = aggregate_projects(private, estates, mrt, master, project_locations, school_metrics)
    latest_month = month_text(private["sale_month_dt"].max())
    html_text = render_html(rows, latest_month)
    out_path.write_text(html_text, encoding="utf-8")
    return out_path, len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate private condo project comparison HTML")
    parser.add_argument("--private", default=str(ROOT / "data/inputs/ura_private.csv"), help="URA private transaction CSV")
    parser.add_argument(
        "--locations",
        default=str(DEFAULT_LOCATION_PATH),
        help="Optional private project geocode CSV from models/geocode_private_projects.py",
    )
    parser.add_argument(
        "--school-metrics",
        default=str(DEFAULT_SCHOOL_METRICS_PATH),
        help="Optional project school diagnostics CSV from models/private_school_metrics.py",
    )
    parser.add_argument("--out", default=str(ROOT / "private_project_comparison_table.html"), help="HTML output path")
    args = parser.parse_args()

    out_path, row_count = generate(
        pathlib.Path(args.private),
        pathlib.Path(args.locations),
        pathlib.Path(args.school_metrics),
        pathlib.Path(args.out),
    )
    print(f"Written: {out_path} ({out_path.stat().st_size // 1024} KB, {row_count} project records)")


if __name__ == "__main__":
    main()
