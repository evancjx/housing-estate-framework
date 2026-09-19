"""Fail-closed URA acquisition ingestion and review-gate coverage."""

from __future__ import annotations

from argparse import Namespace
import json
from pathlib import Path

import pandas as pd
import pytest

from scrapers import ingest_ura_raw, run_download
from sg_estate import scrape_generation
from sg_estate.contracts import ContractError
from sg_estate.source_receipts import read_source_receipt, receipt_path_for, sha256_file
from sg_estate.ura_acquisition import acquisition_path_for, read_acquisition_manifest


TIMESTAMP = "2026-08-13T03:00:00+08:00"


def _raw_partition(path: Path, district: str, month: str) -> None:
    pd.DataFrame(
        {
            "Project": [f"TEST D{district}"],
            "Type": ["Condominium"],
            "Postal District": [district],
            "Price ($)": ["1000000"],
            "Area (sqm)": ["80"],
            "Date of Sale": [month],
            "Tenure": ["Freehold"],
            "Type of Area": ["Strata"],
        }
    ).to_csv(path, index=False)


def _attempt(path: Path, district: str) -> dict:
    return {
        "partition_id": f"d{district}-p3",
        "district": district,
        "property_type": "3",
        "property_type_label": "Apartments & Condominiums",
        "method": "playwright",
        "status": "succeeded",
        "started_at": TIMESTAMP,
        "completed_at": TIMESTAMP,
        "artifact": {
            "relative_path": path.name,
            "sha256": sha256_file(path),
            "byte_count": path.stat().st_size,
            "row_count": 1,
        },
        "observations": {"row_count": 1},
        "error_code": None,
        "error_message": None,
    }


def _write_attempt_manifest(
    tmp_path: Path,
    *,
    include_d16: bool = True,
) -> Path:
    d15 = tmp_path / "d15.csv"
    d16 = tmp_path / "d16.csv"
    _raw_partition(d15, "15", "Jan-2025")
    _raw_partition(d16, "16", "Feb-2025")
    attempts = [_attempt(d15, "15")]
    if include_d16:
        attempts.append(_attempt(d16, "16"))
    manifest = {
        "schema_version": 1,
        "source": "URA PMI",
        "method": "playwright",
        "status": "succeeded",
        "started_at": TIMESTAMP,
        "completed_at": TIMESTAMP,
        "requested_scope": {
            "districts": ["15", "16"],
            "property_types": ["3"],
            "sale_types": ["1", "2", "3"],
            "year_from": "2025",
            "month_from": "1",
            "year_to": "2025",
            "month_to": "2",
        },
        "source_requests": [],
        "attempts": attempts,
        "summary": {
            "requested": 2,
            "succeeded": len(attempts),
            "confirmed_empty": 0,
            "failed": 0,
        },
    }
    path = tmp_path / "attempts.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _stage_args(attempt_manifest: Path, output: Path) -> Namespace:
    return Namespace(
        out=str(output),
        attempt_manifest=str(attempt_manifest),
        promote_run=None,
        merge=False,
        source_quality=None,
        acquisition_id="fixture-acquisition",
    )


def _write_generation_for_attempt_manifest(attempt_manifest: Path) -> Path:
    manifest = json.loads(attempt_manifest.read_text(encoding="utf-8"))
    request = manifest["requested_scope"]
    scope = run_download.generation_scope(
        request["districts"],
        request["property_types"],
        year_from=request["year_from"],
        month_from=request["month_from"],
        year_to=request["year_to"],
        month_to=request["month_to"],
        sale_types=request["sale_types"],
    )
    generation_path = attempt_manifest.with_name("generation.json")
    generation = scrape_generation.new_generation(
        "ura_pmi",
        scope,
        generation_id="fixture-generation",
        now=TIMESTAMP,
    )
    scrape_generation.write_generation(generation_path, generation)
    run_download._append_child_attempts(
        generation_path,
        attempt_manifest,
        manifest,
    )
    snapshot = run_download.attempt_manifest_from_generation(
        generation_path,
        method_hint=manifest["method"],
    )
    attempt_manifest.write_text(json.dumps(snapshot), encoding="utf-8")
    return generation_path


def test_complete_fixture_reconciles_every_dimension_and_preserves_unknown_age(
    tmp_path,
):
    attempts = _write_attempt_manifest(tmp_path)
    output = tmp_path / "stage" / "ura_private.csv"

    ingest_ura_raw.run(_stage_args(attempts, output))

    frame = pd.read_csv(output)
    manifest = read_acquisition_manifest(
        acquisition_path_for(output),
        output_path=output,
        allowed_statuses=("awaiting_review",),
    )
    receipt = read_source_receipt(receipt_path_for(output), output_path=output)
    reconciliation = manifest["reconciliation"]
    assert len(frame) == 2
    assert frame["project_age_years"].isna().all()
    assert set(frame["project_age_status"]) == {"unknown_no_completion_evidence"}
    assert reconciliation["district_counts"] == {"15": 1, "16": 1}
    assert reconciliation["property_type_counts"] == {"3": 2}
    assert reconciliation["month_counts"] == {"2025-01": 1, "2025-02": 1}
    assert reconciliation["raw_rows"] == reconciliation["valid_rows"] == 2
    assert reconciliation["invalid_rows"] == reconciliation["duplicate_rows"] == 0
    assert reconciliation["published_rows"] == 2
    assert reconciliation["missing_project_age_rows"] == 2
    assert receipt["validation_status"] == "passed"
    assert receipt["source_identity"] == "ura-acquisition:fixture-acquisition"


def test_missing_requested_district_fails_without_touching_canonical_bytes(tmp_path):
    attempts = _write_attempt_manifest(tmp_path, include_d16=False)
    canonical = ingest_ura_raw.CANONICAL_OUTPUT
    before = canonical.read_bytes()
    staged = tmp_path / "stage" / "ura_private.csv"

    result = ingest_ura_raw.main(
        [
            "--attempt-manifest",
            str(attempts),
            "--out",
            str(staged),
        ]
    )

    assert result != 0
    assert canonical.read_bytes() == before
    assert not staged.exists()


def test_partial_scope_cannot_promote_over_canonical_file(tmp_path):
    attempts = _write_attempt_manifest(tmp_path)
    staged = tmp_path / "stage" / "ura_private.csv"
    ingest_ura_raw.run(_stage_args(attempts, staged))
    canonical = ingest_ura_raw.CANONICAL_OUTPUT
    before = canonical.read_bytes()

    with pytest.raises(ContractError, match="complete district 01-28"):
        ingest_ura_raw.run(
            Namespace(
                out=str(canonical),
                promote_run=str(staged),
                attempt_manifest=None,
            )
        )

    assert canonical.read_bytes() == before
    assert staged.is_file()
    assert read_acquisition_manifest(
        acquisition_path_for(staged),
        output_path=staged,
        allowed_statuses=("awaiting_review",),
    )["status"] == "awaiting_review"


def test_reconciled_stage_finalizes_matching_generic_generation(tmp_path):
    attempts = _write_attempt_manifest(tmp_path)
    generation_path = _write_generation_for_attempt_manifest(attempts)
    output = tmp_path / "stage" / "ura_private.csv"
    args = _stage_args(attempts, output)
    args.generation_manifest = str(generation_path)

    ingest_ura_raw.run(args)

    generation = scrape_generation.load_generation(generation_path)
    assert generation["status"] == "complete"
    assert generation["generation_id"] == "fixture-generation"
    assert generation["output"]["relative_path"] == "generation.reconciled.csv"
    assert generation["output"]["sha256"] == sha256_file(output)
    assert (tmp_path / "generation.reconciled.csv").read_bytes() == output.read_bytes()
    acquisition = read_acquisition_manifest(
        acquisition_path_for(output),
        output_path=output,
        allowed_statuses=("awaiting_review",),
    )
    assert acquisition["status"] == "awaiting_review"


def test_mixed_generation_attempt_snapshot_is_rejected_before_staging(tmp_path):
    attempts = _write_attempt_manifest(tmp_path)
    generation_path = _write_generation_for_attempt_manifest(attempts)
    manifest = json.loads(attempts.read_text(encoding="utf-8"))
    manifest["attempts"][0]["observations"]["row_count"] = 2
    attempts.write_text(json.dumps(manifest), encoding="utf-8")
    output = tmp_path / "stage" / "ura_private.csv"
    args = _stage_args(attempts, output)
    args.generation_manifest = str(generation_path)

    with pytest.raises(ContractError, match="does not match the selected generation"):
        ingest_ura_raw.run(args)

    assert not output.exists()
    assert scrape_generation.load_generation(generation_path)["status"] == "open"
