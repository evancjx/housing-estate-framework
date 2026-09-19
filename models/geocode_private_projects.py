#!/usr/bin/env python3
"""
Geocode private condominium projects with OneMap.

Reads:
  data/inputs/ura_private.csv

Writes:
  data/outputs/private_project_locations.csv

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
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import math
import os
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Any, Callable, TextIO

import pandas as pd

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sg_estate.adapters.http import get_bytes

SEARCH_URL = "https://www.onemap.gov.sg/api/common/elastic/search"
CONDO_TYPE_RE = re.compile(r"\b(?:apartment|condominium|executive condominium)\b", re.I)
DEFAULT_MAX_CACHE_AGE_DAYS = 30.0
TRANSIENT_HTTP_STATUSES = frozenset({408, 425, 429, *range(500, 600)})

LEGACY_OUT_COLUMNS = [
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

# Append-only cache metadata. The first fourteen columns are retained in their
# original order so existing readers can continue selecting the legacy fields.
METADATA_COLUMNS = [
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
]
OUT_COLUMNS = [*LEGACY_OUT_COLUMNS, *METADATA_COLUMNS]

MATCH_STATUSES = frozenset(
    {"matched", "needs_review", "low_confidence", "error", "no_match"}
)
COORDINATE_MATCH_STATUSES = frozenset(
    {"matched", "needs_review", "low_confidence"}
)
RETRY_STATES = frozenset(
    {"legacy", "complete", "transient_failure", "permanent_failure", "not_found"}
)
REVIEW_STATUSES = frozenset(
    {
        "approved_legacy",
        "pending_new",
        "pending_changed",
        "pending_low_confidence",
        "pending_error",
        "approved",
        "rejected",
    }
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DISTRICT_RE = re.compile(r"^[0-9]{2}$")
MATCH_DIGEST_FIELDS = (
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
)
OFFLINE_CACHE_STATES = ("fresh", "stale", "missing", "pending", "error")


class OneMapSchemaError(ValueError):
    """A permanent OneMap response-contract failure."""

    def __init__(
        self,
        message: str,
        *,
        response_trace: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.response_trace = list(response_trace or [])


class OneMapAcquisitionError(RuntimeError):
    """A request failure annotated with any completed response pages."""

    def __init__(
        self,
        error: BaseException,
        *,
        response_trace: list[dict[str, Any]],
    ) -> None:
        super().__init__(f"{type(error).__name__}: {error}")
        self.error = error
        self.response_trace = list(response_trace)


class OneMapSearchResults(list[dict[str, Any]]):
    """List-compatible search results carrying canonical response pages."""

    def __init__(
        self,
        results: list[dict[str, Any]],
        response_trace: list[dict[str, Any]],
    ) -> None:
        super().__init__(results)
        self.response_trace = response_trace


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


def _text(value: Any) -> str:
    """Return one stable CSV scalar without inventing missing values."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def utc_now() -> datetime:
    """Return a timezone-aware acquisition clock value."""
    return datetime.now(timezone.utc)


def timestamp_text(value: datetime) -> str:
    """Serialize one aware timestamp in stable UTC form."""
    if value.tzinfo is None:
        raise ValueError("acquisition clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json_sha256(value: Any) -> str:
    """Hash a JSON value after deterministic UTF-8 canonicalization."""
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_number(value: Any) -> int | float | str:
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


def canonical_match_sha256(match: dict[str, Any]) -> str:
    """Hash the selected OneMap match independently of CSV scalar formatting."""
    project, street, district, planning_area = key_for(match)
    canonical: dict[str, Any] = {
        "project_name": project,
        "street_name": street,
        "postal_district": district,
        "planning_area": planning_area,
    }
    for field in MATCH_DIGEST_FIELDS[4:]:
        value = match.get(field, "")
        canonical[field] = (
            _canonical_number(value)
            if field in {"lat", "lon", "match_score"}
            else _text(value)
        )
    return canonical_json_sha256(canonical)


def classify_acquisition_error(error: BaseException) -> str:
    """Classify request/contract failures for targeted retry behavior."""
    if isinstance(error, OneMapAcquisitionError):
        return classify_acquisition_error(error.error)
    if isinstance(error, urllib.error.HTTPError):
        return (
            "transient_failure"
            if error.code in TRANSIENT_HTTP_STATUSES
            else "permanent_failure"
        )
    if isinstance(
        error,
        (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            http.client.IncompleteRead,
        ),
    ):
        return "transient_failure"
    if isinstance(
        error,
        (OneMapSchemaError, json.JSONDecodeError, UnicodeDecodeError),
    ):
        return "permanent_failure"
    return "permanent_failure"


def _legacy_metadata(match_status: str, review_note: str) -> dict[str, str]:
    if match_status == "matched":
        review_status = "approved_legacy"
    elif match_status in {"needs_review", "low_confidence"}:
        review_status = "pending_low_confidence"
    else:
        review_status = "pending_error"
    if match_status == "no_match":
        retry_state = "not_found"
    elif match_status == "error":
        retry_state = "transient_failure"
    else:
        retry_state = "legacy"
    return {
        "retrieved_at": "",
        "response_sha256": "",
        "match_sha256": "",
        "retry_state": retry_state,
        "attempt_count": "0",
        "last_error": review_note if match_status == "error" else "",
        "review_status": review_status,
        "reviewed_at": "",
        "reviewed_match_sha256": "",
        "review_decision_note": "",
    }


def _validate_timestamp(value: str, *, field: str) -> None:
    if not value:
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp with timezone") from exc
    if "T" not in value or parsed.tzinfo is None:
        raise ValueError(f"{field} must be an ISO-8601 timestamp with timezone")
    if field == "retrieved_at" and parsed.utcoffset() != timedelta(0):
        raise ValueError("retrieved_at must use UTC")
    if field == "retrieved_at" and not value.endswith("Z"):
        raise ValueError("retrieved_at must use canonical UTC Z notation")


def _validate_hash(value: str, *, field: str) -> None:
    if value and not SHA256_RE.fullmatch(value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest or empty")


def _validate_coordinate(value: str, *, field: str, lower: float, upper: float) -> None:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or not lower <= number <= upper:
        raise ValueError(f"{field} is outside the valid coordinate range")


def normalize_cache_row(
    row: dict[str, Any],
    *,
    legacy: bool = False,
) -> dict[str, str]:
    """Migrate and validate one cache row without changing its identity."""
    unexpected = sorted(set(row) - set(OUT_COLUMNS))
    if unexpected:
        raise ValueError(f"geocode cache row has unexpected fields: {unexpected}")
    missing_legacy = sorted(set(LEGACY_OUT_COLUMNS) - set(row))
    if missing_legacy:
        raise ValueError(f"geocode cache row is missing fields: {missing_legacy}")

    supplied_metadata = set(row) & set(METADATA_COLUMNS)
    normalized = {column: _text(row.get(column, "")) for column in OUT_COLUMNS}
    normalized["postal_district"] = district_text(normalized["postal_district"])
    normalized["match_status"] = normalized["match_status"].lower()
    for field in ("retry_state", "review_status"):
        normalized[field] = normalized[field].lower()

    if legacy or not supplied_metadata:
        normalized.update(
            _legacy_metadata(
                normalized["match_status"],
                normalized["review_note"],
            )
        )
    elif not any(normalized[field] for field in METADATA_COLUMNS):
        raise ValueError("current geocode cache metadata cannot all be empty")

    identity = key_for(normalized)
    if any(not value for value in identity):
        raise ValueError("geocode cache identity fields must be non-empty")
    if not DISTRICT_RE.fullmatch(normalized["postal_district"]):
        raise ValueError("postal_district must be a zero-padded two-digit value")

    status = normalized["match_status"]
    if status not in MATCH_STATUSES:
        raise ValueError(f"unsupported match_status: {status!r}")
    try:
        score = float(normalized["match_score"])
    except (TypeError, ValueError) as exc:
        raise ValueError("match_score must be numeric") from exc
    if not math.isfinite(score) or not -100 <= score <= 105:
        raise ValueError("match_score must be finite and between -100 and 105")

    lat = normalized["lat"]
    lon = normalized["lon"]
    if bool(lat) != bool(lon):
        raise ValueError("lat and lon must either both be present or both be empty")
    if status in COORDINATE_MATCH_STATUSES and not lat:
        raise ValueError(f"{status} rows require coordinates")
    if lat:
        _validate_coordinate(lat, field="lat", lower=-90, upper=90)
        _validate_coordinate(lon, field="lon", lower=-180, upper=180)
    if status in COORDINATE_MATCH_STATUSES and not normalized["query_used"]:
        raise ValueError(f"{status} rows require query_used")

    retry_state = normalized["retry_state"]
    if retry_state not in RETRY_STATES:
        raise ValueError(f"unsupported retry_state: {retry_state!r}")
    attempt_text = normalized["attempt_count"]
    if not attempt_text.isdigit():
        raise ValueError("attempt_count must be a non-negative integer")
    normalized["attempt_count"] = str(int(attempt_text))

    review_status = normalized["review_status"]
    if review_status not in REVIEW_STATUSES:
        raise ValueError(f"unsupported review_status: {review_status!r}")
    for field in ("retrieved_at", "reviewed_at"):
        _validate_timestamp(normalized[field], field=field)
    for field in ("response_sha256", "match_sha256", "reviewed_match_sha256"):
        _validate_hash(normalized[field], field=field)
    if normalized["match_sha256"]:
        expected_match_sha256 = canonical_match_sha256(normalized)
        if normalized["match_sha256"] != expected_match_sha256:
            raise ValueError("match_sha256 does not match canonical row semantics")
    evidenced_attempt = int(normalized["attempt_count"]) > 0
    if retry_state in {"complete", "not_found"} and evidenced_attempt:
        if not normalized["retrieved_at"] or not normalized["match_sha256"]:
            raise ValueError(
                f"{retry_state} rows require retrieved_at and match_sha256"
            )
        if normalized["last_error"]:
            raise ValueError(f"{retry_state} rows cannot retain last_error")
    if (
        retry_state in {"complete", "not_found"}
        and evidenced_attempt
        and not normalized["response_sha256"]
    ):
        raise ValueError(f"{retry_state} rows require response_sha256")
    if retry_state == "complete" and status not in COORDINATE_MATCH_STATUSES:
        raise ValueError("complete rows require a coordinate match_status")
    if retry_state == "complete" and not evidenced_attempt:
        raise ValueError("complete rows require a positive attempt_count")
    if retry_state == "not_found" and status != "no_match":
        raise ValueError("not_found rows require match_status=no_match")
    if retry_state == "permanent_failure" and not normalized["last_error"]:
        raise ValueError("permanent_failure rows require last_error")
    if retry_state == "transient_failure" and not normalized["last_error"]:
        raise ValueError("transient_failure rows require last_error")
    if review_status == "approved":
        if not normalized["reviewed_at"] or not normalized["reviewed_match_sha256"]:
            raise ValueError(
                "approved rows require reviewed_at and reviewed_match_sha256"
            )
        if normalized["reviewed_match_sha256"] != normalized["match_sha256"]:
            raise ValueError("approved review hash must match match_sha256")
    return normalized


def _row_sort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    project, street, district, planning_area = key_for(row)
    return district, project, street, planning_area


def prepare_cache_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return unique, validated cache rows in deterministic publication order."""
    prepared: list[dict[str, str]] = []
    identities: set[tuple[str, str, str, str]] = set()
    for position, row in enumerate(rows, start=1):
        try:
            normalized = normalize_cache_row(dict(row))
        except ValueError as exc:
            raise ValueError(f"invalid geocode cache row {position}: {exc}") from exc
        identity = key_for(normalized)
        if identity in identities:
            raise ValueError(f"duplicate geocode cache identity: {identity!r}")
        identities.add(identity)
        prepared.append(normalized)
    return sorted(prepared, key=_row_sort_key)


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


def load_existing(path: Path) -> dict[tuple[str, str, str, str], dict[str, str]]:
    if not path.exists():
        return {}
    existing: dict[tuple[str, str, str, str], dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        if header == LEGACY_OUT_COLUMNS:
            legacy = True
        elif header == OUT_COLUMNS:
            legacy = False
        else:
            raise ValueError(
                f"{path} has an invalid geocode cache header; expected the legacy "
                "or current exact column order"
            )
        for position, row in enumerate(reader, start=2):
            try:
                normalized = normalize_cache_row(dict(row), legacy=legacy)
            except ValueError as exc:
                raise ValueError(f"{path}:{position}: {exc}") from exc
            identity = key_for(normalized)
            if identity in existing:
                raise ValueError(
                    f"{path}:{position}: duplicate geocode cache identity {identity!r}"
                )
            existing[identity] = normalized
    return existing


def onemap_search(query: str, token: str, max_pages: int) -> OneMapSearchResults:
    """Search OneMap through the shared bounded-retry HTTP adapter."""
    results: list[dict[str, Any]] = []
    response_trace: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        params = urllib.parse.urlencode(
            {
                "searchVal": query,
                "returnGeom": "Y",
                "getAddrDetails": "Y",
                "pageNum": page,
            }
        )
        try:
            response_bytes = get_bytes(
                f"{SEARCH_URL}?{params}",
                timeout=20,
                headers={"Authorization": token},
            )
        except Exception as exc:
            raise OneMapAcquisitionError(
                exc,
                response_trace=response_trace,
            ) from exc
        response_trace.append(
            {
                "query": query,
                "page": page,
                "body_sha256": hashlib.sha256(response_bytes).hexdigest(),
            }
        )
        try:
            payload = json.loads(response_bytes.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OneMapSchemaError(
                "OneMap returned invalid JSON",
                response_trace=response_trace,
            ) from exc
        if not isinstance(payload, dict):
            raise OneMapSchemaError(
                "OneMap response must be an object",
                response_trace=response_trace,
            )
        page_results = payload.get("results", [])
        if not isinstance(page_results, list) or any(
            not isinstance(result, dict) for result in page_results
        ):
            raise OneMapSchemaError(
                "OneMap results must be a list of objects",
                response_trace=response_trace,
            )
        if not page_results:
            break
        results.extend(page_results)
        try:
            total = int(payload.get("found", len(results)) or len(results))
        except (TypeError, ValueError) as exc:
            raise OneMapSchemaError(
                "OneMap found must be an integer",
                response_trace=response_trace,
            ) from exc
        if total < 0:
            raise OneMapSchemaError(
                "OneMap found cannot be negative",
                response_trace=response_trace,
            )
        if len(results) >= total:
            break
    return OneMapSearchResults(results, response_trace)


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


def _error_match(
    error: BaseException,
    query: str,
    response_transcript: list[dict[str, Any]],
) -> dict[str, Any]:
    retry_state = classify_acquisition_error(error)
    response_transcript = [
        *response_transcript,
        *getattr(error, "response_trace", []),
    ]
    response_sha256 = (
        canonical_json_sha256(response_transcript) if response_transcript else ""
    )
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
        "review_note": f"{type(error).__name__}: {error}",
        "_response_sha256": response_sha256,
        "_retry_state": retry_state,
        "_last_error": f"{type(error).__name__}: {error}",
    }


def best_match(project: str, street: str, token: str, max_pages: int) -> dict[str, Any]:
    queries = [
        f"{project} {street}",
        project,
        street,
    ]
    best: tuple[int, str, str, dict[str, Any] | None] = (-999, "", "", None)
    response_transcript: list[dict[str, Any]] = []
    for query in queries:
        try:
            results = onemap_search(query, token, max_pages)
        except Exception as exc:
            return _error_match(exc, query, response_transcript)
        trace = getattr(results, "response_trace", None)
        response_transcript.extend(
            trace
            if trace is not None
            else [
                {
                    "query": query,
                    "page": 1,
                    "body_sha256": canonical_json_sha256(list(results)),
                }
            ]
        )
        for result in results:
            score, reasons = score_result(project, street, result)
            if score > best[0]:
                best = (score, reasons, query, result)
        if best[0] >= 90:
            break

    score, reasons, query, result = best
    response_sha256 = canonical_json_sha256(response_transcript)
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
            "_response_sha256": response_sha256,
            "_retry_state": "not_found",
            "_last_error": "OneMap returned no candidates",
        }

    if score >= 90:
        status = "matched"
    elif score >= 55:
        status = "needs_review"
    else:
        status = "low_confidence"

    match = {
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
        "_response_sha256": response_sha256,
        "_retry_state": "complete",
        "_last_error": "",
    }
    try:
        _validate_coordinate(
            _text(match["lat"]), field="OneMap LATITUDE", lower=-90, upper=90
        )
        _validate_coordinate(
            _text(match["lon"]), field="OneMap LONGITUDE", lower=-180, upper=180
        )
    except ValueError as exc:
        return _error_match(
            OneMapSchemaError(
                str(exc),
                response_trace=[],
            ),
            query,
            response_transcript,
        )
    return match


def _serialize_rows(
    handle: TextIO,
    rows: list[dict[str, str]],
) -> None:
    writer = csv.DictWriter(handle, fieldnames=OUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


def _fsync_directory(path: Path, *, fsync: Callable[[int], None] = os.fsync) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        fsync(descriptor)
    finally:
        os.close(descriptor)


def write_rows(
    path: Path,
    rows: list[dict[str, Any]],
    *,
    serializer: Callable[[TextIO, list[dict[str, str]]], None] = _serialize_rows,
    replace: Callable[[str | bytes | os.PathLike[str] | os.PathLike[bytes], str | bytes | os.PathLike[str] | os.PathLike[bytes]], None] = os.replace,
    fsync: Callable[[int], None] = os.fsync,
    fsync_directory: Callable[..., None] = _fsync_directory,
) -> None:
    """Validate and atomically replace the complete geocode checkpoint."""
    prepared = prepare_cache_rows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as handle:
            serializer(handle, prepared)
            handle.flush()
            fsync(handle.fileno())

        staged = load_existing(temporary)
        staged_rows = list(staged.values())
        if staged_rows != prepared:
            raise ValueError("staged geocode cache did not round-trip exactly")
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        else:
            os.chmod(temporary, 0o644)
        replace(temporary, path)
        fsync_directory(path.parent, fsync=fsync)
    finally:
        temporary.unlink(missing_ok=True)


def _parse_retrieved_at(row: dict[str, Any]) -> datetime | None:
    value = _text(row.get("retrieved_at"))
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def cache_row_is_stale(
    row: dict[str, Any],
    *,
    now: datetime,
    max_cache_age_days: float,
) -> bool:
    """Return whether one cache row is older than the accepted acquisition age."""
    if now.tzinfo is None:
        raise ValueError("cache clock must be timezone-aware")
    retrieved_at = _parse_retrieved_at(row)
    if retrieved_at is None:
        return True
    age = now.astimezone(timezone.utc) - retrieved_at.astimezone(timezone.utc)
    return age < timedelta(0) or age > timedelta(days=max_cache_age_days)


def _has_usable_result(row: dict[str, Any]) -> bool:
    return row.get("match_status") in COORDINATE_MATCH_STATUSES | {"no_match"}


def _attempt_count(row: dict[str, Any] | None) -> int:
    if row is None:
        return 0
    value = _text(row.get("attempt_count"))
    return int(value) if value.isdigit() else 0


def _review_status_for_success(
    row: dict[str, Any],
    prior: dict[str, str] | None,
) -> str:
    if prior is not None and _has_usable_result(prior):
        prior_hash = prior.get("match_sha256") or canonical_match_sha256(prior)
        if prior_hash != row["match_sha256"]:
            return "pending_changed"
        return prior["review_status"]
    if row["match_status"] in {"needs_review", "low_confidence"}:
        return "pending_low_confidence"
    if row["match_status"] == "no_match":
        return "pending_error"
    return "pending_new"


def compose_attempt_row(
    project: dict[str, Any] | pd.Series,
    match: dict[str, Any],
    *,
    prior: dict[str, str] | None,
    retrieved_at: datetime,
) -> dict[str, str]:
    """Merge one matcher attempt without letting failure erase valid evidence."""
    attempt = dict(match)
    response_sha256 = _text(attempt.pop("_response_sha256", ""))
    retry_state = _text(attempt.pop("_retry_state", "")).lower()
    last_error = _text(attempt.pop("_last_error", ""))
    unexpected_private = sorted(key for key in attempt if key.startswith("_"))
    if unexpected_private:
        raise ValueError(f"matcher returned unsupported metadata: {unexpected_private}")
    identity = {
        "project_name": project["project_name"],
        "street_name": project["street_name"],
        "postal_district": project["postal_district"],
        "planning_area": project["planning_area"],
    }
    status = _text(attempt.get("match_status")).lower()
    if not retry_state:
        retry_state = (
            "not_found"
            if status == "no_match"
            else "transient_failure"
            if status == "error"
            else "complete"
        )
    if retry_state not in RETRY_STATES - {"legacy"}:
        raise ValueError(f"matcher returned unsupported retry state: {retry_state!r}")
    attempts = str(_attempt_count(prior) + 1)
    if retry_state in {"transient_failure", "permanent_failure"}:
        error = last_error or _text(attempt.get("review_note")) or retry_state
        if prior is not None and _has_usable_result(prior):
            retained = dict(prior)
            retained.update(
                {
                    "retry_state": retry_state,
                    "attempt_count": attempts,
                    "last_error": error,
                }
            )
            return normalize_cache_row(retained)
        error_row = {
            **identity,
            "lat": "",
            "lon": "",
            "match_status": "error",
            "match_score": 0,
            "query_used": _text(attempt.get("query_used")),
            "onemap_building": "",
            "onemap_road": "",
            "onemap_address": "",
            "onemap_postal": "",
            "review_note": error,
            "retrieved_at": "",
            "response_sha256": response_sha256,
            "match_sha256": "",
            "retry_state": retry_state,
            "attempt_count": attempts,
            "last_error": error,
            "review_status": "pending_error",
            "reviewed_at": "",
            "reviewed_match_sha256": "",
            "review_decision_note": "",
        }
        return normalize_cache_row(error_row)

    row: dict[str, Any] = {
        **identity,
        **attempt,
        "retrieved_at": timestamp_text(retrieved_at),
        "response_sha256": response_sha256,
        "match_sha256": "",
        "retry_state": retry_state,
        "attempt_count": attempts,
        "last_error": "",
        "review_status": "pending_error",
        "reviewed_at": prior["reviewed_at"] if prior else "",
        "reviewed_match_sha256": prior["reviewed_match_sha256"] if prior else "",
        "review_decision_note": prior["review_decision_note"] if prior else "",
    }
    row["match_sha256"] = canonical_match_sha256(row)
    row["review_status"] = _review_status_for_success(row, prior)
    if retry_state in {"complete", "not_found"} and not response_sha256:
        # Injected legacy matchers intentionally preserve their four-argument
        # interface; a deterministic sentinel distinguishes them from HTTP bytes.
        row["response_sha256"] = canonical_json_sha256(
            {"acquisition": "injected_matcher", "match_sha256": row["match_sha256"]}
        )
    return normalize_cache_row(row)


def offline_cache_summary(
    projects: pd.DataFrame,
    existing: dict[tuple[str, str, str, str], dict[str, str]],
    *,
    now: datetime,
    max_cache_age_days: float,
) -> dict[str, int]:
    """Classify required identities without mutating or acquiring cache data."""
    counts = {state: 0 for state in OFFLINE_CACHE_STATES}
    required_keys = {key_for(project) for _, project in projects.iterrows()}
    for key in required_keys:
        row = existing.get(key)
        if row is None:
            counts["missing"] += 1
        elif row["retry_state"] in {"transient_failure", "permanent_failure"}:
            counts["error"] += 1
        elif not _has_usable_result(row) or row["match_status"] == "no_match":
            counts["error"] += 1
        elif row["review_status"] not in {"approved", "approved_legacy"}:
            counts["pending"] += 1
        elif cache_row_is_stale(
            row, now=now, max_cache_age_days=max_cache_age_days
        ):
            counts["stale"] += 1
        else:
            counts["fresh"] += 1
    counts["orphans"] = len(set(existing) - required_keys)
    counts["total"] = len(required_keys)
    return counts


def _print_offline_summary(counts: dict[str, int]) -> None:
    print(
        "Offline geocode cache: "
        + " ".join(
            f"{key}={counts[key]}"
            for key in (
                "total",
                "fresh",
                "stale",
                "missing",
                "pending",
                "error",
                "orphans",
            )
        )
    )


def _should_query(
    row: dict[str, str] | None,
    *,
    resume: bool,
    retry_transient: bool,
    now: datetime,
    max_cache_age_days: float,
) -> bool:
    if retry_transient:
        return row is not None and row.get("retry_state") == "transient_failure"
    if not resume or row is None:
        return True
    if row.get("retry_state") == "transient_failure":
        return True
    if row.get("retry_state") == "permanent_failure":
        return False
    return cache_row_is_stale(
        row, now=now, max_cache_age_days=max_cache_age_days
    )


def run(
    args: argparse.Namespace,
    *,
    matcher: Callable[[str, str, str, int], dict[str, Any]] = best_match,
    checkpoint_writer: Callable[[Path, list[dict[str, Any]]], None] = write_rows,
    clock: Callable[[], datetime] = utc_now,
) -> None:
    private_path = Path(args.private)
    out_path = Path(args.out)
    projects = load_project_keys(private_path)
    existing = load_existing(out_path)
    now = clock()
    max_cache_age_days = getattr(
        args, "max_cache_age_days", DEFAULT_MAX_CACHE_AGE_DAYS
    )
    if not math.isfinite(max_cache_age_days) or max_cache_age_days < 0:
        raise SystemExit("--max-cache-age-days must be a finite non-negative number")
    timestamp_text(now)
    offline = getattr(args, "offline", False)
    retry_transient = getattr(args, "retry_transient", False)
    if retry_transient and not args.resume:
        raise SystemExit("--retry-transient cannot be combined with --no-resume")
    if retry_transient and offline:
        raise SystemExit("--retry-transient cannot be combined with --offline")
    if offline:
        _print_offline_summary(
            offline_cache_summary(
                projects,
                existing,
                now=now,
                max_cache_age_days=max_cache_age_days,
            )
        )
        return
    token = args.token or os.environ.get("ONEMAP_TOKEN")
    if not token:
        raise SystemExit("Set ONEMAP_TOKEN or pass --token.")

    merged: dict[tuple[str, str, str, str], dict[str, Any]] = dict(existing)
    processed = 0
    for _, project in projects.iterrows():
        key = key_for(project)
        prior = existing.get(key)
        if not _should_query(
            prior,
            resume=args.resume,
            retry_transient=retry_transient,
            now=now,
            max_cache_age_days=max_cache_age_days,
        ):
            continue

        try:
            match = matcher(
                project["project_name"],
                project["street_name"],
                token,
                args.max_pages,
            )
        except Exception as exc:
            match = _error_match(
                exc,
                f"{project['project_name']} {project['street_name']}",
                [],
            )
        row = compose_attempt_row(
            project,
            match,
            prior=prior,
            retrieved_at=clock(),
        )
        merged[key] = row
        processed += 1
        print(
            f"[{processed}/{len(projects)} queried] D{project['postal_district']} "
            f"{project['project_name']} -> {row['match_status']} "
            f"({row['match_score']}; {row['retry_state']})"
        )
        checkpoint_writer(out_path, list(merged.values()))
        if args.limit and processed >= args.limit:
            break
        time.sleep(args.sleep)

    # Also migrates a legacy cache when every current row was resumed. Existing
    # identities outside the current feed remain part of the complete map.
    checkpoint_writer(out_path, list(merged.values()))
    print(
        f"\nWritten: {out_path} "
        f"({len(merged)} project location rows, {processed} queried)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Geocode private condo projects with OneMap")
    parser.add_argument("--private", default=str(ROOT / "data/inputs/ura_private.csv"), help="URA private transaction CSV")
    parser.add_argument("--out", default=str(ROOT / "data/outputs/private_project_locations.csv"), help="Output geocode CSV")
    parser.add_argument("--token", help="OneMap token; defaults to ONEMAP_TOKEN")
    parser.add_argument("--resume", action="store_true", default=True, help="Reuse existing non-empty geocode rows")
    parser.add_argument("--no-resume", dest="resume", action="store_false", help="Requery all project rows")
    parser.add_argument("--limit", type=int, help="Geocode at most N new rows")
    parser.add_argument("--max-pages", type=int, default=1, help="OneMap result pages to inspect per query")
    parser.add_argument(
        "--max-cache-age-days",
        type=float,
        default=DEFAULT_MAX_CACHE_AGE_DAYS,
        help="Refresh successful cache rows older than this many days",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Perform no requests or writes; report cache state only",
    )
    parser.add_argument(
        "--retry-transient",
        action="store_true",
        help="Query only rows whose latest attempt was a transient failure",
    )
    parser.add_argument("--sleep", type=float, default=0.25, help="Delay between queries")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
