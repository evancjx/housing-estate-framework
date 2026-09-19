"""Executable DataFrame contracts for pipeline boundaries."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Iterable, Mapping
from urllib.parse import parse_qsl, urlsplit

import pandas as pd

from sg_estate.domain.framework import BAND_EDGES, PROVISION_WEIGHTS


class ContractError(ValueError):
    """Raised when a pipeline dataset violates its declared contract."""


SOURCE_RECEIPT_SCHEMA_VERSION = 2
SOURCE_RECEIPT_CACHE_STATES = frozenset(
    {"fresh", "cached", "mixed", "offline", "derived", "unknown"}
)
SOURCE_RECEIPT_FALLBACK_STATES = frozenset({"not_used", "used", "unknown"})
SOURCE_RECEIPT_VALIDATION_STATUSES = frozenset(
    {"passed", "failed", "not_run", "unknown"}
)
SOURCE_RECEIPT_FIELDS = (
    "schema_version",
    "dataset_id",
    "authority",
    "source_url",
    "source_urls",
    "source_identity",
    "retrieved_at",
    "coverage_start",
    "coverage_end",
    "row_count",
    "sha256",
    "cache_state",
    "fallback_state",
    "validation_status",
)

URA_ACQUISITION_SCHEMA_VERSION = 1
URA_ACQUISITION_STATUSES = frozenset({"awaiting_review", "complete", "failed"})
URA_ACQUISITION_METHODS = frozenset({"playwright", "api"})
URA_ACQUISITION_ATTEMPT_STATUSES = frozenset(
    {"succeeded", "confirmed_empty", "failed"}
)
URA_PROPERTY_TYPES = frozenset({"1", "2", "3", "4"})

SCRAPE_GENERATION_CONTRACT = "scrape-generation"
SCRAPE_GENERATION_SCHEMA_VERSION = 1
SCRAPE_GENERATION_SOURCES = frozenset(
    {"edgeprop_condo_apartment", "edgeprop_landed", "ura_pmi"}
)
SCRAPE_GENERATION_STATUSES = frozenset({"open", "complete"})
SCRAPE_GENERATION_METHODS = frozenset({"playwright", "api"})
SCRAPE_GENERATION_ATTEMPT_STATUSES = frozenset(
    {"succeeded", "confirmed_empty", "failed"}
)
SCRAPE_GENERATION_FIELDS = (
    "contract",
    "schema_version",
    "source",
    "generation_id",
    "status",
    "started_at",
    "updated_at",
    "completed_at",
    "scope_sha256",
    "requested_scope",
    "partitions",
    "summary",
    "output",
)
SCRAPE_GENERATION_SCOPE_FIELDS = (
    "project_catalog",
    "partitions",
    "parameters",
)
SCRAPE_GENERATION_SCOPE_PARTITION_FIELDS = (
    "partition_id",
    "name",
    "source_url",
    "source_slug",
)
SCRAPE_GENERATION_PARTITION_FIELDS = (
    "partition_id",
    "selected_attempt_id",
    "attempts",
)
SCRAPE_GENERATION_ATTEMPT_FIELDS = (
    "attempt_id",
    "generation_id",
    "method",
    "status",
    "started_at",
    "completed_at",
    "retrieved_at",
    "artifact",
    "source_reported_row_count",
    "error_code",
    "error_message",
    "observations",
)
SCRAPE_GENERATION_ARTIFACT_FIELDS = (
    "relative_path",
    "sha256",
    "byte_count",
    "row_count",
)
SCRAPE_GENERATION_SUMMARY_FIELDS = (
    "requested",
    "selected",
    "succeeded",
    "confirmed_empty",
    "failed",
    "pending",
)


def _non_empty_string(value: object, *, label: str, source: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{source}.{label} must be a non-empty string")
    if value != value.strip():
        raise ContractError(f"{source}.{label} must not have surrounding whitespace")
    return value


def _optional_string(value: object, *, label: str, source: str) -> str | None:
    if value is None:
        return None
    return _non_empty_string(value, label=label, source=source)


def _optional_iso_period(
    value: object,
    *,
    label: str,
    source: str,
) -> tuple[date, date] | None:
    text = _optional_string(value, label=label, source=source)
    if text is None:
        return None
    try:
        if re.fullmatch(r"\d{4}", text):
            year = int(text)
            return date(year, 1, 1), date(year, 12, 31)
        if re.fullmatch(r"\d{4}-\d{2}", text):
            year, month = (int(part) for part in text.split("-"))
            last_day = calendar.monthrange(year, month)[1]
            return date(year, month, 1), date(year, month, last_day)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            value_date = date.fromisoformat(text)
            return value_date, value_date
    except (ValueError, OverflowError) as exc:
        raise ContractError(
            f"{source}.{label} must use ISO precision YYYY, YYYY-MM, or YYYY-MM-DD"
        ) from exc
    raise ContractError(
        f"{source}.{label} must use ISO precision YYYY, YYYY-MM, or YYYY-MM-DD"
    )


def _http_url(value: object, *, label: str, source: str) -> str:
    text = _non_empty_string(value, label=label, source=source)
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ContractError(
            f"{source}.{label} must be an absolute HTTP(S) URL"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ContractError(f"{source}.{label} must not contain credentials")
    sensitive_query_names = {
        "access_token",
        "api_key",
        "apikey",
        "credential",
        "key",
        "signature",
        "token",
        "x-amz-credential",
        "x-amz-security-token",
        "x-amz-signature",
    }
    query_names = {
        name.lower()
        for name, _value in parse_qsl(parsed.query, keep_blank_values=True)
    }
    unsafe = sorted(query_names & sensitive_query_names)
    if unsafe:
        raise ContractError(
            f"{source}.{label} must not contain credential-bearing query fields: {unsafe}"
        )
    return text


@dataclass(frozen=True)
class SourceReceiptContract:
    """Executable contract for one staged source-acquisition receipt.

    Nullable fields must be present and encoded as JSON ``null`` when their
    values are unknown. State fields are deliberately separate so a direct
    retrieval, cache hit, reviewed fallback, and deliberately offline run have
    distinct machine-readable representations.
    """

    schema_version: int = SOURCE_RECEIPT_SCHEMA_VERSION
    fields: tuple[str, ...] = SOURCE_RECEIPT_FIELDS

    def validate(
        self,
        receipt: Mapping[str, object],
        *,
        source: str = "source receipt",
    ) -> dict[str, object]:
        if not isinstance(receipt, Mapping):
            raise ContractError(f"{source} must be a JSON object")

        expected = set(self.fields)
        actual = set(receipt)
        missing = sorted(expected - actual)
        if missing:
            raise ContractError(f"{source} missing required fields: {missing}")
        unexpected = sorted(actual - expected)
        if unexpected:
            raise ContractError(f"{source} has unexpected fields: {unexpected}")

        version = receipt["schema_version"]
        if (
            not isinstance(version, int)
            or isinstance(version, bool)
            or version != self.schema_version
        ):
            raise ContractError(
                f"{source}.schema_version must be {self.schema_version}"
            )

        _non_empty_string(receipt["dataset_id"], label="dataset_id", source=source)
        _non_empty_string(receipt["authority"], label="authority", source=source)

        source_url = _optional_string(
            receipt["source_url"], label="source_url", source=source
        )
        source_urls_value = receipt["source_urls"]
        if source_urls_value is not None:
            if not isinstance(source_urls_value, list) or not source_urls_value:
                raise ContractError(
                    f"{source}.source_urls must be a non-empty JSON array or null"
                )
            source_urls = [
                _http_url(
                    value,
                    label=f"source_urls[{index}]",
                    source=source,
                )
                for index, value in enumerate(source_urls_value)
            ]
            if len(source_urls) != len(set(source_urls)):
                raise ContractError(f"{source}.source_urls must not contain duplicates")
            if source_url is None:
                raise ContractError(
                    f"{source}.source_url must identify the primary composite source"
                )
            if source_urls[0] != source_url:
                raise ContractError(
                    f"{source}.source_urls must list source_url first"
                )
        source_identity = _optional_string(
            receipt["source_identity"], label="source_identity", source=source
        )
        if source_url is None and source_identity is None:
            raise ContractError(
                f"{source} requires source_url or source_identity"
            )
        if source_url is not None:
            _http_url(source_url, label="source_url", source=source)

        retrieved_at = _optional_string(
            receipt["retrieved_at"], label="retrieved_at", source=source
        )
        if retrieved_at is not None:
            try:
                parsed_retrieval = datetime.fromisoformat(
                    retrieved_at.replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise ContractError(
                    f"{source}.retrieved_at must be an ISO-8601 timestamp with timezone or null"
                ) from exc
            if "T" not in retrieved_at or parsed_retrieval.tzinfo is None:
                raise ContractError(
                    f"{source}.retrieved_at must be an ISO-8601 timestamp with timezone or null"
                )

        coverage_start = _optional_iso_period(
            receipt["coverage_start"], label="coverage_start", source=source
        )
        coverage_end = _optional_iso_period(
            receipt["coverage_end"], label="coverage_end", source=source
        )
        if (
            coverage_start is not None
            and coverage_end is not None
            and coverage_start[0] > coverage_end[1]
        ):
            raise ContractError(
                f"{source}.coverage_start must not be after coverage_end"
            )

        row_count = receipt["row_count"]
        if row_count is not None and (
            isinstance(row_count, bool)
            or not isinstance(row_count, int)
            or row_count < 0
        ):
            raise ContractError(f"{source}.row_count must be a non-negative integer or null")

        sha256 = _optional_string(receipt["sha256"], label="sha256", source=source)
        if sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ContractError(
                f"{source}.sha256 must be a lowercase SHA-256 digest or null"
            )

        states = (
            ("cache_state", SOURCE_RECEIPT_CACHE_STATES),
            ("fallback_state", SOURCE_RECEIPT_FALLBACK_STATES),
            ("validation_status", SOURCE_RECEIPT_VALIDATION_STATUSES),
        )
        for field_name, allowed in states:
            value = receipt[field_name]
            if not isinstance(value, str) or value not in allowed:
                raise ContractError(
                    f"{source}.{field_name} must be one of {sorted(allowed)}"
                )

        # Return a plain dict in schema order so callers cannot accidentally
        # publish a custom Mapping implementation or unstable key ordering.
        return {field_name: receipt[field_name] for field_name in self.fields}


SOURCE_RECEIPT = SourceReceiptContract()


def _scrape_identifier(value: object, *, label: str, source: str) -> str:
    text = _non_empty_string(value, label=label, source=source)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", text):
        raise ContractError(
            f"{source}.{label} must contain only identifier-safe characters"
        )
    return text


def _scrape_url_path_segment(value: object, *, label: str, source: str) -> str:
    """Validate one exact RFC 3986-style source path segment.

    Source slugs are evidence, not internal identifiers. Preserve their exact
    case and punctuation while excluding separators, dot traversal segments,
    whitespace/control characters, and malformed percent escapes.
    """

    text = _non_empty_string(value, label=label, source=source)
    if text in {".", ".."} or not re.fullmatch(
        r"(?:[A-Za-z0-9._~-]|%[0-9A-Fa-f]{2}|[!$&'()*+,;=:@])+",
        text,
    ):
        raise ContractError(
            f"{source}.{label} must be one safe non-empty URL path segment"
        )
    return text


def _scrape_sha256(value: object, *, label: str, source: str) -> str:
    digest = _non_empty_string(value, label=label, source=source)
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ContractError(f"{source}.{label} must be a lowercase SHA-256")
    return digest


def _scrape_nonnegative_int(value: object, *, label: str, source: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{source}.{label} must be a non-negative integer")
    return value


def _scrape_utc_timestamp(
    value: object,
    *,
    label: str,
    source: str,
    nullable: bool = False,
) -> datetime | None:
    if value is None and nullable:
        return None
    text = _non_empty_string(value, label=label, source=source)
    if not text.endswith("Z") or "T" not in text:
        raise ContractError(f"{source}.{label} must be a canonical UTC timestamp ending Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(
            f"{source}.{label} must be a canonical UTC timestamp ending Z"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ContractError(f"{source}.{label} must be a canonical UTC timestamp ending Z")
    return parsed


def _scrape_json_value(value: object, *, source: str) -> object:
    """Return a plain, deterministic JSON value or reject non-JSON evidence."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"{source} must not contain NaN or infinity")
        return value
    if isinstance(value, list):
        return [
            _scrape_json_value(item, source=f"{source}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) or not key for key in value):
            raise ContractError(f"{source} object keys must be non-empty strings")
        return {
            key: _scrape_json_value(value[key], source=f"{source}.{key}")
            for key in sorted(value)
        }
    raise ContractError(f"{source} must contain only JSON values")


def _scrape_relative_path(value: object, *, label: str, source: str) -> str:
    text = _non_empty_string(value, label=label, source=source)
    posix = PurePosixPath(text)
    windows = PureWindowsPath(text)
    if (
        "\\" in text
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or any(part in {"", ".", ".."} for part in posix.parts)
        or posix.as_posix() != text
    ):
        raise ContractError(f"{source}.{label} must be a safe canonical relative path")
    return text


def _validate_scrape_artifact(
    artifact: object,
    *,
    source: str,
) -> dict[str, object]:
    if not isinstance(artifact, Mapping) or set(artifact) != set(
        SCRAPE_GENERATION_ARTIFACT_FIELDS
    ):
        raise ContractError(f"{source} has an unexpected schema")
    relative_path = _scrape_relative_path(
        artifact["relative_path"], label="relative_path", source=source
    )
    digest = _scrape_sha256(artifact["sha256"], label="sha256", source=source)
    byte_count = _scrape_nonnegative_int(
        artifact["byte_count"], label="byte_count", source=source
    )
    if byte_count == 0:
        raise ContractError(f"{source}.byte_count must be positive")
    row_count = _scrape_nonnegative_int(
        artifact["row_count"], label="row_count", source=source
    )
    return {
        "relative_path": relative_path,
        "sha256": digest,
        "byte_count": byte_count,
        "row_count": row_count,
    }


@dataclass(frozen=True)
class ScrapeGenerationContract:
    """Strict checkpoint contract for one resumable scraper generation.

    This contract deliberately stops before source-specific reconciliation or
    promotion. A selected partition proves only that one exact checkpoint
    artifact was successfully retrieved within this generation.
    """

    schema_version: int = SCRAPE_GENERATION_SCHEMA_VERSION
    fields: tuple[str, ...] = SCRAPE_GENERATION_FIELDS

    @staticmethod
    def normalize_requested_scope(
        requested_scope: Mapping[str, object],
        *,
        source: str = "scrape generation requested_scope",
    ) -> dict[str, object]:
        if not isinstance(requested_scope, Mapping) or set(requested_scope) != set(
            SCRAPE_GENERATION_SCOPE_FIELDS
        ):
            raise ContractError(f"{source} has an unexpected schema")

        catalog_value = requested_scope["project_catalog"]
        catalog: dict[str, object] | None
        if catalog_value is None:
            catalog = None
        else:
            if not isinstance(catalog_value, Mapping) or set(catalog_value) != {
                "name",
                "sha256",
            }:
                raise ContractError(f"{source}.project_catalog has an unexpected schema")
            catalog = {
                "name": _non_empty_string(
                    catalog_value["name"],
                    label="name",
                    source=f"{source}.project_catalog",
                ),
                "sha256": _scrape_sha256(
                    catalog_value["sha256"],
                    label="sha256",
                    source=f"{source}.project_catalog",
                ),
            }

        partition_values = requested_scope["partitions"]
        if not isinstance(partition_values, list) or not partition_values:
            raise ContractError(f"{source}.partitions must be a non-empty JSON array")
        partitions: list[dict[str, object]] = []
        partition_ids: set[str] = set()
        source_urls: set[str] = set()
        source_slugs: set[str] = set()
        for index, value in enumerate(partition_values):
            partition_source = f"{source}.partitions[{index}]"
            if not isinstance(value, Mapping) or set(value) != set(
                SCRAPE_GENERATION_SCOPE_PARTITION_FIELDS
            ):
                raise ContractError(f"{partition_source} has an unexpected schema")
            partition_id = _scrape_identifier(
                value["partition_id"], label="partition_id", source=partition_source
            )
            source_url = _http_url(
                value["source_url"], label="source_url", source=partition_source
            )
            source_slug = _scrape_url_path_segment(
                value["source_slug"], label="source_slug", source=partition_source
            )
            if partition_id in partition_ids:
                raise ContractError(f"{source}.partitions contains duplicate partition IDs")
            if source_url in source_urls:
                raise ContractError(f"{source}.partitions contains duplicate source URLs")
            if source_slug in source_slugs:
                raise ContractError(f"{source}.partitions contains duplicate source slugs")
            partition_ids.add(partition_id)
            source_urls.add(source_url)
            source_slugs.add(source_slug)
            partitions.append(
                {
                    "partition_id": partition_id,
                    "name": _non_empty_string(
                        value["name"], label="name", source=partition_source
                    ),
                    "source_url": source_url,
                    "source_slug": source_slug,
                }
            )
        partitions.sort(key=lambda value: str(value["partition_id"]))

        parameters_value = requested_scope["parameters"]
        if not isinstance(parameters_value, Mapping):
            raise ContractError(f"{source}.parameters must be a JSON object")
        parameters = _scrape_json_value(
            parameters_value, source=f"{source}.parameters"
        )
        assert isinstance(parameters, dict)
        return {
            "project_catalog": catalog,
            "partitions": partitions,
            "parameters": parameters,
        }

    @classmethod
    def compute_scope_sha256(cls, requested_scope: Mapping[str, object]) -> str:
        normalized = cls.normalize_requested_scope(requested_scope)
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _validate_attempt(
        attempt: object,
        *,
        generation_id: str,
        generation_source: str,
        source: str,
    ) -> tuple[dict[str, object], datetime, datetime]:
        if not isinstance(attempt, Mapping) or set(attempt) != set(
            SCRAPE_GENERATION_ATTEMPT_FIELDS
        ):
            raise ContractError(f"{source} has an unexpected schema")
        attempt_id = _scrape_identifier(
            attempt["attempt_id"], label="attempt_id", source=source
        )
        attempt_generation = _scrape_identifier(
            attempt["generation_id"], label="generation_id", source=source
        )
        if attempt_generation != generation_id:
            raise ContractError(f"{source}.generation_id does not match the generation")
        method = attempt["method"]
        if method not in SCRAPE_GENERATION_METHODS:
            raise ContractError(
                f"{source}.method must be one of {sorted(SCRAPE_GENERATION_METHODS)}"
            )
        status = attempt["status"]
        if status not in SCRAPE_GENERATION_ATTEMPT_STATUSES:
            raise ContractError(
                f"{source}.status must be one of "
                f"{sorted(SCRAPE_GENERATION_ATTEMPT_STATUSES)}"
            )
        if generation_source.startswith("edgeprop_") and status == "confirmed_empty":
            raise ContractError(
                f"{source}.status cannot confirm an empty EdgeProp partition"
            )

        started_at = _scrape_utc_timestamp(
            attempt["started_at"], label="started_at", source=source
        )
        completed_at = _scrape_utc_timestamp(
            attempt["completed_at"], label="completed_at", source=source
        )
        assert started_at is not None and completed_at is not None
        if completed_at < started_at:
            raise ContractError(f"{source}.completed_at must not precede started_at")
        retrieved_at = _scrape_utc_timestamp(
            attempt["retrieved_at"],
            label="retrieved_at",
            source=source,
            nullable=True,
        )
        if retrieved_at is not None and not started_at <= retrieved_at <= completed_at:
            raise ContractError(
                f"{source}.retrieved_at must fall within the attempt interval"
            )

        artifact_value = attempt["artifact"]
        artifact = (
            None
            if artifact_value is None
            else _validate_scrape_artifact(
                artifact_value, source=f"{source}.artifact"
            )
        )
        reported_count = attempt["source_reported_row_count"]
        if reported_count is not None:
            reported_count = _scrape_nonnegative_int(
                reported_count,
                label="source_reported_row_count",
                source=source,
            )
        error_code = _optional_string(
            attempt["error_code"], label="error_code", source=source
        )
        error_message = _optional_string(
            attempt["error_message"], label="error_message", source=source
        )
        observations_value = attempt["observations"]
        if not isinstance(observations_value, Mapping):
            raise ContractError(f"{source}.observations must be a JSON object")
        observations = _scrape_json_value(
            observations_value, source=f"{source}.observations"
        )
        assert isinstance(observations, dict)

        if status == "succeeded":
            if artifact is None or artifact["row_count"] == 0:
                raise ContractError(
                    f"{source} succeeded attempt requires a positive-row artifact"
                )
            if (
                reported_count is not None
                and reported_count != artifact["row_count"]
            ):
                raise ContractError(
                    f"{source}.source_reported_row_count must match artifact.row_count"
                )
            if retrieved_at is None:
                raise ContractError(f"{source} succeeded attempt requires retrieved_at")
            if error_code is not None or error_message is not None:
                raise ContractError(f"{source} passing attempt must not retain an error")
        elif status == "confirmed_empty":
            if artifact is not None or reported_count != 0:
                raise ContractError(
                    f"{source} confirmed-empty attempt requires zero rows and no artifact"
                )
            if retrieved_at is None:
                raise ContractError(
                    f"{source} confirmed-empty attempt requires retrieved_at"
                )
            if error_code is not None or error_message is not None:
                raise ContractError(f"{source} passing attempt must not retain an error")
        else:
            if artifact is not None:
                raise ContractError(f"{source} failed attempt must not publish an artifact")
            if error_code is None or error_message is None:
                raise ContractError(
                    f"{source} failed attempt requires error_code and error_message"
                )

        return (
            {
                "attempt_id": attempt_id,
                "generation_id": attempt_generation,
                "method": method,
                "status": status,
                "started_at": attempt["started_at"],
                "completed_at": attempt["completed_at"],
                "retrieved_at": attempt["retrieved_at"],
                "artifact": artifact,
                "source_reported_row_count": reported_count,
                "error_code": error_code,
                "error_message": error_message,
                "observations": observations,
            },
            started_at,
            completed_at,
        )

    def validate(
        self,
        manifest: Mapping[str, object],
        *,
        source: str = "scrape generation manifest",
    ) -> dict[str, object]:
        if not isinstance(manifest, Mapping):
            raise ContractError(f"{source} must be a JSON object")
        expected = set(self.fields)
        actual = set(manifest)
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing:
            raise ContractError(f"{source} missing required fields: {missing}")
        if unexpected:
            raise ContractError(f"{source} has unexpected fields: {unexpected}")
        if manifest["contract"] != SCRAPE_GENERATION_CONTRACT:
            raise ContractError(
                f"{source}.contract must be {SCRAPE_GENERATION_CONTRACT!r}"
            )
        if manifest["schema_version"] != self.schema_version or isinstance(
            manifest["schema_version"], bool
        ):
            raise ContractError(
                f"{source}.schema_version must be {self.schema_version}"
            )
        generation_source = manifest["source"]
        if generation_source not in SCRAPE_GENERATION_SOURCES:
            raise ContractError(
                f"{source}.source must be one of {sorted(SCRAPE_GENERATION_SOURCES)}"
            )
        assert isinstance(generation_source, str)
        generation_id = _scrape_identifier(
            manifest["generation_id"], label="generation_id", source=source
        )
        status = manifest["status"]
        if status not in SCRAPE_GENERATION_STATUSES:
            raise ContractError(
                f"{source}.status must be one of {sorted(SCRAPE_GENERATION_STATUSES)}"
            )
        started_at = _scrape_utc_timestamp(
            manifest["started_at"], label="started_at", source=source
        )
        updated_at = _scrape_utc_timestamp(
            manifest["updated_at"], label="updated_at", source=source
        )
        completed_at = _scrape_utc_timestamp(
            manifest["completed_at"],
            label="completed_at",
            source=source,
            nullable=True,
        )
        assert started_at is not None and updated_at is not None
        if updated_at < started_at:
            raise ContractError(f"{source}.updated_at must not precede started_at")

        requested_scope = self.normalize_requested_scope(
            manifest["requested_scope"], source=f"{source}.requested_scope"
        )
        scope_sha256 = _scrape_sha256(
            manifest["scope_sha256"], label="scope_sha256", source=source
        )
        if scope_sha256 != self.compute_scope_sha256(requested_scope):
            raise ContractError(f"{source}.scope_sha256 does not match requested_scope")

        partition_values = manifest["partitions"]
        if not isinstance(partition_values, list):
            raise ContractError(f"{source}.partitions must be a JSON array")
        expected_partition_ids = [
            str(value["partition_id"]) for value in requested_scope["partitions"]
        ]
        if len(partition_values) != len(expected_partition_ids):
            raise ContractError(
                f"{source}.partitions must exactly match requested_scope partitions"
            )

        partitions: list[dict[str, object]] = []
        all_attempt_ids: set[str] = set()
        all_artifact_paths: set[str] = set()
        selected_statuses: list[str] = []
        failed_partitions = 0
        latest_completed = started_at
        for index, value in enumerate(partition_values):
            partition_source = f"{source}.partitions[{index}]"
            if not isinstance(value, Mapping) or set(value) != set(
                SCRAPE_GENERATION_PARTITION_FIELDS
            ):
                raise ContractError(f"{partition_source} has an unexpected schema")
            partition_id = _scrape_identifier(
                value["partition_id"], label="partition_id", source=partition_source
            )
            if partition_id != expected_partition_ids[index]:
                raise ContractError(
                    f"{source}.partitions must exactly match requested_scope partitions"
                )
            attempts_value = value["attempts"]
            if not isinstance(attempts_value, list):
                raise ContractError(f"{partition_source}.attempts must be a JSON array")
            attempts: list[dict[str, object]] = []
            passing_ids: dict[str, str] = {}
            for attempt_index, attempt_value in enumerate(attempts_value):
                attempt, attempt_started, attempt_completed = self._validate_attempt(
                    attempt_value,
                    generation_id=generation_id,
                    generation_source=generation_source,
                    source=f"{partition_source}.attempts[{attempt_index}]",
                )
                if attempt_started < started_at:
                    raise ContractError(
                        f"{partition_source}.attempts[{attempt_index}] starts before the generation"
                    )
                latest_completed = max(latest_completed, attempt_completed)
                attempt_id = str(attempt["attempt_id"])
                if attempt_id in all_attempt_ids:
                    raise ContractError(f"{source} contains duplicate attempt IDs")
                all_attempt_ids.add(attempt_id)
                artifact = attempt["artifact"]
                if isinstance(artifact, Mapping):
                    artifact_path = str(artifact["relative_path"])
                    if artifact_path in all_artifact_paths:
                        raise ContractError(f"{source} contains duplicate attempt artifacts")
                    all_artifact_paths.add(artifact_path)
                if attempt["status"] in {"succeeded", "confirmed_empty"}:
                    passing_ids[attempt_id] = str(attempt["status"])
                attempts.append(attempt)
            selected = value["selected_attempt_id"]
            if selected is not None:
                selected = _scrape_identifier(
                    selected, label="selected_attempt_id", source=partition_source
                )
                if selected not in passing_ids:
                    raise ContractError(
                        f"{partition_source}.selected_attempt_id must select a passing attempt"
                    )
                selected_statuses.append(passing_ids[selected])
            elif passing_ids:
                raise ContractError(
                    f"{partition_source} has a passing attempt but no selected_attempt_id"
                )
            elif attempts and attempts[-1]["status"] == "failed":
                failed_partitions += 1
            partitions.append(
                {
                    "partition_id": partition_id,
                    "selected_attempt_id": selected,
                    "attempts": attempts,
                }
            )
        if updated_at < latest_completed:
            raise ContractError(f"{source}.updated_at precedes a recorded attempt")

        summary_value = manifest["summary"]
        if not isinstance(summary_value, Mapping) or set(summary_value) != set(
            SCRAPE_GENERATION_SUMMARY_FIELDS
        ):
            raise ContractError(f"{source}.summary has an unexpected schema")
        requested_count = len(partitions)
        selected_count = len(selected_statuses)
        expected_summary = {
            "requested": requested_count,
            "selected": selected_count,
            "succeeded": selected_statuses.count("succeeded"),
            "confirmed_empty": selected_statuses.count("confirmed_empty"),
            "failed": failed_partitions,
            "pending": requested_count - selected_count,
        }
        for field_name, expected_value in expected_summary.items():
            actual_value = _scrape_nonnegative_int(
                summary_value[field_name],
                label=field_name,
                source=f"{source}.summary",
            )
            if actual_value != expected_value:
                raise ContractError(
                    f"{source}.summary.{field_name} must be {expected_value}"
                )

        output_value = manifest["output"]
        output = (
            None
            if output_value is None
            else _validate_scrape_artifact(output_value, source=f"{source}.output")
        )
        if status == "open":
            if completed_at is not None or output is not None:
                raise ContractError(
                    f"{source} open generation must not have completed_at or output"
                )
        else:
            if completed_at is None or output is None:
                raise ContractError(
                    f"{source} complete generation requires completed_at and output"
                )
            if completed_at != updated_at:
                raise ContractError(
                    f"{source} complete generation completed_at must equal updated_at"
                )
            if selected_count != requested_count:
                raise ContractError(
                    f"{source} complete generation requires every partition selected"
                )
            if str(output["relative_path"]) in all_artifact_paths:
                raise ContractError(
                    f"{source}.output must be distinct from partition artifacts"
                )

        return {
            "contract": SCRAPE_GENERATION_CONTRACT,
            "schema_version": self.schema_version,
            "source": generation_source,
            "generation_id": generation_id,
            "status": status,
            "started_at": manifest["started_at"],
            "updated_at": manifest["updated_at"],
            "completed_at": manifest["completed_at"],
            "scope_sha256": scope_sha256,
            "requested_scope": requested_scope,
            "partitions": partitions,
            "summary": expected_summary,
            "output": output,
        }


SCRAPE_GENERATION = ScrapeGenerationContract()


@dataclass(frozen=True)
class UraAcquisitionContract:
    """Strict contract for one review-gated URA acquisition generation."""

    schema_version: int = URA_ACQUISITION_SCHEMA_VERSION
    fields: tuple[str, ...] = (
        "schema_version",
        "dataset_id",
        "acquisition_id",
        "status",
        "started_at",
        "completed_at",
        "request",
        "partitions",
        "reconciliation",
        "output",
    )

    def validate(
        self,
        manifest: Mapping[str, object],
        *,
        source: str = "URA acquisition manifest",
    ) -> dict[str, object]:
        if not isinstance(manifest, Mapping):
            raise ContractError(f"{source} must be a JSON object")
        expected = set(self.fields)
        actual = set(manifest)
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing:
            raise ContractError(f"{source} missing required fields: {missing}")
        if unexpected:
            raise ContractError(f"{source} has unexpected fields: {unexpected}")
        if manifest["schema_version"] != self.schema_version:
            raise ContractError(
                f"{source}.schema_version must be {self.schema_version}"
            )
        if manifest["dataset_id"] != "ura_private.csv":
            raise ContractError(f"{source}.dataset_id must be 'ura_private.csv'")
        _non_empty_string(
            manifest["acquisition_id"], label="acquisition_id", source=source
        )
        if manifest["status"] not in URA_ACQUISITION_STATUSES:
            raise ContractError(
                f"{source}.status must be one of {sorted(URA_ACQUISITION_STATUSES)}"
            )
        for field_name in ("started_at", "completed_at"):
            value = manifest[field_name]
            if value is None and field_name == "completed_at":
                continue
            text = _non_empty_string(value, label=field_name, source=source)
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ContractError(
                    f"{source}.{field_name} must be an ISO-8601 timestamp with timezone"
                ) from exc
            if "T" not in text or parsed.tzinfo is None:
                raise ContractError(
                    f"{source}.{field_name} must be an ISO-8601 timestamp with timezone"
                )

        request = manifest["request"]
        if not isinstance(request, Mapping):
            raise ContractError(f"{source}.request must be a JSON object")
        request_fields = {
            "districts",
            "property_types",
            "sale_types",
            "coverage_start",
            "coverage_end",
        }
        if set(request) != request_fields:
            raise ContractError(f"{source}.request must have fields {sorted(request_fields)}")
        districts = _string_list(
            request["districts"], source=f"{source}.request.districts"
        )
        if any(not re.fullmatch(r"(?:0[1-9]|1\d|2[0-8])", value) for value in districts):
            raise ContractError(f"{source}.request.districts contains an invalid district")
        property_types = _string_list(
            request["property_types"],
            source=f"{source}.request.property_types",
        )
        if any(value not in URA_PROPERTY_TYPES for value in property_types):
            raise ContractError(f"{source}.request.property_types contains an invalid type")
        sale_types = request["sale_types"]
        if not isinstance(sale_types, list) or any(
            not isinstance(value, str) or value not in {"1", "2", "3"}
            for value in sale_types
        ):
            raise ContractError(f"{source}.request.sale_types must contain 1, 2, or 3")
        if len(sale_types) != len(set(sale_types)):
            raise ContractError(f"{source}.request.sale_types contains duplicates")
        coverage_start = _optional_iso_period(
            request["coverage_start"], label="coverage_start", source=f"{source}.request"
        )
        coverage_end = _optional_iso_period(
            request["coverage_end"], label="coverage_end", source=f"{source}.request"
        )
        if coverage_start is None or coverage_end is None:
            raise ContractError(f"{source}.request coverage must be known")
        if coverage_start[0] > coverage_end[1]:
            raise ContractError(f"{source}.request coverage_start is after coverage_end")

        partitions = manifest["partitions"]
        if not isinstance(partitions, list):
            raise ContractError(f"{source}.partitions must be a JSON array")
        observed_partitions: set[tuple[str, str]] = set()
        for index, partition in enumerate(partitions):
            self._validate_partition(
                partition,
                source=f"{source}.partitions[{index}]",
            )
            key = (partition["district"], partition["property_type"])
            if key in observed_partitions:
                raise ContractError(f"{source}.partitions contains duplicate {key}")
            observed_partitions.add(key)
        expected_partitions = {
            (district, property_type)
            for district in districts
            for property_type in property_types
        }
        if observed_partitions != expected_partitions:
            raise ContractError(
                f"{source}.partitions must exactly match requested district/type pairs"
            )

        reconciliation = manifest["reconciliation"]
        if not isinstance(reconciliation, Mapping):
            raise ContractError(f"{source}.reconciliation must be a JSON object")
        reconciliation_fields = {
            "status",
            "expected_partitions",
            "selected_partitions",
            "raw_rows",
            "valid_rows",
            "invalid_rows",
            "duplicate_rows",
            "published_rows",
            "missing_sale_month_rows",
            "missing_project_age_rows",
            "district_counts",
            "property_type_counts",
            "month_counts",
            "invalid_reasons",
            "failures",
        }
        if set(reconciliation) != reconciliation_fields:
            raise ContractError(
                f"{source}.reconciliation must have fields {sorted(reconciliation_fields)}"
            )
        if reconciliation["status"] not in {"passed", "failed"}:
            raise ContractError(f"{source}.reconciliation.status must be passed or failed")
        for field_name in (
            "expected_partitions",
            "selected_partitions",
            "raw_rows",
            "valid_rows",
            "invalid_rows",
            "duplicate_rows",
            "published_rows",
            "missing_sale_month_rows",
            "missing_project_age_rows",
        ):
            value = reconciliation[field_name]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ContractError(
                    f"{source}.reconciliation.{field_name} must be a non-negative integer"
                )
        for field_name in (
            "district_counts",
            "property_type_counts",
            "month_counts",
            "invalid_reasons",
        ):
            counts = reconciliation[field_name]
            if not isinstance(counts, Mapping) or any(
                not isinstance(key, str)
                or isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                for key, value in counts.items()
            ):
                raise ContractError(
                    f"{source}.reconciliation.{field_name} must be non-negative counts"
                )
        failures = reconciliation["failures"]
        if not isinstance(failures, list) or any(
            not isinstance(value, str) or not value for value in failures
        ):
            raise ContractError(f"{source}.reconciliation.failures must be strings")

        output = manifest["output"]
        if not isinstance(output, Mapping) or set(output) != {
            "path",
            "sha256",
            "row_count",
        }:
            raise ContractError(f"{source}.output has an unexpected schema")
        _non_empty_string(output["path"], label="path", source=f"{source}.output")
        digest = _non_empty_string(
            output["sha256"], label="sha256", source=f"{source}.output"
        )
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ContractError(f"{source}.output.sha256 must be a lowercase SHA-256")
        row_count = output["row_count"]
        if isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 0:
            raise ContractError(f"{source}.output.row_count must be non-negative")
        return {field_name: manifest[field_name] for field_name in self.fields}

    @staticmethod
    def _validate_partition(partition: object, *, source: str) -> None:
        if not isinstance(partition, Mapping) or set(partition) != {
            "district",
            "property_type",
            "selected_attempt_id",
            "attempts",
        }:
            raise ContractError(f"{source} has an unexpected schema")
        district = _non_empty_string(partition["district"], label="district", source=source)
        if not re.fullmatch(r"(?:0[1-9]|1\d|2[0-8])", district):
            raise ContractError(f"{source}.district is invalid")
        property_type = _non_empty_string(
            partition["property_type"], label="property_type", source=source
        )
        if property_type not in URA_PROPERTY_TYPES:
            raise ContractError(f"{source}.property_type is invalid")
        attempts = partition["attempts"]
        if not isinstance(attempts, list) or not attempts:
            raise ContractError(f"{source}.attempts must be non-empty")
        ids: set[str] = set()
        terminal: set[str] = set()
        for index, attempt in enumerate(attempts):
            attempt_source = f"{source}.attempts[{index}]"
            _validate_ura_attempt(attempt, source=attempt_source)
            attempt_id = attempt["attempt_id"]
            if attempt_id in ids:
                raise ContractError(f"{source}.attempts contains duplicate attempt IDs")
            ids.add(attempt_id)
            if attempt["status"] in {"succeeded", "confirmed_empty"}:
                terminal.add(attempt_id)
        selected = partition["selected_attempt_id"]
        if selected is not None and selected not in terminal:
            raise ContractError(f"{source}.selected_attempt_id must select a successful attempt")


def _string_list(value: object, *, source: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ContractError(f"{source} must be a non-empty JSON array")
    if any(not isinstance(item, str) or not item for item in value):
        raise ContractError(f"{source} must contain non-empty strings")
    if len(value) != len(set(value)):
        raise ContractError(f"{source} must not contain duplicates")
    return value


def _validate_ura_attempt(attempt: object, *, source: str) -> None:
    fields = {
        "attempt_id",
        "method",
        "status",
        "started_at",
        "completed_at",
        "retrieved_at",
        "source_url",
        "artifact",
        "sha256",
        "source_reported_row_count",
        "artifact_row_count",
        "error_code",
        "error_message",
    }
    if not isinstance(attempt, Mapping) or set(attempt) != fields:
        raise ContractError(f"{source} has an unexpected schema")
    _non_empty_string(attempt["attempt_id"], label="attempt_id", source=source)
    if attempt["method"] not in URA_ACQUISITION_METHODS:
        raise ContractError(f"{source}.method is invalid")
    if attempt["status"] not in URA_ACQUISITION_ATTEMPT_STATUSES:
        raise ContractError(f"{source}.status is invalid")
    for field_name in ("started_at", "completed_at", "retrieved_at"):
        value = attempt[field_name]
        if value is None and field_name == "retrieved_at":
            continue
        text = _non_empty_string(value, label=field_name, source=source)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractError(f"{source}.{field_name} must be ISO-8601") from exc
        if parsed.tzinfo is None:
            raise ContractError(f"{source}.{field_name} must include a timezone")
    source_url = _optional_string(attempt["source_url"], label="source_url", source=source)
    if source_url is not None:
        _http_url(source_url, label="source_url", source=source)
    for field_name in ("artifact", "sha256", "error_code", "error_message"):
        _optional_string(attempt[field_name], label=field_name, source=source)
    if attempt["sha256"] is not None and not re.fullmatch(r"[0-9a-f]{64}", attempt["sha256"]):
        raise ContractError(f"{source}.sha256 must be a lowercase SHA-256")
    for field_name in ("source_reported_row_count", "artifact_row_count"):
        value = attempt[field_name]
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ContractError(f"{source}.{field_name} must be non-negative or null")


URA_ACQUISITION = UraAcquisitionContract()


@dataclass(frozen=True)
class DataFrameContract:
    required: frozenset[str]
    unique: tuple[tuple[str, ...], ...] = ()
    numeric_ranges: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    allowed_values: Mapping[str, frozenset[object]] = field(default_factory=dict)

    def validate(self, frame: pd.DataFrame, *, source: str = "dataframe") -> pd.DataFrame:
        missing = sorted(self.required - set(frame.columns))
        if missing:
            raise ContractError(f"{source} missing required columns: {missing}")

        for columns in self.unique:
            duplicate_mask = frame.duplicated(list(columns), keep=False)
            if duplicate_mask.any():
                examples = (
                    frame.loc[duplicate_mask, list(columns)]
                    .drop_duplicates()
                    .head(5)
                    .to_dict("records")
                )
                raise ContractError(
                    f"{source} has duplicate key {columns}: {examples}"
                )

        for column, (minimum, maximum) in self.numeric_ranges.items():
            if column not in frame:
                continue
            numeric = pd.to_numeric(frame[column], errors="coerce")
            invalid_type = frame[column].notna() & numeric.isna()
            if invalid_type.any():
                raise ContractError(f"{source}.{column} contains non-numeric values")
            outside = numeric.notna() & ~numeric.between(minimum, maximum)
            if outside.any():
                values = sorted(numeric.loc[outside].unique())[:5]
                raise ContractError(
                    f"{source}.{column} outside [{minimum}, {maximum}]: {values}"
                )

        for column, allowed in self.allowed_values.items():
            if column not in frame:
                continue
            invalid = frame[column].dropna().loc[lambda values: ~values.isin(allowed)]
            if not invalid.empty:
                values = sorted({str(value) for value in invalid.unique()})[:5]
                raise ContractError(f"{source}.{column} has invalid values: {values}")

        return frame

    def read_csv(self, path: str | Path, **kwargs) -> pd.DataFrame:
        frame = pd.read_csv(path, **kwargs)
        return self.validate(frame, source=str(path))


def require_estate_coverage(
    spine: Iterable[object],
    candidate: Iterable[object],
    *,
    source: str,
    allow_missing: bool = True,
) -> set[str]:
    """Validate that a candidate dataset does not introduce unknown estates."""

    expected = {str(value).strip().upper() for value in spine}
    actual = {str(value).strip().upper() for value in candidate}
    unknown = actual - expected
    if unknown:
        raise ContractError(f"{source} contains unknown estates: {sorted(unknown)}")
    missing = expected - actual
    if missing and not allow_missing:
        raise ContractError(f"{source} missing estates: {sorted(missing)}")
    return missing


ESTATES = DataFrameContract(
    required=frozenset({"estate", "lat", "lon"}),
    unique=(("estate",),),
    numeric_ranges={"lat": (-90.0, 90.0), "lon": (-180.0, 180.0)},
)

POINT_LAYER = DataFrameContract(
    required=frozenset({"lat", "lon"}),
    numeric_ranges={"lat": (-90.0, 90.0), "lon": (-180.0, 180.0)},
)

SCORE_BASE = DataFrameContract(
    required=frozenset({"estate", "score"}),
    unique=(("estate",),),
    numeric_ranges={"score": (1.0, 5.0)},
)

PROVISION = DataFrameContract(
    required=frozenset(
        {"estate", "score", "score_private", "band", *PROVISION_WEIGHTS.keys()}
    ),
    unique=(("estate",),),
    numeric_ranges={
        **{component: (1.0, 5.0) for component in PROVISION_WEIGHTS},
        "score": (1.0, 5.0),
        "score_private": (1.0, 5.0),
    },
    allowed_values={"band": frozenset(label for _, label in BAND_EDGES)},
)

MASTER_PROVISION = DataFrameContract(
    required=frozenset({"estate", "score_private", "measured_only"}),
    unique=(("estate",),),
    numeric_ranges={"score_private": (1.0, 5.0)},
)

LIVEABILITY = DataFrameContract(
    required=frozenset(
        {
            "estate",
            "archetype",
            "provision_score",
            "provision_band",
            "D_T0",
            "D_T5",
            "D_T15",
        }
    ),
    unique=(("estate",),),
    numeric_ranges={
        "provision_score": (1.0, 5.0),
        "D_T0": (0.70, 1.0),
        "D_T5": (0.70, 1.0),
        "D_T15": (0.70, 1.0),
    },
)

VALUE = DataFrameContract(
    required=frozenset(
        {"estate", "segment", "n", "value_score", "value_band", "value_basis"}
    ),
    unique=(("estate", "segment"),),
    numeric_ranges={"n": (0.0, float("inf")), "value_score": (0.0, 10.0)},
)

EMPLOYMENT = DataFrameContract(
    required=frozenset(
        {"estate", "emp_score", "emp_band", "best_node", "worst_node"}
    ),
    unique=(("estate",),),
    numeric_ranges={"emp_score": (1.0, 5.0)},
)

LEASE_RISK = DataFrameContract(
    required=frozenset(
        {"estate", "lease_score", "lease_band", "source"}
    ),
    unique=(("estate",),),
    numeric_ranges={"lease_score": (1.0, 5.0)},
)

ARCHETYPES = DataFrameContract(
    required=frozenset({"estate", "archetype", "confidence"}),
    unique=(("estate",),),
)

MASTER_OUTPUT = DataFrameContract(
    required=frozenset(
        {
            "estate",
            "model_version",
            "provision_score",
            "provision_band",
            "provision_private_status",
            "value_hdb_status",
            "employment_status",
            "lease_status",
            "value_private_status",
        }
    ),
    unique=(("estate",),),
    numeric_ranges={
        "provision_score": (1.0, 5.0),
        "value_hdb_score": (0.0, 10.0),
        "emp_score": (1.0, 5.0),
        "lease_score": (1.0, 5.0),
        "value_private_score": (0.0, 10.0),
    },
    allowed_values={
        column: frozenset(
            {"available", "no_data", "not_covered", "not_applicable"}
        )
        for column in (
            "provision_private_status",
            "value_hdb_status",
            "employment_status",
            "lease_status",
            "value_private_status",
        )
    },
)

__all__ = [
    "ARCHETYPES",
    "EMPLOYMENT",
    "ESTATES",
    "LEASE_RISK",
    "LIVEABILITY",
    "MASTER_OUTPUT",
    "MASTER_PROVISION",
    "POINT_LAYER",
    "PROVISION",
    "SCORE_BASE",
    "SCRAPE_GENERATION",
    "SCRAPE_GENERATION_ARTIFACT_FIELDS",
    "SCRAPE_GENERATION_ATTEMPT_FIELDS",
    "SCRAPE_GENERATION_ATTEMPT_STATUSES",
    "SCRAPE_GENERATION_CONTRACT",
    "SCRAPE_GENERATION_FIELDS",
    "SCRAPE_GENERATION_METHODS",
    "SCRAPE_GENERATION_PARTITION_FIELDS",
    "SCRAPE_GENERATION_SCHEMA_VERSION",
    "SCRAPE_GENERATION_SCOPE_FIELDS",
    "SCRAPE_GENERATION_SCOPE_PARTITION_FIELDS",
    "SCRAPE_GENERATION_SOURCES",
    "SCRAPE_GENERATION_STATUSES",
    "SCRAPE_GENERATION_SUMMARY_FIELDS",
    "SOURCE_RECEIPT",
    "SOURCE_RECEIPT_CACHE_STATES",
    "SOURCE_RECEIPT_FALLBACK_STATES",
    "SOURCE_RECEIPT_FIELDS",
    "SOURCE_RECEIPT_SCHEMA_VERSION",
    "SOURCE_RECEIPT_VALIDATION_STATUSES",
    "URA_ACQUISITION",
    "URA_ACQUISITION_ATTEMPT_STATUSES",
    "URA_ACQUISITION_METHODS",
    "URA_ACQUISITION_SCHEMA_VERSION",
    "URA_ACQUISITION_STATUSES",
    "URA_PROPERTY_TYPES",
    "VALUE",
    "ContractError",
    "DataFrameContract",
    "ScrapeGenerationContract",
    "SourceReceiptContract",
    "UraAcquisitionContract",
    "require_estate_coverage",
]
