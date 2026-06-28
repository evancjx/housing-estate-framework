#!/usr/bin/env python3
"""
Geocode private condominium projects with OneMap.

Reads:
  data/ura_private.csv

Writes:
  data/private_project_locations.csv

Run locally with network access:
  export ONEMAP_TOKEN="..."
  python3 models/geocode_private_projects.py

The script geocodes unique project/street/district keys, not every
transaction row. Output is intended to be reviewed and committed before
generating private_project_comparison_table.html.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).parent.parent
SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
CONDO_TYPE_RE = re.compile(r"\b(?:apartment|condominium|executive condominium)\b", re.I)

OUT_COLUMNS = [
    "project_name",
    "street_name",
    "postal_district",
    "planning_area",
    "lat",
    "lon",
    "match_status",
    "match_score",
    "query_used",
    "onemap_building",
    "onemap_road",
    "onemap_address",
    "onemap_postal",
    "review_note",
]


def normalise_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def clean_name(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def district_text(value: Any) -> str:
    text = clean_name(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(2) if text.isdigit() else text


def key_for(row: dict[str, Any] | pd.Series) -> tuple[str, str, str, str]:
    return (
        clean_name(row["project_name"]).upper(),
        clean_name(row["street_name"]).upper(),
        district_text(row["postal_district"]),
        clean_name(row["planning_area"]).upper(),
    )


def load_project_keys(private_path: Path) -> pd.DataFrame:
    private = pd.read_csv(private_path)
    required = {"planning_area", "project_name", "street_name", "postal_district", "property_type"}
    missing = sorted(required - set(private.columns))
    if missing:
        raise SystemExit(f"{private_path} missing required columns: {missing}")

    private = private.copy()
    private["property_type"] = private["property_type"].apply(clean_name)
    private = private[private["property_type"].str.contains(CONDO_TYPE_RE, na=False)].copy()
    private["project_name"] = private["project_name"].apply(clean_name)
    private["street_name"] = private["street_name"].apply(clean_name)
    private["postal_district"] = private["postal_district"].apply(district_text)
    private["planning_area"] = private["planning_area"].apply(lambda value: clean_name(value).upper())
    private = private[
        private["project_name"].ne("")
        & private["street_name"].ne("")
        & private["postal_district"].ne("")
        & private["planning_area"].ne("")
    ]
    keys = private[["project_name", "street_name", "postal_district", "planning_area"]].drop_duplicates()
    return keys.sort_values(["postal_district", "project_name", "street_name"]).reset_index(drop=True)


def load_existing(path: Path) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    if not path.exists():
        return {}
    existing: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            existing[key_for(row)] = row
    return existing


def onemap_search(query: str, token: str, max_pages: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        params = urllib.parse.urlencode(
            {
                "searchVal": query,
                "returnGeom": "Y",
                "getAddrDetails": "Y",
                "pageNum": page,
            }
        )
        req = urllib.request.Request(f"{SEARCH_URL}?{params}", headers={"Authorization": token})
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.load(response)
        page_results = payload.get("results", [])
        if not page_results:
            break
        results.extend(page_results)
        total = int(payload.get("found", len(results)) or len(results))
        if len(results) >= total:
            break
    return results


def score_result(project: str, street: str, result: dict[str, Any]) -> tuple[int, str]:
    project_norm = normalise_text(project)
    street_norm = normalise_text(street)
    building_norm = normalise_text(result.get("BUILDING"))
    road_norm = normalise_text(result.get("ROAD_NAME"))
    address_norm = normalise_text(result.get("ADDRESS"))

    haystack = " ".join([building_norm, road_norm, address_norm])
    score = 0
    reasons = []

    if project_norm and project_norm in haystack:
        score += 70
        reasons.append("project")
    else:
        project_words = [word for word in project_norm.split() if len(word) >= 3]
        if project_words:
            overlap = sum(1 for word in project_words if word in haystack)
            if overlap:
                score += min(50, int(50 * overlap / len(project_words)))
                reasons.append("partial_project")

    if street_norm and (street_norm in road_norm or street_norm in address_norm):
        score += 35
        reasons.append("street")
    else:
        street_words = [word for word in street_norm.split() if len(word) >= 3]
        if street_words:
            overlap = sum(1 for word in street_words if word in haystack)
            if overlap:
                score += min(25, int(25 * overlap / len(street_words)))
                reasons.append("partial_street")

    if "mrt station" in address_norm or "lrt station" in address_norm:
        score -= 25
        reasons.append("station_penalty")

    return score, ",".join(reasons)


def best_match(project: str, street: str, token: str, max_pages: int) -> dict[str, Any]:
    queries = [
        f"{project} {street}",
        project,
        street,
    ]
    best: tuple[int, str, str, dict[str, Any] | None] = (-999, "", "", None)
    for query in queries:
        try:
            results = onemap_search(query, token, max_pages)
        except Exception as exc:
            return {
                "lat": "",
                "lon": "",
                "match_status": "error",
                "match_score": 0,
                "query_used": query,
                "onemap_building": "",
                "onemap_road": "",
                "onemap_address": "",
                "onemap_postal": "",
                "review_note": str(exc),
            }
        for result in results:
            score, reasons = score_result(project, street, result)
            if score > best[0]:
                best = (score, reasons, query, result)
        if best[0] >= 90:
            break

    score, reasons, query, result = best
    if result is None:
        return {
            "lat": "",
            "lon": "",
            "match_status": "no_match",
            "match_score": 0,
            "query_used": "",
            "onemap_building": "",
            "onemap_road": "",
            "onemap_address": "",
            "onemap_postal": "",
            "review_note": "OneMap returned no candidates",
        }

    if score >= 90:
        status = "matched"
    elif score >= 55:
        status = "needs_review"
    else:
        status = "low_confidence"

    return {
        "lat": result.get("LATITUDE", ""),
        "lon": result.get("LONGITUDE", ""),
        "match_status": status,
        "match_score": score,
        "query_used": query,
        "onemap_building": result.get("BUILDING", ""),
        "onemap_road": result.get("ROAD_NAME", ""),
        "onemap_address": result.get("ADDRESS", ""),
        "onemap_postal": result.get("POSTAL", ""),
        "review_note": reasons,
    }


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> None:
    token = args.token or os.environ.get("ONEMAP_TOKEN")
    if not token:
        raise SystemExit("Set ONEMAP_TOKEN or pass --token.")

    private_path = Path(args.private)
    out_path = Path(args.out)
    projects = load_project_keys(private_path)
    existing = load_existing(out_path)
    rows: list[dict[str, Any]] = []
    processed = 0

    for _, project in projects.iterrows():
        key = key_for(project)
        if args.resume and key in existing and existing[key].get("match_status") not in {"", "error", "no_match"}:
            rows.append(existing[key])
            continue

        match = best_match(project["project_name"], project["street_name"], token, args.max_pages)
        row = {
            "project_name": project["project_name"],
            "street_name": project["street_name"],
            "postal_district": project["postal_district"],
            "planning_area": project["planning_area"],
            **match,
        }
        rows.append(row)
        processed += 1
        print(
            f"[{len(rows)}/{len(projects)}] D{project['postal_district']} "
            f"{project['project_name']} -> {row['match_status']} ({row['match_score']})"
        )
        write_rows(out_path, rows)
        if args.limit and processed >= args.limit:
            break
        time.sleep(args.sleep)

    if args.limit and processed >= args.limit:
        for _, project in projects.iloc[len(rows):].iterrows():
            key = key_for(project)
            if key in existing:
                rows.append(existing[key])

    # Preserve any existing manually-added rows not present in the current private feed.
    current_keys = {key_for(row) for row in rows}
    for key, row in existing.items():
        if key not in current_keys:
            rows.append(row)

    rows.sort(key=lambda row: (district_text(row["postal_district"]), clean_name(row["project_name"]), clean_name(row["street_name"])))
    write_rows(out_path, rows)
    print(f"\nWritten: {out_path} ({len(rows)} project location rows, {processed} queried)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocode private condo projects with OneMap")
    parser.add_argument("--private", default=str(ROOT / "data/ura_private.csv"), help="URA private transaction CSV")
    parser.add_argument("--out", default=str(ROOT / "data/private_project_locations.csv"), help="Output geocode CSV")
    parser.add_argument("--token", help="OneMap token; defaults to ONEMAP_TOKEN")
    parser.add_argument("--resume", action="store_true", default=True, help="Reuse existing non-empty geocode rows")
    parser.add_argument("--no-resume", dest="resume", action="store_false", help="Requery all project rows")
    parser.add_argument("--limit", type=int, help="Geocode at most N new rows")
    parser.add_argument("--max-pages", type=int, default=1, help="OneMap result pages to inspect per query")
    parser.add_argument("--sleep", type=float, default=0.25, help="Delay between queries")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
