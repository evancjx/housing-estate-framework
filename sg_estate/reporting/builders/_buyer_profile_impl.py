"""Internal buyer-profile report renderer.

Reads the committed buyer-profile output and its scenario definitions, applies
publication trust rules, and writes ``buyer_profile_table.html``. Execute via
``sg_estate.reporting.builders.buyer_profile`` or the compatibility CLI in
``models/gen_buyer_profile_html.py``.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from sg_estate.paths import REPOSITORY_ROOT as ROOT
from sg_estate.reporting.common import atomic_write_text, html_json


DEFAULT_INPUT = ROOT / "data/outputs/buyer_profile_output.csv"
DEFAULT_PROFILE_INPUT = ROOT / "data/inputs/buyer_profiles.example.json"
DEFAULT_OUT = ROOT / "buyer_profile_table.html"
TEMPLATE = ROOT / "sg_estate/reporting/templates/buyer_profile_table.html"
VALUE_TRUST_THRESHOLD = 100

REQUIRED_COLUMNS = {
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
}

PROFILE_LABELS = {
    "forming-family-hdb-balanced": "Forming family · HDB",
    "single-pro-condo-commute-value": "Single professional · Condo",
    "forming-family-condo-balanced": "Forming family · Condo",
    "landed-family-amenity-upside": "Family upgrader · Landed",
    "ageing-in-place-hdb-care-lease": "Ageing in place · HDB",
}


def clean_text(value: Any, default: str = "") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    text = str(value).strip()
    if text.lower() in {"nan", "none"}:
        return default
    return text


def number_or_none(value: Any) -> float | None:
    text = clean_text(value)
    if not text or text in {"N/R", "N/A", "no_data", "not_covered"}:
        return None
    try:
        result = float(text)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return clean_text(value).lower() in {"true", "1", "yes", "y"}


def _rank_rows_within_tenure(rows: list[dict[str, Any]]) -> None:
    """Publish ranks only inside a profile and tenure universe.

    The current committed scenarios each use one tenure. Recomputing the
    display rank here also keeps custom multi-tenure profiles from blending
    HDB, condominium and landed choices into one apparent league table.
    """

    keys = {(row["profile_id"], row["tenure"]) for row in rows}
    for profile_id, tenure in keys:
        candidates = [
            row
            for row in rows
            if row["profile_id"] == profile_id
            and row["tenure"] == tenure
            and row["eligible"]
            and row["profile_score"] is not None
        ]
        candidates.sort(
            key=lambda row: (-row["profile_score"], row["estate"])
        )
        for rank, row in enumerate(candidates, start=1):
            row["rank"] = rank


def load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"{path} not found. Run models/buyer_profile_model.py first.")
    frame = pd.read_csv(path, keep_default_na=False)
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise SystemExit(f"{path} missing required columns: {missing}")

    rows: list[dict[str, Any]] = []
    for _, source in frame.iterrows():
        archetype = clean_text(source["archetype"]).upper()
        eligible = bool_value(source["eligible"]) and archetype != "X"
        sample = number_or_none(source["value_n"])
        trusted_value = sample is not None and sample >= VALUE_TRUST_THRESHOLD
        not_residential = archetype == "X"

        score_reporting = (
            "not_residential"
            if not_residential
            else "filtered"
            if not eligible
            else "withheld_value_sample"
            if sample is not None and 0 < sample < VALUE_TRUST_THRESHOLD
            else "available"
        )
        row = {
            "profile_id": clean_text(source["profile_id"]),
            "estate": clean_text(source["estate"]),
            "tenure": clean_text(source["tenure"]).lower(),
            "eligible": eligible,
            "rank": None,
            # Hard-filtered rows are not ranked choices, so their aggregate
            # decimals are intentionally not published as a shadow ranking.
            "profile_score": (
                number_or_none(source["profile_score"])
                if score_reporting == "available"
                else None
            ),
            "score_reporting": score_reporting,
            "soft_weight_covered": (
                number_or_none(source["soft_weight_covered"])
                if not not_residential
                else None
            ),
            "filter_reasons": clean_text(source["filter_reasons"]),
            "persona": clean_text(source["persona"]),
            "horizon": clean_text(source["horizon"]).upper(),
            "life_path": clean_text(source["life_path"]),
            "liveability_score": (
                number_or_none(source["liveability_score"])
                if not not_residential
                else None
            ),
            "liveability_band": (
                clean_text(source["liveability_band"]) if not not_residential else "N/R"
            ),
            "life_path_end_score": (
                number_or_none(source["life_path_end_score"])
                if not not_residential
                else None
            ),
            "life_path_delta": (
                number_or_none(source["life_path_delta"])
                if not not_residential
                else None
            ),
            # Decimal Value evidence is suppressed below the publication
            # trust threshold. The band, basis and sample remain visible.
            "value_score": (
                number_or_none(source["value_score"])
                if trusted_value and not not_residential
                else None
            ),
            "value_band": (
                clean_text(source["value_band"]) if not not_residential else "N/R"
            ),
            "value_basis": (
                clean_text(source["value_basis"]) if not not_residential else "N/R"
            ),
            "value_n": sample if not not_residential else None,
            "value_reporting": (
                "not_residential"
                if not_residential
                else "decimal"
                if trusted_value
                else "band_only"
                if sample is not None and sample > 0
                else "unavailable"
            ),
            "employment_score": (
                number_or_none(source["employment_score"])
                if not not_residential
                else None
            ),
            "employment_band": (
                clean_text(source["employment_band"]) if not not_residential else "N/R"
            ),
            "lease_score": (
                number_or_none(source["lease_score"])
                if not not_residential
                else None
            ),
            "lease_band": (
                clean_text(source["lease_band"]) if not not_residential else "N/R"
            ),
            "provision_score": (
                number_or_none(source["provision_score"])
                if not not_residential
                else None
            ),
            "provision_band": (
                clean_text(source["provision_band"]) if not not_residential else "N/R"
            ),
            "archetype": archetype,
            "measured_only": (
                bool_value(source["measured_only"]) if not not_residential else False
            ),
        }
        rows.append(row)

    _rank_rows_within_tenure(rows)
    return rows


def load_profile_definitions(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"{path} not found.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read profile definitions {path}: {exc}") from exc

    if "profiles" in payload:
        definitions = payload.get("profiles")
        defaults = payload.get("defaults", {}) or {}
    else:
        definitions = [payload]
        defaults = {}
    if not isinstance(definitions, list) or not definitions:
        raise SystemExit(f"{path} must contain a non-empty profiles list")
    if not isinstance(defaults, dict):
        raise SystemExit(f"{path} defaults must be an object")

    result: dict[str, dict[str, Any]] = {}
    for position, definition in enumerate(definitions):
        if not isinstance(definition, dict):
            raise SystemExit(f"{path} profile at index {position} must be an object")
        merged = dict(defaults)
        merged.update(definition)
        profile_id = clean_text(merged.get("profile_id"))
        if not profile_id:
            raise SystemExit(f"{path} profile at index {position} is missing profile_id")
        if profile_id in result:
            raise SystemExit(f"{path} repeats profile_id {profile_id!r}")
        result[profile_id] = merged
    return result


def _profile_label(profile_id: str) -> str:
    if profile_id in PROFILE_LABELS:
        return PROFILE_LABELS[profile_id]
    return " ".join(word.capitalize() for word in profile_id.replace("_", "-").split("-") if word)


def validate_profile_coverage(
    rows: list[dict[str, Any]],
    definitions: dict[str, dict[str, Any]],
) -> None:
    """Require profile metadata and model output to describe the same scenarios."""

    row_ids = {row["profile_id"] for row in rows}
    definition_ids = set(definitions)
    missing = sorted(row_ids - definition_ids)
    extra = sorted(definition_ids - row_ids)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing definitions: {missing}")
        if extra:
            details.append(f"unused definitions: {extra}")
        raise SystemExit("Profile definition/output mismatch (" + "; ".join(details) + ")")


def profile_summary(
    rows: list[dict[str, Any]],
    definitions: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    definitions = definitions or {}
    ordered_ids = list(dict.fromkeys(row["profile_id"] for row in rows))
    output: list[dict[str, Any]] = []
    for profile_id in ordered_ids:
        profile_rows = [row for row in rows if row["profile_id"] == profile_id]
        definition = definitions.get(profile_id, {})
        personas = list(dict.fromkeys(row["persona"] for row in profile_rows if row["persona"]))
        horizons = list(dict.fromkeys(row["horizon"] for row in profile_rows if row["horizon"]))
        life_paths = list(dict.fromkeys(row["life_path"] for row in profile_rows if row["life_path"]))
        tenures = list(dict.fromkeys(row["tenure"] for row in profile_rows if row["tenure"]))
        output.append(
            {
                "profile_id": profile_id,
                "label": _profile_label(profile_id),
                "description": clean_text(definition.get("description")),
                "rows": len(profile_rows),
                "eligible": sum(1 for row in profile_rows if row["eligible"]),
                "ranked": sum(1 for row in profile_rows if row.get("rank") is not None),
                "persona": clean_text(definition.get("persona")) or ", ".join(personas),
                "horizon": clean_text(definition.get("horizon")).upper() or ", ".join(horizons),
                "life_path": clean_text(definition.get("life_path")) or ", ".join(life_paths),
                "tenures": tenures,
                "hard_filters": definition.get("hard_filters", {}) or {},
                "soft_weights": definition.get("soft_weights", {}) or {},
                "partial_coverage": sum(
                    1
                    for row in profile_rows
                    if row["eligible"]
                    and row["soft_weight_covered"] is not None
                    and row["soft_weight_covered"] < 1
                ),
                "band_only_value": sum(
                    1 for row in profile_rows if row.get("value_reporting") == "band_only"
                ),
            }
        )
    return output


def render_html(
    rows: list[dict[str, Any]],
    generated_on: date | str | None = None,
    definitions: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Render buyer-profile rows without writing a file."""

    generated_on = generated_on or date.today()
    if isinstance(generated_on, str):
        generated_date = date.fromisoformat(generated_on)
    else:
        generated_date = generated_on
    if definitions is not None:
        validate_profile_coverage(rows, definitions)
    profiles = profile_summary(rows, definitions)
    tenures = {row["tenure"] for row in rows if row["tenure"]}
    html = TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "__PROFILE_COUNT__": str(len(profiles)),
        "__ROW_COUNT__": str(len(rows)),
        "__ELIGIBLE_COUNT__": str(sum(1 for row in rows if row["eligible"])),
        "__SEGMENT_COUNT__": str(len(tenures)),
        "__GENERATED_DATE_ISO__": generated_date.isoformat(),
        "__GENERATED_DATE_LABEL__": f"{generated_date.day} {generated_date:%b %Y}",
        "__BUYER_PROFILE_DATA_JSON__": html_json(rows, indent=2),
        "__BUYER_PROFILE_SUMMARY_JSON__": html_json(profiles, indent=2),
    }
    for marker, value in replacements.items():
        html = html.replace(marker, value)
    unresolved = [marker for marker in replacements if marker in html]
    if unresolved:
        raise RuntimeError(f"Unresolved buyer-profile template markers: {unresolved}")
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate buyer-profile HTML explorer")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--profiles", default=str(DEFAULT_PROFILE_INPUT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    rows = load_rows(Path(args.input))
    definitions = load_profile_definitions(Path(args.profiles))
    output = atomic_write_text(
        args.out,
        render_html(rows, definitions=definitions),
    )
    print(
        f"gen_buyer_profile_html: wrote {len(rows)} rows across "
        f"{len(profile_summary(rows, definitions))} profiles -> {output}"
    )


if __name__ == "__main__":
    main()
