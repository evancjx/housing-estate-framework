#!/usr/bin/env python3
"""
URA Master Plan 2019 mixed-use ingester
=======================================
Fetches URA Master Plan 2019 Land Use polygons from data.gov.sg dataset
d_90d86daa5bfaa371668b84fa5f01424f via the poll-download API and computes
the commercial/mixed-use share inside a 2 km buffer around each estate
centroid in data/inputs/estates.csv.

PROVENANCE: MEASURED.
  Land-use polygons are from the URA Master Plan 2019 public GeoJSON layer.
  Per-estate shares are measured by polygon intersection against local
  equirectangular buffers centered on each estate.

LAND-USE ATTRIBUTE ASSUMPTION:
  The live payload could not be inspected in this restricted environment.
  The parser assumes the zoning description field is LU_DESC, while also
  accepting common equivalents (LANDUSE, LAND_USE, LANDUSE_DESC) and KML-style
  HTML Description tables. A production refresh should verify the live payload
  still exposes LU_DESC or one of those equivalents.

MATCHED LAND-USE CATEGORY STRINGS:
  COMMERCIAL, WHITE, BUSINESS PARK

OUTPUT (data/inputs/mixed_use.csv):
  estate, mixed_use_share, commercial_share, white_share,
         business_park_share, buffer_km

INPUT CONTRACT:
  --estates    CSV with estate, lat, lon (UPPERCASE)
  --out        output CSV path
  --buffer-km  estate buffer radius in kilometres (default: 2.0)
  --cache-dir  optional cache directory for fetched GeoJSON bytes
  --max-cache-age-hours  refresh online caches older than this (default: 24)
  --offline    perform no HTTP; require a valid cache (stale is warned and used)

RUN:
  python3 models/ingest_ura_landuse.py \\
      --estates data/inputs/estates.csv \\
      --out data/inputs/mixed_use.csv
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.error

import pandas as pd
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sg_estate.adapters.http import get_bytes, get_json

DATASET_ID = "d_90d86daa5bfaa371668b84fa5f01424f"
POLL_URL = "https://api-open.data.gov.sg/v1/public/api/datasets/{ds}/poll-download"
_UA = "sg-estate-ingest/1.0 (ura-landuse)"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data", "inputs")
DEFAULT_ESTATES = os.path.join(DATA_DIR, "estates.csv")
DEFAULT_OUT = os.path.join(DATA_DIR, "mixed_use.csv")

EARTH_RADIUS_M = 6_371_000.0
DEFAULT_BUFFER_KM = 2.0
DEFAULT_MAX_CACHE_AGE_HOURS = 24.0
_LAST_CACHE_STATE = "unknown"

LANDUSE_ATTR_CANDIDATES = [
    "LU_DESC",
    "LANDUSE",
    "LAND_USE",
    "LANDUSE_DESC",
    "LAND_USE_DESC",
    "MP19_LU_DESC",
]
TARGET_CATEGORIES = {
    "COMMERCIAL": "commercial_share",
    "WHITE": "white_share",
    "BUSINESS PARK": "business_park_share",
}

_DESC_RE = re.compile(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", re.S | re.I)


def _http_json(url: str, timeout: int = 30) -> dict:
    return get_json(
        url,
        timeout=timeout,
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )


def _http_bytes(url: str, timeout: int = 120) -> bytes:
    return get_bytes(url, timeout=timeout, headers={"User-Agent": _UA})


def _validated_geojson(raw: bytes, source: str) -> dict:
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid URA land-use cache {source}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("features"), list):
        raise ValueError(
            f"invalid URA land-use cache {source}: missing features array"
        )
    if not payload["features"]:
        raise ValueError(f"invalid URA land-use cache {source}: zero features")
    return payload


def _validated_max_cache_age(value: float) -> float:
    try:
        maximum = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max cache age must be a positive number of hours") from exc
    if not math.isfinite(maximum) or maximum <= 0:
        raise ValueError("max cache age must be a positive number of hours")
    return maximum


def _cache_age_hours(path: Path) -> float:
    return max(0.0, (time.time() - path.stat().st_mtime) / 3600.0)


def _write_staged_cache(path: Path, raw: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_validated_cache(path: Path, raw: bytes, source: str) -> None:
    _validated_geojson(raw, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        _write_staged_cache(temporary, raw)
        staged = temporary.read_bytes()
        if staged != raw:
            raise ValueError(f"staged URA land-use cache bytes differ for {source}")
        _validated_geojson(staged, source)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def poll_download_geojson(
    cache_dir: str | None = None,
    *,
    max_cache_age_hours: float = DEFAULT_MAX_CACHE_AGE_HOURS,
    offline: bool = False,
) -> dict:
    global _LAST_CACHE_STATE

    _LAST_CACHE_STATE = "unknown"
    maximum_age = _validated_max_cache_age(max_cache_age_hours)
    cache_path = (
        Path(cache_dir) / f"{DATASET_ID}.geojson" if cache_dir else None
    )
    if offline and cache_path is None:
        sys.exit("ERROR: --offline requires --cache-dir for URA land use")

    if cache_path is not None and cache_path.is_file():
        try:
            cached = _validated_geojson(cache_path.read_bytes(), str(cache_path))
        except (OSError, ValueError) as exc:
            if offline:
                sys.exit(f"ERROR: offline URA land-use cache is invalid: {exc}")
            print(f"WARNING: ignoring invalid cache {cache_path}: {exc}", file=sys.stderr)
        else:
            age_hours = _cache_age_hours(cache_path)
            stale = age_hours > maximum_age
            if offline:
                _LAST_CACHE_STATE = "offline_stale" if stale else "offline"
                if stale:
                    print(
                        f"WARNING: offline URA land-use cache {cache_path} is stale "
                        f"({age_hours:.1f}h > {maximum_age:.1f}h); "
                        "using it because --offline was requested",
                        file=sys.stderr,
                    )
                else:
                    print(f"Using offline URA land-use cache {cache_path}", file=sys.stderr)
                return cached
            if not stale:
                _LAST_CACHE_STATE = "cached"
                print(
                    f"Using validated URA land-use cache {cache_path} "
                    f"({age_hours:.1f}h old)",
                    file=sys.stderr,
                )
                return cached
            _LAST_CACHE_STATE = "stale_refreshing"
            print(
                f"WARNING: URA land-use cache {cache_path} is stale "
                f"({age_hours:.1f}h > {maximum_age:.1f}h); refreshing",
                file=sys.stderr,
            )
    elif offline:
        sys.exit(
            f"ERROR: offline URA land-use cache is missing: {cache_path}; "
            "run once online with --cache-dir"
        )

    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)

    poll_url = POLL_URL.format(ds=DATASET_ID)
    for attempt in range(4):
        try:
            poll = _http_json(poll_url, timeout=30)
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 3:
                wait = 5 * (2 ** attempt)
                print(f"poll-download 429 for {DATASET_ID}; waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            sys.exit(f"ERROR: poll-download failed for {DATASET_ID}: {exc}")
        except Exception as exc:
            sys.exit(f"ERROR: poll-download failed for {DATASET_ID}: {exc}")
    else:
        sys.exit(f"ERROR: poll-download exhausted retries for {DATASET_ID}")

    file_url = poll.get("data", {}).get("url") or poll.get("url")
    if not file_url:
        sys.exit(f"ERROR: poll-download for {DATASET_ID} returned no download URL")
    try:
        raw = _http_bytes(file_url, timeout=120)
    except Exception as exc:
        sys.exit(f"ERROR: download failed for {DATASET_ID}: {exc}")
    try:
        payload = _validated_geojson(raw, file_url)
    except ValueError as exc:
        sys.exit(f"ERROR: downloaded URA land-use payload is invalid: {exc}")
    if cache_path is not None:
        _atomic_write_validated_cache(cache_path, raw, file_url)
    _LAST_CACHE_STATE = "fresh"
    return payload


def feature_list(geojson: dict) -> list[dict]:
    features = geojson.get("features", []) if isinstance(geojson, dict) else []
    if not features:
        sys.exit("ERROR: URA land-use GeoJSON has zero features")
    return features


def _clean_html_text(value) -> str:
    if value is None:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _normalise_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", value).upper()


def _normalise_landuse(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip().upper()


def _description_props(value) -> dict:
    text = "" if value is None else str(value)
    out = {}
    for key, val in _DESC_RE.findall(text):
        clean_key = _clean_html_text(key)
        if clean_key:
            out[clean_key] = _clean_html_text(val)
    return out


def landuse_category(feature: dict) -> str | None:
    props = dict(feature.get("properties") or {})
    desc = props.get("Description") or props.get("description")
    props.update(_description_props(desc))
    keyed = {_normalise_key(k): v for k, v in props.items()}
    for attr in LANDUSE_ATTR_CANDIDATES:
        value = keyed.get(_normalise_key(attr))
        if value is not None and not pd.isna(value):
            category = _normalise_landuse(str(value))
            if category:
                return category
    return None


def project_lonlat_geometry(geometry, origin_lat: float, origin_lon: float):
    cos_lat = math.cos(math.radians(origin_lat))

    def _project(x, y, z=None):
        px = math.radians(x - origin_lon) * EARTH_RADIUS_M * cos_lat
        py = math.radians(y - origin_lat) * EARTH_RADIUS_M
        if z is None:
            return px, py
        return px, py, z

    return transform(_project, geometry)


def share_for_estate(
    estate_lat: float,
    estate_lon: float,
    features: list[dict],
    buffer_km: float = DEFAULT_BUFFER_KM,
) -> dict:
    if not features:
        sys.exit("ERROR: URA land-use GeoJSON has zero features")

    radius_m = buffer_km * 1000.0
    buffer_geom = Point(0, 0).buffer(radius_m, 64)
    total_area = buffer_geom.area
    if total_area <= 0:
        sys.exit(f"ERROR: invalid buffer area for buffer_km={buffer_km}")

    by_category = {category: [] for category in TARGET_CATEGORIES}
    valid_polygon_count = 0
    for feature in features:
        category = landuse_category(feature)
        if category not in TARGET_CATEGORIES:
            continue
        try:
            geom = shape(feature.get("geometry") or {})
        except Exception:
            continue
        if geom.is_empty:
            continue
        valid_polygon_count += 1
        projected = project_lonlat_geometry(geom, estate_lat, estate_lon)
        clipped = projected.intersection(buffer_geom)
        if not clipped.is_empty:
            by_category[category].append(clipped)

    if valid_polygon_count == 0:
        return {
            "mixed_use_share": 0.0,
            "commercial_share": 0.0,
            "white_share": 0.0,
            "business_park_share": 0.0,
            "buffer_km": buffer_km,
        }

    shares = {}
    mixed_geoms = []
    for category, output_col in TARGET_CATEGORIES.items():
        geoms = by_category[category]
        unioned = unary_union(geoms) if geoms else None
        area = unioned.area if unioned is not None and not unioned.is_empty else 0.0
        share = area / total_area
        if share < 0 and share > -1e-12:
            share = 0.0
        if share > 1 and share < 1 + 1e-12:
            share = 1.0
        shares[output_col] = share
        if unioned is not None and not unioned.is_empty:
            mixed_geoms.append(unioned)

    mixed_union = unary_union(mixed_geoms) if mixed_geoms else None
    mixed_area = mixed_union.area if mixed_union is not None and not mixed_union.is_empty else 0.0
    mixed_share = mixed_area / total_area
    if mixed_share > 1 and mixed_share < 1 + 1e-12:
        mixed_share = 1.0
    shares["mixed_use_share"] = mixed_share
    shares["buffer_km"] = buffer_km
    return shares


def rows_for_estates(estates: pd.DataFrame, geojson: dict, buffer_km: float = DEFAULT_BUFFER_KM) -> list[dict]:
    required = {"estate", "lat", "lon"}
    missing = required - set(estates.columns)
    if missing:
        sys.exit(f"ERROR: estates CSV missing columns: {sorted(missing)}")

    features = feature_list(geojson)
    rows = []
    for est in estates.itertuples():
        row = share_for_estate(float(est.lat), float(est.lon), features, buffer_km=buffer_km)
        row["estate"] = str(est.estate).upper().strip()
        rows.append(row)

    for row in rows:
        for col in [
            "mixed_use_share",
            "commercial_share",
            "white_share",
            "business_park_share",
            "buffer_km",
        ]:
            value = row[col]
            if pd.isna(value):
                sys.exit(f"ERROR: computed NaN for {row['estate']} {col}")
            if col.endswith("_share") and not (0.0 <= value <= 1.0):
                sys.exit(f"ERROR: computed out-of-range share for {row['estate']} {col}: {value}")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--estates", default=DEFAULT_ESTATES)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--buffer-km", type=float, default=DEFAULT_BUFFER_KM)
    ap.add_argument("--cache-dir", help="cache fetched GeoJSON bytes")
    ap.add_argument(
        "--max-cache-age-hours",
        type=float,
        default=DEFAULT_MAX_CACHE_AGE_HOURS,
        help="refresh online caches older than this many hours (default: 24)",
    )
    ap.add_argument(
        "--offline",
        action="store_true",
        help="perform no HTTP and require a valid cache (stale caches are warned)",
    )
    args = ap.parse_args()

    estates = pd.read_csv(args.estates)
    try:
        geojson = poll_download_geojson(
            args.cache_dir,
            max_cache_age_hours=args.max_cache_age_hours,
            offline=args.offline,
        )
    except ValueError as exc:
        sys.exit(f"ERROR: {exc}")
    rows = rows_for_estates(estates, geojson, buffer_km=args.buffer_km)

    out_df = pd.DataFrame(rows)[
        [
            "estate",
            "mixed_use_share",
            "commercial_share",
            "white_share",
            "business_park_share",
            "buffer_km",
        ]
    ]
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    out_df.to_csv(args.out, index=False)
    print(f"Wrote {len(out_df)} rows -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
