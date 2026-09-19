from __future__ import annotations

from pathlib import Path

import pytest

from sg_estate.contracts import ContractError, URA_ACQUISITION_SCHEMA_VERSION
from sg_estate import source_receipts, ura_acquisition


TIMESTAMP = "2026-08-13T03:00:00+00:00"


def _write_output(
    directory: Path,
    *,
    rows: int = 4,
    missing_sale_rows: int = 0,
    missing_age_rows: int = 0,
) -> Path:
    output = directory / "ura_private.csv"
    directory.mkdir(parents=True, exist_ok=True)
    values = [
        ["03", "3", "2026-01", "5", "1000000"],
        ["03", "3", "2026-02", "5", "1100000"],
        ["04", "3", "2026-01", "5", "1200000"],
        ["04", "3", "2026-02", "5", "1300000"],
    ]
    for index in range(min(missing_sale_rows, len(values))):
        values[index][2] = ""
    for index in range(min(missing_age_rows, len(values))):
        values[index][3] = ""
    records = [
        "postal_district,property_type_group,sale_month,project_age_years,transacted_price",
        *(",".join(value) for value in values),
    ]
    output.write_text("\n".join(records[: rows + 1]) + "\n", encoding="utf-8")
    return output


def _attempt(
    attempt_id: str,
    district: str,
    *,
    status: str = "succeeded",
    row_count: int | None = 2,
) -> dict[str, object]:
    empty = status == "confirmed_empty"
    return {
        "attempt_id": attempt_id,
        "method": "playwright",
        "status": status,
        "started_at": TIMESTAMP,
        "completed_at": TIMESTAMP,
        "retrieved_at": TIMESTAMP,
        "source_url": (
            "https://eservice.ura.gov.sg/"
            "property-market-information/pmiResidentialTransactionSearch"
        ),
        "artifact": None if empty else f"pmi_d{district}_2026-2026.csv",
        "sha256": None if empty else "a" * 64,
        "source_reported_row_count": 0 if empty else row_count,
        "artifact_row_count": 0 if empty else row_count,
        "error_code": None,
        "error_message": None,
    }


def _manifest(output: Path, *, status: str = "awaiting_review") -> dict[str, object]:
    raw_dir = output.parent / "raw"
    raw_dir.mkdir(exist_ok=True)
    raw_artifacts: dict[str, tuple[str, str]] = {}
    for district, prices in (("03", (1000000, 1100000)), ("04", (1200000, 1300000))):
        artifact = raw_dir / f"pmi_d{district}_2026-2026.csv"
        artifact.write_text(
            "postal_district,price\n"
            f"{district},{prices[0]}\n"
            f"{district},{prices[1]}\n",
            encoding="utf-8",
        )
        raw_artifacts[district] = (
            artifact.relative_to(output.parent).as_posix(),
            source_receipts.sha256_file(artifact),
        )

    manifest = {
        "schema_version": URA_ACQUISITION_SCHEMA_VERSION,
        "dataset_id": "ura_private.csv",
        "acquisition_id": "acq-test-001",
        "status": status,
        "started_at": TIMESTAMP,
        "completed_at": TIMESTAMP,
        "request": {
            "districts": ["03", "04"],
            "property_types": ["3"],
            "sale_types": ["1", "2", "3"],
            "coverage_start": "2026-01",
            "coverage_end": "2026-02",
        },
        "partitions": [
            {
                "district": "03",
                "property_type": "3",
                "selected_attempt_id": "pw-d03-p3",
                "attempts": [_attempt("pw-d03-p3", "03")],
            },
            {
                "district": "04",
                "property_type": "3",
                "selected_attempt_id": "pw-d04-p3",
                "attempts": [_attempt("pw-d04-p3", "04")],
            },
        ],
        "reconciliation": {
            "status": "passed",
            "expected_partitions": 2,
            "selected_partitions": 2,
            "raw_rows": 4,
            "valid_rows": 4,
            "invalid_rows": 0,
            "duplicate_rows": 0,
            "published_rows": 4,
            "missing_sale_month_rows": 0,
            "missing_project_age_rows": 0,
            "district_counts": {"03": 2, "04": 2},
            "property_type_counts": {"3": 4},
            "month_counts": {"2026-01": 2, "2026-02": 2},
            "invalid_reasons": {},
            "failures": [],
        },
        "output": {
            "path": output.name,
            "sha256": source_receipts.sha256_file(output),
            "row_count": 4,
        },
    }
    for partition in manifest["partitions"]:
        district = partition["district"]
        attempt = partition["attempts"][0]
        attempt["artifact"], attempt["sha256"] = raw_artifacts[district]
    return manifest


def _write_receipt(
    output: Path,
    *,
    row_count: int = 4,
    authority: str = "URA PMI",
    source_identity: str = "ura-acquisition:acq-test-001",
    coverage_start: str = "2026-01",
    coverage_end: str = "2026-02",
    cache_state: str = "fresh",
    fallback_state: str = "not_used",
    retrieved_at: str | None = TIMESTAMP,
) -> Path:
    receipt = source_receipts.build_source_receipt(
        output,
        dataset_id="ura_private.csv",
        authority=authority,
        source_url=(
            "https://eservice.ura.gov.sg/"
            "property-market-information/pmiResidentialTransactionSearch"
        ),
        source_identity=source_identity,
        retrieved_at=retrieved_at,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        row_count=row_count,
        cache_state=cache_state,
        fallback_state=fallback_state,
        validation_status="passed",
    )
    return source_receipts.write_source_receipt(output, receipt)


def _write_bundle(directory: Path, *, status: str = "complete") -> Path:
    output = _write_output(directory)
    _write_receipt(output)
    ura_acquisition.write_acquisition_manifest(output, _manifest(output, status=status))
    return output


def test_acquisition_path_is_a_csv_sidecar(tmp_path: Path) -> None:
    output = tmp_path / "ura_private.csv"

    assert ura_acquisition.acquisition_path_for(output) == (
        tmp_path / "ura_private.csv.acquisition.json"
    )


def test_manifest_round_trip_is_bound_to_exact_output_and_status(tmp_path: Path) -> None:
    output = _write_output(tmp_path)
    manifest = _manifest(output)

    path = ura_acquisition.write_acquisition_manifest(
        output,
        manifest,
        allowed_statuses={"awaiting_review"},
    )

    assert path == ura_acquisition.acquisition_path_for(output)
    assert ura_acquisition.read_acquisition_manifest(
        path,
        allowed_statuses={"awaiting_review"},
    ) == manifest
    assert not list(tmp_path.glob(".ura_private.csv.acquisition.json.*.tmp"))


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        ("schema", "schema_version"),
        ("digest", "sha256 does not match"),
        ("output_rows", "row_count does not match"),
        ("expected_partitions", "expected_partitions must be 2"),
        ("selected_partitions", "selected_partitions must be 2"),
        ("selected_raw_rows", "raw_rows must equal selected artifact rows"),
        ("raw_arithmetic", "raw_rows must equal valid_rows"),
        ("published_arithmetic", "published_rows must equal valid_rows"),
        ("district_keys", "district_counts keys do not match"),
        ("district_sum", "district_counts sums to"),
        ("district_distribution", "district_counts does not match persisted CSV"),
        ("property_sum", "property_type_counts sums to"),
        ("month_keys", "month_counts keys do not match"),
        ("month_sum", "month_counts sums to"),
        ("month_distribution", "month_counts does not match persisted CSV"),
        ("invalid_reason_sum", "invalid_reasons must sum"),
        ("passing_failures", "must have no failures"),
        ("missing_selection", "must select every requested partition"),
        ("invalid_rows", "requires zero invalid and duplicate"),
        ("duplicate_rows", "requires zero invalid and duplicate"),
        ("status_mismatch", "awaiting_review manifest requires passed"),
    ],
)
def test_cross_field_reconciliation_fails_closed(
    tmp_path: Path,
    damage: str,
    message: str,
) -> None:
    output = _write_output(tmp_path)
    manifest = _manifest(output)
    reconciliation = manifest["reconciliation"]
    assert isinstance(reconciliation, dict)

    if damage == "schema":
        manifest["schema_version"] = 999
    elif damage == "digest":
        manifest["output"]["sha256"] = "b" * 64
    elif damage == "output_rows":
        manifest["output"]["row_count"] = 3
    elif damage == "expected_partitions":
        reconciliation["expected_partitions"] = 1
    elif damage == "selected_partitions":
        reconciliation["selected_partitions"] = 1
    elif damage == "selected_raw_rows":
        reconciliation["raw_rows"] = 3
    elif damage == "raw_arithmetic":
        manifest["partitions"][0]["attempts"][0]["source_reported_row_count"] = 3
        manifest["partitions"][0]["attempts"][0]["artifact_row_count"] = 3
        reconciliation["raw_rows"] = 5
    elif damage == "published_arithmetic":
        reconciliation["published_rows"] = 3
    elif damage == "district_keys":
        reconciliation["district_counts"] = {"03": 2, "05": 2}
    elif damage == "district_sum":
        reconciliation["district_counts"] = {"03": 1, "04": 2}
    elif damage == "district_distribution":
        reconciliation["district_counts"] = {"03": 1, "04": 3}
    elif damage == "property_sum":
        reconciliation["property_type_counts"] = {"3": 3}
    elif damage == "month_keys":
        reconciliation["month_counts"] = {"2026-01": 2, "2026-03": 2}
    elif damage == "month_sum":
        reconciliation["month_counts"] = {"2026-01": 1, "2026-02": 2}
    elif damage == "month_distribution":
        reconciliation["month_counts"] = {"2026-01": 3, "2026-02": 1}
    elif damage == "invalid_reason_sum":
        reconciliation["invalid_reasons"] = {"bad_date": 1}
    elif damage == "passing_failures":
        reconciliation["failures"] = ["unexpected failure marker"]
    elif damage == "missing_selection":
        manifest["partitions"][1]["selected_attempt_id"] = None
        reconciliation.update(
            {
                "selected_partitions": 1,
                "raw_rows": 2,
                "valid_rows": 2,
                "published_rows": 2,
                "district_counts": {"03": 2, "04": 0},
                "property_type_counts": {"3": 2},
                "month_counts": {"2026-01": 1, "2026-02": 1},
            }
        )
    elif damage == "invalid_rows":
        reconciliation.update(
            {
                "valid_rows": 3,
                "invalid_rows": 1,
                "published_rows": 3,
                "district_counts": {"03": 2, "04": 1},
                "property_type_counts": {"3": 3},
                "month_counts": {"2026-01": 2, "2026-02": 1},
                "invalid_reasons": {"bad_date": 1},
            }
        )
    elif damage == "duplicate_rows":
        reconciliation.update(
            {
                "duplicate_rows": 1,
                "published_rows": 3,
                "district_counts": {"03": 2, "04": 1},
                "property_type_counts": {"3": 3},
                "month_counts": {"2026-01": 2, "2026-02": 1},
            }
        )
    else:
        reconciliation["status"] = "failed"
        reconciliation["failures"] = ["missing partition"]

    with pytest.raises(ContractError, match=message):
        ura_acquisition.validate_acquisition_manifest(manifest, output)


def test_confirmed_empty_partition_is_an_explicit_success(tmp_path: Path) -> None:
    output = _write_output(tmp_path, rows=2)
    manifest = _manifest(output)
    manifest["partitions"][1] = {
        "district": "04",
        "property_type": "3",
        "selected_attempt_id": "pw-d04-p3-empty",
        "attempts": [
            _attempt(
                "pw-d04-p3-empty",
                "04",
                status="confirmed_empty",
                row_count=0,
            )
        ],
    }
    manifest["reconciliation"].update(
        {
            "raw_rows": 2,
            "valid_rows": 2,
            "published_rows": 2,
            "district_counts": {"03": 2, "04": 0},
            "property_type_counts": {"3": 2},
            "month_counts": {"2026-01": 1, "2026-02": 1},
        }
    )
    manifest["output"].update(
        {
            "sha256": source_receipts.sha256_file(output),
            "row_count": 2,
        }
    )

    validated = ura_acquisition.validate_acquisition_manifest(manifest, output)

    assert validated["reconciliation"]["selected_partitions"] == 2
    assert validated["reconciliation"]["raw_rows"] == 2


def test_known_null_date_and_age_counts_reconcile_without_invention(
    tmp_path: Path,
) -> None:
    output = _write_output(tmp_path, missing_sale_rows=1, missing_age_rows=2)
    manifest = _manifest(output)
    manifest["reconciliation"].update(
        {
            "missing_sale_month_rows": 1,
            "missing_project_age_rows": 2,
            "month_counts": {"2026-01": 1, "2026-02": 2},
        }
    )

    validated = ura_acquisition.validate_acquisition_manifest(manifest, output)

    reconciliation = validated["reconciliation"]
    assert reconciliation["missing_sale_month_rows"] == 1
    assert reconciliation["missing_project_age_rows"] == 2
    assert sum(reconciliation["month_counts"].values()) == 3


def test_succeeded_attempt_requires_source_reported_count_and_retrieval_evidence(
    tmp_path: Path,
) -> None:
    output = _write_output(tmp_path)
    manifest = _manifest(output)
    attempt = manifest["partitions"][0]["attempts"][0]
    attempt["source_reported_row_count"] = None

    with pytest.raises(ContractError, match="source-reported row count"):
        ura_acquisition.validate_acquisition_manifest(manifest, output)

    attempt["source_reported_row_count"] = 2
    attempt["retrieved_at"] = None
    with pytest.raises(ContractError, match="retrieval time and source URL"):
        ura_acquisition.validate_acquisition_manifest(manifest, output)


def test_staged_validation_rehashes_and_recounts_selected_raw_artifacts(
    tmp_path: Path,
) -> None:
    output = _write_output(tmp_path)
    manifest = _manifest(output)

    ura_acquisition.validate_acquisition_manifest(
        manifest,
        output,
        validate_selected_artifacts=True,
    )

    selected = manifest["partitions"][0]["attempts"][0]
    artifact = output.parent / selected["artifact"]
    artifact.write_text(
        "postal_district,price\n03,9000000\n03,9100000\n",
        encoding="utf-8",
    )
    with pytest.raises(ContractError, match="artifact sha256 does not match"):
        ura_acquisition.validate_acquisition_manifest(
            manifest,
            output,
            validate_selected_artifacts=True,
        )

    selected["sha256"] = source_receipts.sha256_file(artifact)
    artifact.write_text(
        artifact.read_text(encoding="utf-8") + "03,9200000\n",
        encoding="utf-8",
    )
    selected["sha256"] = source_receipts.sha256_file(artifact)
    with pytest.raises(ContractError, match="artifact row count does not match"):
        ura_acquisition.validate_acquisition_manifest(
            manifest,
            output,
            validate_selected_artifacts=True,
        )


@pytest.mark.parametrize("unsafe", ["/tmp/raw.csv", "../raw.csv", "raw/../../raw.csv"])
def test_selected_raw_artifact_path_is_always_relative_and_confined(
    tmp_path: Path,
    unsafe: str,
) -> None:
    output = _write_output(tmp_path)
    manifest = _manifest(output)
    manifest["partitions"][0]["attempts"][0]["artifact"] = unsafe

    with pytest.raises(ContractError, match="artifact must be a safe relative path"):
        ura_acquisition.validate_acquisition_manifest(manifest, output)


def test_failed_manifest_requires_failed_reconciliation_and_explanation(
    tmp_path: Path,
) -> None:
    output = _write_output(tmp_path, rows=2)
    manifest = _manifest(output, status="failed")
    manifest["partitions"][1]["selected_attempt_id"] = None
    manifest["reconciliation"].update(
        {
            "status": "failed",
            "selected_partitions": 1,
            "raw_rows": 2,
            "valid_rows": 2,
            "published_rows": 2,
            "district_counts": {"03": 2, "04": 0},
            "property_type_counts": {"3": 2},
            "month_counts": {"2026-01": 1, "2026-02": 1},
            "failures": ["D04/property-type 3 has no successful attempt"],
        }
    )
    manifest["output"].update(
        {
            "sha256": source_receipts.sha256_file(output),
            "row_count": 2,
        }
    )

    validated = ura_acquisition.validate_acquisition_manifest(
        manifest,
        output,
        allowed_statuses={"failed"},
    )

    assert validated["status"] == "failed"


def test_atomic_manifest_failure_preserves_existing_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = _write_output(tmp_path)
    destination = ura_acquisition.write_acquisition_manifest(output, _manifest(output))
    original = destination.read_bytes()
    replacement = _manifest(output, status="complete")
    real_replace = ura_acquisition.os.replace

    def fail_manifest_replace(source: object, target: object) -> None:
        if Path(target) == destination:
            raise OSError("simulated manifest replacement failure")
        real_replace(source, target)

    monkeypatch.setattr(ura_acquisition.os, "replace", fail_manifest_replace)

    with pytest.raises(OSError, match="simulated manifest replacement failure"):
        ura_acquisition.write_acquisition_manifest(output, replacement)

    assert destination.read_bytes() == original
    assert not list(tmp_path.glob(".ura_private.csv.acquisition.json.*.tmp"))


@pytest.mark.parametrize(
    ("receipt_overrides", "message"),
    [
        ({"row_count": 3}, "receipt row_count must match"),
        ({"authority": "Not URA"}, "authority must be 'URA PMI'"),
        (
            {"source_identity": "ura-acquisition:different"},
            "identity must match the acquisition ID",
        ),
        ({"coverage_start": "2025-12"}, "coverage_start must match"),
        ({"coverage_end": "2026-03"}, "coverage_end must match"),
        ({"cache_state": "derived"}, "cache_state must be 'fresh'"),
        ({"fallback_state": "used"}, "fallback_state must be 'not_used'"),
        ({"retrieved_at": "2026-08-13T02:00:00+00:00"}, "retrieved_at must match"),
    ],
)
def test_bundle_validation_binds_receipt_to_manifest(
    tmp_path: Path,
    receipt_overrides: dict[str, object],
    message: str,
) -> None:
    output = _write_output(tmp_path)
    _write_receipt(output, **receipt_overrides)
    ura_acquisition.write_acquisition_manifest(output, _manifest(output))

    with pytest.raises(ContractError, match=message):
        ura_acquisition.validate_acquisition_bundle(output)


def _write_old_canonical_bundle(directory: Path) -> tuple[Path, dict[Path, bytes]]:
    canonical = directory / "ura_private.csv"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    paths = (
        canonical,
        source_receipts.receipt_path_for(canonical),
        ura_acquisition.acquisition_path_for(canonical),
    )
    contents = (b"old canonical csv\n", b"old receipt\n", b"old manifest\n")
    for path, content in zip(paths, contents):
        path.write_bytes(content)
    return canonical, dict(zip(paths, contents))


def test_promotion_replaces_bundle_in_csv_receipt_manifest_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    staged = _write_bundle(tmp_path / "run")
    staged_paths = (
        staged,
        source_receipts.receipt_path_for(staged),
        ura_acquisition.acquisition_path_for(staged),
    )
    staged_bytes = {path: path.read_bytes() for path in staged_paths}
    canonical, _old = _write_old_canonical_bundle(tmp_path / "inputs")
    moved_sources: list[Path] = []
    real_replace = ura_acquisition.os.replace

    def record_replace(source: object, target: object) -> None:
        source_path = Path(source)
        if source_path in staged_paths:
            moved_sources.append(source_path)
        real_replace(source, target)

    monkeypatch.setattr(ura_acquisition.os, "replace", record_replace)

    result = ura_acquisition.promote_acquisition_bundle(staged, canonical)

    canonical_paths = (
        canonical,
        source_receipts.receipt_path_for(canonical),
        ura_acquisition.acquisition_path_for(canonical),
    )
    assert result == canonical_paths[-1]
    assert moved_sources == list(staged_paths)
    assert [path.read_bytes() for path in canonical_paths] == [
        staged_bytes[path] for path in staged_paths
    ]
    assert not any(path.exists() for path in staged_paths)
    manifest, receipt = ura_acquisition.validate_acquisition_bundle(
        canonical,
        allowed_statuses={"complete"},
    )
    assert manifest["status"] == "complete"
    assert receipt["validation_status"] == "passed"


@pytest.mark.parametrize("failure_index", [0, 1, 2])
def test_promotion_failure_restores_every_prior_canonical_byte_and_staged_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure_index: int,
) -> None:
    staged = _write_bundle(tmp_path / "run")
    staged_paths = (
        staged,
        source_receipts.receipt_path_for(staged),
        ura_acquisition.acquisition_path_for(staged),
    )
    staged_bytes = {path: path.read_bytes() for path in staged_paths}
    canonical, old_bytes = _write_old_canonical_bundle(tmp_path / "inputs")
    failing_source = staged_paths[failure_index]
    real_replace = ura_acquisition.os.replace
    failed = False

    def fail_once(source: object, target: object) -> None:
        nonlocal failed
        if Path(source) == failing_source and not failed:
            failed = True
            raise OSError(f"simulated promotion failure {failure_index}")
        real_replace(source, target)

    monkeypatch.setattr(ura_acquisition.os, "replace", fail_once)

    with pytest.raises(OSError, match="simulated promotion failure"):
        ura_acquisition.promote_acquisition_bundle(staged, canonical)

    assert {path: path.read_bytes() for path in old_bytes} == old_bytes
    assert {path: path.read_bytes() for path in staged_paths} == staged_bytes
    assert not list(
        canonical.parent.glob(".ura_private.csv.promotion-backup.*")
    )


def test_promotion_rejects_awaiting_review_without_touching_canonical(
    tmp_path: Path,
) -> None:
    staged = _write_bundle(tmp_path / "run", status="awaiting_review")
    canonical, old_bytes = _write_old_canonical_bundle(tmp_path / "inputs")

    with pytest.raises(ContractError, match="status must be one of.*complete"):
        ura_acquisition.promote_acquisition_bundle(staged, canonical)

    assert {path: path.read_bytes() for path in old_bytes} == old_bytes
    assert staged.is_file()
    assert source_receipts.receipt_path_for(staged).is_file()
    assert ura_acquisition.acquisition_path_for(staged).is_file()


def test_promotion_rejects_tampered_selected_raw_before_touching_canonical(
    tmp_path: Path,
) -> None:
    staged = _write_bundle(tmp_path / "run")
    manifest = ura_acquisition.read_acquisition_manifest(
        ura_acquisition.acquisition_path_for(staged),
        output_path=staged,
    )
    selected = manifest["partitions"][0]["attempts"][0]
    artifact = staged.parent / selected["artifact"]
    artifact.write_text(
        "postal_district,price\n03,9999999\n03,9999998\n",
        encoding="utf-8",
    )
    canonical, old_bytes = _write_old_canonical_bundle(tmp_path / "inputs")

    with pytest.raises(ContractError, match="artifact sha256 does not match"):
        ura_acquisition.promote_acquisition_bundle(staged, canonical)

    assert {path: path.read_bytes() for path in old_bytes} == old_bytes
    assert staged.is_file()
    assert source_receipts.receipt_path_for(staged).is_file()
    assert ura_acquisition.acquisition_path_for(staged).is_file()
