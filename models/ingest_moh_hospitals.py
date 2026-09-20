#!/usr/bin/env python3
"""
MOH public-hospital ingester
============================
Fetches the Singapore hospital directory from the OneMap `moh_hospitals` theme
(owner: MINISTRY OF HEALTH), keeps the public acute and community hospitals, and
writes data/inputs/hospitals.csv.

PROVENANCE: MEASURED names and coordinates.
  Both the facility list and its coordinates come from the MOH-owned OneMap
  theme, so no geocoding step is involved.
  The 24h A&E flag remains a hand-curated allowlist because the theme exposes no
  emergency-department boolean. Keeping the allowlist explicit is more honest
  than inferring A&E from name/type strings.

WHY NOT data.gov.sg (changed 2026-09-20):
  The previous discovery path is dead — collection 521 and the public dataset
  search API both return HTTP 403. The OneMap Search geocoder it fed is also
  unsafe for this job: taking the first result returns "SGH BLK 4 (TAXI STAND)"
  for Singapore General Hospital, a clinical department for Tan Tock Seng, and
  an unrelated GP clinic for "Woodlands Health". The theme carries authoritative
  per-facility coordinates, which removes that failure mode entirely.
  `geocode_onemap` is retained only as an explicit opt-in fallback.

WHAT IS EXCLUDED AND WHY:
  The theme lists 31 facilities including private hospitals (Gleneagles, Mount
  Elizabeth, Raffles, Farrer Park, Parkway East, Thomson, Mount Alvernia,
  Crawfurd) and non-acute specialist sites (National Heart Centre, TTSH
  Integrated Care Hub, IMH/Woodbridge). Only names in HOSPITAL_TIER_ALIASES are
  retained, so the layer measures public-system access rather than total
  hospital capacity. Revisit that choice if the framework ever wants to price
  private healthcare access.

OUTPUT (data/inputs/hospitals.csv):
  name, lat, lon, has_ae, tier

  tier in {"acute", "community"}. The acute tier is the public acute-hospital
  set; community hospitals are retained when present in the source, but the
  hard-fail guard applies to acute hospitals because that is the provision
  layer this ingester is intended to support.

INPUT CONTRACT:
  --out         output CSV path (default: data/inputs/hospitals.csv)
  --theme-json  optional path to a saved theme payload, for an offline rebuild
                (data/raw/onemap/moh_hospitals.json is committed for this)
  --cache-dir   optional directory for the fetched theme payload

ENVIRONMENT:
  ONEMAP_TOKEN  required unless --theme-json is given. OneMap tokens expire
                every 3 days; the script fails loudly rather than writing a
                short list.

RUN:
  python3 models/ingest_moh_hospitals.py --out data/inputs/hospitals.csv
  python3 models/ingest_moh_hospitals.py --theme-json data/raw/onemap/moh_hospitals.json
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "inputs")
OUT = os.path.join(DATA_DIR, "hospitals.csv")

COLLECTION_ID = "521"
COLLECTION_URL = (
    "https://api-open.data.gov.sg/v1/public/api/collections/{collection_id}"
)
DATASET_SEARCH_URL = (
    "https://api-open.data.gov.sg/v1/public/api/datasets"
    "?query={query}&resultSize=25"
)
POLL_URL = "https://api-open.data.gov.sg/v1/public/api/datasets/{ds}/poll-download"
ONEMAP_SEARCH = "https://www.onemap.gov.sg/api/common/elastic/search"
_UA = "sg-estate-ingest/1.0 (moh-hospitals)"

MIN_EXPECTED_ACUTE = 8

# Alias/name inventory for public acute and community hospitals. The source
# dataset is still authoritative: these aliases only decide which source rows
# are retained and how their tier is labeled.
HOSPITAL_TIER_ALIASES = {
    "Alexandra Hospital": ("Alexandra Hospital", "acute"),
    "Changi General Hospital": ("Changi General Hospital", "acute"),
    "Khoo Teck Puat Hospital": ("Khoo Teck Puat Hospital", "acute"),
    "KK Women's and Children's Hospital": (
        "KK Women's and Children's Hospital",
        "acute",
    ),
    "KK Womens and Childrens Hospital": (
        "KK Women's and Children's Hospital",
        "acute",
    ),
    "National University Hospital": ("National University Hospital", "acute"),
    "Ng Teng Fong General Hospital": (
        "Ng Teng Fong General Hospital",
        "acute",
    ),
    "Sengkang General Hospital": ("Sengkang General Hospital", "acute"),
    "Singapore General Hospital": ("Singapore General Hospital", "acute"),
    "Tan Tock Seng Hospital": ("Tan Tock Seng Hospital", "acute"),
    "Woodlands Health": ("Woodlands Health", "acute"),
    "Woodlands Hospital": ("Woodlands Health", "acute"),
    "Woodlands Health Campus": ("Woodlands Health", "acute"),
    "Ang Mo Kio Thye Hua Kwan Hospital": (
        "Ang Mo Kio - Thye Hua Kwan Hospital",
        "community",
    ),
    "Bright Vision Hospital": ("Bright Vision Hospital", "community"),
    "Jurong Community Hospital": ("Jurong Community Hospital", "community"),
    "Outram Community Hospital": ("Outram Community Hospital", "community"),
    "Ren Ci Community Hospital": ("Ren Ci Community Hospital", "community"),
    "Sengkang Community Hospital": ("Sengkang Community Hospital", "community"),
    "St Andrew's Community Hospital": (
        "St Andrew's Community Hospital",
        "community",
    ),
    "St Andrews Community Hospital": (
        "St Andrew's Community Hospital",
        "community",
    ),
    "Woodlands Community Hospital": ("Woodlands Community Hospital", "community"),
    "Yishun Community Hospital": ("Yishun Community Hospital", "community"),
}

# 24h emergency/A&E handling is hand-curated because the data.gov.sg/MOH layer
# does not publish a reliable machine-readable emergency-department flag.
AE_24H_ALLOWLIST = {
    "Changi General Hospital",
    "Khoo Teck Puat Hospital",
    "KK Women's and Children's Hospital",
    "National University Hospital",
    "Ng Teng Fong General Hospital",
    "Sengkang General Hospital",
    "Singapore General Hospital",
    "Tan Tock Seng Hospital",
    "Woodlands Health",
}


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9]+", " ", value)).strip().upper()


_TIER_MATCHERS = sorted(
    (
        (_normalise_text(alias), canonical, tier)
        for alias, (canonical, tier) in HOSPITAL_TIER_ALIASES.items()
    ),
    key=lambda item: -len(item[0]),
)
_AE_ALLOWLIST_NORM = {_normalise_text(name) for name in AE_24H_ALLOWLIST}


def has_ae_24h(name: str) -> bool:
    """Return True when `name` is in the explicit 24h A&E allowlist."""
    return _normalise_text(name) in _AE_ALLOWLIST_NORM


def classify_hospital(name: str) -> tuple[str, str] | None:
    """Return (canonical_name, tier) for retained public hospital names."""
    n = _normalise_text(name)
    if not n:
        return None
    for needle, canonical, tier in _TIER_MATCHERS:
        if needle in n:
            return canonical, tier
    return None


THEME_URL = (
    "https://www.onemap.gov.sg/api/public/themesvc/retrieveTheme"
    "?queryName=moh_hospitals"
)


def fetch_theme_payload(token: str | None = None, timeout: int = 60) -> dict:
    """Fetch the MOH hospitals theme. Requires a live ONEMAP_TOKEN."""
    token = token if token is not None else os.environ.get("ONEMAP_TOKEN", "")
    if not token:
        raise RuntimeError(
            "ONEMAP_TOKEN is not set. The moh_hospitals theme requires a token "
            "(they expire every 3 days). Refresh it, or pass --theme-json to "
            "rebuild offline from the committed payload."
        )
    req = urllib.request.Request(
        THEME_URL,
        headers={"Authorization": token, "User-Agent": _UA, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise RuntimeError(
                "OneMap rejected ONEMAP_TOKEN (401). The token has expired; "
                "refresh it or pass --theme-json."
            ) from exc
        raise RuntimeError(f"moh_hospitals theme fetch failed: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"moh_hospitals theme fetch failed: {exc}") from exc


def parse_theme_rows(payload: dict) -> list[dict]:
    """Theme features as {name, address, lat, lon}, coordinates taken verbatim.

    SrchResults[0] is a FeatCount/Theme_Name header rather than a facility, and a
    feature whose LatLng is missing or unparseable is dropped rather than guessed.
    """
    results = (payload or {}).get("SrchResults") or []
    rows = []
    for feature in results[1:]:
        if not isinstance(feature, dict):
            continue
        name = str(feature.get("NAME") or "").strip()
        if not name:
            continue
        parts = str(feature.get("LatLng") or "").split(",")
        if len(parts) != 2:
            continue
        try:
            lat, lon = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        if not (math.isfinite(lat) and math.isfinite(lon)) or (lat == 0 and lon == 0):
            continue
        rows.append({
            "name": name,
            "address": str(feature.get("ADDRESSSTREETNAME") or "").strip(),
            "lat": lat,
            "lon": lon,
        })
    return rows


def _http_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _UA, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_bytes(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _extract_dataset_ids(node) -> list[str]:
    ids = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"datasetId", "dataset_id"} and isinstance(value, str):
                ids.append(value)
            else:
                ids.extend(_extract_dataset_ids(value))
    elif isinstance(node, list):
        for item in node:
            ids.extend(_extract_dataset_ids(item))
    seen = set()
    out = []
    for ds in ids:
        if ds not in seen:
            seen.add(ds)
            out.append(ds)
    return out


def discover_collection_dataset_ids() -> list[str]:
    url = COLLECTION_URL.format(collection_id=COLLECTION_ID)
    try:
        payload = _http_json(url, timeout=30)
    except Exception as exc:
        print(f"  data.gov.sg collection {COLLECTION_ID} lookup failed: {exc}", file=sys.stderr)
        return []
    return _extract_dataset_ids(payload)


def search_health_facility_dataset_ids() -> list[str]:
    ids = []
    for query in ["MOH health facilities", "health facilities hospital"]:
        url = DATASET_SEARCH_URL.format(query=urllib.parse.quote(query))
        try:
            payload = _http_json(url, timeout=30)
        except Exception as exc:
            print(f"  data.gov.sg dataset search '{query}' failed: {exc}", file=sys.stderr)
            continue
        for ds in _extract_dataset_ids(payload):
            if ds not in ids:
                ids.append(ds)
    return ids


def poll_download(dataset_id: str, timeout: int = 90, retries: int = 4) -> bytes:
    poll_url = POLL_URL.format(ds=dataset_id)
    for attempt in range(retries):
        try:
            poll = _http_json(poll_url, timeout=30)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt + 1 < retries:
                wait = 5 * (2 ** attempt)
                print(
                    f"  poll-download 429 for {dataset_id}; waiting {wait}s",
                    file=sys.stderr,
                )
                time.sleep(wait)
                continue
            raise RuntimeError(f"poll-download failed for {dataset_id}: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"poll-download failed for {dataset_id}: {exc}") from exc

        file_url = poll.get("data", {}).get("url") or poll.get("url")
        if not file_url:
            raise RuntimeError(f"poll-download for {dataset_id} returned no download URL")
        try:
            return _http_bytes(file_url, timeout=timeout)
        except Exception as exc:
            raise RuntimeError(f"download failed for {dataset_id}: {exc}") from exc
    raise RuntimeError(f"poll-download exhausted retries for {dataset_id}")


_DESC_RE = re.compile(r"<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>", re.S | re.I)


def _clean_html_text(value) -> str:
    if value is None:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _normalise_key(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", value).upper()


def _description_props(value) -> dict:
    text = "" if value is None else str(value)
    out = {}
    for key, val in _DESC_RE.findall(text):
        clean_key = _clean_html_text(key)
        if clean_key:
            out[clean_key] = _clean_html_text(val)
    return out


def _merged_props(props: dict) -> dict:
    merged = dict(props or {})
    desc = props.get("Description") or props.get("description") if props else None
    merged.update(_description_props(desc))
    return merged


def _prop(props: dict, candidates: list[str]) -> str:
    keyed = {_normalise_key(k): v for k, v in props.items()}
    for candidate in candidates:
        val = keyed.get(_normalise_key(candidate))
        if val is not None and not pd.isna(val):
            text = str(val).strip()
            if text:
                return text
    return ""


def parse_health_facility_rows(raw: bytes) -> list[dict]:
    """Parse data.gov.sg bytes into source rows with name/address/type fields."""
    if not raw:
        return []
    stripped = raw.lstrip()
    rows = []
    if stripped[:1] in {b"{", b"["}:
        payload = json.loads(raw.decode("utf-8"))
        features = payload.get("features") if isinstance(payload, dict) else payload
        if not isinstance(features, list):
            return []
        for item in features:
            props = item.get("properties", item) if isinstance(item, dict) else {}
            props = _merged_props(props)
            name = _prop(
                props,
                [
                    "HCI_NAME",
                    "NAME",
                    "name",
                    "LICENCE_NAME",
                    "INSTITUTION_NAME",
                    "PREMISES_NAME",
                    "FACILITY_NAME",
                    "HEALTHCARE_INSTITUTION_NAME",
                ],
            )
            address = _prop(
                props,
                ["ADDRESS", "addr", "LOCATION", "PREMISES_ADDRESS", "street_address"],
            )
            facility_type = _prop(
                props,
                [
                    "HCI_TYPE",
                    "TYPE",
                    "FACILITY_TYPE",
                    "HEALTHCARE_SERVICE",
                    "INSTITUTION_TYPE",
                ],
            )
            if name:
                rows.append({"name": name, "address": address, "type": facility_type})
        return rows

    df = pd.read_csv(io.BytesIO(raw))
    if df.empty:
        return []
    for _, record in df.iterrows():
        props = record.to_dict()
        name = _prop(
            props,
            [
                "HCI_NAME",
                "NAME",
                "name",
                "LICENCE_NAME",
                "INSTITUTION_NAME",
                "PREMISES_NAME",
                "FACILITY_NAME",
                "HEALTHCARE_INSTITUTION_NAME",
            ],
        )
        address = _prop(
            props,
            ["ADDRESS", "addr", "LOCATION", "PREMISES_ADDRESS", "street_address"],
        )
        facility_type = _prop(
            props,
            ["HCI_TYPE", "TYPE", "FACILITY_TYPE", "HEALTHCARE_SERVICE", "INSTITUTION_TYPE"],
        )
        if name:
            rows.append({"name": name, "address": address, "type": facility_type})
    return rows


def fetch_health_facility_rows(cache_dir: str | None = None) -> list[dict]:
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)

    dataset_ids = discover_collection_dataset_ids()
    if not dataset_ids:
        dataset_ids = search_health_facility_dataset_ids()
    if not dataset_ids:
        raise RuntimeError(
            "could not discover MOH health-facilities dataset IDs from "
            "data.gov.sg collection 521 or dataset search"
        )

    print(f"Trying {len(dataset_ids)} data.gov.sg candidate dataset(s)", file=sys.stderr)
    for dataset_id in dataset_ids:
        cache_path = os.path.join(cache_dir, f"{dataset_id}.raw") if cache_dir else None
        try:
            if cache_path and os.path.exists(cache_path):
                with open(cache_path, "rb") as f:
                    raw = f.read()
            else:
                raw = poll_download(dataset_id)
                if cache_path:
                    with open(cache_path, "wb") as f:
                        f.write(raw)
        except RuntimeError as exc:
            print(f"  {exc}", file=sys.stderr)
            continue

        rows = parse_health_facility_rows(raw)
        retained = [r for r in rows if classify_hospital(r.get("name", ""))]
        print(
            f"  {dataset_id}: parsed {len(rows)} facility rows, "
            f"{len(retained)} retained public hospitals",
            file=sys.stderr,
        )
        if retained:
            return retained

    raise RuntimeError("no public hospital rows found in discovered MOH datasets")


def geocode_onemap(name: str, address: str = "") -> tuple[float, float] | None:
    search_text = " ".join(part for part in [name, address] if part).strip()
    if not search_text:
        return None
    url = (
        f"{ONEMAP_SEARCH}?searchVal={urllib.parse.quote(search_text)}"
        "&returnGeom=Y&getAddrDetails=Y&pageNum=1"
    )
    try:
        payload = _http_json(url, timeout=20)
    except Exception as exc:
        raise RuntimeError(f"OneMap search failed for {name}: {exc}") from exc
    for result in payload.get("results", []):
        try:
            lat = float(result["LATITUDE"])
            lon = float(result["LONGITUDE"])
        except (KeyError, TypeError, ValueError):
            continue
        if lat == 0 and lon == 0:
            continue
        return lat, lon
    return None


def build_hospital_rows(source_rows: list[dict], geocode_func=geocode_onemap) -> list[dict]:
    rows = []
    seen = set()
    for source in source_rows:
        classified = classify_hospital(source.get("name", ""))
        if classified is None:
            continue
        canonical, tier = classified
        if canonical in seen:
            continue
        seen.add(canonical)
        if source.get("lat") is not None and source.get("lon") is not None:
            # Theme-sourced rows already carry MOH coordinates; geocoding them
            # would only reintroduce the OneMap Search mismatch problem.
            lat, lon = float(source["lat"]), float(source["lon"])
        else:
            geocoded = geocode_func(canonical, source.get("address", ""))
            if not geocoded:
                continue
            lat, lon = geocoded
        if lat == 0 and lon == 0:
            continue
        rows.append(
            {
                "name": canonical,
                "lat": lat,
                "lon": lon,
                "has_ae": has_ae_24h(canonical),
                "tier": tier,
            }
        )
    return sorted(rows, key=lambda row: (row["tier"], row["name"]))


def require_min_acute(rows: list[dict], out_path: str = OUT) -> None:
    n_acute = sum(1 for row in rows if row.get("tier") == "acute")
    if n_acute < MIN_EXPECTED_ACUTE:
        sys.exit(
            f"ERROR: only {n_acute} acute public hospitals resolved/geocoded "
            f"(< {MIN_EXPECTED_ACUTE}); refusing to write {out_path}. "
            "The MOH source or OneMap geocoding path is likely incomplete."
        )


def write_rows(rows: list[dict], out_path: str) -> None:
    if not rows:
        sys.exit(f"ERROR: no hospital rows to write; refusing to write {out_path}")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "lat", "lon", "has_ae", "tier"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=OUT)
    ap.add_argument(
        "--theme-json",
        help="rebuild offline from a saved moh_hospitals payload "
             "(e.g. data/raw/onemap/moh_hospitals.json)",
    )
    ap.add_argument("--cache-dir", help="cache the fetched theme payload")
    args = ap.parse_args()

    try:
        if args.theme_json:
            with open(args.theme_json, encoding="utf-8") as fh:
                payload = json.load(fh)
        else:
            payload = fetch_theme_payload()
            if args.cache_dir:
                os.makedirs(args.cache_dir, exist_ok=True)
                cached = os.path.join(args.cache_dir, "moh_hospitals.json")
                with open(cached, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=1, ensure_ascii=False, sort_keys=True)
                    fh.write("\n")
        source_rows = parse_theme_rows(payload)
        if not source_rows:
            sys.exit("ERROR: moh_hospitals theme returned no usable facilities")
        print(f"Theme returned {len(source_rows)} facilities", file=sys.stderr)
        rows = build_hospital_rows(source_rows)
    except OSError as exc:
        sys.exit(f"ERROR: could not read {args.theme_json}: {exc}")
    except RuntimeError as exc:
        sys.exit(f"ERROR: {exc}")

    require_min_acute(rows, args.out)
    write_rows(rows, args.out)
    print(f"Wrote {len(rows)} hospitals -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
