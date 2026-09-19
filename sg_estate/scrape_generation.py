"""Generation-scoped, recoverable scraper checkpoints.

This module owns generic checkpoint evidence only. Source-specific completeness
reconciliation and reviewed publication remain with their existing producers
(notably :mod:`sg_estate.ura_acquisition`).
"""

from __future__ import annotations

import copy
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping
import uuid

from sg_estate.contracts import (
    ContractError,
    SCRAPE_GENERATION,
    SCRAPE_GENERATION_ATTEMPT_STATUSES,
    SCRAPE_GENERATION_CONTRACT,
    SCRAPE_GENERATION_SCHEMA_VERSION,
)
from sg_estate.source_receipts import sha256_file


@dataclass(frozen=True)
class SelectedArtifact:
    """One selected positive-row artifact resolved under a generation root."""

    partition_id: str
    path: Path
    sha256: str
    byte_count: int
    row_count: int


def _utc_text(value: datetime | str | None = None) -> str:
    if value is None:
        parsed = datetime.now(timezone.utc)
    elif isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be ISO-8601 with a timezone") from exc
    else:
        raise TypeError("timestamp must be a datetime, ISO-8601 string, or None")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_scope_sha256(requested_scope: Mapping[str, object]) -> str:
    """Return the contract-defined digest of one normalized requested scope."""

    return SCRAPE_GENERATION.compute_scope_sha256(requested_scope)


def _summary(partitions: list[dict[str, object]]) -> dict[str, int]:
    selected_statuses: list[str] = []
    failed = 0
    for partition in partitions:
        selected_id = partition["selected_attempt_id"]
        attempts = partition["attempts"]
        assert isinstance(attempts, list)
        if selected_id is not None:
            selected = next(
                attempt
                for attempt in attempts
                if isinstance(attempt, Mapping)
                and attempt["attempt_id"] == selected_id
            )
            selected_statuses.append(str(selected["status"]))
        elif attempts and isinstance(attempts[-1], Mapping) and attempts[-1]["status"] == "failed":
            failed += 1
    requested = len(partitions)
    selected = len(selected_statuses)
    return {
        "requested": requested,
        "selected": selected,
        "succeeded": selected_statuses.count("succeeded"),
        "confirmed_empty": selected_statuses.count("confirmed_empty"),
        "failed": failed,
        "pending": requested - selected,
    }


def new_generation(
    source: str,
    requested_scope: Mapping[str, object],
    *,
    generation_id: str | None = None,
    now: datetime | str | None = None,
) -> dict[str, object]:
    """Build a new open generation with one empty checkpoint per partition."""

    normalized_scope = SCRAPE_GENERATION.normalize_requested_scope(requested_scope)
    timestamp = _utc_text(now)
    identity = generation_id or str(uuid.uuid4())
    partitions = [
        {
            "partition_id": descriptor["partition_id"],
            "selected_attempt_id": None,
            "attempts": [],
        }
        for descriptor in normalized_scope["partitions"]
    ]
    manifest: dict[str, object] = {
        "contract": SCRAPE_GENERATION_CONTRACT,
        "schema_version": SCRAPE_GENERATION_SCHEMA_VERSION,
        "source": source,
        "generation_id": identity,
        "status": "open",
        "started_at": timestamp,
        "updated_at": timestamp,
        "completed_at": None,
        "scope_sha256": canonical_scope_sha256(normalized_scope),
        "requested_scope": normalized_scope,
        "partitions": partitions,
        "summary": _summary(partitions),
        "output": None,
    }
    return SCRAPE_GENERATION.validate(manifest)


def _csv_row_count(path: Path) -> int:
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise ContractError(f"cannot open scrape-generation artifact {path}: {exc}") from exc
    with handle:
        try:
            reader = csv.reader(handle)
            header = next(reader)
            if not header or not any(value.strip() for value in header):
                raise ContractError(f"scrape-generation artifact has no CSV header: {path}")
            if len(header) != len(set(header)):
                raise ContractError(
                    f"scrape-generation artifact has duplicate CSV columns: {path}"
                )
            return sum(
                1
                for row in reader
                if row and any(str(value or "").strip() for value in row)
            )
        except (csv.Error, UnicodeDecodeError) as exc:
            raise ContractError(
                f"cannot parse scrape-generation CSV artifact {path}: {exc}"
            ) from exc


def _safe_artifact_path(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ContractError(
            f"scrape-generation artifact escapes its generation root: {relative_path}"
        ) from exc
    if not candidate.is_file():
        raise ContractError(f"scrape-generation artifact is missing: {relative_path}")
    return candidate


def _validate_artifact_bytes(
    artifact: Mapping[str, object],
    *,
    root: Path,
    source: str,
) -> Path:
    relative_path = str(artifact["relative_path"])
    path = _safe_artifact_path(root, relative_path)
    actual_bytes = path.stat().st_size
    if artifact["byte_count"] != actual_bytes:
        raise ContractError(
            f"{source}.byte_count does not match {relative_path}: "
            f"expected {artifact['byte_count']}, got {actual_bytes}"
        )
    actual_digest = sha256_file(path)
    if artifact["sha256"] != actual_digest:
        raise ContractError(
            f"{source}.sha256 does not match {relative_path}: "
            f"expected {artifact['sha256']}, got {actual_digest}"
        )
    actual_rows = _csv_row_count(path)
    if artifact["row_count"] != actual_rows:
        raise ContractError(
            f"{source}.row_count does not match {relative_path}: "
            f"expected {artifact['row_count']}, got {actual_rows}"
        )
    return path


def _reject_manifest_as_artifact(
    artifact: Mapping[str, object],
    *,
    manifest_path: Path,
    source: str,
) -> None:
    resolved = (manifest_path.resolve().parent / str(artifact["relative_path"])).resolve()
    if resolved == manifest_path.resolve():
        raise ContractError(f"{source} must not reference the generation manifest itself")


def _artifact_metadata(path: Path, *, root: Path) -> dict[str, object]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ContractError(
            f"scrape-generation artifact must be inside {root}: {path}"
        ) from exc
    if not resolved.is_file():
        raise ContractError(f"scrape-generation artifact is missing: {path}")
    relative_path = relative.as_posix()
    if relative_path in {"", "."}:
        raise ContractError("scrape-generation artifact cannot be the generation root")
    return {
        "relative_path": relative_path,
        "sha256": sha256_file(resolved),
        "byte_count": resolved.stat().st_size,
        "row_count": _csv_row_count(resolved),
    }


def validate_generation(
    manifest: Mapping[str, object],
    *,
    manifest_path: str | Path | None = None,
    expected_source: str | None = None,
    expected_scope: Mapping[str, object] | None = None,
    expected_generation_id: str | None = None,
    validate_artifacts: bool = True,
) -> dict[str, object]:
    """Validate shape, ancestry, exact scope, and persisted artifact bytes."""

    source_label = str(manifest_path) if manifest_path is not None else "scrape generation manifest"
    validated = SCRAPE_GENERATION.validate(manifest, source=source_label)
    if expected_source is not None and validated["source"] != expected_source:
        raise ContractError(
            f"{source_label}.source does not match expected source {expected_source!r}"
        )
    if expected_generation_id is not None and validated["generation_id"] != expected_generation_id:
        raise ContractError(
            f"{source_label}.generation_id does not match {expected_generation_id!r}"
        )
    if expected_scope is not None:
        normalized = SCRAPE_GENERATION.normalize_requested_scope(expected_scope)
        expected_digest = canonical_scope_sha256(normalized)
        if validated["scope_sha256"] != expected_digest or validated["requested_scope"] != normalized:
            raise ContractError(f"{source_label}.requested_scope does not match expected scope")

    artifact_values: list[tuple[Mapping[str, object], str]] = []
    for partition_index, partition in enumerate(validated["partitions"]):
        assert isinstance(partition, Mapping)
        for attempt_index, attempt in enumerate(partition["attempts"]):
            assert isinstance(attempt, Mapping)
            artifact = attempt["artifact"]
            if isinstance(artifact, Mapping):
                artifact_values.append(
                    (
                        artifact,
                        f"{source_label}.partitions[{partition_index}].attempts[{attempt_index}].artifact",
                    )
                )
    if isinstance(validated["output"], Mapping):
        artifact_values.append((validated["output"], f"{source_label}.output"))

    if artifact_values and manifest_path is not None:
        for artifact, artifact_source in artifact_values:
            _reject_manifest_as_artifact(
                artifact,
                manifest_path=Path(manifest_path),
                source=artifact_source,
            )
    if validate_artifacts and artifact_values:
        if manifest_path is None:
            raise ContractError(
                "manifest_path is required to validate scrape-generation artifacts"
            )
        root = Path(manifest_path).resolve().parent
        for artifact, artifact_source in artifact_values:
            _validate_artifact_bytes(artifact, root=root, source=artifact_source)
    return validated


def _read_manifest(path: Path) -> Mapping[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise FileNotFoundError(f"scrape-generation manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid scrape-generation JSON {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ContractError(f"scrape-generation manifest must be a JSON object: {path}")
    return value


def load_generation(
    path: str | Path,
    *,
    expected_source: str | None = None,
    expected_scope: Mapping[str, object] | None = None,
    expected_generation_id: str | None = None,
    validate_artifacts: bool = True,
) -> dict[str, object]:
    """Read and fully validate one checkpoint manifest."""

    manifest_path = Path(path)
    value = _read_manifest(manifest_path)
    return validate_generation(
        value,
        manifest_path=manifest_path,
        expected_source=expected_source,
        expected_scope=expected_scope,
        expected_generation_id=expected_generation_id,
        validate_artifacts=validate_artifacts,
    )


def _validate_update(
    previous: Mapping[str, object],
    current: Mapping[str, object],
    *,
    source: str,
) -> None:
    identity_fields = (
        "contract",
        "schema_version",
        "source",
        "generation_id",
        "started_at",
        "scope_sha256",
        "requested_scope",
    )
    if any(previous[field] != current[field] for field in identity_fields):
        raise ContractError(f"{source} cannot change generation identity or requested scope")
    if previous["status"] == "complete":
        if previous != current:
            raise ContractError(f"{source} complete generation is immutable")
        return
    previous_updated = datetime.fromisoformat(str(previous["updated_at"]).replace("Z", "+00:00"))
    current_updated = datetime.fromisoformat(str(current["updated_at"]).replace("Z", "+00:00"))
    if current_updated < previous_updated:
        raise ContractError(f"{source}.updated_at cannot move backwards")
    previous_partitions = previous["partitions"]
    current_partitions = current["partitions"]
    assert isinstance(previous_partitions, list) and isinstance(current_partitions, list)
    for index, (old_partition, new_partition) in enumerate(
        zip(previous_partitions, current_partitions, strict=True)
    ):
        assert isinstance(old_partition, Mapping) and isinstance(new_partition, Mapping)
        if old_partition["partition_id"] != new_partition["partition_id"]:
            raise ContractError(f"{source}.partitions[{index}] identity changed")
        old_attempts = old_partition["attempts"]
        new_attempts = new_partition["attempts"]
        assert isinstance(old_attempts, list) and isinstance(new_attempts, list)
        if len(new_attempts) < len(old_attempts) or new_attempts[: len(old_attempts)] != old_attempts:
            raise ContractError(
                f"{source}.partitions[{index}] attempt history must be append-only"
            )
        if old_partition["selected_attempt_id"] is not None and (
            new_partition["selected_attempt_id"] != old_partition["selected_attempt_id"]
        ):
            raise ContractError(
                f"{source}.partitions[{index}] selected attempt is immutable"
            )


def write_generation(path: str | Path, manifest: Mapping[str, object]) -> Path:
    """Atomically write a validated append-only generation checkpoint."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    validated = validate_generation(manifest, manifest_path=destination)
    if destination.is_file():
        previous = load_generation(destination)
        _validate_update(previous, validated, source=str(destination))
        if previous == validated:
            return destination
    encoded = json.dumps(validated, ensure_ascii=False, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def record_attempt(
    manifest_path: str | Path,
    partition_id: str,
    *,
    method: str,
    status: str,
    started_at: datetime | str,
    completed_at: datetime | str,
    retrieved_at: datetime | str | None = None,
    artifact_path: str | Path | None = None,
    source_reported_row_count: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    observations: Mapping[str, object] | None = None,
    attempt_id: str | None = None,
    now: datetime | str | None = None,
) -> dict[str, object]:
    """Append one terminal attempt and atomically advance its partition."""

    path = Path(manifest_path)
    manifest = load_generation(path)
    if manifest["status"] != "open":
        raise ContractError("cannot append an attempt to a complete generation")
    if status not in SCRAPE_GENERATION_ATTEMPT_STATUSES:
        raise ValueError(f"unknown scrape-generation attempt status: {status}")
    partitions = manifest["partitions"]
    assert isinstance(partitions, list)
    try:
        partition = next(
            value
            for value in partitions
            if isinstance(value, dict) and value["partition_id"] == partition_id
        )
    except StopIteration as exc:
        raise ContractError(f"partition is outside the requested scope: {partition_id}") from exc
    if partition["selected_attempt_id"] is not None:
        raise ContractError(f"partition already has a selected attempt: {partition_id}")

    artifact: dict[str, object] | None = None
    if artifact_path is not None:
        artifact = _artifact_metadata(Path(artifact_path), root=path.resolve().parent)
    attempt = {
        "attempt_id": attempt_id or str(uuid.uuid4()),
        "generation_id": manifest["generation_id"],
        "method": method,
        "status": status,
        "started_at": _utc_text(started_at),
        "completed_at": _utc_text(completed_at),
        "retrieved_at": _utc_text(retrieved_at) if retrieved_at is not None else None,
        "artifact": artifact,
        "source_reported_row_count": source_reported_row_count,
        "error_code": error_code,
        "error_message": error_message,
        "observations": dict(observations or {}),
    }
    updated = copy.deepcopy(manifest)
    updated_partitions = updated["partitions"]
    assert isinstance(updated_partitions, list)
    updated_partition = next(
        value
        for value in updated_partitions
        if isinstance(value, dict) and value["partition_id"] == partition_id
    )
    updated_attempts = updated_partition["attempts"]
    assert isinstance(updated_attempts, list)
    updated_attempts.append(attempt)
    if status in {"succeeded", "confirmed_empty"}:
        updated_partition["selected_attempt_id"] = attempt["attempt_id"]
    updated["updated_at"] = _utc_text(now)
    updated["summary"] = _summary(updated_partitions)
    validated = validate_generation(updated, manifest_path=path)
    write_generation(path, validated)
    return validated


def _validated_value(
    generation: Mapping[str, object] | str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> tuple[dict[str, object], Path | None]:
    if isinstance(generation, Mapping):
        path = Path(manifest_path) if manifest_path is not None else None
        return (
            validate_generation(generation, manifest_path=path),
            path,
        )
    path = Path(generation)
    return load_generation(path), path


def successful_partition_ids(
    generation: Mapping[str, object] | str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> set[str]:
    """Return only partitions with a selected, currently valid passing attempt."""

    manifest, _path = _validated_value(generation, manifest_path=manifest_path)
    return {
        str(partition["partition_id"])
        for partition in manifest["partitions"]
        if isinstance(partition, Mapping) and partition["selected_attempt_id"] is not None
    }


def pending_partition_ids(
    generation: Mapping[str, object] | str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> set[str]:
    """Return never-attempted and failed partitions that still require work."""

    manifest, _path = _validated_value(generation, manifest_path=manifest_path)
    return {
        str(partition["partition_id"])
        for partition in manifest["partitions"]
        if isinstance(partition, Mapping) and partition["selected_attempt_id"] is None
    }


def selected_artifacts(
    generation: Mapping[str, object] | str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> tuple[SelectedArtifact, ...]:
    """Resolve positive-row selected artifacts in requested-scope order."""

    manifest, path = _validated_value(generation, manifest_path=manifest_path)
    if path is None:
        if any(
            attempt["artifact"] is not None
            for partition in manifest["partitions"]
            for attempt in partition["attempts"]
        ):
            raise ContractError("manifest_path is required to resolve selected artifacts")
        return ()
    root = path.resolve().parent
    selected: list[SelectedArtifact] = []
    for partition in manifest["partitions"]:
        assert isinstance(partition, Mapping)
        selected_id = partition["selected_attempt_id"]
        if selected_id is None:
            continue
        attempt = next(
            value
            for value in partition["attempts"]
            if isinstance(value, Mapping) and value["attempt_id"] == selected_id
        )
        artifact = attempt["artifact"]
        if not isinstance(artifact, Mapping):
            continue
        selected.append(
            SelectedArtifact(
                partition_id=str(partition["partition_id"]),
                path=_safe_artifact_path(root, str(artifact["relative_path"])),
                sha256=str(artifact["sha256"]),
                byte_count=int(artifact["byte_count"]),
                row_count=int(artifact["row_count"]),
            )
        )
    return tuple(selected)


def finalize_generation(
    manifest_path: str | Path,
    output_path: str | Path,
    *,
    now: datetime | str | None = None,
) -> dict[str, object]:
    """Bind one complete generation immutably to its reconciled candidate CSV."""

    path = Path(manifest_path)
    manifest = load_generation(path)
    output = _artifact_metadata(Path(output_path), root=path.resolve().parent)
    if manifest["status"] == "complete":
        if manifest["output"] != output:
            raise ContractError("complete generation is bound to different output bytes")
        return manifest
    if pending_partition_ids(manifest, manifest_path=path):
        raise ContractError("cannot finalize while requested partitions remain pending")
    updated = copy.deepcopy(manifest)
    completed_at = _utc_text(now)
    updated["status"] = "complete"
    updated["updated_at"] = completed_at
    updated["completed_at"] = completed_at
    updated["output"] = output
    validated = validate_generation(updated, manifest_path=path)
    write_generation(path, validated)
    return validated


__all__ = [
    "SelectedArtifact",
    "canonical_scope_sha256",
    "finalize_generation",
    "load_generation",
    "new_generation",
    "pending_partition_ids",
    "record_attempt",
    "selected_artifacts",
    "successful_partition_ids",
    "validate_generation",
    "write_generation",
]
