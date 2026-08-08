"""Internal MRT comparison renderer; execute through ``mrt_comparison.build``.

The report joins each committed station-code record to the nearest framework
estate centroid.  That spatial join is context only: it is neither a formal
station catchment nor a station-level Provision, Liveability or Value score.
"""

from __future__ import annotations

from datetime import date
import math
from pathlib import Path
import re
from typing import Any

import pandas as pd

from sg_estate.paths import REPOSITORY_ROOT as ROOT
from sg_estate.domain.value import CFG as VALUE_CFG
from sg_estate.reporting.common import (
    atomic_write_text,
    html_json,
    optional_float,
    optional_value,
)


DEFAULT_MRT = ROOT / "data/inputs/mrt_layer.csv"
DEFAULT_ESTATES = ROOT / "data/inputs/estates.csv"
DEFAULT_MASTER = ROOT / "data/outputs/master_output.csv"
DEFAULT_OUT = ROOT / "mrt_comparison_table.html"
TEMPLATE = ROOT / "sg_estate/reporting/templates/mrt_comparison_table.html"
VALUE_TRUST_THRESHOLD = int(VALUE_CFG["trust_decimal_n"])

MRT_COLUMNS = {
    "lat",
    "lon",
    "name",
    "stn_code",
    "line",
    "operational",
    "network_status",
    "planned_opening",
    "status_as_of",
    "network_status_source",
    "geometry_basis",
    "geometry_source",
}
NETWORK_STATUSES = {"open", "under_construction", "deferred", "planned"}
ESTATE_COLUMNS = {"estate", "lat", "lon"}
MASTER_COLUMNS = {
    "estate",
    "model_version",
    "archetype",
    "provision_band",
    "provision_score",
    "measured_only",
    "yf_T0_band",
    "sp_T0_band",
    "ret_T0_band",
    "ls_T0_band",
    "ls_T5_band",
    "ls_T15_band",
    "value_hdb_band",
    "value_hdb_basis",
    "value_hdb_n",
    "value_hdb_status",
    "value_private_band",
    "value_private_basis",
    "value_private_n",
    "value_private_status",
    "emp_band",
    "employment_status",
    "lease_band",
    "lease_status",
    "lease_source",
}

LINE_SHORT_NAMES = {
    "Bukit Panjang LRT": "BPLRT",
    "Changi Airport Branch Line": "CG",
    "Circle Line": "CCL",
    "Cross Island Line": "CRL",
    "Downtown Line": "DTL",
    "East West Line": "EWL",
    "East-West Line": "EWL",
    "Jurong Region Line": "JRL",
    "North East Line": "NEL",
    "North South Line": "NSL",
    "North-South Line": "NSL",
    "Punggol LRT": "PLRT",
    "Sengkang LRT": "SLRT",
    "Thomson-East Coast Line": "TEL",
}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two WGS84 points."""

    radius = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def distance_band(meters: float) -> str:
    """Bucket centroid distance without implying a walking catchment."""

    if meters <= 600:
        return "le600"
    if meters <= 1000:
        return "601-1000"
    if meters <= 1400:
        return "1001-1400"
    return "gt1400"


def clean_text(value: Any, default: str | None = None) -> str | None:
    value = optional_value(value)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def clean_band(value: Any) -> str | None:
    return clean_text(value)


def controlled_text(value: Any) -> str | None:
    """Preserve controlled states such as ``no_data`` and ``not_covered``."""

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def clean_number(value: Any, digits: int | None = None) -> float | None:
    number = optional_float(value)
    if number is None:
        return None
    return round(number, digits) if digits is not None else number


def clean_integer(value: Any) -> int | None:
    number = optional_float(value)
    return int(number) if number is not None else None


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def short_line(line: str) -> str:
    if line in LINE_SHORT_NAMES:
        return LINE_SHORT_NAMES[line]
    words = str(line).replace("-", " ").split()
    code = "".join(word[0].upper() for word in words if word.lower() not in {"line", "branch"})
    return code or "RAIL"


def _require_columns(frame: pd.DataFrame, required: set[str], path: Path) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")


def _validated_coordinates(frame: pd.DataFrame, path: Path) -> pd.DataFrame:
    result = frame.copy()
    for column in ("lat", "lon"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    invalid = result[~result["lat"].between(-90, 90) | ~result["lon"].between(-180, 180)]
    if not invalid.empty:
        raise SystemExit(f"{path} contains {len(invalid)} invalid coordinate row(s)")
    return result


def _context_value(context: pd.Series | None, column: str) -> Any:
    if context is None:
        return None
    return context.get(column)


def _masked_context_row(
    station: pd.Series,
    context: pd.Series | None,
    *,
    nearest_estate: str,
    nearest_m: float,
    centroids_800m: int,
    centroids_1400m: int,
) -> dict[str, Any]:
    line = clean_text(station["line"], "Unspecified line") or "Unspecified line"
    archetype = clean_text(_context_value(context, "archetype"))
    context_status = (
        "unavailable"
        if context is None
        else "not_residential"
        if archetype == "X"
        else "out_of_range"
        if nearest_m > 1400
        else "available"
    )
    publish_model = context_status == "available"

    def model_text(column: str) -> str | None:
        return controlled_text(_context_value(context, column)) if publish_model else None

    def model_band(column: str) -> str | None:
        return clean_band(_context_value(context, column)) if publish_model else None

    def model_number(column: str, digits: int | None = None) -> float | None:
        return clean_number(_context_value(context, column), digits) if publish_model else None

    status = "open" if clean_integer(station["operational"]) == 1 else "future"
    network_status = controlled_text(station.get("network_status")) or status
    mode = "lrt" if "lrt" in line.lower() else "mrt"
    return {
        "station": clean_text(station["name"], "Unnamed station"),
        "code": clean_text(station["stn_code"], "No code"),
        "line": line,
        "line_key": slug(line),
        "line_short": short_line(line),
        "mode": mode,
        "status": status,
        "network_status": network_status,
        "planned_opening": controlled_text(station.get("planned_opening")),
        "status_as_of": controlled_text(station.get("status_as_of")),
        "network_status_source": controlled_text(station.get("network_status_source")),
        "geometry_basis": controlled_text(station.get("geometry_basis")),
        "geometry_source": controlled_text(station.get("geometry_source")),
        "lat": round(float(station["lat"]), 6),
        "lon": round(float(station["lon"]), 6),
        "estate": nearest_estate,
        "distance_m": int(round(nearest_m)),
        "distance_band": distance_band(nearest_m),
        "centroids_800m": centroids_800m,
        "centroids_1400m": centroids_1400m,
        "context_status": context_status,
        "archetype": archetype if publish_model else None,
        "provision_band": model_band("provision_band"),
        "provision_score": model_number("provision_score", 2),
        "measured_only": bool_value(_context_value(context, "measured_only")) if publish_model else False,
        "yf0": model_band("yf_T0_band"),
        "sp0": model_band("sp_T0_band"),
        "ret0": model_band("ret_T0_band"),
        "ls0": model_band("ls_T0_band"),
        "ls5": model_band("ls_T5_band"),
        "ls15": model_band("ls_T15_band"),
        "hdb_value_band": model_band("value_hdb_band"),
        "hdb_value_basis": model_text("value_hdb_basis"),
        "hdb_value_n": model_number("value_hdb_n"),
        "hdb_value_status": model_text("value_hdb_status") or ("unavailable" if publish_model else context_status),
        "private_value_band": model_band("value_private_band"),
        "private_value_basis": model_text("value_private_basis"),
        "private_value_n": model_number("value_private_n"),
        "private_value_status": model_text("value_private_status") or ("unavailable" if publish_model else context_status),
        "employment_band": model_band("emp_band"),
        "employment_status": model_text("employment_status") or ("unavailable" if publish_model else context_status),
        "lease_band": model_band("lease_band"),
        "lease_status": model_text("lease_status") or ("unavailable" if publish_model else context_status),
        "lease_source": model_text("lease_source"),
    }


def load_rows(
    mrt_path: Path = DEFAULT_MRT,
    estates_path: Path = DEFAULT_ESTATES,
    master_path: Path = DEFAULT_MASTER,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str, int]:
    """Load and join canonical inputs, returning rows and display metadata."""

    mrt = pd.read_csv(mrt_path)
    estates = pd.read_csv(estates_path)
    master = pd.read_csv(master_path)
    _require_columns(mrt, MRT_COLUMNS, mrt_path)
    _require_columns(estates, ESTATE_COLUMNS, estates_path)
    _require_columns(master, MASTER_COLUMNS, master_path)
    mrt = _validated_coordinates(mrt, mrt_path)
    estates = _validated_coordinates(estates, estates_path)

    if mrt["stn_code"].astype(str).str.strip().duplicated().any():
        raise SystemExit(f"{mrt_path} contains duplicate station codes")
    if estates["estate"].astype(str).str.strip().duplicated().any():
        raise SystemExit(f"{estates_path} contains duplicate estate keys")
    if master["estate"].astype(str).str.strip().duplicated().any():
        raise SystemExit(f"{master_path} contains duplicate estate keys")

    operational = pd.to_numeric(mrt["operational"], errors="coerce")
    if not operational.isin([0, 1]).all():
        raise SystemExit(f"{mrt_path} operational must contain only 0 or 1")
    mrt = mrt.assign(operational=operational.astype(int))

    network_status = mrt["network_status"].astype(str).str.strip()
    invalid_statuses = sorted(set(network_status) - NETWORK_STATUSES)
    if invalid_statuses:
        raise SystemExit(
            f"{mrt_path} network_status has invalid values: {invalid_statuses}"
        )
    mismatched_status = (mrt["operational"] == 1) != network_status.eq("open")
    if mismatched_status.any():
        raise SystemExit(
            f"{mrt_path} operational and network_status disagree on "
            f"{int(mismatched_status.sum())} row(s)"
        )
    status_dates = mrt["status_as_of"].astype(str).str.strip()
    if status_dates.nunique() != 1:
        raise SystemExit(f"{mrt_path} must contain one consistent status_as_of date")
    try:
        date.fromisoformat(status_dates.iloc[0])
    except ValueError as error:
        raise SystemExit(f"{mrt_path} status_as_of must be an ISO date") from error
    for column in (
        "name",
        "stn_code",
        "line",
        "network_status_source",
        "geometry_basis",
        "geometry_source",
    ):
        if mrt[column].isna().any() or mrt[column].astype(str).str.strip().eq("").any():
            raise SystemExit(f"{mrt_path} {column} must be populated on every row")
    mrt = mrt.assign(network_status=network_status, status_as_of=status_dates)

    estate_points = [
        (clean_text(row["estate"], "") or "", float(row["lat"]), float(row["lon"]))
        for _, row in estates.iterrows()
    ]
    if not estate_points:
        raise SystemExit(f"{estates_path} contains no estate centroids")
    context_by_estate = {
        clean_text(row["estate"], "") or "": row
        for _, row in master.iterrows()
    }

    rows: list[dict[str, Any]] = []
    for _, station in mrt.iterrows():
        slat = float(station["lat"])
        slon = float(station["lon"])
        distances = [
            (estate, haversine_m(slat, slon, latitude, longitude))
            for estate, latitude, longitude in estate_points
        ]
        nearest_estate, nearest_m = min(distances, key=lambda item: item[1])
        rows.append(
            _masked_context_row(
                station,
                context_by_estate.get(nearest_estate),
                nearest_estate=nearest_estate,
                nearest_m=nearest_m,
                centroids_800m=sum(distance <= 800 for _, distance in distances),
                centroids_1400m=sum(distance <= 1400 for _, distance in distances),
            )
        )

    rows.sort(key=lambda row: (str(row["station"]), str(row["code"])))
    line_summary = []
    for line, group in mrt.groupby("line", sort=True):
        line_text = clean_text(line, "Unspecified line") or "Unspecified line"
        line_summary.append(
            {
                "line": line_text,
                "line_key": slug(line_text),
                "line_short": short_line(line_text),
                "mode": "lrt" if "lrt" in line_text.lower() else "mrt",
                "records": int(len(group)),
                "open": int((group["operational"] == 1).sum()),
                "future": int((group["operational"] == 0).sum()),
            }
        )

    model_versions = sorted(
        {
            str(value).strip()
            for value in master["model_version"].dropna()
            if str(value).strip()
        }
    )
    model_version = ", ".join(model_versions) or "not recorded"
    return rows, line_summary, model_version, len(estate_points)


def render_html(
    rows: list[dict[str, Any]] | None = None,
    line_summary: list[dict[str, Any]] | None = None,
    *,
    model_version: str | None = None,
    estate_count: int | None = None,
    generated_on: date | str | None = None,
) -> str:
    """Render the station explorer without writing its public artifact."""

    if rows is None or line_summary is None or model_version is None or estate_count is None:
        loaded_rows, loaded_lines, loaded_version, loaded_estates = load_rows()
        rows = loaded_rows if rows is None else rows
        line_summary = loaded_lines if line_summary is None else line_summary
        model_version = loaded_version if model_version is None else model_version
        estate_count = loaded_estates if estate_count is None else estate_count

    generated_on = generated_on or date.today()
    if isinstance(generated_on, str):
        generated_date = date.fromisoformat(generated_on)
    else:
        generated_date = generated_on

    open_count = sum(row["status"] == "open" for row in rows)
    future_count = sum(row["status"] == "future" for row in rows)
    status_dates = sorted(
        {
            str(row["status_as_of"]).strip()
            for row in rows
            if row.get("status_as_of") and str(row["status_as_of"]).strip()
        }
    )
    status_as_of = status_dates[-1] if status_dates else "not recorded"
    try:
        parsed_status_date = date.fromisoformat(status_as_of)
        status_as_of_label = f"{parsed_status_date.day} {parsed_status_date:%b %Y}"
    except ValueError:
        status_as_of_label = status_as_of
    html = TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "__STATION_COUNT__": str(len(rows)),
        "__LINE_COUNT__": str(len(line_summary)),
        "__OPEN_COUNT__": str(open_count),
        "__FUTURE_COUNT__": str(future_count),
        "__ESTATE_COUNT__": str(estate_count),
        "__MODEL_VERSION__": model_version,
        "__VALUE_TRUST_THRESHOLD__": str(VALUE_TRUST_THRESHOLD),
        "__GENERATED_DATE_ISO__": generated_date.isoformat(),
        "__GENERATED_DATE_LABEL__": f"{generated_date.day} {generated_date:%b %Y}",
        "__STATUS_AS_OF__": status_as_of,
        "__STATUS_AS_OF_LABEL__": status_as_of_label,
        "__MRT_COMPARISON_DATA_JSON__": html_json(rows, indent=2),
        "__MRT_LINE_SUMMARY_JSON__": html_json(line_summary, indent=2),
        "__MRT_CONFIG_JSON__": html_json(
            {
                "value_trust_threshold": VALUE_TRUST_THRESHOLD,
                "status_as_of": status_as_of,
                "planned_horizon": 2031,
            }
        ),
    }
    for marker, value in replacements.items():
        html = html.replace(marker, str(value))
    unresolved = [marker for marker in replacements if marker in html]
    if unresolved:
        raise RuntimeError(f"Unresolved MRT comparison template markers: {unresolved}")
    return html


def main() -> None:
    rows, line_summary, model_version, estate_count = load_rows()
    output = atomic_write_text(
        DEFAULT_OUT,
        render_html(
            rows,
            line_summary,
            model_version=model_version,
            estate_count=estate_count,
        ),
    )
    print(
        f"Written: {output} ({output.stat().st_size // 1024} KB, "
        f"{len(rows)} station-code records)"
    )


if __name__ == "__main__":
    main()
