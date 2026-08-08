#!/usr/bin/env python3
"""Build the canonical MRT/LRT layer from versioned official source datasets.

The station coordinate in this layer is a *derived representative point*.  It
is not an official point supplied by LTA or URA.  Geometry is selected in this
order:

1. centroid of the union of matching LTA station polygons;
2. for open CCL6 stations absent from that polygon release, the mean of LTA
   station-exit points; and
3. for non-open stations still lacking geometry, the centroid of the union of
   matching URA rail-station outlines.

The official LTA station-code workbook is the open code/line-membership base.
Every downloaded geometry/code payload is SHA-256 pinned so mutable upstream
URLs cannot silently change a dated snapshot. ``mrt_network_status.csv``
applies the small, reviewable reconciliation needed for CCL6 and adds the
separately sourced future network overlay.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import tempfile
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd
import shapefile
from pyproj import Transformer
from shapely.geometry import shape as shapely_shape
from shapely.ops import unary_union


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS_FILE = REPO_ROOT / "data" / "inputs" / "mrt_network_status.csv"
DEFAULT_REGISTRY = REPO_ROOT / "data" / "inputs" / "mrt_source_registry.json"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "inputs" / "mrt_layer.csv"
DEFAULT_NAMES_OUTPUT = REPO_ROOT / "data" / "inputs" / "mrt_layer_names.csv"

STATUS_AS_OF = "2026-08-08"
ALLOWED_STATUSES = {"open", "under_construction", "deferred", "planned"}
LEGACY_COLUMNS = ["lat", "lon", "name", "stn_code", "line", "operational"]
PROVENANCE_COLUMNS = [
    "network_status",
    "planned_opening",
    "status_as_of",
    "network_status_source",
    "geometry_basis",
    "geometry_source",
]
OUTPUT_COLUMNS = LEGACY_COLUMNS + PROVENANCE_COLUMNS

REMOVED_CODES = {"CE1", "CE2"}
CCL6_OPENING = "2026-07-12"
CCL6_MEMBERSHIPS = {
    "CC30": ("Keppel", "Circle Line"),
    "CC31": ("Cantonment", "Circle Line"),
    "CC32": ("Prince Edward Road", "Circle Line"),
    "CC33": ("Marina Bay", "Circle Line"),
    "CC34": ("Bayfront", "Circle Line"),
}
FUTURE_MEMBERSHIPS = {
    "TE10": ("Mount Pleasant", "Thomson-East Coast Line", "deferred", "TBA"),
    "TE21": ("Marina South", "Thomson-East Coast Line", "deferred", "TBA"),
    "TE22A": ("Founders' Memorial", "Thomson-East Coast Line", "deferred", "TBA"),
    "TE30": ("Bedok South", "Thomson-East Coast Line", "under_construction", "2026-H2"),
    "TE31": ("Sungei Bedok", "Thomson-East Coast Line", "under_construction", "2026-H2"),
    "DT36": ("Xilin", "Downtown Line", "under_construction", "2026-H2"),
    "DT37": ("Sungei Bedok", "Downtown Line", "under_construction", "2026-H2"),
    "JS1": ("Choa Chu Kang", "Jurong Region Line", "planned", "2028"),
    "JS2": ("Choa Chu Kang West", "Jurong Region Line", "planned", "2028"),
    "JS3": ("Tengah", "Jurong Region Line", "planned", "2028"),
    "JS4": ("Hong Kah", "Jurong Region Line", "planned", "2028"),
    "JS5": ("Corporation", "Jurong Region Line", "planned", "2028"),
    "JS6": ("Jurong West", "Jurong Region Line", "planned", "2028"),
    "JS7": ("Bahar Junction", "Jurong Region Line", "planned", "2028"),
    "JS8": ("Boon Lay", "Jurong Region Line", "planned", "2028"),
    "JW1": ("Gek Poh", "Jurong Region Line", "planned", "2028"),
    "JW2": ("Tawas", "Jurong Region Line", "planned", "2028"),
    "JE1": ("Tengah Plantation", "Jurong Region Line", "planned", "2028"),
    "JE2": ("Tengah Park", "Jurong Region Line", "planned", "2028"),
    "JE3": ("Bukit Batok West", "Jurong Region Line", "planned", "2028"),
    "JE4": ("Toh Guan", "Jurong Region Line", "planned", "2028"),
    "JE5": ("Jurong East", "Jurong Region Line", "planned", "2028"),
    "JE6": ("Jurong Town Hall", "Jurong Region Line", "planned", "2028"),
    "JE7": ("Pandan Reservoir", "Jurong Region Line", "planned", "2028"),
    "JS9": ("Enterprise", "Jurong Region Line", "planned", "2029"),
    "JS10": ("Tukang", "Jurong Region Line", "planned", "2029"),
    "JS11": ("Jurong Hill", "Jurong Region Line", "planned", "2029"),
    "JS12": ("Jurong Pier", "Jurong Region Line", "planned", "2029"),
    "JW3": ("Nanyang Gateway", "Jurong Region Line", "planned", "2029"),
    "JW4": ("Nanyang Crescent", "Jurong Region Line", "planned", "2029"),
    "JW5": ("Peng Kang Hill", "Jurong Region Line", "planned", "2029"),
    "CR2": ("Aviation Park", "Cross Island Line", "planned", "2030"),
    "CR3": ("Loyang", "Cross Island Line", "planned", "2030"),
    "CR4": ("Pasir Ris East", "Cross Island Line", "planned", "2030"),
    "CR5": ("Pasir Ris", "Cross Island Line", "planned", "2030"),
    "CR6": ("Tampines North", "Cross Island Line", "planned", "2030"),
    "CR7": ("Defu", "Cross Island Line", "planned", "2030"),
    "CR8": ("Hougang", "Cross Island Line", "planned", "2030"),
    "CR9": ("Serangoon North", "Cross Island Line", "planned", "2030"),
    "CR10": ("Tavistock", "Cross Island Line", "planned", "2030"),
    "CR11": ("Ang Mo Kio", "Cross Island Line", "planned", "2030"),
    "CR12": ("Teck Ghee", "Cross Island Line", "planned", "2030"),
    "CR13": ("Bright Hill", "Cross Island Line", "planned", "2030"),
}
DEFERRED_CODES = {
    code for code, membership in FUTURE_MEMBERSHIPS.items()
    if membership[2] == "deferred"
}
UNDER_CONSTRUCTION_CODES = {
    code for code, membership in FUTURE_MEMBERSHIPS.items()
    if membership[2] == "under_construction"
}
JRL_CODES = {
    code for code, membership in FUTURE_MEMBERSHIPS.items()
    if membership[1] == "Jurong Region Line"
}
CRL1_CODES = {
    code for code, membership in FUTURE_MEMBERSHIPS.items()
    if membership[1] == "Cross Island Line"
}
EXPECTED_NON_OPEN_CODES = (
    DEFERRED_CODES | UNDER_CONSTRUCTION_CODES | JRL_CODES | CRL1_CODES
)
EXPECTED_STATUS_COUNTS = {
    "open": 216,
    "under_construction": 4,
    "deferred": 3,
    "planned": 36,
}

SOURCE_CODES = "lta_station_codes_jan_2025"
SOURCE_POLYGONS = "lta_train_station_mar_2026"
SOURCE_EXITS = "lta_train_station_exits_jul_2026"
SOURCE_URA = "ura_mp2019_rail_station_sep_2025"
SOURCE_SYSTEM_MAP = "lta_system_map_jul_2026"
STATUS_SOURCE_KEYS = {
    SOURCE_SYSTEM_MAP,
    "lta_ccl6_opening_jul_2026",
    "lta_tel_project",
    "lta_dtl_extensions",
    "lta_jrl_project",
    "lta_crl1_project",
}
EXPECTED_STATUS_SOURCE_BY_CODE = {
    **{code: SOURCE_SYSTEM_MAP for code in REMOVED_CODES},
    **{code: "lta_ccl6_opening_jul_2026" for code in CCL6_MEMBERSHIPS},
    **{
        code: "lta_tel_project"
        for code in {"TE10", "TE21", "TE22A", "TE30", "TE31"}
    },
    **{code: "lta_dtl_extensions" for code in {"DT36", "DT37"}},
    **{code: "lta_jrl_project" for code in JRL_CODES},
    **{code: "lta_crl1_project" for code in CRL1_CODES},
}
PINNED_DOWNLOAD_SOURCES = {
    SOURCE_CODES,
    SOURCE_POLYGONS,
    SOURCE_EXITS,
    SOURCE_URA,
}

_SVY21_TO_WGS84 = Transformer.from_crs("EPSG:3414", "EPSG:4326", always_xy=True)
_SPACE_RE = re.compile(r"\s+")
_STATION_SUFFIX_RE = re.compile(r"\s+(?:MRT|LRT)\s+STATION\s*$", re.IGNORECASE)
_INTERCHANGE_SUFFIX_RE = re.compile(r"\s+INTERCHANGE\s*$", re.IGNORECASE)


class RailDataError(ValueError):
    """Raised when an input cannot satisfy the rail-layer data contract."""


def clean_text(value: Any) -> str:
    """Return stable human-readable text without changing official spelling."""

    if value is None or pd.isna(value):
        return ""
    return _SPACE_RE.sub(" ", unicodedata.normalize("NFKC", str(value))).strip()


def normalize_station_name(value: Any) -> str:
    """Return a source-independent station-name join key."""

    text = clean_text(value).replace("’", "'").replace("`", "'")
    text = _INTERCHANGE_SUFFIX_RE.sub("", text)
    text = _STATION_SUFFIX_RE.sub("", text)
    text = re.sub(r"[^0-9A-Za-z]+", " ", text)
    return _SPACE_RE.sub(" ", text).strip().upper()


def _read_local_bytes(path: Path) -> bytes:
    if not path.is_file():
        raise RailDataError(f"Input file does not exist: {path}")
    return path.read_bytes()


def download_bytes(url: str, *, timeout: int = 90) -> bytes:
    """Download one source to memory; no partially downloaded file is retained."""

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "sg-estate-framework/rail-ingester"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def load_registry(path: Path | str = DEFAULT_REGISTRY) -> dict[str, Any]:
    registry = json.loads(Path(path).read_text(encoding="utf-8"))
    if registry.get("status_as_of") != STATUS_AS_OF:
        raise RailDataError(
            f"Registry status_as_of must be {STATUS_AS_OF}, got "
            f"{registry.get('status_as_of')!r}"
        )
    sources = registry.get("sources")
    if not isinstance(sources, dict):
        raise RailDataError("Registry must contain a 'sources' object")
    required_sources = PINNED_DOWNLOAD_SOURCES | STATUS_SOURCE_KEYS
    for key in sorted(required_sources):
        if key not in sources:
            raise RailDataError(f"Registry is missing required source {key!r}")
    for key in sorted(PINNED_DOWNLOAD_SOURCES):
        digest = clean_text(sources[key].get("sha256")).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RailDataError(f"Registry source {key!r} must contain a SHA-256 digest")
    return registry


def _source_url(registry: Mapping[str, Any], key: str, field: str = "download_url") -> str:
    source = registry["sources"][key]
    url = clean_text(source.get(field))
    if not url:
        raise RailDataError(f"Source {key!r} has no {field!r}")
    return url


def verify_source_bytes(payload: bytes, registry: Mapping[str, Any], key: str) -> bytes:
    """Reject mutable upstream bytes that no longer match the reviewed snapshot."""

    expected = clean_text(registry["sources"][key].get("sha256")).lower()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise RailDataError(
            f"Source {key!r} SHA-256 changed: expected {expected}, got {actual}. "
            "Review the upstream revision before updating the registry."
        )
    return payload


def _read_tabular_member(name: str, payload: bytes) -> pd.DataFrame:
    suffix = Path(name).suffix.lower()
    stream = io.BytesIO(payload)
    if suffix == ".csv":
        return pd.read_csv(stream)
    if suffix == ".xls":
        try:
            return pd.read_excel(stream, engine="xlrd")
        except ImportError as exc:
            raise RailDataError(
                "Reading the official legacy .xls workbook requires xlrd"
            ) from exc
    raise RailDataError(f"Unsupported station-code table type: {suffix}; use XLS or CSV")


def read_code_table(source: Path | str | bytes) -> pd.DataFrame:
    """Read an official code workbook, ZIP archive, or CSV test fixture."""

    if isinstance(source, bytes):
        payload = source
        source_name = "download.zip"
    else:
        path = Path(source)
        payload = _read_local_bytes(path)
        source_name = path.name

    if zipfile.is_zipfile(io.BytesIO(payload)):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = sorted(
                name for name in archive.namelist()
                if not name.startswith("__MACOSX/")
                and Path(name).suffix.lower() in {".xls", ".csv"}
            )
            if not members:
                raise RailDataError("Station-code ZIP contains no XLS or CSV table")
            preferred = next(
                (name for name in members if Path(name).suffix.lower() == ".xls"),
                members[0],
            )
            frame = _read_tabular_member(preferred, archive.read(preferred))
    else:
        frame = _read_tabular_member(source_name, payload)

    frame = frame.rename(
        columns={
            column: re.sub(r"[^a-z0-9]+", "_", clean_text(column).lower()).strip("_")
            for column in frame.columns
        }
    )
    aliases = {
        "station_code": "stn_code",
        "station_name": "mrt_station_english",
        "station_name_english": "mrt_station_english",
        "line": "mrt_line_english",
        "line_name": "mrt_line_english",
    }
    frame = frame.rename(columns={key: value for key, value in aliases.items() if key in frame})
    required = ["stn_code", "mrt_station_english", "mrt_line_english"]
    missing = [column for column in required if column not in frame]
    if missing:
        raise RailDataError(f"Station-code table is missing columns: {', '.join(missing)}")

    result = frame[required].copy()
    result["stn_code"] = result["stn_code"].map(clean_text).str.upper()
    result["mrt_station_english"] = result["mrt_station_english"].map(clean_text)
    result["mrt_line_english"] = result["mrt_line_english"].map(clean_text)
    result = result[result["stn_code"] != ""].reset_index(drop=True)
    if result[required].eq("").any(axis=None):
        raise RailDataError("Station-code table contains blank required values")
    duplicates = result.loc[result["stn_code"].duplicated(), "stn_code"].tolist()
    if duplicates:
        raise RailDataError(f"Station-code table has duplicate codes: {duplicates}")
    return result


def _zip_shapefile_parts(payload: bytes) -> tuple[bytes, bytes, bytes]:
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        raise RailDataError("LTA geometry source must be a ZIP containing a shapefile")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = [name for name in archive.namelist() if not name.startswith("__MACOSX/")]
        stems: dict[str, dict[str, str]] = defaultdict(dict)
        for name in names:
            suffix = Path(name).suffix.lower()
            if suffix in {".shp", ".shx", ".dbf"}:
                stems[str(Path(name).with_suffix(""))][suffix] = name
        complete = sorted(
            (stem, parts) for stem, parts in stems.items()
            if {".shp", ".shx", ".dbf"}.issubset(parts)
        )
        if not complete:
            raise RailDataError("Geometry ZIP contains no complete SHP/SHX/DBF set")
        _, parts = complete[0]
        return tuple(archive.read(parts[suffix]) for suffix in (".shp", ".shx", ".dbf"))


def _shape_records(source: Path | str | bytes) -> tuple[list[str], Iterable[Any]]:
    payload = source if isinstance(source, bytes) else _read_local_bytes(Path(source))
    shp, shx, dbf = _zip_shapefile_parts(payload)
    reader = shapefile.Reader(
        shp=io.BytesIO(shp),
        shx=io.BytesIO(shx),
        dbf=io.BytesIO(dbf),
        encoding="utf-8",
    )
    fields = [field[0] for field in reader.fields[1:]]
    return fields, list(reader.iterShapeRecords())


def _record_value(fields: list[str], record: Any, candidates: tuple[str, ...]) -> Any:
    values = dict(zip(fields, record.record))
    folded = {key.casefold(): value for key, value in values.items()}
    for candidate in candidates:
        if candidate.casefold() in folded:
            return folded[candidate.casefold()]
    raise RailDataError(f"Shapefile is missing a station-name field from {candidates}")


def _to_wgs84(x: float, y: float) -> tuple[float, float]:
    lon, lat = _SVY21_TO_WGS84.transform(x, y)
    return float(lat), float(lon)


def read_lta_station_polygons(source: Path | str | bytes) -> dict[str, dict[str, Any]]:
    fields, records = _shape_records(source)
    grouped: dict[str, list[Any]] = defaultdict(list)
    for item in records:
        name = _record_value(fields, item, ("STN_NAM_DE", "STN_NAM", "stn_name"))
        key = normalize_station_name(name)
        geometry = shapely_shape(item.shape.__geo_interface__)
        if key and not geometry.is_empty:
            grouped[key].append(geometry)

    result: dict[str, dict[str, Any]] = {}
    for key, geometries in grouped.items():
        centroid = unary_union(geometries).centroid
        lat, lon = _to_wgs84(centroid.x, centroid.y)
        result[key] = {
            "lat": lat,
            "lon": lon,
            "geometry_basis": "derived_lta_station_polygon_union_centroid",
            "geometry_source": SOURCE_POLYGONS,
        }
    return result


def read_lta_exit_points(source: Path | str | bytes) -> dict[str, dict[str, Any]]:
    fields, records = _shape_records(source)
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for item in records:
        name = _record_value(fields, item, ("stn_name", "STN_NAM_DE", "STN_NAM"))
        key = normalize_station_name(name)
        points = item.shape.points
        if key and points:
            grouped[key].extend((float(x), float(y)) for x, y in points)

    result: dict[str, dict[str, Any]] = {}
    for key, points in grouped.items():
        mean_x = sum(point[0] for point in points) / len(points)
        mean_y = sum(point[1] for point in points) / len(points)
        lat, lon = _to_wgs84(mean_x, mean_y)
        result[key] = {
            "lat": lat,
            "lon": lon,
            "geometry_basis": "derived_lta_station_exit_points_mean",
            "geometry_source": SOURCE_EXITS,
        }
    return result


def _extract_geojson(payload: bytes) -> dict[str, Any]:
    if zipfile.is_zipfile(io.BytesIO(payload)):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = sorted(
                name for name in archive.namelist()
                if Path(name).suffix.lower() in {".geojson", ".json"}
            )
            if not members:
                raise RailDataError("URA archive contains no GeoJSON file")
            payload = archive.read(members[0])
    try:
        document = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RailDataError("URA station-outline source is not valid GeoJSON") from exc
    if document.get("type") != "FeatureCollection":
        raise RailDataError("URA station-outline source must be a GeoJSON FeatureCollection")
    return document


def read_ura_station_outlines(source: Path | str | bytes) -> dict[str, dict[str, Any]]:
    payload = source if isinstance(source, bytes) else _read_local_bytes(Path(source))
    document = _extract_geojson(payload)
    grouped: dict[str, list[Any]] = defaultdict(list)
    for feature in document.get("features", []):
        properties = feature.get("properties") or {}
        name = next(
            (properties[key] for key in properties if key.casefold() == "name"),
            "",
        )
        key = normalize_station_name(name)
        geometry_data = feature.get("geometry")
        if not key or not geometry_data:
            continue
        geometry = shapely_shape(geometry_data)
        if not geometry.is_empty:
            grouped[key].append(geometry)

    result: dict[str, dict[str, Any]] = {}
    for key, geometries in grouped.items():
        centroid = unary_union(geometries).centroid
        result[key] = {
            "lat": float(centroid.y),
            "lon": float(centroid.x),
            "geometry_basis": "derived_ura_station_outline_union_centroid",
            "geometry_source": SOURCE_URA,
        }
    return result


def load_status_contract(path: Path | str = DEFAULT_STATUS_FILE) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = [
        "record_action", "stn_code", "name", "line", "network_status",
        "planned_opening", "status_as_of", "source_key",
    ]
    missing = [column for column in required if column not in frame]
    if missing:
        raise RailDataError(f"Status contract is missing columns: {', '.join(missing)}")
    frame = frame[required].copy()
    for column in required:
        frame[column] = frame[column].map(clean_text)
    frame["record_action"] = frame["record_action"].str.lower()
    frame["stn_code"] = frame["stn_code"].str.upper()
    frame["network_status"] = frame["network_status"].str.lower()
    validate_status_contract(frame)
    return frame


def validate_status_contract(frame: pd.DataFrame) -> None:
    required_text = ["stn_code", "name", "line", "network_status", "status_as_of", "source_key"]
    if frame[required_text].eq("").any(axis=None):
        raise RailDataError("Status contract contains blank required values")
    if set(frame["record_action"]) != {"remove", "upsert"}:
        raise RailDataError("Status contract actions must be exactly remove/upsert")
    if frame["stn_code"].duplicated().any():
        raise RailDataError("Status contract contains duplicate station codes")
    if set(frame["source_key"]) != STATUS_SOURCE_KEYS:
        raise RailDataError(
            "Status contract source keys must match the reviewed registry sources"
        )
    for row in frame[["stn_code", "source_key"]].to_dict("records"):
        expected_source = EXPECTED_STATUS_SOURCE_BY_CODE.get(row["stn_code"])
        if row["source_key"] != expected_source:
            raise RailDataError(
                f"Incorrect status source for {row['stn_code']}: "
                f"expected {expected_source}, got {row['source_key']}"
            )
    removals = set(frame.loc[frame["record_action"] == "remove", "stn_code"])
    if removals != REMOVED_CODES:
        raise RailDataError(f"Status contract removals must be {sorted(REMOVED_CODES)}")
    upserts = frame[frame["record_action"] == "upsert"]
    if not set(upserts["network_status"]).issubset(ALLOWED_STATUSES):
        raise RailDataError("Status contract contains an unsupported network status")
    if set(frame["status_as_of"]) != {STATUS_AS_OF}:
        raise RailDataError(f"Every status row must have status_as_of={STATUS_AS_OF}")
    open_codes = set(upserts.loc[upserts["network_status"] == "open", "stn_code"])
    if open_codes != set(CCL6_MEMBERSHIPS):
        raise RailDataError("Open reconciliation rows must be exactly CC30-CC34")
    open_dates = set(
        upserts.loc[upserts["network_status"] == "open", "planned_opening"]
    )
    if open_dates != {CCL6_OPENING}:
        raise RailDataError(f"CCL6 opening date must be {CCL6_OPENING}")
    future = upserts[upserts["network_status"] != "open"]
    if set(future["stn_code"]) != EXPECTED_NON_OPEN_CODES:
        raise RailDataError("Future-overlay station memberships do not match the contract")
    expected_by_status = {
        "deferred": DEFERRED_CODES,
        "under_construction": UNDER_CONSTRUCTION_CODES,
        "planned": JRL_CODES | CRL1_CODES,
    }
    for status, expected_codes in expected_by_status.items():
        actual = set(future.loc[future["network_status"] == status, "stn_code"])
        if actual != expected_codes:
            raise RailDataError(f"Incorrect {status} station memberships")
    for code, (name, line) in CCL6_MEMBERSHIPS.items():
        row = upserts[upserts["stn_code"] == code].iloc[0]
        if row["name"] != name or row["line"] != line:
            raise RailDataError(f"Incorrect CCL6 membership for {code}")
    for code, (name, line, network_status, planned_opening) in FUTURE_MEMBERSHIPS.items():
        row = future[future["stn_code"] == code].iloc[0]
        actual = (
            row["name"],
            row["line"],
            row["network_status"],
            row["planned_opening"],
        )
        expected = (name, line, network_status, planned_opening)
        if actual != expected:
            raise RailDataError(f"Incorrect future membership for {code}")
    jrl_lines = set(future.loc[future["stn_code"].isin(JRL_CODES), "line"])
    crl_lines = set(future.loc[future["stn_code"].isin(CRL1_CODES), "line"])
    if jrl_lines != {"Jurong Region Line"} or crl_lines != {"Cross Island Line"}:
        raise RailDataError("Future line memberships do not match JRL/CRL1")


def reconcile_memberships(base: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    rows = base.rename(
        columns={
            "mrt_station_english": "name",
            "mrt_line_english": "line",
        }
    ).copy()
    rows = rows[~rows["stn_code"].isin(REMOVED_CODES)].copy()
    rows["network_status"] = "open"
    rows["planned_opening"] = ""
    rows["status_as_of"] = STATUS_AS_OF
    rows["network_status_source"] = SOURCE_SYSTEM_MAP

    for item in status[status["record_action"] == "upsert"].to_dict("records"):
        rows = rows[rows["stn_code"] != item["stn_code"]]
        rows = pd.concat(
            [
                rows,
                pd.DataFrame(
                    [{
                        "stn_code": item["stn_code"],
                        "name": item["name"],
                        "line": item["line"],
                        "network_status": item["network_status"],
                        "planned_opening": item["planned_opening"],
                        "status_as_of": item["status_as_of"],
                        "network_status_source": item["source_key"],
                    }]
                ),
            ],
            ignore_index=True,
        )
    return rows


def attach_geometry(
    memberships: pd.DataFrame,
    polygons: Mapping[str, Mapping[str, Any]],
    exits: Mapping[str, Mapping[str, Any]],
    ura_outlines: Mapping[str, Mapping[str, Any]],
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    ccl6_exit_codes = {"CC30", "CC31", "CC32"}
    for row in memberships.to_dict("records"):
        key = normalize_station_name(row["name"])
        geometry = polygons.get(key)
        if geometry is None and row["stn_code"] in ccl6_exit_codes:
            geometry = exits.get(key)
        if geometry is None and row["network_status"] != "open":
            geometry = ura_outlines.get(key)
        if geometry is None:
            raise RailDataError(
                f"No permitted geometry for {row['stn_code']} {row['name']!r} "
                f"({row['network_status']})"
            )
        records.append(
            {
                "lat": geometry["lat"],
                "lon": geometry["lon"],
                "name": row["name"],
                "stn_code": row["stn_code"],
                "line": row["line"],
                "operational": int(row["network_status"] == "open"),
                "network_status": row["network_status"],
                "planned_opening": row["planned_opening"],
                "status_as_of": row["status_as_of"],
                "network_status_source": row["network_status_source"],
                "geometry_basis": geometry["geometry_basis"],
                "geometry_source": geometry["geometry_source"],
            }
        )
    return pd.DataFrame(records, columns=OUTPUT_COLUMNS)


def validate_layer(frame: pd.DataFrame) -> None:
    if list(frame.columns) != OUTPUT_COLUMNS:
        raise RailDataError(f"Output columns must be {OUTPUT_COLUMNS}")
    if len(frame) != 259:
        raise RailDataError(f"Expected 259 code-line memberships, got {len(frame)}")
    if frame["stn_code"].duplicated().any():
        duplicates = frame.loc[frame["stn_code"].duplicated(), "stn_code"].tolist()
        raise RailDataError(f"Output has duplicate station codes: {duplicates}")
    status_counts = frame["network_status"].value_counts().to_dict()
    if status_counts != EXPECTED_STATUS_COUNTS:
        raise RailDataError(
            f"Expected status counts {EXPECTED_STATUS_COUNTS}, got {status_counts}"
        )
    if set(frame.loc[frame["network_status"] != "open", "stn_code"]) != EXPECTED_NON_OPEN_CODES:
        raise RailDataError("Output future-overlay memberships are incorrect")
    if frame["stn_code"].str.startswith("CE").any() or (frame["stn_code"] == "JR1").any():
        raise RailDataError("Output must not contain legacy CE codes or JR1")
    if set(frame["status_as_of"]) != {STATUS_AS_OF}:
        raise RailDataError(f"Output status_as_of must be {STATUS_AS_OF}")
    for column in ("lat", "lon"):
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any():
            raise RailDataError(f"Output contains missing/non-numeric {column}")
    if not frame["lat"].between(1.0, 1.6).all() or not frame["lon"].between(103.5, 104.2).all():
        raise RailDataError("Output contains coordinates outside Singapore bounds")
    if not frame["geometry_basis"].str.startswith("derived_").all():
        raise RailDataError("Every coordinate must be labelled as a derived representative point")
    if not set(frame["network_status_source"]).issubset(STATUS_SOURCE_KEYS):
        raise RailDataError("Output contains an unreviewed network-status source")
    for row in frame[["stn_code", "network_status_source"]].to_dict("records"):
        expected_source = EXPECTED_STATUS_SOURCE_BY_CODE.get(
            row["stn_code"], SOURCE_SYSTEM_MAP
        )
        if row["network_status_source"] != expected_source:
            raise RailDataError(
                f"Incorrect network-status source for {row['stn_code']}: "
                f"expected {expected_source}, got {row['network_status_source']}"
            )
    if (frame["operational"] != (frame["network_status"] == "open").astype(int)).any():
        raise RailDataError("operational must equal 1 only for open memberships")
    for code, (name, line) in CCL6_MEMBERSHIPS.items():
        match = frame[frame["stn_code"] == code]
        if len(match) != 1:
            raise RailDataError(f"Missing CCL6 membership {code}")
        row = match.iloc[0]
        if (row["name"], row["line"], row["network_status"]) != (name, line, "open"):
            raise RailDataError(f"Incorrect CCL6 membership {code}")


def build_layer(
    codes_source: Path | str | bytes,
    station_polygons_source: Path | str | bytes,
    exit_points_source: Path | str | bytes,
    ura_outlines_source: Path | str | bytes,
    *,
    status_file: Path | str = DEFAULT_STATUS_FILE,
) -> pd.DataFrame:
    codes = read_code_table(codes_source)
    status = load_status_contract(status_file)
    memberships = reconcile_memberships(codes, status)
    polygons = read_lta_station_polygons(station_polygons_source)
    exits = read_lta_exit_points(exit_points_source)
    ura_outlines = read_ura_station_outlines(ura_outlines_source)
    result = attach_geometry(memberships, polygons, exits, ura_outlines)
    validate_layer(result)
    return result.sort_values("stn_code", kind="stable").reset_index(drop=True)


def names_frame(layer: pd.DataFrame) -> pd.DataFrame:
    """Return the normalized compatibility table without losing interchanges."""

    return layer[["stn_code", "name", "line"]].rename(
        columns={
            "name": "mrt_station_english",
            "line": "mrt_line_english",
        }
    )


def atomic_write_csv(frame: pd.DataFrame, destination: Path | str) -> None:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            suffix=".tmp",
            prefix=f".{target.name}.",
            dir=target.parent,
            delete=False,
        ) as handle:
            temporary_name = handle.name
            frame.to_csv(handle, index=False, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _find_download_url(value: Any) -> str | None:
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        return value
    if isinstance(value, dict):
        for preferred in ("url", "downloadUrl", "download_url"):
            found = _find_download_url(value.get(preferred))
            if found:
                return found
        for child in value.values():
            found = _find_download_url(child)
            if found:
                return found
    if isinstance(value, list):
        for child in value:
            found = _find_download_url(child)
            if found:
                return found
    return None


def download_ura_geojson(registry: Mapping[str, Any]) -> bytes:
    poll_url = _source_url(registry, SOURCE_URA, "poll_url")
    poll_payload = download_bytes(poll_url)
    try:
        poll_document = json.loads(poll_payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RailDataError("URA poll endpoint did not return JSON") from exc
    download_url = _find_download_url(poll_document)
    if not download_url or download_url == poll_url:
        raise RailDataError("URA poll response did not contain a download URL")
    return download_bytes(download_url)


def _local_or_download(local: str | None, registry: Mapping[str, Any], key: str) -> bytes:
    payload = _read_local_bytes(Path(local)) if local else download_bytes(
        _source_url(registry, key)
    )
    return verify_source_bytes(payload, registry, key)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the verified MRT layer from official LTA/URA datasets.",
    )
    parser.add_argument("--codes-archive", help="Local LTA code ZIP/XLS/CSV; otherwise download")
    parser.add_argument("--station-archive", help="Local LTA station-polygon ZIP; otherwise download")
    parser.add_argument("--exit-archive", help="Local LTA station-exit ZIP; otherwise download")
    parser.add_argument("--ura-geojson", help="Local URA GeoJSON/ZIP; otherwise poll and download")
    parser.add_argument("--status-file", default=str(DEFAULT_STATUS_FILE))
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--names-output", default=str(DEFAULT_NAMES_OUTPUT))
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Build and validate without replacing either canonical CSV",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    registry = load_registry(args.registry)
    codes = _local_or_download(args.codes_archive, registry, SOURCE_CODES)
    polygons = _local_or_download(args.station_archive, registry, SOURCE_POLYGONS)
    exits = _local_or_download(args.exit_archive, registry, SOURCE_EXITS)
    ura_payload = (
        _read_local_bytes(Path(args.ura_geojson))
        if args.ura_geojson
        else download_ura_geojson(registry)
    )
    ura = verify_source_bytes(ura_payload, registry, SOURCE_URA)
    layer = build_layer(
        codes,
        polygons,
        exits,
        ura,
        status_file=args.status_file,
    )
    if args.validate_only:
        print(f"Validated {len(layer)} code-line memberships; canonical files unchanged.")
        return 0
    atomic_write_csv(layer, args.output)
    atomic_write_csv(names_frame(layer), args.names_output)
    print(f"Wrote {len(layer)} code-line memberships to {args.output}")
    print(f"Wrote normalized membership names to {args.names_output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
