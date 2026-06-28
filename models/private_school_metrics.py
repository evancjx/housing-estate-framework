#!/usr/bin/env python3
"""
Private project school-access diagnostics.

This is intentionally a sidecar to provision_model.py. Provision keeps its
generic estate-level school component, while this module reports private-buyer
diagnostics at the project coordinate level when reviewed OneMap geocodes are
available.

Reads:
  data/private_project_locations.csv
  data/schools.csv
  data/school_selectivity.csv

Writes:
  data/private_project_school_metrics.csv
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).parent.parent

DEFAULT_LOCATIONS = ROOT / "data/private_project_locations.csv"
DEFAULT_SCHOOLS = ROOT / "data/schools.csv"
DEFAULT_SELECTIVITY = ROOT / "data/school_selectivity.csv"
DEFAULT_OUT = ROOT / "data/private_project_school_metrics.csv"
DEFAULT_ELIGIBLE_MATCH_STATUSES = {"matched"}


def normalise_school_name(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return re.sub(r"[^A-Z0-9]+", " ", str(value).upper()).strip()


def normalise_level(value: Any) -> str:
    text = str(value).strip().lower()
    if text in {"primary", "secondary", "year_5_jc"}:
        return text
    if "primary" in text or re.search(r"\bP1\b", text.upper()):
        return "primary"
    if "junior college" in text or re.search(r"\bJC\d*\b", text.upper()):
        return "year_5_jc"
    if "secondary" in text or re.search(r"\bS[1-5]\b", text.upper()):
        return "secondary"
    return text


def school_levels(mainlevel_code: Any) -> list[str]:
    text = str(mainlevel_code).upper()
    levels: list[str] = []
    if "PRIMARY" in text or re.search(r"\bP1\b", text):
        levels.append("primary")
    if "SECONDARY" in text or re.search(r"\bS[1-5]\b", text):
        levels.append("secondary")
    if "JUNIOR COLLEGE" in text or re.search(r"\bJC\d*\b", text):
        levels.append("year_5_jc")
    return levels


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def load_schools(path: Path) -> pd.DataFrame:
    schools = pd.read_csv(path)
    required = {"name", "lat", "lon", "mainlevel_code"}
    missing = sorted(required - set(schools.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")

    rows: list[dict[str, Any]] = []
    for _, row in schools.iterrows():
        for level in school_levels(row["mainlevel_code"]):
            rows.append({
                "school_name": str(row["name"]).strip(),
                "school_name_norm": normalise_school_name(row["name"]),
                "level": level,
                "school_lat": float(row["lat"]),
                "school_lon": float(row["lon"]),
                "mainlevel_code": row["mainlevel_code"],
            })
    return pd.DataFrame(rows)


def load_selectivity(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=[
            "school_name_norm", "level", "rank", "score_raw", "score_normalized",
            "metric_type", "source_year", "source_quality", "source_url",
        ])

    selectivity = pd.read_csv(path)
    required = {"school_name", "level", "rank", "score_raw", "score_normalized", "metric_type"}
    missing = sorted(required - set(selectivity.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")

    selectivity = selectivity.copy()
    selectivity["school_name_norm"] = selectivity["school_name"].apply(normalise_school_name)
    selectivity["level"] = selectivity["level"].apply(normalise_level)
    selectivity["rank"] = pd.to_numeric(selectivity["rank"], errors="coerce")
    selectivity["score_normalized"] = pd.to_numeric(selectivity["score_normalized"], errors="coerce")
    return selectivity


def load_locations(
    path: Path,
    eligible_match_statuses: set[str] | None = None,
) -> pd.DataFrame:
    locations = pd.read_csv(path)
    required = {"project_name", "street_name", "postal_district", "planning_area", "lat", "lon"}
    missing = sorted(required - set(locations.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")

    locations = locations.copy()
    locations["lat"] = pd.to_numeric(locations["lat"], errors="coerce")
    locations["lon"] = pd.to_numeric(locations["lon"], errors="coerce")
    locations = locations[locations["lat"].notna() & locations["lon"].notna()].copy()

    if "match_status" in locations.columns:
        eligible = eligible_match_statuses or DEFAULT_ELIGIBLE_MATCH_STATUSES
        normalized = {status.strip().lower() for status in eligible}
        locations = locations[
            locations["match_status"].fillna("").astype(str).str.strip().str.lower().isin(normalized)
        ].copy()

    return locations.reset_index(drop=True)


def enrich_schools(schools: pd.DataFrame, selectivity: pd.DataFrame) -> pd.DataFrame:
    if selectivity.empty:
        schools = schools.copy()
        schools["rank"] = pd.NA
        schools["score_raw"] = pd.NA
        schools["score_normalized"] = pd.NA
        schools["metric_type"] = pd.NA
        schools["source_year"] = pd.NA
        schools["source_quality"] = pd.NA
        schools["source_url"] = pd.NA
        return schools

    selectivity_cols = [
        "school_name_norm", "level", "rank", "score_raw", "score_normalized",
        "metric_type", "source_year", "source_quality", "source_url",
    ]
    return schools.merge(selectivity[selectivity_cols], on=["school_name_norm", "level"], how="left")


def metric_prefix(level: str, radius_m: int) -> str:
    if level == "year_5_jc":
        return f"jc_{radius_m // 1000}km"
    return f"{level}_{radius_m // 1000}km"


def best_ranked_school(nearby: pd.DataFrame) -> pd.Series | None:
    ranked = nearby[nearby["rank"].notna()].copy()
    if ranked.empty:
        return None
    return ranked.sort_values(["rank", "distance_m", "school_name"]).iloc[0]


def metrics_for_project(
    project: pd.Series,
    schools: pd.DataFrame,
    primary_radius_m: int = 1000,
    secondary_radius_m: int = 2000,
    jc_radius_m: int = 5000,
    top_rank_cutoff: int = 10,
) -> dict[str, Any]:
    config = {
        "primary": primary_radius_m,
        "secondary": secondary_radius_m,
        "year_5_jc": jc_radius_m,
    }
    out: dict[str, Any] = {}

    for level, radius_m in config.items():
        prefix = metric_prefix(level, radius_m)
        subset = schools[schools["level"] == level].copy()
        if subset.empty:
            out[f"{prefix}_count"] = 0
            out[f"{prefix}_ranked_count"] = 0
            out[f"top_{prefix}_count"] = 0
            out[f"best_{prefix}_school"] = ""
            out[f"best_{prefix}_rank"] = ""
            out[f"best_{prefix}_distance_m"] = ""
            out[f"best_{prefix}_metric"] = ""
            out[f"best_{prefix}_source_year"] = ""
            continue

        subset["distance_m"] = subset.apply(
            lambda row: haversine_m(
                float(project["lat"]), float(project["lon"]),
                float(row["school_lat"]), float(row["school_lon"]),
            ),
            axis=1,
        )
        nearby = subset[subset["distance_m"] <= radius_m].copy()
        ranked = nearby[nearby["rank"].notna()]
        best = best_ranked_school(nearby)

        out[f"{prefix}_count"] = int(len(nearby))
        out[f"{prefix}_ranked_count"] = int(len(ranked))
        out[f"top_{prefix}_count"] = int((ranked["rank"] <= top_rank_cutoff).sum())
        if best is None:
            out[f"best_{prefix}_school"] = ""
            out[f"best_{prefix}_rank"] = ""
            out[f"best_{prefix}_distance_m"] = ""
            out[f"best_{prefix}_metric"] = ""
            out[f"best_{prefix}_source_year"] = ""
        else:
            out[f"best_{prefix}_school"] = best["school_name"]
            out[f"best_{prefix}_rank"] = int(best["rank"])
            out[f"best_{prefix}_distance_m"] = int(round(best["distance_m"]))
            out[f"best_{prefix}_metric"] = best.get("score_raw", "")
            out[f"best_{prefix}_source_year"] = best.get("source_year", "")

    out["has_primary_1km"] = bool(out.get("primary_1km_count", 0) >= 1)
    out["has_ranked_primary_1km"] = bool(out.get("primary_1km_ranked_count", 0) >= 1)
    return out


def build_project_school_metrics(
    locations: pd.DataFrame,
    schools: pd.DataFrame,
    selectivity: pd.DataFrame,
    primary_radius_m: int = 1000,
    secondary_radius_m: int = 2000,
    jc_radius_m: int = 5000,
) -> pd.DataFrame:
    enriched = enrich_schools(schools, selectivity)
    rows: list[dict[str, Any]] = []
    for _, project in locations.iterrows():
        base = {
            "project_name": project["project_name"],
            "street_name": project["street_name"],
            "postal_district": project["postal_district"],
            "planning_area": project["planning_area"],
            "lat": project["lat"],
            "lon": project["lon"],
            "match_status": project.get("match_status", ""),
        }
        base.update(metrics_for_project(project, enriched, primary_radius_m, secondary_radius_m, jc_radius_m))
        rows.append(base)
    return pd.DataFrame(rows)


def run(args: argparse.Namespace) -> Path:
    locations_path = Path(args.locations)
    if not locations_path.exists():
        raise SystemExit(
            f"{locations_path} not found. Run `make private-project-locations` and review the geocodes first."
        )

    schools = load_schools(Path(args.schools))
    selectivity = load_selectivity(Path(args.selectivity))
    locations = load_locations(locations_path, set(args.include_match_status))
    out = build_project_school_metrics(
        locations,
        schools,
        selectivity,
        primary_radius_m=args.primary_radius_m,
        secondary_radius_m=args.secondary_radius_m,
        jc_radius_m=args.jc_radius_m,
    )
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False, lineterminator="\n")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build private project school diagnostics")
    parser.add_argument("--locations", default=str(DEFAULT_LOCATIONS))
    parser.add_argument("--schools", default=str(DEFAULT_SCHOOLS))
    parser.add_argument("--selectivity", default=str(DEFAULT_SELECTIVITY))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--primary-radius-m", type=int, default=1000)
    parser.add_argument("--secondary-radius-m", type=int, default=2000)
    parser.add_argument("--jc-radius-m", type=int, default=5000)
    parser.add_argument(
        "--include-match-status",
        action="append",
        default=["matched"],
        help="OneMap geocode match_status eligible for school metrics; repeat to include more statuses.",
    )
    args = parser.parse_args()
    out = run(args)
    print(f"Written: {out}")


if __name__ == "__main__":
    main()
