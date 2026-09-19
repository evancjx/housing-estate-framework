#!/usr/bin/env python3
"""
Generate the focused private-project explorer from committed URA private data.

Reads:
  data/inputs/ura_private.csv      - URA private residential transactions
  data/outputs/private_project_locations.csv - optional OneMap-geocoded project points
  data/outputs/private_project_school_metrics.csv - optional project school diagnostics
  data/inputs/mrt_layer.csv        - station coordinates, line, operational flag
  data/inputs/estates.csv          - framework estate centroids
  data/outputs/master_output.csv    - estate-level model context

Writes:
  private_project_comparison_table.html

Presentation:
  sg_estate/reporting/templates/private_project_comparison_table.html
  site/assets/private-project-comparison.css
  site/assets/private-project-comparison.js

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
import hashlib
import html
import json
import math
import pathlib
import re
import sys
from datetime import date
from typing import Any

import pandas as pd

import private_project_catalog

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sg_estate.domain.value import CFG as VALUE_CFG  # noqa: E402
from sg_estate.project_locations import (  # noqa: E402
    ProjectLocationContractError,
    load_usable_project_locations,
)

DEFAULT_LOCATION_PATH = ROOT / "data/outputs/private_project_locations.csv"
DEFAULT_SCHOOL_METRICS_PATH = ROOT / "data/outputs/private_project_school_metrics.csv"
TEMPLATE_PATH = ROOT / "sg_estate/reporting/templates/private_project_comparison_table.html"
VALUE_TRUST_THRESHOLD = int(VALUE_CFG["trust_decimal_n"])
BOOTSTRAP_PROJECTS = 100
CATALOG_SCHEMA = private_project_catalog.CATALOG_SCHEMA
TRANSACTION_MANIFEST_PATH = ROOT / "site/assets/condo-transactions/manifest.json"
DEFAULT_PROJECT_CATALOG = ROOT / "site/assets/project-catalog/manifest.json"

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
    try:
        locations = load_usable_project_locations(path, missing_ok=True)
    except ProjectLocationContractError as exc:
        raise SystemExit(f"{path} has an invalid project-location contract: {exc}") from exc
    required = {"project_name", "street_name", "postal_district", "planning_area", "lat", "lon"}
    missing = sorted(required - set(locations.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")

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


def operational_station_records(mrt: pd.DataFrame) -> list[dict[str, Any]]:
    """Return current-service station memberships for access diagnostics."""

    if "operational" not in mrt.columns:
        raise ValueError("MRT layer is missing the operational column")
    operational = pd.to_numeric(mrt["operational"], errors="coerce")
    stations = mrt[operational.eq(1)]
    if stations.empty:
        raise ValueError("MRT layer contains no operational station rows")
    return list(stations.to_dict("records"))


def build_station_lookup(estates: pd.DataFrame, mrt: pd.DataFrame) -> dict[str, dict[str, Any]]:
    estate_rows = {
        str(row["estate"]).strip().upper(): row
        for _, row in estates.iterrows()
    }
    stations = operational_station_records(mrt)
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
            "context_status": "unavailable",
            "archetype": None,
            "provision_band": None,
            "provision_score": None,
            "private_value_band": None,
            "private_value_score": None,
            "private_value_n": None,
        }
    row = master.loc[context_area]
    archetype = normalise_name(row.get("archetype"), "-").upper()
    if archetype == "X":
        return {
            "context_status": "not_residential",
            "archetype": "X",
            "provision_band": None,
            "provision_score": None,
            "private_value_band": None,
            "private_value_score": None,
            "private_value_n": None,
        }
    private_n = value_or_none(row.get("value_private_n"))
    private_n_int = int(float(private_n)) if private_n is not None else None
    private_score = value_or_none(row.get("value_private_score"))
    return {
        "context_status": "available",
        "archetype": archetype if archetype != "-" else None,
        "provision_band": value_or_none(row.get("provision_band")),
        "provision_score": round(float(row["provision_score"]), 2)
        if value_or_none(row.get("provision_score")) is not None
        else None,
        "private_value_band": value_or_none(row.get("value_private_band")),
        "private_value_score": round(float(private_score), 2)
        if private_score is not None
        and private_n_int is not None
        and private_n_int >= VALUE_TRUST_THRESHOLD
        else None,
        "private_value_n": private_n_int,
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
    stations = operational_station_records(mrt)
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
        school = school_context(
            (school_metrics or {}).get(location_key) if location else None
        )
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
                "context_status": model_context["context_status"],
                "archetype": model_context["archetype"],
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


def _sha256_payload(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _transaction_dataset_revision() -> str:
    try:
        manifest = json.loads(TRANSACTION_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Cannot load transaction dataset revision from {TRANSACTION_MANIFEST_PATH}: {exc}"
        ) from exc
    revision = manifest.get("dataset_revision")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{64}", revision):
        raise RuntimeError("Transaction manifest has no valid dataset_revision")
    return revision


def _published_catalog_revisions(
    rows: list[dict[str, Any]],
    latest_month: str | None,
    catalog_path: pathlib.Path,
) -> tuple[str, str, list[dict[str, Any]]]:
    try:
        catalog = private_project_catalog.load_project_catalog(catalog_path)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot load shared project catalog {catalog_path}: {exc}") from exc
    required_keys = {
        "schema",
        "catalog_revision",
        "transaction_dataset_revision",
        "latest_project_month",
        "counts",
        "projects",
        "contexts",
    }
    if not isinstance(catalog, dict) or set(catalog) != required_keys:
        raise RuntimeError("Shared project catalog has an unexpected top-level contract")
    if catalog.get("schema") != CATALOG_SCHEMA:
        raise RuntimeError(f"Shared project catalog schema must be {CATALOG_SCHEMA}")
    catalog_revision = catalog.get("catalog_revision")
    transaction_revision = catalog.get("transaction_dataset_revision")
    if not isinstance(catalog_revision, str) or not re.fullmatch(
        r"[0-9a-f]{64}", catalog_revision
    ):
        raise RuntimeError("Shared project catalog has no valid catalog_revision")
    if not isinstance(transaction_revision, str) or not re.fullmatch(
        r"[0-9a-f]{64}", transaction_revision
    ):
        raise RuntimeError("Shared project catalog has no valid transaction revision")
    if transaction_revision != _transaction_dataset_revision():
        raise RuntimeError("Shared project catalog transaction revision is stale")
    if catalog.get("latest_project_month") != latest_month:
        raise RuntimeError("Shared project catalog latest month differs from explorer data")

    projects = catalog.get("projects")
    if not isinstance(projects, list):
        raise RuntimeError("Shared project catalog projects must be an array")
    explorer_projects = private_project_catalog.explorer_projects(catalog)
    def identity(row: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            normalise_name(row.get("project")),
            normalise_name(row.get("street")),
            normalise_district(row.get("district")),
            normalise_name(row.get("planning_area")),
        )

    published_by_identity = {identity(project): project for project in explorer_projects}
    if len(published_by_identity) != len(explorer_projects) or set(
        published_by_identity
    ) != {identity(row) for row in rows}:
        raise RuntimeError(
            "Shared project catalog private-explorer membership differs from generated rows"
        )
    for row in rows:
        published = published_by_identity[identity(row)]
        if any(published.get(field) != value for field, value in row.items()):
            raise RuntimeError(
                "Shared project catalog private-explorer evidence differs from generated rows"
            )
    return catalog_revision, transaction_revision, explorer_projects


def render_html(
    rows: list[dict[str, Any]],
    latest_month: str | None,
    *,
    generated_on: date | None = None,
    catalog_revision: str | None = None,
    transaction_dataset_revision: str | None = None,
    catalog_projects: list[dict[str, Any]] | None = None,
) -> str:
    generated_on = generated_on or date.today()
    today = generated_on.isoformat()
    bootstrap_rows = sorted(
        catalog_projects or rows,
        key=lambda row: (
            normalise_name(row.get("project")).casefold(),
            normalise_name(row.get("street")).casefold(),
            normalise_district(row.get("district")),
        ),
    )[:BOOTSTRAP_PROJECTS]
    data_js = json.dumps(
        bootstrap_rows,
        ensure_ascii=True,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    transaction_dataset_revision = (
        transaction_dataset_revision or _transaction_dataset_revision()
    )
    catalog_revision = catalog_revision or _sha256_payload(
        {
            "schema": CATALOG_SCHEMA,
            "latest_project_month": latest_month,
            "transaction_dataset_revision": transaction_dataset_revision,
            "projects": rows,
        }
    )
    if not re.fullmatch(r"[0-9a-f]{64}", catalog_revision):
        raise ValueError("catalog_revision must be a lowercase SHA-256 digest")

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

    config = {
        "page_size": 100,
        "bootstrap_projects": len(bootstrap_rows),
        "explorer_fields": sorted(rows[0]) if rows else [],
        "catalog_path": private_project_catalog.catalog_asset_path(catalog_revision),
        "catalog_revision": catalog_revision,
        "transaction_dataset_revision": transaction_dataset_revision,
        "recent_window_months": 12,
        "value_trust_threshold": VALUE_TRUST_THRESHOLD,
        "latest_month": latest_month,
        "generated_on": today,
        "counts": {
            "projects": project_count,
            "transactions": transaction_count,
            "districts": district_count,
            "stations": station_count,
            "project_geocodes": geocoded_count,
            "centroid_fallbacks": centroid_count,
            "school_metrics": school_metrics_count,
        },
    }
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    replacements = {
        "__PROJECT_DATA_JSON__": data_js,
        "__PROJECT_CONFIG_JSON__": json.dumps(config, separators=(",", ":")).replace("</", "<\\/"),
        "__STATION_OPTIONS__": station_options,
        "__DISTRICT_OPTIONS__": district_options,
        "__PROJECT_COUNT__": f"{project_count:,}",
        "__PROJECT_COUNT_RAW__": str(project_count),
        "__TRANSACTION_COUNT__": f"{transaction_count:,}",
        "__DISTRICT_COUNT__": f"{district_count:,}",
        "__STATION_COUNT__": f"{station_count:,}",
        "__GEOCODED_COUNT__": f"{geocoded_count:,}",
        "__CENTROID_COUNT__": f"{centroid_count:,}",
        "__SCHOOL_METRICS_COUNT__": f"{school_metrics_count:,}",
        "__LATEST_MONTH__": latest_month or "",
        "__GENERATED_DATE_ISO__": today,
        "__GENERATED_DATE_LABEL__": f"{generated_on.day} {generated_on:%b %Y}",
    }
    for marker, value in replacements.items():
        template = template.replace(marker, value)
    unresolved = sorted(marker for marker in replacements if marker in template)
    if unresolved:
        raise RuntimeError(f"Unresolved private-project template markers: {unresolved}")
    return template



def generate(
    private_path: pathlib.Path,
    location_path: pathlib.Path,
    school_metrics_path: pathlib.Path,
    out_path: pathlib.Path,
    *,
    generated_on: date | None = None,
    catalog_revision: str | None = None,
    transaction_dataset_revision: str | None = None,
    project_catalog_path: pathlib.Path = DEFAULT_PROJECT_CATALOG,
) -> tuple[pathlib.Path, int]:
    private = load_private(private_path)
    project_locations = load_project_locations(location_path)
    school_metrics = load_school_metrics(school_metrics_path)
    estates = pd.read_csv(ROOT / "data/inputs/estates.csv")
    mrt = pd.read_csv(ROOT / "data/inputs/mrt_layer.csv")
    master = pd.read_csv(ROOT / "data/outputs/master_output.csv").set_index("estate")

    rows = aggregate_projects(private, estates, mrt, master, project_locations, school_metrics)
    latest_month = month_text(private["sale_month_dt"].max())
    catalog_projects: list[dict[str, Any]] | None = None
    if catalog_revision is None or transaction_dataset_revision is None:
        (
            published_catalog_revision,
            published_transaction_revision,
            catalog_projects,
        ) = (
            _published_catalog_revisions(rows, latest_month, project_catalog_path)
        )
        catalog_revision = catalog_revision or published_catalog_revision
        transaction_dataset_revision = (
            transaction_dataset_revision or published_transaction_revision
        )
    html_text = render_html(
        rows,
        latest_month,
        generated_on=generated_on,
        catalog_revision=catalog_revision,
        transaction_dataset_revision=transaction_dataset_revision,
        catalog_projects=catalog_projects,
    )
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
    parser.add_argument(
        "--project-catalog",
        default=str(DEFAULT_PROJECT_CATALOG),
        help="Published shared project catalog selector used to bind the page revision",
    )
    args = parser.parse_args()

    out_path, row_count = generate(
        pathlib.Path(args.private),
        pathlib.Path(args.locations),
        pathlib.Path(args.school_metrics),
        pathlib.Path(args.out),
        project_catalog_path=pathlib.Path(args.project_catalog),
    )
    print(f"Written: {out_path} ({out_path.stat().st_size // 1024} KB, {row_count} project records)")


if __name__ == "__main__":
    main()
