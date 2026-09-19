"""Validate and transactionally publish final URA acquisition bundles."""

from __future__ import annotations

from collections import Counter
import csv
from datetime import date
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Collection, Mapping

from sg_estate.contracts import (
    ContractError,
    URA_ACQUISITION,
    URA_ACQUISITION_STATUSES,
)
from sg_estate.source_receipts import (
    read_source_receipt,
    receipt_path_for,
    sha256_file,
)


ACQUISITION_SUFFIX = ".acquisition.json"
PASSING_ATTEMPT_STATUSES = frozenset({"succeeded", "confirmed_empty"})


def acquisition_path_for(output_path: str | Path) -> Path:
    """Return the final acquisition-manifest path beside a transaction CSV."""

    output = Path(output_path)
    return output.with_name(f"{output.name}{ACQUISITION_SUFFIX}")


def _csv_observations(path: Path) -> dict[str, object]:
    """Independently observe the persisted completeness dimensions."""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames
        if header is None:
            raise ContractError(f"URA acquisition output has no CSV header: {path}")
        if not header or not any(value.strip() for value in header):
            raise ContractError(f"URA acquisition output has an empty CSV header: {path}")
        if len(header) != len(set(header)):
            raise ContractError(f"URA acquisition output has duplicate CSV columns: {path}")
        required = {
            "postal_district",
            "property_type_group",
            "sale_month",
            "project_age_years",
        }
        missing = sorted(required - set(header))
        if missing:
            raise ContractError(
                f"URA acquisition output missing completeness columns: {missing}"
            )

        row_count = 0
        district_counts: Counter[str] = Counter()
        property_type_counts: Counter[str] = Counter()
        month_counts: Counter[str] = Counter()
        missing_sale_month_rows = 0
        missing_project_age_rows = 0
        for row in reader:
            if not row or not any(str(value or "").strip() for value in row.values()):
                continue
            row_count += 1
            district = str(row["postal_district"] or "").strip()
            property_type = str(row["property_type_group"] or "").strip()
            sale_month = str(row["sale_month"] or "").strip()
            project_age = str(row["project_age_years"] or "").strip()
            district_counts[district] += 1
            property_type_counts[property_type] += 1
            if sale_month:
                month_counts[sale_month] += 1
            else:
                missing_sale_month_rows += 1
            if not project_age:
                missing_project_age_rows += 1

    return {
        "row_count": row_count,
        "district_counts": dict(district_counts),
        "property_type_counts": dict(property_type_counts),
        "month_counts": dict(month_counts),
        "missing_sale_month_rows": missing_sale_month_rows,
        "missing_project_age_rows": missing_project_age_rows,
    }


def _month_range(start: str, end: str, *, source: str) -> list[str]:
    """Return every YYYY-MM value in an inclusive, strictly monthly range."""

    try:
        if len(start) != 7 or len(end) != 7:
            raise ValueError
        start_date = date.fromisoformat(f"{start}-01")
        end_date = date.fromisoformat(f"{end}-01")
    except ValueError as exc:
        raise ContractError(
            f"{source} coverage_start and coverage_end must use YYYY-MM precision"
        ) from exc
    if start_date > end_date:
        raise ContractError(f"{source} coverage_start is after coverage_end")

    months: list[str] = []
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        months.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return months


def _allowed_status_set(
    allowed_statuses: Collection[str] | None,
) -> frozenset[str] | None:
    if allowed_statuses is None:
        return None
    if isinstance(allowed_statuses, str):
        statuses = frozenset({allowed_statuses})
    else:
        statuses = frozenset(allowed_statuses)
    if not statuses:
        raise ValueError("allowed_statuses must not be empty")
    unknown = statuses - URA_ACQUISITION_STATUSES
    if unknown:
        raise ValueError(f"unknown allowed URA acquisition statuses: {sorted(unknown)}")
    return statuses


def _selected_attempt(partition: Mapping[str, object]) -> Mapping[str, object] | None:
    selected_id = partition["selected_attempt_id"]
    if selected_id is None:
        return None
    attempts = partition["attempts"]
    assert isinstance(attempts, list)
    for attempt in attempts:
        assert isinstance(attempt, Mapping)
        if attempt["attempt_id"] == selected_id:
            return attempt
    # The executable base contract normally catches this first. Keep this
    # branch fail-closed if that contract is relaxed independently later.
    return None


def _validate_selected_attempt(
    attempt: Mapping[str, object],
    *,
    artifact_root: Path,
    validate_selected_artifacts: bool,
    source: str,
) -> tuple[int, Path | None]:
    status = attempt["status"]
    if status not in PASSING_ATTEMPT_STATUSES:
        raise ContractError(f"{source} must select a successful or confirmed-empty attempt")

    reported = attempt["source_reported_row_count"]
    observed = attempt["artifact_row_count"]
    if reported is not None and observed is not None and reported != observed:
        raise ContractError(
            f"{source} source-reported row count does not match artifact row count"
        )

    if status == "succeeded":
        if not attempt["artifact"] or not attempt["sha256"]:
            raise ContractError(f"{source} succeeded attempt requires artifact and sha256")
        artifact = Path(str(attempt["artifact"]))
        if artifact.is_absolute() or ".." in artifact.parts:
            raise ContractError(f"{source} artifact must be a safe relative path")
        resolved_artifact = (artifact_root / artifact).resolve()
        try:
            resolved_artifact.relative_to(artifact_root.resolve())
        except ValueError as exc:
            raise ContractError(f"{source} artifact escapes its acquisition root") from exc
        if not isinstance(observed, int) or isinstance(observed, bool) or observed <= 0:
            raise ContractError(
                f"{source} succeeded attempt requires a positive artifact row count"
            )
        if not isinstance(reported, int) or isinstance(reported, bool):
            raise ContractError(
                f"{source} succeeded attempt requires a source-reported row count"
            )
        if attempt["retrieved_at"] is None or attempt["source_url"] is None:
            raise ContractError(
                f"{source} succeeded attempt requires retrieval time and source URL"
            )
        if attempt["error_code"] is not None or attempt["error_message"] is not None:
            raise ContractError(f"{source} passing attempt must not retain an error")
        if validate_selected_artifacts:
            if not resolved_artifact.is_file():
                raise ContractError(f"{source} artifact is missing: {artifact}")
            actual_digest = sha256_file(resolved_artifact)
            if attempt["sha256"] != actual_digest:
                raise ContractError(
                    f"{source} artifact sha256 does not match {artifact}: "
                    f"expected {attempt['sha256']}, got {actual_digest}"
                )
            actual_rows = _raw_csv_row_count(resolved_artifact)
            if observed != actual_rows:
                raise ContractError(
                    f"{source} artifact row count does not match {artifact}: "
                    f"expected {observed}, got {actual_rows}"
                )
        return observed, resolved_artifact

    if reported not in {None, 0} or observed not in {None, 0}:
        raise ContractError(f"{source} confirmed-empty attempt must report zero rows")
    if attempt["artifact"] is not None or attempt["sha256"] is not None:
        raise ContractError(f"{source} confirmed-empty attempt must not claim an artifact")
    if attempt["source_url"] is None:
        raise ContractError(f"{source} confirmed-empty attempt requires a source URL")
    if attempt["error_code"] is not None or attempt["error_message"] is not None:
        raise ContractError(f"{source} confirmed-empty attempt must not retain an error")
    return 0, None


def _raw_csv_row_count(path: Path) -> int:
    """Count exact non-empty raw CSV records independently of metadata."""

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ContractError(f"selected URA artifact has no CSV header: {path}") from exc
        if not header or not any(value.strip() for value in header):
            raise ContractError(f"selected URA artifact has an empty CSV header: {path}")
        return sum(
            1 for row in reader if row and any(str(value or "").strip() for value in row)
        )


def _validate_count_map(
    counts: Mapping[str, object],
    *,
    expected_keys: set[str],
    expected_total: int,
    source: str,
) -> None:
    if set(counts) != expected_keys:
        missing = sorted(expected_keys - set(counts))
        unexpected = sorted(set(counts) - expected_keys)
        raise ContractError(
            f"{source} keys do not match acquisition scope: "
            f"missing={missing}, unexpected={unexpected}"
        )
    total = sum(int(value) for value in counts.values())
    if total != expected_total:
        raise ContractError(
            f"{source} sums to {total}, expected published_rows={expected_total}"
        )


def validate_acquisition_manifest(
    manifest: Mapping[str, object],
    output_path: str | Path,
    *,
    source: str = "URA acquisition manifest",
    allowed_statuses: Collection[str] | None = None,
    validate_selected_artifacts: bool = False,
) -> dict[str, object]:
    """Validate a final manifest and bind it to exact staged CSV bytes.

    The base contract owns shape and scalar validation. This helper owns the
    cross-field reconciliation that turns those fields into fail-closed
    evidence: partition selection, row arithmetic, scoped count maps, and the
    exact output digest and persisted row count.
    """

    output = Path(output_path)
    if not output.is_file():
        raise FileNotFoundError(f"URA acquisition output not found: {output}")
    validated = URA_ACQUISITION.validate(manifest, source=source)

    allowed = _allowed_status_set(allowed_statuses)
    status = str(validated["status"])
    if allowed is not None and status not in allowed:
        raise ContractError(
            f"{source}.status must be one of {sorted(allowed)}, got {status!r}"
        )
    if validated["completed_at"] is None:
        raise ContractError(f"{source}.completed_at is required for a final manifest")

    request = validated["request"]
    reconciliation = validated["reconciliation"]
    partitions = validated["partitions"]
    output_record = validated["output"]
    assert isinstance(request, Mapping)
    assert isinstance(reconciliation, Mapping)
    assert isinstance(partitions, list)
    assert isinstance(output_record, Mapping)

    districts = list(request["districts"])
    property_types = list(request["property_types"])
    months = _month_range(
        str(request["coverage_start"]),
        str(request["coverage_end"]),
        source=f"{source}.request",
    )
    expected_partitions = len(districts) * len(property_types)
    if reconciliation["expected_partitions"] != expected_partitions:
        raise ContractError(
            f"{source}.reconciliation.expected_partitions must be {expected_partitions}"
        )
    if len(partitions) != expected_partitions:
        raise ContractError(
            f"{source}.partitions count must be {expected_partitions}"
        )

    selected_count = 0
    selected_raw_rows = 0
    selected_attempt_ids: set[str] = set()
    selected_artifact_paths: set[Path] = set()
    for index, partition in enumerate(partitions):
        assert isinstance(partition, Mapping)
        attempt = _selected_attempt(partition)
        if attempt is None:
            continue
        selected_attempt_id = str(attempt["attempt_id"])
        if selected_attempt_id in selected_attempt_ids:
            raise ContractError(f"{source} selected attempt IDs must be globally unique")
        selected_attempt_ids.add(selected_attempt_id)
        attempt_rows, artifact_path = _validate_selected_attempt(
            attempt,
            artifact_root=output.parent,
            validate_selected_artifacts=validate_selected_artifacts,
            source=f"{source}.partitions[{index}].selected_attempt_id",
        )
        if artifact_path is not None:
            if artifact_path in selected_artifact_paths:
                raise ContractError(f"{source} selected artifacts must be globally unique")
            selected_artifact_paths.add(artifact_path)
        selected_count += 1
        selected_raw_rows += attempt_rows

    if reconciliation["selected_partitions"] != selected_count:
        raise ContractError(
            f"{source}.reconciliation.selected_partitions must be {selected_count}"
        )
    if reconciliation["raw_rows"] != selected_raw_rows:
        raise ContractError(
            f"{source}.reconciliation.raw_rows must equal selected artifact rows "
            f"({selected_raw_rows})"
        )

    raw_rows = int(reconciliation["raw_rows"])
    valid_rows = int(reconciliation["valid_rows"])
    invalid_rows = int(reconciliation["invalid_rows"])
    duplicate_rows = int(reconciliation["duplicate_rows"])
    published_rows = int(reconciliation["published_rows"])
    missing_sale_month_rows = int(reconciliation["missing_sale_month_rows"])
    missing_project_age_rows = int(reconciliation["missing_project_age_rows"])
    if raw_rows != valid_rows + invalid_rows:
        raise ContractError(
            f"{source}.reconciliation raw_rows must equal valid_rows + invalid_rows"
        )
    if duplicate_rows > valid_rows:
        raise ContractError(
            f"{source}.reconciliation duplicate_rows must not exceed valid_rows"
        )
    if published_rows != valid_rows - duplicate_rows:
        raise ContractError(
            f"{source}.reconciliation published_rows must equal valid_rows - duplicate_rows"
        )
    for field_name, value in (
        ("missing_sale_month_rows", missing_sale_month_rows),
        ("missing_project_age_rows", missing_project_age_rows),
    ):
        if value > published_rows:
            raise ContractError(
                f"{source}.reconciliation.{field_name} must not exceed published_rows"
            )

    invalid_reasons = reconciliation["invalid_reasons"]
    assert isinstance(invalid_reasons, Mapping)
    if sum(int(value) for value in invalid_reasons.values()) != invalid_rows:
        raise ContractError(
            f"{source}.reconciliation.invalid_reasons must sum to invalid_rows"
        )

    district_counts = reconciliation["district_counts"]
    property_type_counts = reconciliation["property_type_counts"]
    month_counts = reconciliation["month_counts"]
    assert isinstance(district_counts, Mapping)
    assert isinstance(property_type_counts, Mapping)
    assert isinstance(month_counts, Mapping)
    _validate_count_map(
        district_counts,
        expected_keys=set(districts),
        expected_total=published_rows,
        source=f"{source}.reconciliation.district_counts",
    )
    _validate_count_map(
        property_type_counts,
        expected_keys=set(property_types),
        expected_total=published_rows,
        source=f"{source}.reconciliation.property_type_counts",
    )
    _validate_count_map(
        month_counts,
        expected_keys=set(months),
        expected_total=published_rows - missing_sale_month_rows,
        source=f"{source}.reconciliation.month_counts",
    )

    reconciliation_status = reconciliation["status"]
    failures = reconciliation["failures"]
    assert isinstance(failures, list)
    if reconciliation_status == "passed":
        if failures:
            raise ContractError(f"{source} passing reconciliation must have no failures")
        if selected_count != expected_partitions:
            raise ContractError(
                f"{source} passing reconciliation must select every requested partition"
            )
        if invalid_rows or duplicate_rows:
            raise ContractError(
                f"{source} passing reconciliation requires zero invalid and duplicate rows"
            )
    elif not failures:
        raise ContractError(f"{source} failed reconciliation must explain its failures")

    if status in {"awaiting_review", "complete"} and reconciliation_status != "passed":
        raise ContractError(f"{source}.{status} manifest requires passed reconciliation")
    if status == "failed" and reconciliation_status != "failed":
        raise ContractError(f"{source}.failed manifest requires failed reconciliation")

    if output_record["path"] != output.name:
        raise ContractError(
            f"{source}.output.path must be the staged CSV basename {output.name!r}"
        )
    actual_digest = sha256_file(output)
    if output_record["sha256"] != actual_digest:
        raise ContractError(
            f"{source}.output.sha256 does not match {output}: "
            f"expected {output_record['sha256']}, got {actual_digest}"
        )
    observations = _csv_observations(output)
    actual_rows = observations["row_count"]
    if output_record["row_count"] != actual_rows:
        raise ContractError(
            f"{source}.output.row_count does not match {output}: "
            f"expected {actual_rows}, got {output_record['row_count']}"
        )
    if output_record["row_count"] != published_rows:
        raise ContractError(
            f"{source}.output.row_count must equal reconciliation.published_rows"
        )
    observed_fields = (
        "district_counts",
        "property_type_counts",
        "month_counts",
        "missing_sale_month_rows",
        "missing_project_age_rows",
    )
    for field_name in observed_fields:
        expected_value = reconciliation[field_name]
        observed_value = observations[field_name]
        if isinstance(expected_value, Mapping) and isinstance(observed_value, Mapping):
            unexpected = set(observed_value) - set(expected_value)
            if unexpected:
                raise ContractError(
                    f"{source}.reconciliation.{field_name} has persisted CSV values "
                    f"outside its scope: {sorted(unexpected)}"
                )
            observed_value = {
                key: observed_value.get(key, 0) for key in expected_value
            }
        if expected_value != observed_value:
            raise ContractError(
                f"{source}.reconciliation.{field_name} does not match persisted CSV"
            )
    return validated


def write_acquisition_manifest(
    output_path: str | Path,
    manifest: Mapping[str, object],
    *,
    allowed_statuses: Collection[str] | None = None,
    validate_selected_artifacts: bool = False,
) -> Path:
    """Atomically write a validated manifest beside its exact output bytes."""

    output = Path(output_path)
    destination = acquisition_path_for(output)
    validated = validate_acquisition_manifest(
        manifest,
        output,
        source=str(destination),
        allowed_statuses=allowed_statuses,
        validate_selected_artifacts=validate_selected_artifacts,
    )
    encoded = json.dumps(validated, ensure_ascii=False, indent=2) + "\n"

    destination.parent.mkdir(parents=True, exist_ok=True)
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
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def read_acquisition_manifest(
    manifest_path: str | Path,
    *,
    output_path: str | Path | None = None,
    allowed_statuses: Collection[str] | None = None,
    validate_selected_artifacts: bool = False,
) -> dict[str, object]:
    """Read a final acquisition manifest and verify its exact CSV output."""

    path = Path(manifest_path)
    if output_path is None:
        if not path.name.endswith(ACQUISITION_SUFFIX):
            raise ValueError(
                f"cannot infer output from acquisition manifest path without "
                f"{ACQUISITION_SUFFIX!r} suffix: {path}"
            )
        output_name = path.name[: -len(ACQUISITION_SUFFIX)]
        output = path.with_name(output_name)
    else:
        output = Path(output_path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid URA acquisition manifest JSON: {path}: {exc}") from exc
    return validate_acquisition_manifest(
        value,
        output,
        source=str(path),
        allowed_statuses=allowed_statuses,
        validate_selected_artifacts=validate_selected_artifacts,
    )


def validate_acquisition_bundle(
    output_path: str | Path,
    *,
    allowed_statuses: Collection[str] | None = None,
    validate_selected_artifacts: bool = False,
) -> tuple[dict[str, object], dict[str, object]]:
    """Validate the CSV, source receipt, and final manifest as one bundle."""

    output = Path(output_path)
    manifest = read_acquisition_manifest(
        acquisition_path_for(output),
        output_path=output,
        allowed_statuses=allowed_statuses,
        validate_selected_artifacts=validate_selected_artifacts,
    )
    receipt = read_source_receipt(receipt_path_for(output), output_path=output)
    if receipt["dataset_id"] != "ura_private.csv":
        raise ContractError("URA acquisition source receipt dataset_id must be 'ura_private.csv'")
    if receipt["authority"] != "URA PMI":
        raise ContractError("URA acquisition source receipt authority must be 'URA PMI'")
    if receipt["validation_status"] != "passed":
        raise ContractError("URA acquisition source receipt validation_status must be 'passed'")
    if receipt["cache_state"] != "fresh":
        raise ContractError("URA acquisition source receipt cache_state must be 'fresh'")
    if receipt["fallback_state"] != "not_used":
        raise ContractError(
            "URA acquisition source receipt fallback_state must be 'not_used'"
        )
    expected_identity = f"ura-acquisition:{manifest['acquisition_id']}"
    if receipt["source_identity"] != expected_identity:
        raise ContractError(
            "URA acquisition source receipt identity must match the acquisition ID"
        )
    if receipt["row_count"] != manifest["output"]["row_count"]:
        raise ContractError(
            "URA acquisition source receipt row_count must match the acquisition manifest"
        )
    request = manifest["request"]
    assert isinstance(request, Mapping)
    if receipt["coverage_start"] != request["coverage_start"]:
        raise ContractError(
            "URA acquisition source receipt coverage_start must match the acquisition manifest"
        )
    if receipt["coverage_end"] != request["coverage_end"]:
        raise ContractError(
            "URA acquisition source receipt coverage_end must match the acquisition manifest"
        )
    succeeded_retrievals = [
        str(attempt["retrieved_at"])
        for partition in manifest["partitions"]
        for attempt in partition["attempts"]
        if attempt["attempt_id"] == partition["selected_attempt_id"]
        and attempt["status"] == "succeeded"
    ]
    expected_retrieval = max(succeeded_retrievals, default=None)
    if receipt["retrieved_at"] != expected_retrieval:
        raise ContractError(
            "URA acquisition source receipt retrieved_at must match selected attempts"
        )
    return manifest, receipt


def promote_acquisition_bundle(
    staged_output_path: str | Path,
    canonical_output_path: str | Path,
    *,
    allowed_statuses: Collection[str] = ("complete",),
) -> Path:
    """Promote a validated CSV/receipt/manifest bundle with full rollback.

    The acquisition manifest is always replaced last, making it the bundle's
    commit marker. The helper never changes ``awaiting_review`` to ``complete``;
    the explicit review caller must publish and validate that state transition
    in the staged manifest before invoking this function.
    """

    staged_output = Path(staged_output_path)
    canonical_output = Path(canonical_output_path)
    if staged_output.resolve() == canonical_output.resolve():
        raise ValueError("staged and canonical URA acquisition outputs must differ")
    validate_acquisition_bundle(
        staged_output,
        allowed_statuses=allowed_statuses,
        validate_selected_artifacts=True,
    )

    staged_receipt = receipt_path_for(staged_output)
    staged_manifest = acquisition_path_for(staged_output)
    canonical_receipt = receipt_path_for(canonical_output)
    canonical_manifest = acquisition_path_for(canonical_output)
    promotions = (
        (staged_output, canonical_output),
        (staged_receipt, canonical_receipt),
        # The validated manifest is the last visible commit marker.
        (staged_manifest, canonical_manifest),
    )

    canonical_output.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = Path(
        tempfile.mkdtemp(
            prefix=f".{canonical_output.name}.promotion-backup.",
            dir=canonical_output.parent,
        )
    )
    completed: list[tuple[Path, Path | None, Path]] = []
    try:
        for index, (source, target) in enumerate(promotions):
            if not source.is_file():
                raise FileNotFoundError(f"staged URA acquisition artifact missing: {source}")
            backup: Path | None = None
            if target.exists():
                backup = backup_dir / f"{index:02d}-{target.name}"
                os.replace(target, backup)
            try:
                os.replace(source, target)
            except Exception:
                if backup is not None and backup.exists():
                    os.replace(backup, target)
                raise
            completed.append((target, backup, source))

        # Keep backups until the promoted bundle independently revalidates at
        # its canonical destination.
        validate_acquisition_bundle(
            canonical_output,
            allowed_statuses=allowed_statuses,
            validate_selected_artifacts=False,
        )
    except Exception as promotion_error:
        rollback_errors: list[str] = []
        for target, backup, source in reversed(completed):
            try:
                if target.exists():
                    os.replace(target, source)
                if backup is not None and backup.exists():
                    os.replace(backup, target)
            except Exception as rollback_error:  # pragma: no cover - catastrophic FS failure
                rollback_errors.append(f"{target}: {rollback_error}")
        if rollback_errors:
            raise RuntimeError(
                "URA acquisition promotion failed and rollback was incomplete; "
                f"recover originals from {backup_dir}: {rollback_errors}"
            ) from promotion_error
        shutil.rmtree(backup_dir)
        raise

    shutil.rmtree(backup_dir)
    return canonical_manifest


__all__ = [
    "ACQUISITION_SUFFIX",
    "acquisition_path_for",
    "promote_acquisition_bundle",
    "read_acquisition_manifest",
    "validate_acquisition_bundle",
    "validate_acquisition_manifest",
    "write_acquisition_manifest",
]
