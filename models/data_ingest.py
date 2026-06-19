#!/usr/bin/env python3
"""
Singapore Estate Data Ingestion  —  data_ingest.py
===================================================
Downloads publicly available geospatial layers from data.gov.sg and the
OneMap Search API, standardises column names to match provision_model.py's
input contract, and writes cleaned CSVs to SG-Estate-Framework/data/.

Run from the models/ directory (no API keys required):
    python data_ingest.py

Outputs written to ../data/:
    parks.csv           --parks  flag
    markets.csv         --markets flag  (hawker centres)
    schools.csv         --schools flag
    polyclinics.csv     --polyclinics flag
    mrt_layer_names.csv skeleton for onemap_geocode_mrt.py (no coordinates)
    hdb_resale.csv      --hdb flag (cleaned for value_model.py)

Layers NOT fetched (require LTA DataMall or OneMap token):
    mrt_layer.csv       use onemap_geocode_mrt.py with ONEMAP_TOKEN
    bus.csv             requires LTA DataMall API key
    chas.csv            CHAS clinic layer requires OneMap token

Column contract for provision_model.py geospatial layers:
    lat, lon            mandatory for all layers
    operational         for --mrt only (1/0)

Column contract for value_model.py --hdb:
    town, resale_price, floor_area_sqm, flat_type,
    storey_band, remaining_lease_years, month
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

import pandas as pd

# ---------------------------------------------------------------------------
# Paths — resolve relative to this script so it works from any cwd
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# data.gov.sg poll-download API
# ---------------------------------------------------------------------------
POLL_BASE = "https://api-open.data.gov.sg/v1/public/api/datasets/{dataset_id}/poll-download"

# Dataset IDs confirmed or plausible (all tried in order; first success wins)
DATASETS = {
    "parks": {
        "ids": ["d_0542d48f0991541706b58059381a6eca"],
        "format": "geojson",
        "desc": "NParks Parks (GeoJSON)",
    },
    "markets": {
        "ids": ["d_4a086da0a5553be1d89383cd90d07ecd"],
        "format": "geojson",
        "desc": "NEA Hawker Centres (GeoJSON)",
    },
    "mrt_names": {
        "ids": ["d_d312a5b127e1ae74299b8ae664cedd4e"],
        "format": "csv",
        "desc": "Train Station Names (CSV — no coordinates)",
    },
    "hdb_resale": {
        # collection 189 — try each ID until one returns ResaleFlatPrices...
        "ids": [
            "d_8b84c4ee58e3cfc0ece0d773c8ca6abc",
            "d_43f493c6c50d54243cc1eab0df142d6a",
            "d_2d5ff9ea31397b66239f245f57751537",
            "d_ebc5ab87086db484f88045b47411ebc5",
            "d_ea9ed51da2787afaf8e51f827c304208",
        ],
        "format": "csv",
        "desc": "HDB Resale Flat Prices from Jan 2017 (CSV)",
    },
    "schools": {
        # d_688b934f82c1059ed0a6993d2a829089 = Generalinformationofschools.csv (confirmed)
        "ids": [
            "d_688b934f82c1059ed0a6993d2a829089",
        ],
        "format": "csv",
        "desc": "MOE Schools General Information (CSV)",
    },
}

# OneMap Search — no auth required
ONEMAP_SEARCH = "https://www.onemap.gov.sg/api/common/elastic/search"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
def http_get_json(url: str, timeout: int = 30) -> dict:
    """Fetch URL and parse as JSON. Raises on HTTP error."""
    req = urllib.request.Request(url, headers={"User-Agent": "sg-estate-ingest/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_get_bytes(url: str, timeout: int = 60) -> bytes:
    """Fetch URL and return raw bytes."""
    req = urllib.request.Request(url, headers={"User-Agent": "sg-estate-ingest/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def poll_download(dataset_id: str, timeout: int = 60, retries: int = 4) -> bytes | None:
    """
    data.gov.sg poll-download pattern:
      1. GET poll URL -> JSON with 'url' field (presigned S3)
      2. Fetch the presigned URL -> raw file bytes
    Retries on 429 with exponential backoff (5s, 10s, 20s, 40s).
    Returns None on any error.
    """
    poll_url = POLL_BASE.format(dataset_id=dataset_id)
    for attempt in range(retries):
        wait = 5 * (2 ** attempt)
        try:
            meta = http_get_json(poll_url, timeout=30)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                print(f"    [poll] 429 rate-limited (id={dataset_id}), waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"    [poll] GET {poll_url} failed: {exc}")
            return None
        except Exception as exc:
            print(f"    [poll] GET {poll_url} failed: {exc}")
            return None

        # The API returns {"data": {"url": "..."}} or {"url": "..."}
        file_url = (
            meta.get("data", {}).get("url")
            or meta.get("url")
        )
        if not file_url:
            print(f"    [poll] No URL in response for {dataset_id}: {list(meta.keys())}")
            return None

        try:
            raw = http_get_bytes(file_url, timeout=timeout)
            return raw
        except Exception as exc:
            print(f"    [s3] Fetch failed for {dataset_id}: {exc}")
            return None

    print(f"    [poll] Exhausted retries for {dataset_id}")
    return None


# ---------------------------------------------------------------------------
# GeoJSON -> DataFrame with (lat, lon, name)
# ---------------------------------------------------------------------------
def geojson_to_df(raw: bytes, name_candidates: list[str] | None = None) -> pd.DataFrame:
    """
    Parse a GeoJSON FeatureCollection into a flat DataFrame.
    Extracts lat/lon from geometry (Point expected) and flattens properties.
    Tries each string in name_candidates to produce a 'name' column.
    """
    data = json.loads(raw.decode("utf-8"))
    features = data.get("features", [])
    rows = []
    for feat in features:
        geom = feat.get("geometry") or {}
        props = feat.get("properties") or {}
        coords = geom.get("coordinates")
        if not coords:
            continue
        # GeoJSON is [lon, lat]
        lon, lat = float(coords[0]), float(coords[1])
        row = {"lat": lat, "lon": lon}
        row.update({k: v for k, v in props.items()})
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Standardise name column
    if name_candidates:
        for col in name_candidates:
            if col in df.columns:
                df["name"] = df[col]
                break
    return df


# ---------------------------------------------------------------------------
# OneMap polyclinic search (paginated, no auth)
# ---------------------------------------------------------------------------
def fetch_polyclinics_onemap() -> pd.DataFrame:
    """
    Searches OneMap for polyclinics.  No auth required.
    Returns DataFrame with lat, lon, name.
    """
    print("  Fetching polyclinics from OneMap Search (no auth required)...")
    results = []
    page = 1
    total_pages = 1  # updated after first request

    while page <= total_pages:
        url = (
            f"{ONEMAP_SEARCH}"
            f"?searchVal={urllib.parse.quote('polyclinic')}"
            f"&returnGeom=Y&getAddrDetails=Y&pageNum={page}"
        )
        fetched = False
        for attempt in range(4):
            try:
                data = http_get_json(url, timeout=20)
                fetched = True
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    wait = 5 * (2 ** attempt)
                    print(f"    [OneMap] 429 on page {page}, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"    [OneMap] page {page} failed: {exc}")
                    break
            except Exception as exc:
                print(f"    [OneMap] page {page} failed: {exc}")
                break

        if not fetched:
            print(f"    [OneMap] skipping page {page} after retries")
            page += 1
            continue

        if page == 1:
            total_pages = data.get("totalNumPages", 1)
            print(f"    total pages: {total_pages}, total results: {data.get('found', '?')}")

        for r in data.get("results", []):
            try:
                lat = float(r["LATITUDE"])
                lon = float(r["LONGITUDE"])
            except (KeyError, TypeError, ValueError):
                continue
            name = r.get("BUILDING") or r.get("ADDRESS") or ""
            results.append({"lat": lat, "lon": lon, "name": name})

        page += 1
        if page <= total_pages:
            time.sleep(1.0)  # polite rate limiting

    df = pd.DataFrame(results).drop_duplicates(subset=["lat", "lon"])
    return df


# ---------------------------------------------------------------------------
# Processors: raw bytes -> standardised DataFrame
# ---------------------------------------------------------------------------
def process_parks(raw: bytes) -> pd.DataFrame:
    """Parks: lat, lon, name"""
    df = geojson_to_df(raw, name_candidates=["Name", "NAME", "name", "PARK_NAME", "DESCRIPTION"])
    if "name" not in df.columns and not df.empty:
        # Use first string column as name fallback
        str_cols = [c for c in df.columns if df[c].dtype == object and c not in ("lat","lon")]
        if str_cols:
            df["name"] = df[str_cols[0]]
        else:
            df["name"] = ""
    keep = ["lat", "lon"] + (["name"] if "name" in df.columns else [])
    return df[keep].dropna(subset=["lat", "lon"])


def process_markets(raw: bytes) -> pd.DataFrame:
    """Hawker centres: lat, lon, name"""
    df = geojson_to_df(raw, name_candidates=[
        "name", "NAME", "name_of_centre", "HAWKER_CENTRE_NAME",
        "Description", "DESCRIPTION", "HawkerCentreName"
    ])
    if "name" not in df.columns and not df.empty:
        str_cols = [c for c in df.columns if df[c].dtype == object and c not in ("lat","lon")]
        if str_cols:
            df["name"] = df[str_cols[0]]
    keep = ["lat", "lon"]
    if "name" in df.columns:
        keep.append("name")
    return df[keep].dropna(subset=["lat", "lon"])


def process_schools(raw: bytes) -> pd.DataFrame:
    """
    MOE Schools General Information CSV.
    Candidate column names for lat/lon vary across collection releases.
    Accepted patterns: latitude/longitude, lat/lng, y_address/x_address (SVY21 — rejected),
    address columns with geocoded coords.
    Falls back to OneMap search per school if coordinates not present.
    """
    import io
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        print(f"    [schools] CSV parse failed: {exc}")
        return pd.DataFrame()

    print(f"    Schools CSV columns: {list(df.columns)}")

    # Try to find lat/lon columns (case-insensitive)
    col_map = {c.lower(): c for c in df.columns}
    lat_col = col_map.get("latitude") or col_map.get("lat")
    lon_col = col_map.get("longitude") or col_map.get("lng") or col_map.get("lon")

    # Some releases have 'y_coord'/'x_coord' in SVY21 — not directly usable as lat/lon
    # Some have 'address' only — fallback to OneMap

    if lat_col and lon_col:
        df = df.rename(columns={lat_col: "lat", lon_col: "lon"})
        name_col = col_map.get("school_name") or col_map.get("name") or col_map.get("schoolname")
        if name_col:
            df = df.rename(columns={name_col: "name"})
        keep = ["lat", "lon"] + (["name"] if "name" in df.columns else [])
        df = df[keep].dropna(subset=["lat", "lon"])
        df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
        df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
        return df.dropna(subset=["lat", "lon"])
    else:
        # No coordinate columns — geocode via OneMap using postal codes (more accurate than names)
        name_col_raw = col_map.get("school_name") or col_map.get("name") or col_map.get("schoolname")
        postal_col_raw = col_map.get("postal_code") or col_map.get("postalcode") or col_map.get("postal")

        if postal_col_raw:
            print(f"    No lat/lon columns; geocoding {len(df)} schools via postal code...")
            rows = []
            for i, row in df.iterrows():
                postal = str(row[postal_col_raw]).strip().zfill(6)
                name = str(row[name_col_raw]).strip() if name_col_raw else postal
                result = onemap_geocode_single(postal)
                if result:
                    # carry useful extra columns for framework use
                    entry = {"lat": result[0], "lon": result[1], "name": name}
                    for extra in ["mainlevel_code", "type_code", "zone_code",
                                  "nature_code", "autonomous_ind", "gifted_ind",
                                  "ip_ind", "sap_ind", "postal_code"]:
                        if extra in df.columns:
                            entry[extra] = row.get(extra, "")
                    rows.append(entry)
                n = i + 1
                if n % 20 == 0:
                    print(f"    geocoded {n}/{len(df)} schools...")
                time.sleep(0.5)
            return pd.DataFrame(rows)
        elif name_col_raw:
            # Fallback: geocode by name
            print("    No postal_code column; geocoding by school name (less accurate)...")
            school_names = df[name_col_raw].dropna().unique()
            rows = []
            for i, sn in enumerate(school_names):
                result = onemap_geocode_single(sn)
                if result:
                    rows.append({"lat": result[0], "lon": result[1], "name": sn})
                if (i + 1) % 20 == 0:
                    print(f"    geocoded {i+1}/{len(school_names)} schools...")
                time.sleep(0.25)
            return pd.DataFrame(rows)
        else:
            print("    Cannot find school name or postal code column — skipping schools layer")
            return pd.DataFrame()


def process_mrt_names(raw: bytes) -> pd.DataFrame:
    """
    Train Station Names CSV (no coordinates).
    Outputs skeleton mrt_layer_names.csv for use with onemap_geocode_mrt.py.
    Expected columns: stn_code, mrt_station_english, mrt_line_english
    """
    import io
    try:
        df = pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
    except Exception as exc:
        print(f"    [mrt_names] CSV parse failed: {exc}")
        return pd.DataFrame()

    print(f"    MRT names CSV columns: {list(df.columns)}")

    # Normalise column names
    col_map = {c.lower().strip(): c for c in df.columns}
    rename = {}
    for src, dst in [
        ("stn_code", "stn_code"),
        ("mrt_station_english", "mrt_station_english"),
        ("mrt_line_english", "mrt_line_english"),
    ]:
        if src in col_map:
            rename[col_map[src]] = dst

    df = df.rename(columns=rename)
    keep = [c for c in ["stn_code", "mrt_station_english", "mrt_line_english"] if c in df.columns]
    df = df[keep].dropna(subset=["mrt_station_english"])
    df = df.drop_duplicates(subset=["mrt_station_english"])
    return df


def process_hdb_resale(raw: bytes) -> pd.DataFrame:
    """
    HDB Resale Flat Prices (Jan 2017 onwards).
    Cleans to the columns value_model.py expects:
        town, resale_price, floor_area_sqm, flat_type,
        storey_band, remaining_lease_years, month
    """
    import io
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:
        print(f"    [hdb] CSV parse failed: {exc}")
        return pd.DataFrame()

    print(f"    HDB CSV shape: {df.shape}, columns: {list(df.columns)[:12]}...")

    # data.gov.sg column names (as of 2024-25 schema)
    col_map = {c.lower().strip(): c for c in df.columns}

    # Town
    town_raw = col_map.get("town")
    if town_raw:
        df = df.rename(columns={town_raw: "town"})
    else:
        print("    [hdb] WARNING: 'town' column not found")

    # Resale price
    price_raw = col_map.get("resale_price")
    if price_raw:
        df = df.rename(columns={price_raw: "resale_price"})
        df["resale_price"] = pd.to_numeric(df["resale_price"], errors="coerce")

    # Floor area
    area_raw = col_map.get("floor_area_sqm")
    if area_raw:
        df = df.rename(columns={area_raw: "floor_area_sqm"})
        df["floor_area_sqm"] = pd.to_numeric(df["floor_area_sqm"], errors="coerce")

    # Flat type
    flat_raw = col_map.get("flat_type")
    if flat_raw:
        df = df.rename(columns={flat_raw: "flat_type"})

    # Storey band — data.gov.sg ships 'storey_range' as "01 TO 03" etc.
    storey_raw = col_map.get("storey_range") or col_map.get("storey_band")
    if storey_raw:
        df = df.rename(columns={storey_raw: "storey_band"})
    else:
        print("    [hdb] WARNING: no storey_range column found for storey_band")

    # Remaining lease — data.gov.sg ships as "95 years 00 months" or "95"
    lease_raw = col_map.get("remaining_lease") or col_map.get("remaining_lease_years")
    if lease_raw:
        df = df.rename(columns={lease_raw: "_lease_raw"})
        # Parse "95 years 00 months" -> 95, or "95" -> 95
        def parse_lease(val):
            if pd.isna(val):
                return float("nan")
            s = str(val).strip()
            if s.isdigit():
                return float(s)
            # extract leading integer
            parts = s.split()
            try:
                return float(parts[0])
            except (ValueError, IndexError):
                return float("nan")
        df["remaining_lease_years"] = df["_lease_raw"].apply(parse_lease)
        df = df.drop(columns=["_lease_raw"])
    else:
        # Derive from lease_commence_date if available
        lcd_raw = col_map.get("lease_commence_date")
        if lcd_raw:
            df["remaining_lease_years"] = 99 - (pd.to_numeric(df[lcd_raw], errors="coerce")
                                                  .rsub(2025))
            print("    [hdb] remaining_lease_years derived from lease_commence_date")
        else:
            print("    [hdb] WARNING: cannot derive remaining_lease_years")

    # Month
    month_raw = col_map.get("month")
    if month_raw:
        df = df.rename(columns={month_raw: "month"})

    expected = ["town", "resale_price", "floor_area_sqm", "flat_type",
                "storey_band", "remaining_lease_years", "month"]
    present = [c for c in expected if c in df.columns]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        print(f"    [hdb] Missing columns (will be absent in output): {missing}")

    df = df[present].dropna(subset=["town", "resale_price", "floor_area_sqm"])
    df["town"] = df["town"].str.upper().str.strip()
    return df


# ---------------------------------------------------------------------------
# OneMap single geocode (for school fallback)
# ---------------------------------------------------------------------------
def onemap_geocode_single(query: str) -> tuple[float, float] | None:
    """Search OneMap for a single query. Returns (lat, lon) or None.
    Retries on 429 with exponential backoff."""
    url = (
        f"{ONEMAP_SEARCH}"
        f"?searchVal={urllib.parse.quote(query)}"
        f"&returnGeom=Y&getAddrDetails=Y&pageNum=1"
    )
    for attempt in range(4):
        try:
            data = http_get_json(url, timeout=20)
            results = data.get("results", [])
            if results:
                r = results[0]
                lat = r.get("LATITUDE", "NIL")
                lon = r.get("LONGITUDE", "NIL")
                if lat != "NIL" and lon != "NIL":
                    return float(lat), float(lon)
            return None  # no results or NIL coords — don't retry
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                wait = 5 * (2 ** attempt)
                time.sleep(wait)
                continue
            return None
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Main ingestion loop
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true",
                        help="Re-download all layers even if output CSV already exists")
    args = parser.parse_args()

    def should_skip(filename: str) -> bool:
        if args.force:
            return False
        path = os.path.join(DATA_DIR, filename)
        if os.path.exists(path):
            print(f"  Skipping — {path} already exists (use --force to re-download)")
            return True
        return False

    status: dict[str, str] = {}

    # ------------------------------------------------------------------
    # 1. PARKS
    # ------------------------------------------------------------------
    print("\n[1/6] Parks (NParks)...")
    if should_skip("parks.csv"):
        status["parks.csv"] = "SKIP — already exists"
    else:
        raw = None
        for did in DATASETS["parks"]["ids"]:
            raw = poll_download(did)
            if raw:
                print(f"  Fetched {len(raw):,} bytes (id={did})")
                break
        if raw:
            df = process_parks(raw)
            if not df.empty:
                out = os.path.join(DATA_DIR, "parks.csv")
                df.to_csv(out, index=False)
                status["parks.csv"] = f"OK  — {len(df)} parks -> {out}"
            else:
                status["parks.csv"] = "WARN — fetched but GeoJSON parsed 0 rows"
        else:
            status["parks.csv"] = "FAIL — could not fetch from data.gov.sg"
        time.sleep(3)

    # ------------------------------------------------------------------
    # 2. MARKETS (Hawker Centres)
    # ------------------------------------------------------------------
    print("\n[2/6] Hawker Centres (markets)...")
    if should_skip("markets.csv"):
        status["markets.csv"] = "SKIP — already exists"
    else:
        raw = None
        for did in DATASETS["markets"]["ids"]:
            raw = poll_download(did)
            if raw:
                print(f"  Fetched {len(raw):,} bytes (id={did})")
                break
        if raw:
            df = process_markets(raw)
            if not df.empty:
                out = os.path.join(DATA_DIR, "markets.csv")
                df.to_csv(out, index=False)
                status["markets.csv"] = f"OK  — {len(df)} hawker centres -> {out}"
            else:
                status["markets.csv"] = "WARN — fetched but GeoJSON parsed 0 rows"
        else:
            status["markets.csv"] = "FAIL — could not fetch from data.gov.sg"
        time.sleep(3)

    # ------------------------------------------------------------------
    # 3. SCHOOLS
    # ------------------------------------------------------------------
    print("\n[3/6] Schools (MOE)...")
    raw = None
    used_id = None
    for did in DATASETS["schools"]["ids"]:
        raw = poll_download(did)
        if raw:
            import io
            # Quick check: is this the general info file or a CCA file?
            try:
                preview = pd.read_csv(io.BytesIO(raw), nrows=2)
                cols_lower = [c.lower() for c in preview.columns]
                has_name = any(x in cols_lower for x in ["school_name", "schoolname", "name"])
                # General Info has many columns (address, postal, telephone, etc.)
                # Narrow files (CCAs, Programmes, Subjects) have <5 columns — skip them
                if has_name and len(preview.columns) >= 5:
                    used_id = did
                    print(f"  Fetched {len(raw):,} bytes (id={did}) — {len(preview.columns)} cols, looks like general info")
                    break
                else:
                    reason = "no name col" if not has_name else f"only {len(preview.columns)} cols (narrow file)"
                    print(f"  id={did} — {reason}, cols: {list(preview.columns)[:6]} — skipping")
                    raw = None
            except Exception:
                used_id = did
                break
    if raw:
        df = process_schools(raw)
        if not df.empty:
            out = os.path.join(DATA_DIR, "schools.csv")
            df.to_csv(out, index=False)
            status["schools.csv"] = f"OK  — {len(df)} schools -> {out}"
        else:
            status["schools.csv"] = "WARN — fetched but produced 0 usable rows"
    else:
        status["schools.csv"] = "FAIL — could not find general info CSV in collection 457"

    time.sleep(3)

    # ------------------------------------------------------------------
    # 4. POLYCLINICS (OneMap Search, no auth)
    # ------------------------------------------------------------------
    print("\n[4/6] Polyclinics (OneMap Search)...")
    if should_skip("polyclinics.csv"):
        status["polyclinics.csv"] = "SKIP — already exists"
    else:
        df = fetch_polyclinics_onemap()
        if not df.empty:
            out = os.path.join(DATA_DIR, "polyclinics.csv")
            df.to_csv(out, index=False)
            status["polyclinics.csv"] = f"OK  — {len(df)} results -> {out}"
        else:
            status["polyclinics.csv"] = "FAIL — OneMap search returned 0 results"
        time.sleep(3)

    # ------------------------------------------------------------------
    # 5. MRT NAMES skeleton
    # ------------------------------------------------------------------
    print("\n[5/6] MRT station names (data.gov.sg — no coordinates)...")
    if should_skip("mrt_layer_names.csv"):
        status["mrt_layer_names.csv"] = "SKIP — already exists"
    else:
        raw = None
        for did in DATASETS["mrt_names"]["ids"]:
            raw = poll_download(did)
            if raw:
                print(f"  Fetched {len(raw):,} bytes (id={did})")
                break
        if raw:
            df = process_mrt_names(raw)
            if not df.empty:
                out = os.path.join(DATA_DIR, "mrt_layer_names.csv")
                df.to_csv(out, index=False)
                status["mrt_layer_names.csv"] = (
                    f"OK  — {len(df)} stations (NAMES ONLY, no coordinates) -> {out}"
                )
            else:
                status["mrt_layer_names.csv"] = "WARN — fetched but parsed 0 rows"
        else:
            status["mrt_layer_names.csv"] = "FAIL — could not fetch from data.gov.sg"
        time.sleep(3)

    # ------------------------------------------------------------------
    # 6. HDB RESALE (value_model.py --hdb)
    # ------------------------------------------------------------------
    print("\n[6/6] HDB Resale Prices (Jan 2017 onwards)...")
    if should_skip("hdb_resale.csv"):
        status["hdb_resale.csv"] = "SKIP — already exists"
    else:
        raw = None
        used_id = None
        for did in DATASETS["hdb_resale"]["ids"]:
            raw = poll_download(did)
            if raw:
                import io
                try:
                    preview = pd.read_csv(io.BytesIO(raw), nrows=2)
                    cols_lower = [c.lower() for c in preview.columns]
                    if "town" in cols_lower and "resale_price" in cols_lower:
                        used_id = did
                        print(f"  Fetched {len(raw):,} bytes (id={did}) — confirmed HDB resale schema")
                        break
                    else:
                        print(f"  id={did} columns {list(preview.columns)[:6]} — not resale schema, skipping")
                        raw = None
                except Exception:
                    used_id = did
                    break
        if raw:
            df = process_hdb_resale(raw)
            if not df.empty:
                out = os.path.join(DATA_DIR, "hdb_resale.csv")
                df.to_csv(out, index=False)
                status["hdb_resale.csv"] = (
                    f"OK  — {len(df):,} transactions -> {out}  "
                    f"(towns: {df['town'].nunique()}, months: {df['month'].nunique() if 'month' in df.columns else '?'})"
                )
            else:
                status["hdb_resale.csv"] = "WARN — fetched but produced 0 usable rows"
        else:
            status["hdb_resale.csv"] = "FAIL — could not find resale CSV in collection 189"

    # ------------------------------------------------------------------
    # STATUS SUMMARY
    # ------------------------------------------------------------------
    print("\n" + "=" * 66)
    print("INGESTION SUMMARY")
    print("=" * 66)
    for fname, msg in status.items():
        tag = msg[:4].strip()
        icon = "+" if tag == "OK" else ("!" if tag == "WARN" else "X")
        print(f"  [{icon}] {fname:<28} {msg}")

    print()
    print("LAYERS REQUIRING MANUAL STEPS:")
    print("  [X] mrt_layer.csv        — run onemap_geocode_mrt.py with ONEMAP_TOKEN")
    print("                             mrt_layer_names.csv (above) provides the name/code list")
    print("  [X] bus.csv              — requires LTA DataMall API key")
    print("                             https://datamall.lta.gov.sg/content/datamall/en/request-for-api.html")
    print("  [X] chas.csv             — CHAS clinic layer requires OneMap token")
    print("                             https://www.onemap.gov.sg/apidocs/")

    print()
    print("NEXT STEPS:")
    print("  1. Obtain ONEMAP_TOKEN, run onemap_geocode_mrt.py to produce mrt_layer.csv")
    print("  2. Obtain LTA DataMall key, download bus stops to bus.csv (lat,lon)")
    print("  3. (Optional) With OneMap token: download CHAS clinics to chas.csv (lat,lon)")
    print("  4. Prepare estates.csv  (estate,lat,lon) and judged_inputs.csv (estate,dens,env,mom)")
    print("  5. Run provision_model.py:")
    print("       python provision_model.py \\")
    print("           --estates ../data/estates.csv \\")
    print("           --mrt     ../data/mrt_layer.csv \\")
    print("           --bus     ../data/bus.csv \\")
    print("           --clinics ../data/chas.csv \\")
    print("           --polyclinics ../data/polyclinics.csv \\")
    print("           --schools ../data/schools.csv \\")
    print("           --parks   ../data/parks.csv \\")
    print("           --markets ../data/markets.csv \\")
    print("           --judged  ../data/judged_inputs.csv \\")
    print("           --out     ../data/provision_scores.csv")
    print("  6. Run value_model.py:")
    print("       python value_model.py \\")
    print("           --scores ../data/provision_scores.csv \\")
    print("           --hdb    ../data/hdb_resale.csv \\")
    print("           --out    ../data/value_output.csv")

    # Return exit code 1 if any FAIL, for CI/scripting use
    failed = [k for k, v in status.items() if v.startswith("FAIL")]
    if failed:
        print(f"\nWARNING: {len(failed)} layer(s) failed to ingest: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
