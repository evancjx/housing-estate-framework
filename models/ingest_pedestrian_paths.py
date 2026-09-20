#!/usr/bin/env python3
# NOT WIRED: produces CSVs but no Provision component consumes them (no entry in framework_config.PROVISION_WEIGHTS). Placeholder for a future component.
"""
Pedestrian + cycling path ingester  (Provision v2.0 §1.6)
==========================================================
Two CSVs feeding the conn sub-metric refinement (Task 2.9):

  data/inputs/walking_routes.csv:
    estate, pct_sheltered_to_mrt, n_covered_linkway_segments_800m,
           provenance_note

  data/inputs/cycling_paths.csv:
    estate, dedicated_path_m_within_800m, pcn_continuous_m,
           bike_parks_at_mrt, provenance_note

PROVENANCE: PARTLY_MEASURED (2026-09-20). Two fields are measured; three
cannot be, and stay blank rather than 0 so a missing input is never read as
a measured zero.

  MEASURED
    pcn_continuous_m — NParks Park Connector Loop GeoJSON on data.gov.sg
      (d_a69ef89737379f231d2ae93fd1c5707f): 878 features with full
      LineString/MultiLineString geometry, mean 37 vertices. Length is summed
      per segment whose midpoint falls within the estate buffer. No token is
      required for this source.
    n_covered_linkway_segments_800m — committed covered_linkway.csv points
      within the estate buffer.

  UNMEASURED, and why
    dedicated_path_m_within_800m — OneMap's `cyclingpath` theme returns a
      representative point for most features (mean 1.14 vertices across 4,998
      checked on 2026-09-20), so path length cannot be derived from it. The
      full LTA Cycling Path Network needs an LTA DataMall account key, which
      this project does not have.
    bike_parks_at_mrt — OneMap's `bicyclerack` theme returns
      "No result(s) found." at every extent tried.
    pct_sheltered_to_mrt — needs routed path geometry plus shelter
      attribution; no available source provides it.

  A OneMap token is NOT the blocker here, contrary to the earlier note in
  this file: the theme service simply does not carry usable path geometry.

  The score_conn function in provision_model.py must treat blank fields as
  missing inputs and renormalise the conn sub-metric weights (not fall back
  to 0).

AUDIT TRAIL: keeping the stub committed lets every Phase-2 scoring change
exercise the same code path it will use once the token is available, and
documents the gap so the next audit can re-attempt the fetch.

INPUT CONTRACT:
  --estates  CSV with estate, lat, lon (UPPERCASE)
  --out-walking  output CSV path for walking-route stub
  --out-cycling  output CSV path for cycling-path stub

RUN:
  python3 models/ingest_pedestrian_paths.py \\
      --estates data/inputs/estates.csv \\
      --out-walking data/inputs/walking_routes.csv \\
      --out-cycling data/inputs/cycling_paths.csv
"""
import argparse
import json
import math
import os
import pathlib
import sys

import pandas as pd

ONEMAP_TOKEN = os.environ.get("ONEMAP_TOKEN", "")
NOTE_UNFETCHED = "unfetched (OneMap token required)"

# NParks Park Connector Loop, data.gov.sg. Full LineString/MultiLineString
# geometry (878 features, mean 37 vertices), so length is measurable.
PCN_DATASET_ID = "d_a69ef89737379f231d2ae93fd1c5707f"
DEFAULT_BUFFER_M = 800

NOTE_CYCLING = (
    "pcn_continuous_m measured from NParks Park Connector Loop (data.gov.sg "
    f"{PCN_DATASET_ID}) within {DEFAULT_BUFFER_M}m of the estate centroid; "
    "dedicated_path_m_within_800m unmeasured (OneMap cyclingpath returns a "
    "representative point for most features; LTA DataMall needs an account "
    "key); bike_parks_at_mrt unmeasured (OneMap bicyclerack returns no results)"
)
NOTE_WALKING = (
    f"n_covered_linkway_segments_800m measured from covered_linkway.csv within "
    f"{DEFAULT_BUFFER_M}m of the estate centroid; pct_sheltered_to_mrt "
    "unmeasured (needs route geometry, which no available source provides)"
)


def _metres_per_degree(lat: float) -> tuple[float, float]:
    """Local equirectangular scale, as used by the other estate-buffer ingesters."""
    return 111_320.0 * math.cos(math.radians(lat)), 110_540.0


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    per_lon, per_lat = _metres_per_degree((lat1 + lat2) / 2)
    return math.hypot((lon2 - lon1) * per_lon, (lat2 - lat1) * per_lat)


def _line_parts(geometry: dict) -> list[list]:
    kind = (geometry or {}).get("type")
    coords = (geometry or {}).get("coordinates") or []
    if kind == "LineString":
        return [coords]
    if kind == "MultiLineString":
        return list(coords)
    return []


def load_pcn_lines(path: pathlib.Path) -> list[list]:
    """Return every park-connector line part as a list of (lon, lat) vertices."""
    payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    parts = []
    for feature in payload.get("features", []):
        parts.extend(_line_parts(feature.get("geometry")))
    return parts


def pcn_metres_within(lines: list[list], lat: float, lon: float, buffer_m: float) -> float:
    """Length of park connector inside the buffer.

    A segment counts when its midpoint falls inside the buffer, which keeps a
    long line from being counted whole just because one end clips the circle.
    """
    total = 0.0
    for part in lines:
        for (lon1, lat1), (lon2, lat2) in zip(part, part[1:]):
            mid_lat, mid_lon = (lat1 + lat2) / 2, (lon1 + lon2) / 2
            if _distance_m(lat, lon, mid_lat, mid_lon) <= buffer_m:
                total += _distance_m(lat1, lon1, lat2, lon2)
    return total


def build_cycling(estates: pd.DataFrame, pcn_path, buffer_m: float = DEFAULT_BUFFER_M) -> pd.DataFrame:
    lines = load_pcn_lines(pcn_path)
    rows = []
    for _, estate in estates.iterrows():
        rows.append({
            "estate": str(estate["estate"]).upper(),
            # Unmeasurable fields stay null so they cannot read as a measured 0.
            "dedicated_path_m_within_800m": pd.NA,
            "pcn_continuous_m": round(
                pcn_metres_within(lines, float(estate["lat"]), float(estate["lon"]), buffer_m)),
            "bike_parks_at_mrt": pd.NA,
            "provenance_note": NOTE_CYCLING,
        })
    return pd.DataFrame(rows, columns=["estate", "dedicated_path_m_within_800m",
                                       "pcn_continuous_m", "bike_parks_at_mrt", "provenance_note"])


def build_walking(estates: pd.DataFrame, linkway_path, buffer_m: float = DEFAULT_BUFFER_M) -> pd.DataFrame:
    linkways = pd.read_csv(linkway_path)
    rows = []
    for _, estate in estates.iterrows():
        lat, lon = float(estate["lat"]), float(estate["lon"])
        near = sum(
            _distance_m(lat, lon, float(r.lat), float(r.lon)) <= buffer_m
            for r in linkways.itertuples()
        )
        rows.append({
            "estate": str(estate["estate"]).upper(),
            "pct_sheltered_to_mrt": pd.NA,
            "n_covered_linkway_segments_800m": int(near),
            "provenance_note": NOTE_WALKING,
        })
    return pd.DataFrame(rows, columns=["estate", "pct_sheltered_to_mrt",
                                       "n_covered_linkway_segments_800m", "provenance_note"])


def stub_walking(estates: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{
        "estate": str(e).upper(),
        "pct_sheltered_to_mrt": 0.0,
        "n_covered_linkway_segments_800m": 0,
        "provenance_note": NOTE_UNFETCHED,
    } for e in estates["estate"]])


def stub_cycling(estates: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([{
        "estate": str(e).upper(),
        "dedicated_path_m_within_800m": 0,
        "pcn_continuous_m": 0,
        "bike_parks_at_mrt": 0,
        "provenance_note": NOTE_UNFETCHED,
    } for e in estates["estate"]])


def fetch_pcn_geojson(cache_path: pathlib.Path) -> pathlib.Path | None:
    """Download the NParks Park Connector Loop GeoJSON, reusing any cached copy."""
    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from data_ingest import poll_download  # local import: only the fetch path needs it

    raw = poll_download(PCN_DATASET_ID)
    if not raw:
        return None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(raw)
    return cache_path


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--estates", required=True)
    ap.add_argument("--out-walking", required=True)
    ap.add_argument("--out-cycling", required=True)
    ap.add_argument("--covered-linkway", default="data/inputs/covered_linkway.csv",
                    help="committed LTA sheltered-linkway points")
    ap.add_argument("--pcn-geojson", help="local NParks Park Connector Loop GeoJSON; downloaded when omitted")
    ap.add_argument("--pcn-cache", default="data/raw/nparks/park_connector_loop.geojson",
                    help="where a downloaded PCN payload is cached")
    ap.add_argument("--buffer-m", type=float, default=DEFAULT_BUFFER_M)
    args = ap.parse_args()

    estates = pd.read_csv(args.estates)
    assert {"estate", "lat", "lon"} <= set(estates.columns)

    pcn_path = pathlib.Path(args.pcn_geojson) if args.pcn_geojson else fetch_pcn_geojson(
        pathlib.Path(args.pcn_cache))
    if pcn_path is None or not pcn_path.exists():
        print("Park Connector Loop payload unavailable — writing zero-filled stubs.",
              file=sys.stderr)
        walking, cycling = stub_walking(estates), stub_cycling(estates)
    else:
        walking = build_walking(estates, args.covered_linkway, args.buffer_m)
        cycling = build_cycling(estates, pcn_path, args.buffer_m)
        print(f"PCN geometry: {pcn_path}", file=sys.stderr)

    walking.to_csv(args.out_walking, index=False)
    cycling.to_csv(args.out_cycling, index=False)
    print(f"Wrote {len(walking)} walking + {len(cycling)} cycling rows",
          file=sys.stderr)


if __name__ == "__main__":
    main()
