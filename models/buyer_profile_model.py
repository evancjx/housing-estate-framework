#!/usr/bin/env python3
"""
Buyer-profile intake model.

This is a demand-side wrapper around the existing estate outputs. It does not
change Provision, Liveability, or Value. It reads one or more buyer profiles,
applies hard filters first, then computes a profile-relative score over the
remaining estate and tenure choices.

Hard filters represent buy/no-buy constraints: tenure segment, minimum bands,
transaction coverage, X-archetype exclusion, lease tolerance, and similar gates.
Soft weights represent trade-offs once a choice is still feasible.

RUN:
    python3 models/buyer_profile_model.py \
        --profile data/buyer_profiles.example.json \
        --master data/master_output.csv \
        --life-paths data/life_paths.csv \
        --out data/buyer_profile_output.csv

INPUT CONTRACT
==============
--profile JSON:
  Either a single profile object or:
    profiles: list[profile]

  A profile has:
  Required:
    profile_id: string
  Optional:
    tenure: "hdb" | "private" | "condo" | "landed" | "any"
    tenures: list of tenure/property segments (overrides tenure). `private`
      uses the legacy combined private bucket; `condo` and `landed` use
      data/private_segment_value.csv when available.
    persona: yf|youngfam|young_family|sp|singlepro|ret|retiree|ls|lifestyle
    horizon: T0|T5|T15
    life_path: one of data/life_paths.csv path values
    hard_filters:
      exclude_archetypes: list[str]
      allowed_archetypes: list[str]
      exclude_measured_only: bool
      min_liveability_band: A|B+|B|C|D|F
      min_value_band: A|B+|B|C|D|F
      min_employment_band: A|B+|B|C|D|F
      min_lease_band: A|B+|B|C|D|F (applies to HDB unless
        require_lease_for_private=true)
      min_provision_band: A|B+|B|C|D|F
      min_value_n: number
      require_direct_value: bool
      require_value_basis: list[str], for example ["direct"]
      min_D_T0 / min_D_T5 / min_D_T15: number
    soft_weights:
      liveability, value, employment, lease, provision, life_path: numbers

--master CSV:
  data/master_output.csv from build_master.py. Required columns include estate,
  archetype, persona/horizon scores, Value columns, Employment, Lease, and
  Provision fields.

--life-paths CSV:
  data/life_paths.csv from build_master.py. Required only when profile.life_path
  is provided. Columns: estate,path,start_score,end_score,delta.

--private-values CSV:
  data/private_segment_value.csv from private_segment_value_model.py. Required
  only for segment-specific condo/landed Value. Missing rows stay no_data rather
  than borrowing from the combined private bucket.

OUTPUT CSV:
  One row per estate x requested tenure segment, with eligibility status,
  filter reasons, profile score, rank, and the component values used.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from framework_config import BAND_NUMERIC


PERSONA_PREFIX = {
    "yf": "yf",
    "youngfam": "yf",
    "young_family": "yf",
    "young-family": "yf",
    "young family": "yf",
    "sp": "sp",
    "singlepro": "sp",
    "single_pro": "sp",
    "single-pro": "sp",
    "single pro": "sp",
    "ret": "ret",
    "retiree": "ret",
    "ls": "ls",
    "lifestyle": "ls",
}

PREFIX_LABEL = {
    "yf": "YoungFam",
    "sp": "SinglePro",
    "ret": "Retiree",
    "ls": "Lifestyle",
}

VALID_HORIZONS = {"T0", "T5", "T15"}
VALID_TENURES = {"hdb", "private", "condo", "landed"}
PROPERTY_SEGMENT_TENURES = {"condo", "landed"}

DEFAULT_SOFT_WEIGHTS = {
    "liveability": 0.45,
    "value": 0.25,
    "employment": 0.10,
    "lease": 0.10,
    "provision": 0.05,
    "life_path": 0.05,
}

OUTPUT_COLUMNS = [
    "profile_id",
    "estate",
    "tenure",
    "eligible",
    "rank",
    "profile_score",
    "soft_weight_covered",
    "filter_reasons",
    "persona",
    "horizon",
    "life_path",
    "liveability_score",
    "liveability_band",
    "life_path_end_score",
    "life_path_delta",
    "value_score",
    "value_band",
    "value_basis",
    "value_n",
    "employment_score",
    "employment_band",
    "lease_score",
    "lease_band",
    "provision_score",
    "provision_band",
    "archetype",
    "measured_only",
]


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _clean_text(value: Any) -> str:
    return str(value).strip()


def _upper_set(value: Any) -> set:
    return {_clean_text(v).upper() for v in _as_list(value) if _clean_text(v)}


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() in {"", "N/R", "N/A", "no_data", "not_covered"}:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(val):
        return None
    return val


def _band_value(value: Any) -> Optional[float]:
    band = _clean_text(value).upper()
    return BAND_NUMERIC.get(band)


def _score_to_band_value(score: Optional[float]) -> Optional[float]:
    if score is None:
        return None
    if score >= 4.5:
        return BAND_NUMERIC["A"]
    if score >= 4.0:
        return BAND_NUMERIC["B+"]
    if score >= 3.5:
        return BAND_NUMERIC["B"]
    if score >= 3.0:
        return BAND_NUMERIC["C"]
    if score >= 2.5:
        return BAND_NUMERIC["D"]
    return BAND_NUMERIC["F"]


def _band_pass(actual: Any, minimum: Any) -> bool:
    actual_value = _band_value(actual)
    minimum_value = _band_value(minimum)
    return actual_value is not None and minimum_value is not None and actual_value >= minimum_value


def _score_pass(score: Optional[float], minimum_band: Any) -> bool:
    actual_value = _score_to_band_value(score)
    minimum_value = _band_value(minimum_band)
    return actual_value is not None and minimum_value is not None and actual_value >= minimum_value


def _normalise_tenures(profile: Dict[str, Any]) -> List[str]:
    raw = profile.get("tenures", profile.get("tenure", "any"))
    values = [_clean_text(v).lower() for v in _as_list(raw)]
    if not values or values == ["any"] or "any" in values or "all" in values:
        return ["hdb", "condo", "landed"]
    invalid = sorted(set(values) - VALID_TENURES)
    if invalid:
        raise ValueError(f"Unknown tenure(s): {invalid}. Use hdb, private, or any.")
    return values


def _normalise_persona(profile: Dict[str, Any]) -> str:
    raw = _clean_text(profile.get("persona", "Lifestyle")).lower()
    persona = PERSONA_PREFIX.get(raw)
    if persona is None:
        raise ValueError(f"Unknown persona '{profile.get('persona')}'.")
    return persona


def _normalise_horizon(profile: Dict[str, Any]) -> str:
    horizon = _clean_text(profile.get("horizon", "T0")).upper()
    if horizon not in VALID_HORIZONS:
        raise ValueError(f"Unknown horizon '{profile.get('horizon')}'. Use T0, T5, or T15.")
    return horizon


def _load_json(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"profile JSON not found: {path}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _profiles_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Accept both the original single-profile JSON and a multi-profile wrapper."""
    if "profiles" not in payload:
        return [payload]
    profiles = payload.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError("profile JSON 'profiles' must be a non-empty list")
    defaults = payload.get("defaults", {}) or {}
    if not isinstance(defaults, dict):
        raise ValueError("profile JSON 'defaults' must be an object when present")

    merged = []
    for i, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            raise ValueError(f"profile at index {i} must be an object")
        p = dict(defaults)
        p.update(profile)
        if not _clean_text(p.get("profile_id", "")):
            raise ValueError(f"profile at index {i} is missing profile_id")
        merged.append(p)
    return merged


def _load_csv(path: str, name: str) -> pd.DataFrame:
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"{name} CSV not found: {path}")
    df = pd.read_csv(path, keep_default_na=False)
    if "estate" not in df.columns:
        raise ValueError(f"{name} CSV must contain an estate column")
    df["estate"] = df["estate"].astype(str).str.strip().str.upper()
    return df


def _life_path_frame(life_paths: Optional[pd.DataFrame], path_name: str) -> pd.DataFrame:
    if not path_name:
        return pd.DataFrame(columns=["estate"])
    if life_paths is None:
        raise ValueError("profile.life_path requires --life-paths")
    required = {"estate", "path", "end_score", "delta"}
    missing = required - set(life_paths.columns)
    if missing:
        raise ValueError(f"life_paths CSV missing columns: {sorted(missing)}")
    path_rows = life_paths[life_paths["path"].astype(str) == path_name].copy()
    if path_rows.empty:
        raise ValueError(f"life_path '{path_name}' not found in life_paths CSV")
    return path_rows[["estate", "end_score", "delta"]].rename(
        columns={"end_score": "_life_path_end_score", "delta": "_life_path_delta"}
    )


def _private_value_lookup(private_values: Optional[pd.DataFrame]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    if private_values is None or private_values.empty:
        return {}
    required = {"estate", "property_segment", "value_score", "value_band", "value_basis", "n"}
    missing = required - set(private_values.columns)
    if missing:
        raise ValueError(f"private-values CSV missing columns: {sorted(missing)}")

    lookup: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for _, r in private_values.iterrows():
        estate = _clean_text(r["estate"]).upper()
        segment = _clean_text(r["property_segment"]).lower()
        lookup[(estate, segment)] = {
            "score": _number(r.get("value_score")),
            "band": _clean_text(r.get("value_band", "")),
            "basis": _clean_text(r.get("value_basis", "")),
            "n": _number(r.get("n")),
        }
    return lookup


def _value_metrics(
    row: pd.Series,
    tenure: str,
    private_value_lookup: Optional[Dict[Tuple[str, str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if tenure == "hdb":
        return {
            "score": _number(row.get("value_hdb_score")),
            "band": _clean_text(row.get("value_hdb_band", "")),
            "basis": _clean_text(row.get("value_hdb_basis", "")),
            "n": _number(row.get("value_hdb_n")),
        }
    if tenure in PROPERTY_SEGMENT_TENURES:
        key = (_clean_text(row.get("estate", "")).upper(), tenure)
        found = (private_value_lookup or {}).get(key)
        if found is not None:
            return found
        return {"score": None, "band": "no_data", "basis": "no_data", "n": None}
    return {
        "score": _number(row.get("value_private_score")),
        "band": _clean_text(row.get("value_private_band", "")),
        "basis": _clean_text(row.get("value_private_basis", "")),
        "n": _number(row.get("value_private_n")),
    }


def _provision_metrics(row: pd.Series, tenure: str) -> Tuple[Optional[float], str]:
    if tenure in {"private", "condo", "landed"}:
        score = _number(row.get("provision_private"))
        return score, ""
    return _number(row.get("provision_score")), _clean_text(row.get("provision_band", ""))


def _value_basis_allowed(actual: str, allowed: Iterable[str]) -> bool:
    actual_clean = actual.strip()
    for basis in allowed:
        b = _clean_text(basis)
        if not b:
            continue
        if b == actual_clean:
            return True
        if b == "proxy" and actual_clean.startswith("proxy_from:"):
            return True
    return False


def _filter_reasons(
    row: pd.Series,
    profile: Dict[str, Any],
    tenure: str,
    persona_prefix: str,
    horizon: str,
    value: Dict[str, Any],
    provision_score: Optional[float],
    provision_band: str,
) -> List[str]:
    hard = profile.get("hard_filters", {}) or {}
    reasons: List[str] = []
    archetype = _clean_text(row.get("archetype", "")).upper()

    excluded = _upper_set(hard.get("exclude_archetypes", ["X"]))
    if archetype in excluded:
        reasons.append(f"excluded_archetype:{archetype}")

    allowed = _upper_set(hard.get("allowed_archetypes"))
    if allowed and archetype not in allowed:
        reasons.append(f"archetype_not_allowed:{archetype or 'missing'}")

    if _boolish(hard.get("exclude_measured_only", False)) and _boolish(row.get("measured_only", False)):
        reasons.append("measured_only")

    live_band = row.get(f"{persona_prefix}_{horizon}_band")
    if hard.get("min_liveability_band") and not _band_pass(live_band, hard["min_liveability_band"]):
        reasons.append(f"liveability_below:{hard['min_liveability_band']}")

    if hard.get("min_value_band") and not _band_pass(value["band"], hard["min_value_band"]):
        reasons.append(f"value_below:{hard['min_value_band']}")

    if hard.get("min_employment_band") and not _band_pass(row.get("emp_band"), hard["min_employment_band"]):
        reasons.append(f"employment_below:{hard['min_employment_band']}")

    if hard.get("min_lease_band") and (tenure == "hdb" or _boolish(hard.get("require_lease_for_private", False))):
        if not _band_pass(row.get("lease_band"), hard["min_lease_band"]):
            reasons.append(f"lease_below:{hard['min_lease_band']}")

    if hard.get("min_provision_band"):
        if provision_band:
            ok = _band_pass(provision_band, hard["min_provision_band"])
        else:
            ok = _score_pass(provision_score, hard["min_provision_band"])
        if not ok:
            reasons.append(f"provision_below:{hard['min_provision_band']}")

    min_value_n = _number(hard.get("min_value_n"))
    if min_value_n is not None and (value["n"] is None or value["n"] < min_value_n):
        reasons.append(f"value_n_below:{int(min_value_n)}")

    if _boolish(hard.get("require_direct_value", False)) and value["basis"] != "direct":
        reasons.append("value_not_direct")

    allowed_basis = _as_list(hard.get("require_value_basis"))
    if allowed_basis and not _value_basis_allowed(value["basis"], allowed_basis):
        reasons.append("value_basis_not_allowed")

    for d_col in ("D_T0", "D_T5", "D_T15"):
        key = f"min_{d_col}"
        if key in hard:
            actual = _number(row.get(d_col))
            minimum = _number(hard.get(key))
            if minimum is not None and (actual is None or actual < minimum):
                reasons.append(f"{d_col}_below:{minimum:g}")

    return reasons


def _soft_score(
    profile: Dict[str, Any],
    liveability_score: Optional[float],
    value_score: Optional[float],
    employment_score: Optional[float],
    lease_score: Optional[float],
    provision_score: Optional[float],
    life_path_score: Optional[float],
) -> Tuple[Optional[float], float]:
    weights = dict(DEFAULT_SOFT_WEIGHTS)
    weights.update(profile.get("soft_weights", {}) or {})

    metrics = {
        "liveability": liveability_score,
        "value": value_score,
        "employment": employment_score,
        "lease": lease_score,
        "provision": provision_score,
        "life_path": life_path_score,
    }

    weighted = 0.0
    covered = 0.0
    total_positive = 0.0
    for name, raw_weight in weights.items():
        weight = _number(raw_weight)
        if weight is None or weight <= 0:
            continue
        total_positive += weight
        score = metrics.get(name)
        if score is None:
            continue
        weighted += weight * score
        covered += weight

    if covered <= 0:
        return None, 0.0
    denominator = total_positive if total_positive > 0 else covered
    return round(weighted / covered, 3), round(covered / denominator, 3)


def run(
    master: pd.DataFrame,
    life_paths: Optional[pd.DataFrame],
    profile: Dict[str, Any],
    private_values: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Apply one buyer profile to master/life-path outputs."""
    profile_id = _clean_text(profile.get("profile_id", "profile"))
    persona_prefix = _normalise_persona(profile)
    horizon = _normalise_horizon(profile)
    tenures = _normalise_tenures(profile)
    life_path = _clean_text(profile.get("life_path", ""))
    private_lookup = _private_value_lookup(private_values)

    master = master.copy()
    master["estate"] = master["estate"].astype(str).str.strip().str.upper()

    if life_path:
        life_frame = _life_path_frame(life_paths, life_path)
        master = master.merge(life_frame, on="estate", how="left")
    else:
        master["_life_path_end_score"] = ""
        master["_life_path_delta"] = ""

    live_col = f"{persona_prefix}_{horizon}"
    live_band_col = f"{persona_prefix}_{horizon}_band"
    missing = {"estate", "archetype", live_col, live_band_col} - set(master.columns)
    if missing:
        raise ValueError(f"master CSV missing columns: {sorted(missing)}")

    rows = []
    for _, row in master.iterrows():
        for tenure in tenures:
            value = _value_metrics(row, tenure, private_lookup)
            provision_score, provision_band = _provision_metrics(row, tenure)
            liveability_score = _number(row.get(live_col))
            employment_score = _number(row.get("emp_score"))
            lease_score = _number(row.get("lease_score")) if tenure == "hdb" else None
            life_path_score = _number(row.get("_life_path_end_score"))
            life_path_delta = _number(row.get("_life_path_delta"))

            reasons = _filter_reasons(
                row=row,
                profile=profile,
                tenure=tenure,
                persona_prefix=persona_prefix,
                horizon=horizon,
                value=value,
                provision_score=provision_score,
                provision_band=provision_band,
            )
            profile_score, weight_covered = _soft_score(
                profile=profile,
                liveability_score=liveability_score,
                value_score=value["score"],
                employment_score=employment_score,
                lease_score=lease_score,
                provision_score=provision_score,
                life_path_score=life_path_score,
            )

            rows.append({
                "profile_id": profile_id,
                "estate": row["estate"],
                "tenure": tenure,
                "eligible": not reasons,
                "rank": "",
                "profile_score": profile_score,
                "soft_weight_covered": weight_covered,
                "filter_reasons": ";".join(reasons),
                "persona": PREFIX_LABEL[persona_prefix],
                "horizon": horizon,
                "life_path": life_path,
                "liveability_score": liveability_score,
                "liveability_band": _clean_text(row.get(live_band_col, "")),
                "life_path_end_score": life_path_score,
                "life_path_delta": life_path_delta,
                "value_score": value["score"],
                "value_band": value["band"],
                "value_basis": value["basis"],
                "value_n": value["n"],
                "employment_score": employment_score,
                "employment_band": _clean_text(row.get("emp_band", "")),
                "lease_score": lease_score,
                "lease_band": _clean_text(row.get("lease_band", "")) if tenure == "hdb" else "",
                "provision_score": provision_score,
                "provision_band": provision_band,
                "archetype": _clean_text(row.get("archetype", "")),
                "measured_only": _boolish(row.get("measured_only", False)),
            })

    out = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    out = out.sort_values(
        by=["eligible", "profile_score", "estate", "tenure"],
        ascending=[False, False, True, True],
        na_position="last",
    ).reset_index(drop=True)

    eligible = out["eligible"] & out["profile_score"].notna()
    out.loc[eligible, "rank"] = range(1, int(eligible.sum()) + 1)
    return out


def run_many(
    master: pd.DataFrame,
    life_paths: Optional[pd.DataFrame],
    profiles: List[Dict[str, Any]],
    private_values: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Apply multiple profiles and concatenate outputs. Ranks remain profile-local."""
    frames = [run(master, life_paths, profile, private_values=private_values) for profile in profiles]
    if not frames:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    records = []
    for frame in frames:
        records.extend(frame.to_dict("records"))
    return pd.DataFrame.from_records(records, columns=OUTPUT_COLUMNS)


def main() -> None:
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    parser = argparse.ArgumentParser(description="Apply a buyer profile to estate outputs")
    parser.add_argument("--profile", default=os.path.join(data_dir, "buyer_profiles.example.json"))
    parser.add_argument("--master", default=os.path.join(data_dir, "master_output.csv"))
    parser.add_argument("--life-paths", default=os.path.join(data_dir, "life_paths.csv"))
    parser.add_argument("--private-values", default=os.path.join(data_dir, "private_segment_value.csv"))
    parser.add_argument("--out", default=os.path.join(data_dir, "buyer_profile_output.csv"))
    args = parser.parse_args()

    try:
        payload = _load_json(args.profile)
        profiles = _profiles_from_payload(payload)
        master = _load_csv(args.master, "master")
        life_paths = _load_csv(args.life_paths, "life_paths") if args.life_paths else None
        private_values = _load_csv(args.private_values, "private-values") if os.path.exists(args.private_values) else None
        out = run_many(master, life_paths, profiles, private_values=private_values)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        sys.exit(f"buyer_profile_model: {exc}")

    out.to_csv(args.out, index=False)
    eligible = out[out["eligible"]]
    print(f"buyer_profile_model: wrote {len(out)} rows -> {args.out}")
    for profile_id, group in out.groupby("profile_id", sort=False):
        n_eligible = int(group["eligible"].sum())
        print(f"  {profile_id}: {n_eligible} / {len(group)} eligible choices")
    if not eligible.empty:
        show = [
            "profile_id", "rank", "estate", "tenure", "profile_score",
            "liveability_band", "value_band", "employment_band", "lease_band",
            "filter_reasons",
        ]
        print(eligible[show].head(12).to_string(index=False))


if __name__ == "__main__":
    main()
