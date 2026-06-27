#!/usr/bin/env python3
"""
Fetch CHAS clinics — tries data.gov.sg first, falls back to OneMap Search.
Writes SG-Estate-Framework/data/chas.csv  (lat, lon, name)
"""
import csv, html, json, os, re, sys, time, urllib.request, urllib.parse, urllib.error

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
OUT = os.path.join(DATA_DIR, "chas.csv")
ONEMAP_SEARCH = "https://www.onemap.gov.sg/api/common/elastic/search"
POLL_BASE = "https://api-open.data.gov.sg/v1/public/api/datasets/{}/poll-download"
# CHAS Clinics — data.gov.sg dataset. The /datasets search API no longer surfaces it, but
# poll-download by this ID works. GeoJSON FeatureCollection (~1190 clinics, lat/lon + HCI_NAME).
CHAS_DATASET_ID = "d_548c33ea2d99e29ec63a7cc9edcccedc"

def http_get_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "sg-estate-ingest/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def http_get_bytes(url, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "sg-estate-ingest/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

# ------------------------------------------------------------------
# Strategy 0 (primary): known CHAS dataset by ID
# ------------------------------------------------------------------
def _chas_from_geojson(raw: bytes):
    """Parse the data.gov.sg CHAS GeoJSON (a KML export): take lon/lat from each feature's
    geometry and the clinic name from HCI_NAME inside the HTML-encoded Description attribute table."""
    d = json.loads(raw)
    rows = []
    for f in d.get("features", []):
        geom = f.get("geometry") or {}
        c = geom.get("coordinates")
        if not c or len(c) < 2:
            continue
        try:
            lon, lat = float(c[0]), float(c[1])
        except (TypeError, ValueError):
            continue
        if lat == 0 and lon == 0:
            continue
        desc = (f.get("properties", {}) or {}).get("Description", "") or ""
        pairs = dict(re.findall(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", desc, re.S))
        name = html.unescape(pairs.get("HCI_NAME", pairs.get("NAME", ""))).strip()
        rows.append({"lat": lat, "lon": lon, "name": name})
    return rows


def try_datagov_known():
    """Primary source: the known CHAS Clinics dataset, fetched by ID via poll-download."""
    print(f"[1/3] Fetching known CHAS dataset {CHAS_DATASET_ID}...")
    try:
        meta = http_get_json(POLL_BASE.format(CHAS_DATASET_ID), timeout=25)
        url = meta.get("data", {}).get("url") or meta.get("url")
        if not url:
            print("    no download URL in poll response")
            return None
        rows = _chas_from_geojson(http_get_bytes(url, timeout=60))
        print(f"    parsed {len(rows)} clinics")
        return rows or None
    except Exception as e:
        print(f"    failed: {e}")
        return None

# ------------------------------------------------------------------
# Strategy 1: data.gov.sg search -> poll-download
# ------------------------------------------------------------------
def try_datagov():
    print("[1/2] Searching data.gov.sg for CHAS clinic dataset...")
    try:
        search = http_get_json(
            "https://api-open.data.gov.sg/v1/public/api/datasets"
            "?query=CHAS+clinic&resultSize=10", timeout=15)
        datasets = search.get("data", {}).get("datasets", [])
        candidates = [d for d in datasets
                      if "chas" in d.get("name", "").lower()
                      or "clinic" in d.get("name", "").lower()]
        print(f"  Found {len(candidates)} candidate(s): "
              f"{[d.get('name','') for d in candidates]}")
    except Exception as e:
        print(f"  data.gov.sg search failed: {e}")
        return None

    for d in candidates:
        did = d.get("datasetId")
        if not did:
            continue
        print(f"  Trying dataset {did} — {d.get('name','')}")
        try:
            meta = http_get_json(POLL_BASE.format(did), timeout=20)
            file_url = (meta.get("data", {}).get("url") or meta.get("url"))
            if not file_url:
                print(f"    No URL in response")
                continue
            raw = http_get_bytes(file_url, timeout=60)
            # detect format
            if raw[:1] == b"{" or raw[:1] == b"[":
                # GeoJSON or JSON array
                data = json.loads(raw)
                rows = []
                features = data.get("features", data if isinstance(data, list) else [])
                for feat in features:
                    geom = feat.get("geometry", {}) if isinstance(feat, dict) else {}
                    props = feat.get("properties", {}) if isinstance(feat, dict) else feat
                    coords = geom.get("coordinates") if geom else None
                    if coords:
                        lon, lat = float(coords[0]), float(coords[1])
                    else:
                        try:
                            lat = float(props.get("lat") or props.get("latitude") or 0)
                            lon = float(props.get("lon") or props.get("longitude") or 0)
                        except (TypeError, ValueError):
                            continue
                    if lat == 0 and lon == 0:
                        continue
                    name = props.get("name") or props.get("NAME") or props.get("clinic_name") or ""
                    rows.append({"lat": lat, "lon": lon, "name": name})
                if rows:
                    print(f"    Got {len(rows)} clinics from GeoJSON/JSON")
                    return rows
            else:
                # CSV
                import io, pandas as pd
                df = pd.read_csv(io.BytesIO(raw))
                print(f"    CSV columns: {list(df.columns)[:10]}")
                col_map = {c.lower().strip(): c for c in df.columns}
                lat_col = col_map.get("lat") or col_map.get("latitude")
                lon_col = col_map.get("lon") or col_map.get("longitude") or col_map.get("lng")
                if lat_col and lon_col:
                    name_col = (col_map.get("name") or col_map.get("clinic_name")
                                or col_map.get("hci_name") or list(df.columns)[0])
                    rows = []
                    for _, r in df.iterrows():
                        try:
                            lat, lon = float(r[lat_col]), float(r[lon_col])
                            if lat == 0 and lon == 0:
                                continue
                            rows.append({"lat": lat, "lon": lon, "name": str(r.get(name_col, ""))})
                        except (TypeError, ValueError):
                            continue
                    if rows:
                        print(f"    Got {len(rows)} clinics from CSV")
                        return rows
        except Exception as e:
            print(f"    Failed: {e}")
    return None

# ------------------------------------------------------------------
# Strategy 2: OneMap Search (no token needed)
# ------------------------------------------------------------------
def try_onemap_search():
    print("[2/2] Falling back to OneMap Search API (no token)...")
    results = []
    for query in ["CHAS clinic", "GP clinic", "family clinic"]:
        print(f"  Searching: '{query}'...")
        page, total_pages = 1, 1
        seen = set()
        while page <= total_pages:
            url = (f"{ONEMAP_SEARCH}?searchVal={urllib.parse.quote(query)}"
                   f"&returnGeom=Y&getAddrDetails=Y&pageNum={page}")
            try:
                data = http_get_json(url, timeout=20)
            except Exception as e:
                print(f"    page {page} failed: {e}")
                break
            if page == 1:
                total_pages = data.get("totalNumPages", 1)
                print(f"    {data.get('found','?')} results, {total_pages} pages")
            for r in data.get("results", []):
                try:
                    lat = float(r["LATITUDE"])
                    lon = float(r["LONGITUDE"])
                    key = (round(lat, 5), round(lon, 5))
                    if key in seen:
                        continue
                    seen.add(key)
                    name = r.get("BUILDING") or r.get("ADDRESS") or ""
                    results.append({"lat": lat, "lon": lon, "name": name})
                except (KeyError, TypeError, ValueError):
                    pass
            page += 1
            if page <= total_pages:
                time.sleep(0.3)
        print(f"    Subtotal after '{query}': {len(results)}")

    # dedupe across all queries
    seen, out = set(), []
    for r in results:
        key = (round(r["lat"], 5), round(r["lon"], 5))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main():
    rows = try_datagov_known()
    if not rows:
        rows = try_datagov()
    if not rows:
        rows = try_onemap_search()

    if not rows:
        print("ERROR: Could not fetch CHAS clinics from any source.")
        sys.exit(1)

    # Fail loud rather than silently overwriting the canonical layer with a near-empty result.
    # The OneMap CHAS search has degraded before (returned ~3 clinics vs the real ~1000+),
    # which would silently collapse the provision `hlth` component across estates.
    MIN_EXPECTED_CLINICS = 200
    if len(rows) < MIN_EXPECTED_CLINICS:
        sys.exit(f"ERROR: only {len(rows)} clinics fetched (< {MIN_EXPECTED_CLINICS}); "
                 f"refusing to overwrite {OUT}. The CHAS source is likely broken — "
                 f"keep the committed chas.csv and investigate the fetch.")

    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["lat", "lon", "name"])
        w.writeheader()
        w.writerows(rows)

    print(f"\nDone — {len(rows)} clinics written to {OUT}")
    print("Re-run provision_model.py adding:  --clinics ../data/chas.csv")

if __name__ == "__main__":
    main()
