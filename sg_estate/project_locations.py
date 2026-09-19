"""Single review gate for private-project coordinate consumers.

The committed legacy cache predates explicit review metadata. Its exact
fourteen-column shape is the only compatibility exception: ``matched`` rows in
that shape are treated as ``approved_legacy``. Newer rows must carry an
explicit approval, and current ``approved`` rows must bind that decision to the
exact selected-match digest.
"""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Iterable

import pandas as pd


LEGACY_LOCATION_COLUMNS = (
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
)
CURRENT_LOCATION_COLUMNS = (
    *LEGACY_LOCATION_COLUMNS,
    "retrieved_at",
    "response_sha256",
    "match_sha256",
    "retry_state",
    "attempt_count",
    "last_error",
    "review_status",
    "reviewed_at",
    "reviewed_match_sha256",
    "review_decision_note",
)
REQUIRED_LOCATION_COLUMNS = frozenset({"project_name", "lat", "lon", "match_status"})
APPROVED_REVIEW_STATUSES = frozenset({"approved", "approved_legacy"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MATCH_DIGEST_FIELDS = (
    "lat",
    "lon",
    "match_status",
    "match_score",
    "query_used",
    "onemap_building",
    "onemap_road",
    "onemap_address",
    "onemap_postal",
)


class ProjectLocationContractError(ValueError):
    """The coordinate source cannot be evaluated safely."""


def _text_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series("", index=frame.index, dtype="object")
    return frame[column].fillna("").astype(str).str.strip()


def _text(value: object) -> str:
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _district(value: object) -> str:
    text = _text(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(2) if text.isdigit() else text


def _canonical_number(value: object) -> int | float | str:
    text = _text(value)
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    if not math.isfinite(number):
        return text
    return int(number) if number.is_integer() else number


def canonical_project_location_match_sha256(row: object) -> str:
    """Recompute the geocoder's identity-bound selected-match digest."""
    get = row.get  # type: ignore[attr-defined]
    canonical: dict[str, object] = {
        "project_name": _text(get("project_name", "")).upper(),
        "street_name": _text(get("street_name", "")).upper(),
        "postal_district": _district(get("postal_district", "")),
        "planning_area": _text(get("planning_area", "")).upper(),
    }
    for field in MATCH_DIGEST_FIELDS:
        value = get(field, "")
        canonical[field] = (
            _canonical_number(value)
            if field in {"lat", "lon", "match_score"}
            else _text(value)
        )
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_aware_timestamp(value: object) -> bool:
    text = str(value).strip() if value is not None else ""
    if not text:
        return False
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def is_legacy_project_location_schema(columns: Iterable[object]) -> bool:
    """Return whether columns are the exact reviewed legacy cache contract."""
    return tuple(str(column) for column in columns) == LEGACY_LOCATION_COLUMNS


def usable_project_locations(
    frame: pd.DataFrame,
    *,
    source_columns: Iterable[object] | None = None,
) -> pd.DataFrame:
    """Return only coordinates permitted as numeric project evidence.

    Usability requires a numeric coordinate pair, ``match_status=matched``, and
    an approved review state. Current ``approved`` rows additionally require a
    timezone-aware review time and equal lowercase SHA-256 match/review hashes.
    """
    columns = tuple(source_columns if source_columns is not None else frame.columns)
    exact_columns = tuple(str(column) for column in columns)
    legacy_schema = is_legacy_project_location_schema(columns)
    current_schema = exact_columns == CURRENT_LOCATION_COLUMNS
    supported_minimal_schema = set(exact_columns) == REQUIRED_LOCATION_COLUMNS
    if not legacy_schema and not current_schema and not supported_minimal_schema:
        raise ProjectLocationContractError(
            "project locations must use the exact legacy, current, or explicit "
            "review-state column contract"
        )
    missing = sorted(REQUIRED_LOCATION_COLUMNS - set(str(column) for column in columns))
    if missing:
        raise ProjectLocationContractError(
            "project locations missing required columns: " + ", ".join(missing)
        )

    locations = frame.copy()
    if legacy_schema or current_schema:
        identity_keys = locations.apply(
            lambda row: (
                _text(row.get("project_name", "")).upper(),
                _text(row.get("street_name", "")).upper(),
                _district(row.get("postal_district", "")),
                _text(row.get("planning_area", "")).upper(),
            ),
            axis=1,
        )
        duplicates = identity_keys.duplicated(keep=False)
        if bool(duplicates.any()):
            raise ProjectLocationContractError(
                "project locations contain duplicate full identities"
            )
    locations["lat"] = pd.to_numeric(locations["lat"], errors="coerce")
    locations["lon"] = pd.to_numeric(locations["lon"], errors="coerce")
    status = _text_series(locations, "match_status").str.lower()
    coordinate_mask = (
        locations["lat"].between(-90, 90, inclusive="both")
        & locations["lon"].between(-180, 180, inclusive="both")
    )

    if legacy_schema:
        review_mask = pd.Series(True, index=locations.index)
        locations["review_status"] = "approved_legacy"
    else:
        review_status = _text_series(locations, "review_status").str.lower()
        match_sha256 = _text_series(locations, "match_sha256")
        response_sha256 = _text_series(locations, "response_sha256")
        reviewed_match_sha256 = _text_series(locations, "reviewed_match_sha256")
        reviewed_at = _text_series(locations, "reviewed_at")
        retrieved_at = _text_series(locations, "retrieved_at")
        attempt_count = pd.to_numeric(
            _text_series(locations, "attempt_count"), errors="coerce"
        )
        canonical_match_sha256 = locations.apply(
            canonical_project_location_match_sha256,
            axis=1,
        )
        acquisition_bound = (
            current_schema
            & match_sha256.map(lambda value: bool(SHA256_RE.fullmatch(value)))
            & match_sha256.eq(canonical_match_sha256)
            & response_sha256.map(lambda value: bool(SHA256_RE.fullmatch(value)))
            & retrieved_at.map(_is_aware_timestamp)
            & attempt_count.ge(1)
        )
        bound_approval = (
            review_status.eq("approved")
            & acquisition_bound
            & reviewed_match_sha256.eq(match_sha256)
            & reviewed_at.map(_is_aware_timestamp)
        )
        retry_state = _text_series(locations, "retry_state").str.lower()
        last_error = _text_series(locations, "last_error")
        migrated_legacy_state = (
            current_schema
            & review_status.eq("approved_legacy")
            & retry_state.eq("legacy")
            & attempt_count.fillna(-1).eq(0)
            & retrieved_at.eq("")
            & response_sha256.eq("")
            & match_sha256.eq("")
            & reviewed_at.eq("")
            & reviewed_match_sha256.eq("")
            & last_error.eq("")
        )
        migrated_legacy_approval = review_status.eq("approved_legacy") & (
            acquisition_bound | migrated_legacy_state
        )
        corrupt_approval = review_status.isin(APPROVED_REVIEW_STATUSES) & ~(
            bound_approval | migrated_legacy_approval
        )
        if bool(corrupt_approval.any()):
            projects = ", ".join(
                _text(value)
                for value in locations.loc[corrupt_approval, "project_name"].head(3)
            )
            raise ProjectLocationContractError(
                "approved project locations have invalid review/hash binding: "
                + projects
            )
        review_mask = migrated_legacy_approval | bound_approval

    usable = locations[status.eq("matched") & coordinate_mask & review_mask].copy()
    return usable.reset_index(drop=True)


def load_usable_project_locations(
    path: str | Path,
    *,
    missing_ok: bool = False,
) -> pd.DataFrame:
    """Read a project-location CSV and apply the canonical review gate."""
    location_path = Path(path)
    if not location_path.exists():
        if missing_ok:
            return pd.DataFrame(columns=sorted(REQUIRED_LOCATION_COLUMNS))
        raise FileNotFoundError(location_path)
    try:
        frame = pd.read_csv(location_path, dtype={"postal_district": str})
    except pd.errors.EmptyDataError as exc:
        raise ProjectLocationContractError(
            f"project location file is empty: {location_path}"
        ) from exc
    return usable_project_locations(frame, source_columns=frame.columns)
