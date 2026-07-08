#!/usr/bin/env python3
"""
MOH public-hospital ingester
============================
Fetches Singapore public hospital records from MOH health-facilities data
on data.gov.sg collection 521 where available, geocodes the retained
hospital names through OneMap Search, and writes data/inputs/hospitals.csv.

PROVENANCE: PARTLY_MEASURED.
  Hospital names are sourced from MOH/data.gov.sg health-facilities data.
  Coordinates are MEASURED by OneMap geocoding of those facility names.
  The 24h A&E flag is a hand-curated allowlist because the public facility
  directory does not expose a clean emergency-department boolean. Keeping the
  allowlist explicit is more honest than inferring A&E from name/type strings.

DATA SOURCE ASSUMPTION:
  data.gov.sg collection 521 is expected to contain the MOH health-facilities
  datasets. This script first tries the collection API, then falls back to the
  public dataset search API for "MOH health facilities" candidates and the
  standard poll-download flow.

OUTPUT (data/inputs/hospitals.csv):
  name, lat, lon, has_ae, tier

  tier in {"acute", "community"}. The acute tier is the public acute-hospital
  set; community hospitals are retained when present in the source, but the
  hard-fail guard applies to acute hospitals because that is the provision
  layer this ingester is intended to support.

INPUT CONTRACT:
  --out        output CSV path (default: data/inputs/hospitals.csv)
  --cache-dir  optional directory for fetched data.gov.sg payload bytes

RUN:
  python3 models/ingest_moh_hospitals.py --out data/inputs/hospitals.csv
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
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
    ap.add_argument("--cache-dir", help="cache fetched data.gov.sg payload bytes")
    args = ap.parse_args()

    try:
        source_rows = fetch_health_facility_rows(args.cache_dir)
        rows = build_hospital_rows(source_rows)
    except RuntimeError as exc:
        sys.exit(f"ERROR: {exc}")

    require_min_acute(rows, args.out)
    write_rows(rows, args.out)
    print(f"Wrote {len(rows)} hospitals -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
