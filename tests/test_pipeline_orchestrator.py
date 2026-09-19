import json
from pathlib import Path

import pytest

from sg_estate.application import pipeline as pipeline_module
from sg_estate import source_receipts, ura_acquisition
from sg_estate.contracts import URA_ACQUISITION_SCHEMA_VERSION


CATALOG_ENTRIES = {
    "tree_canopy.csv": {
        "zone": "derived",
        "producer": "tree",
        "authority": "NParks parks snapshot + MSS / data.gov.sg",
    },
    "hdb_density.csv": {
        "zone": "derived",
        "producer": "density",
        "authority": "HDB / data.gov.sg + framework density assumptions",
    },
    "hawker_v2.csv": {
        "zone": "derived",
        "producer": "hawker",
        "authority": "markets.csv + curated stall counts",
    },
    "coastal.csv": {
        "zone": "derived",
        "producer": "coastal",
        "authority": "curated blue-infrastructure anchors",
    },
    "bca_permits.csv": {
        "zone": "derived",
        "producer": "bca",
        "authority": "pipeline_data.json",
    },
    "hdb_resale.csv": {
        "zone": "ingested",
        "producer": "models/data_ingest.py",
        "authority": "HDB / data.gov.sg",
    },
    "pipeline_data.json": {
        "zone": "curated",
        "producer": "network ingesters + human review",
        "authority": "reviewed public announcements",
    },
    "ura_private.csv": {
        "zone": "ingested",
        "producer": "scrapers/ingest_ura_raw.py",
        "authority": "URA PMI",
    },
}


URA_TEST_TIMESTAMP = "2026-08-13T03:00:00+00:00"


def _write_ura_bundle(inputs: Path) -> Path:
    output = inputs / "ura_private.csv"
    output.write_text(
        "postal_district,property_type_group,sale_month,project_age_years,"
        "transacted_price\n"
        "03,3,2026-01,5,1000000\n",
        encoding="utf-8",
    )
    receipt = source_receipts.build_source_receipt(
        output,
        dataset_id="ura_private.csv",
        authority="URA PMI",
        source_identity="ura-acquisition:pipeline-test",
        retrieved_at=URA_TEST_TIMESTAMP,
        coverage_start="2026-01",
        coverage_end="2026-01",
        row_count=1,
        cache_state="fresh",
        fallback_state="not_used",
        validation_status="passed",
    )
    source_receipts.write_source_receipt(output, receipt)
    manifest = {
        "schema_version": URA_ACQUISITION_SCHEMA_VERSION,
        "dataset_id": "ura_private.csv",
        "acquisition_id": "pipeline-test",
        "status": "complete",
        "started_at": URA_TEST_TIMESTAMP,
        "completed_at": URA_TEST_TIMESTAMP,
        "request": {
            "districts": ["03"],
            "property_types": ["3"],
            "sale_types": ["1", "2", "3"],
            "coverage_start": "2026-01",
            "coverage_end": "2026-01",
        },
        "partitions": [
            {
                "district": "03",
                "property_type": "3",
                "selected_attempt_id": "pw-d03-p3",
                "attempts": [
                    {
                        "attempt_id": "pw-d03-p3",
                        "method": "playwright",
                        "status": "succeeded",
                        "started_at": URA_TEST_TIMESTAMP,
                        "completed_at": URA_TEST_TIMESTAMP,
                        "retrieved_at": URA_TEST_TIMESTAMP,
                        "source_url": (
                            "https://eservice.ura.gov.sg/property-market-information/"
                            "pmiResidentialTransactionSearch"
                        ),
                        "artifact": "pmi_d03_2026-2026.csv",
                        "sha256": "a" * 64,
                        "source_reported_row_count": 1,
                        "artifact_row_count": 1,
                        "error_code": None,
                        "error_message": None,
                    }
                ],
            }
        ],
        "reconciliation": {
            "status": "passed",
            "expected_partitions": 1,
            "selected_partitions": 1,
            "raw_rows": 1,
            "valid_rows": 1,
            "invalid_rows": 0,
            "duplicate_rows": 0,
            "published_rows": 1,
            "missing_sale_month_rows": 0,
            "missing_project_age_rows": 0,
            "district_counts": {"03": 1},
            "property_type_counts": {"3": 1},
            "month_counts": {"2026-01": 1},
            "invalid_reasons": {},
            "failures": [],
        },
        "output": {
            "path": output.name,
            "sha256": source_receipts.sha256_file(output),
            "row_count": 1,
        },
    }
    ura_acquisition.write_acquisition_manifest(
        output,
        manifest,
        allowed_statuses=("complete",),
    )
    return output


def _configure_pipeline_paths(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "repo"
    inputs = root / "data" / "inputs"
    outputs = root / "data" / "outputs"
    runs = root / "data" / "runs"
    for directory in (inputs, outputs, runs):
        directory.mkdir(parents=True)
    (root / "data" / "catalog.json").write_text(
        json.dumps(
            {
                "schema_version": pipeline_module.CATALOG_SCHEMA_VERSION,
                "datasets": CATALOG_ENTRIES,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    for name in (
        *pipeline_module.SOURCE_INPUT_NAMES,
        *pipeline_module.DERIVED_INPUT_NAMES,
    ):
        (inputs / name).write_text(f"{name}\n", encoding="utf-8")
    monkeypatch.setattr(pipeline_module, "REPOSITORY_ROOT", root)
    monkeypatch.setattr(pipeline_module, "INPUT_DIR", inputs)
    monkeypatch.setattr(pipeline_module, "OUTPUT_DIR", outputs)
    monkeypatch.setattr(pipeline_module, "RUNS_DIR", runs)
    return inputs, outputs, runs


def _write_outputs(pipeline: pipeline_module.TransactionalPipeline) -> None:
    for name in pipeline_module.OUTPUT_NAMES:
        (pipeline.staged_outputs / name).write_text(
            f"name,value\nnew-{name},1\n", encoding="utf-8"
        )


def _write_all_staged_receipts(
    pipeline: pipeline_module.TransactionalPipeline,
    *,
    cache_state: str = "fresh",
) -> None:
    for name in pipeline_module.DERIVED_INPUT_NAMES:
        output = pipeline.staged_inputs / name
        receipt = source_receipts.build_source_receipt(
            output,
            dataset_id=name,
            authority=CATALOG_ENTRIES[name]["authority"],
            source_identity=f"test:{name}",
            row_count=pipeline._csv_row_count(output),
            cache_state=cache_state,
            fallback_state="not_used",
            validation_status="passed",
        )
        source_receipts.write_source_receipt(output, receipt)


def _prepare_awaiting_review_run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    with_ura_bundle: bool = False,
) -> tuple[pipeline_module.TransactionalPipeline, Path, Path]:
    inputs, outputs, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    if with_ura_bundle:
        _write_ura_bundle(inputs)
    for name in (*pipeline_module.DERIVED_INPUT_NAMES, *pipeline_module.OUTPUT_NAMES):
        target_dir = inputs if name in pipeline_module.DERIVED_INPUT_NAMES else outputs
        (target_dir / name).write_text(f"canonical-{name}\n", encoding="utf-8")

    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=True,
    )

    def stage_derived() -> list[pipeline_module.Stage]:
        for name in pipeline_module.DERIVED_INPUT_NAMES:
            (pipeline.staged_inputs / name).write_text(
                f"estate,value\n{name},1\n", encoding="utf-8"
            )
        for name in ("tree_canopy.csv", "hdb_density.csv"):
            output = pipeline.staged_inputs / name
            receipt = source_receipts.build_source_receipt(
                output,
                dataset_id=name,
                authority=CATALOG_ENTRIES[name]["authority"],
                source_identity=f"network-test:{name}",
                row_count=1,
                cache_state="fresh",
                fallback_state="not_used",
                validation_status="passed",
            )
            source_receipts.write_source_receipt(output, receipt)
        return []

    monkeypatch.setattr(pipeline, "_derived_stages", stage_derived)
    monkeypatch.setattr(pipeline, "_model_stages", lambda: [])
    monkeypatch.setattr(pipeline, "_validate", lambda: None)
    _write_outputs(pipeline)
    manifest_path = pipeline.run()
    assert manifest_path == pipeline.run_dir / "manifest.json"
    return pipeline, inputs, outputs


def test_reuse_run_stages_derived_inputs_and_records_manifest(monkeypatch, tmp_path):
    inputs, _, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2030,
        refresh_derived=False,
    )
    assert pipeline._derived_stages() == []
    for name in pipeline_module.DERIVED_INPUT_NAMES:
        assert (pipeline.staged_inputs / name).read_bytes() == (inputs / name).read_bytes()
    assert pipeline.manifest["as_of_year"] == 2030
    assert pipeline.manifest["refresh_derived"] is False
    assert pipeline.manifest["schema_version"] == 3
    assert pipeline.manifest["python_version"]
    assert isinstance(pipeline.manifest["code"], dict)
    assert len(pipeline.manifest["inputs"]) == (
        len(pipeline_module.SOURCE_INPUT_NAMES)
        + len(pipeline_module.DERIVED_INPUT_NAMES)
    )
    commands = " ".join(
        argument
        for stage in pipeline._model_stages()
        for argument in stage.command
    )
    assert "--year" in commands
    assert "2030" in commands
    receipts = pipeline._collect_source_receipts()
    assert tuple(receipts) == pipeline_module.DERIVED_INPUT_NAMES
    for name, receipt in receipts.items():
        assert receipt["cache_state"] == "offline"
        assert receipt["retrieved_at"] is None
        assert receipt["coverage_start"] is None
        assert receipt["coverage_end"] is None
        assert receipt["row_count"] == 0
        assert receipt["validation_status"] == "passed"


def test_manifest_collects_valid_optional_canonical_source_receipt(
    monkeypatch,
    tmp_path,
):
    inputs, _, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    source = inputs / "hdb_resale.csv"
    source.write_text("town,resale_price\nALPHA,500000\n", encoding="utf-8")
    receipt = source_receipts.build_source_receipt(
        source,
        dataset_id="hdb_resale.csv",
        authority="HDB / data.gov.sg",
        source_identity="data.gov.sg:test-hdb",
        row_count=1,
        cache_state="fresh",
        fallback_state="not_used",
        validation_status="passed",
    )
    source_receipts.write_source_receipt(source, receipt)
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=False,
    )
    pipeline._derived_stages()

    collected = pipeline._collect_source_receipts()

    assert collected["hdb_resale.csv"] == receipt
    assert set(pipeline_module.DERIVED_INPUT_NAMES).issubset(collected)


def test_manifest_validates_json_source_receipt_row_count(monkeypatch, tmp_path):
    inputs, _, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    source = inputs / "pipeline_data.json"
    source.write_text(
        json.dumps({"pipeline_items": [{"id": 1}, {"id": 2}]}) + "\n",
        encoding="utf-8",
    )
    receipt = source_receipts.build_source_receipt(
        source,
        dataset_id="pipeline_data.json",
        authority="reviewed public announcements",
        source_identity="reviewed:pipeline-data",
        row_count=2,
        cache_state="mixed",
        fallback_state="not_used",
        validation_status="passed",
    )
    source_receipts.write_source_receipt(source, receipt)
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=False,
    )
    pipeline._derived_stages()

    assert pipeline._collect_source_receipts()["pipeline_data.json"]["row_count"] == 2


@pytest.mark.parametrize("damage", ["bytes", "row_count", "authority", "validation"])
def test_optional_canonical_source_receipt_fails_closed(
    monkeypatch,
    tmp_path,
    damage,
):
    inputs, _, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    source = inputs / "hdb_resale.csv"
    source.write_text("town,resale_price\nALPHA,500000\n", encoding="utf-8")
    receipt = source_receipts.build_source_receipt(
        source,
        dataset_id="hdb_resale.csv",
        authority="HDB / data.gov.sg",
        source_identity="data.gov.sg:test-hdb",
        row_count=1,
        cache_state="fresh",
        fallback_state="not_used",
        validation_status="passed",
    )
    sidecar = source_receipts.write_source_receipt(source, receipt)
    if damage == "bytes":
        source.write_text("town,resale_price\nBETA,600000\n", encoding="utf-8")
    else:
        broken = json.loads(sidecar.read_text(encoding="utf-8"))
        if damage == "row_count":
            broken["row_count"] = 99
        elif damage == "authority":
            broken["authority"] = "Wrong authority"
        else:
            broken["validation_status"] = "not_run"
        sidecar.write_text(json.dumps(broken) + "\n", encoding="utf-8")
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=False,
    )
    pipeline._derived_stages()

    with pytest.raises(pipeline_module.ContractError):
        pipeline._collect_source_receipts()


def test_ura_acquisition_manifest_without_receipt_fails_closed(
    monkeypatch,
    tmp_path,
):
    inputs, _, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    acquisition = ura_acquisition.acquisition_path_for(
        inputs / "ura_private.csv"
    )
    acquisition.write_text("{}\n", encoding="utf-8")
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=False,
    )
    pipeline._derived_stages()

    with pytest.raises(
        pipeline_module.ContractError,
        match="acquisition manifest exists without its digest-bound source receipt",
    ):
        pipeline._collect_source_receipts()


def test_artifact_recording_rejects_ura_evidence_changed_during_run(
    monkeypatch,
    tmp_path,
):
    inputs, _, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    _write_ura_bundle(inputs)
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=False,
    )
    pipeline._derived_stages()
    _write_outputs(pipeline)
    acquisition_path = ura_acquisition.acquisition_path_for(
        inputs / "ura_private.csv"
    )
    replacement = json.loads(acquisition_path.read_text(encoding="utf-8"))
    replacement["started_at"] = "2026-08-13T02:59:00+00:00"
    acquisition_path.write_text(
        json.dumps(replacement, indent=2) + "\n",
        encoding="utf-8",
    )
    ura_acquisition.validate_acquisition_bundle(
        inputs / "ura_private.csv",
        allowed_statuses=("complete",),
    )

    with pytest.raises(
        pipeline_module.ContractError,
        match="inputs or evidence sidecars changed during the pipeline run",
    ):
        pipeline._record_validated_artifacts()


def test_promotion_replaces_complete_file_set(monkeypatch, tmp_path):
    inputs, outputs, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=False,
    )
    pipeline._derived_stages()
    _write_outputs(pipeline)
    _write_all_staged_receipts(pipeline, cache_state="offline")
    old_output = outputs / "provision_scores.csv"
    old_output.write_text("old\n", encoding="utf-8")
    pipeline.manifest["status"] = "complete"
    pipeline._write_manifest()

    pipeline._promote()

    assert old_output.read_text(encoding="utf-8") == (
        "name,value\nnew-provision_scores.csv,1\n"
    )
    assert (outputs / "run_manifest.json").is_file()
    for name in pipeline_module.OUTPUT_NAMES:
        assert (outputs / name).is_file()
    for name in pipeline_module.DERIVED_INPUT_NAMES:
        assert source_receipts.receipt_path_for(inputs / name).is_file()


def test_promotion_restores_target_when_replace_fails_after_backup(
    monkeypatch, tmp_path
):
    inputs, _, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=False,
    )
    pipeline._derived_stages()
    _write_outputs(pipeline)
    _write_all_staged_receipts(pipeline, cache_state="offline")
    pipeline.manifest["status"] = "complete"
    pipeline._write_manifest()

    target = inputs / pipeline_module.DERIVED_INPUT_NAMES[0]
    target.write_text("old-tree-canopy\n", encoding="utf-8")
    staged = pipeline.staged_inputs / pipeline_module.DERIVED_INPUT_NAMES[0]
    real_replace = pipeline_module.os.replace
    failed = False

    def fail_once(source, destination):
        nonlocal failed
        if Path(source) == staged and not failed:
            failed = True
            raise OSError("simulated promotion failure")
        return real_replace(source, destination)

    monkeypatch.setattr(pipeline_module.os, "replace", fail_once)

    with pytest.raises(OSError, match="simulated promotion failure"):
        pipeline._promote()

    assert target.read_text(encoding="utf-8") == "old-tree-canopy\n"
    assert staged.is_file()


def test_promotion_rolls_back_already_replaced_targets(monkeypatch, tmp_path):
    inputs, _, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=False,
    )
    pipeline._derived_stages()
    _write_outputs(pipeline)
    _write_all_staged_receipts(pipeline, cache_state="offline")
    pipeline.manifest["status"] = "complete"
    pipeline._write_manifest()

    first_three = pipeline_module.DERIVED_INPUT_NAMES[:3]
    for name in first_three:
        (inputs / name).write_text(f"old-{name}\n", encoding="utf-8")

    failed_source = pipeline.staged_inputs / first_three[-1]
    real_replace = pipeline_module.os.replace
    failed = False

    def fail_once(source, destination):
        nonlocal failed
        if Path(source) == failed_source and not failed:
            failed = True
            raise OSError("simulated later promotion failure")
        return real_replace(source, destination)

    monkeypatch.setattr(pipeline_module.os, "replace", fail_once)

    with pytest.raises(OSError, match="simulated later promotion failure"):
        pipeline._promote()

    for name in first_three:
        assert (inputs / name).read_text(encoding="utf-8") == f"old-{name}\n"
        assert (pipeline.staged_inputs / name).is_file()


def test_refresh_stops_awaiting_review_with_exact_validated_receipts(
    monkeypatch,
    tmp_path,
):
    pipeline, inputs, outputs = _prepare_awaiting_review_run(monkeypatch, tmp_path)

    assert pipeline.manifest["schema_version"] == 3
    assert pipeline.manifest["status"] == "awaiting_review"
    assert "completed_at" not in pipeline.manifest
    receipts = pipeline.manifest["source_receipts"]
    assert isinstance(receipts, dict)
    assert tuple(receipts) == pipeline_module.DERIVED_INPUT_NAMES
    assert receipts["tree_canopy.csv"]["cache_state"] == "fresh"
    assert receipts["hdb_density.csv"]["cache_state"] == "fresh"
    for name in pipeline_module.LOCAL_DERIVED_SOURCE_IDENTITIES:
        assert receipts[name]["cache_state"] == "derived"
        assert receipts[name]["retrieved_at"] is None
        assert receipts[name]["coverage_start"] is None
        assert receipts[name]["coverage_end"] is None

    for name in pipeline_module.DERIVED_INPUT_NAMES:
        assert (inputs / name).read_text(encoding="utf-8") == f"canonical-{name}\n"
        assert not source_receipts.receipt_path_for(inputs / name).exists()
    for name in pipeline_module.OUTPUT_NAMES:
        assert (outputs / name).read_text(encoding="utf-8") == f"canonical-{name}\n"
    assert not (outputs / "run_manifest.json").exists()


def test_offline_reuse_aggregates_receipts_and_promotes_without_review(
    monkeypatch,
    tmp_path,
):
    inputs, outputs, _ = _configure_pipeline_paths(monkeypatch, tmp_path)
    pipeline = pipeline_module.TransactionalPipeline(
        as_of_year=2026,
        refresh_derived=False,
    )
    monkeypatch.setattr(pipeline, "_model_stages", lambda: [])
    monkeypatch.setattr(pipeline, "_validate", lambda: None)
    _write_outputs(pipeline)

    result = pipeline.run()

    assert result == outputs / "run_manifest.json"
    manifest = json.loads(result.read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert set(manifest["source_receipts"]) == set(
        pipeline_module.DERIVED_INPUT_NAMES
    )
    for name, receipt in manifest["source_receipts"].items():
        assert receipt["cache_state"] == "offline"
        assert receipt["retrieved_at"] is None
        assert receipt["coverage_start"] is None
        assert receipt["coverage_end"] is None
        assert receipt["validation_status"] == "passed"
        assert source_receipts.receipt_path_for(inputs / name).is_file()


def test_explicit_reviewed_promotion_reloads_revalidates_and_promotes(
    monkeypatch,
    tmp_path,
):
    staged, inputs, outputs = _prepare_awaiting_review_run(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pipeline_module.TransactionalPipeline,
        "_validate",
        lambda self: None,
    )

    reviewed = pipeline_module.TransactionalPipeline.load_awaiting_review(
        staged.run_id
    )
    result = reviewed.promote_reviewed()

    assert result == outputs / "run_manifest.json"
    promoted_manifest = json.loads(result.read_text(encoding="utf-8"))
    assert promoted_manifest["status"] == "complete"
    assert promoted_manifest["reviewed_at"]
    assert promoted_manifest["completed_at"] == promoted_manifest["reviewed_at"]
    assert set(promoted_manifest["source_receipts"]) == set(
        pipeline_module.DERIVED_INPUT_NAMES
    )
    for name in pipeline_module.DERIVED_INPUT_NAMES:
        assert (inputs / name).read_text(encoding="utf-8").startswith("estate,value")
        assert source_receipts.receipt_path_for(inputs / name).is_file()
    for name in pipeline_module.OUTPUT_NAMES:
        assert (outputs / name).read_text(encoding="utf-8").startswith("name,value")


def test_reviewed_promotion_rejects_valid_ura_evidence_substitution(
    monkeypatch,
    tmp_path,
):
    staged, inputs, outputs = _prepare_awaiting_review_run(
        monkeypatch,
        tmp_path,
        with_ura_bundle=True,
    )
    acquisition_path = ura_acquisition.acquisition_path_for(
        inputs / "ura_private.csv"
    )
    replacement = json.loads(acquisition_path.read_text(encoding="utf-8"))
    replacement["started_at"] = "2026-08-13T02:59:00+00:00"
    acquisition_path.write_text(
        json.dumps(replacement, indent=2) + "\n",
        encoding="utf-8",
    )
    # The replacement is internally valid and bound to the same CSV. Promotion
    # must still reject it because it is not the evidence that was reviewed.
    ura_acquisition.validate_acquisition_bundle(
        inputs / "ura_private.csv",
        allowed_statuses=("complete",),
    )
    monkeypatch.setattr(
        pipeline_module.TransactionalPipeline,
        "_validate",
        lambda self: None,
    )

    reviewed = pipeline_module.TransactionalPipeline.load_awaiting_review(
        staged.run_id
    )
    with pytest.raises(
        pipeline_module.ContractError,
        match="canonical source inputs changed after staging",
    ):
        reviewed.promote_reviewed()

    for name in pipeline_module.DERIVED_INPUT_NAMES:
        assert (inputs / name).read_text(encoding="utf-8") == f"canonical-{name}\n"
    for name in pipeline_module.OUTPUT_NAMES:
        assert (outputs / name).read_text(encoding="utf-8") == f"canonical-{name}\n"
    assert not (outputs / "run_manifest.json").exists()


def test_reviewed_promotion_failure_rolls_back_and_restores_awaiting_state(
    monkeypatch,
    tmp_path,
):
    staged, inputs, outputs = _prepare_awaiting_review_run(monkeypatch, tmp_path)
    monkeypatch.setattr(
        pipeline_module.TransactionalPipeline,
        "_validate",
        lambda self: None,
    )
    reviewed = pipeline_module.TransactionalPipeline.load_awaiting_review(
        staged.run_id
    )
    failed_source = reviewed.staged_inputs / "hdb_density.csv"
    real_replace = pipeline_module.os.replace
    failed = False

    def fail_once(source, destination):
        nonlocal failed
        if Path(source) == failed_source and not failed:
            failed = True
            raise OSError("simulated reviewed promotion failure")
        return real_replace(source, destination)

    monkeypatch.setattr(pipeline_module.os, "replace", fail_once)

    with pytest.raises(OSError, match="simulated reviewed promotion failure"):
        reviewed.promote_reviewed()

    manifest = json.loads(
        (staged.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "awaiting_review"
    assert not (staged.run_dir / "backup").exists()
    for name in pipeline_module.DERIVED_INPUT_NAMES:
        assert (inputs / name).read_text(encoding="utf-8") == f"canonical-{name}\n"
        assert (staged.staged_inputs / name).is_file()
    for name in pipeline_module.OUTPUT_NAMES:
        assert (outputs / name).read_text(encoding="utf-8") == f"canonical-{name}\n"


@pytest.mark.parametrize(
    "damage",
    [
        "missing_sidecar",
        "input_hash",
        "receipt_row_count",
        "receipt_authority",
        "receipt_validation_status",
        "missing_manifest_receipt",
        "output_hash",
    ],
)
def test_reviewed_promotion_fails_closed_and_preserves_canonical_targets(
    monkeypatch,
    tmp_path,
    damage,
):
    staged, inputs, outputs = _prepare_awaiting_review_run(monkeypatch, tmp_path)
    name = pipeline_module.DERIVED_INPUT_NAMES[0]
    sidecar = source_receipts.receipt_path_for(staged.staged_inputs / name)

    if damage == "missing_sidecar":
        sidecar.unlink()
    elif damage == "input_hash":
        (staged.staged_inputs / name).write_text(
            "estate,value\nCHANGED,2\n", encoding="utf-8"
        )
    elif damage in {
        "receipt_row_count",
        "receipt_authority",
        "receipt_validation_status",
    }:
        receipt = json.loads(sidecar.read_text(encoding="utf-8"))
        if damage == "receipt_row_count":
            receipt["row_count"] = 999
        elif damage == "receipt_authority":
            receipt["authority"] = "Wrong authority"
        else:
            receipt["validation_status"] = "failed"
        sidecar.write_text(json.dumps(receipt) + "\n", encoding="utf-8")
        staged.manifest["source_receipts"][name] = receipt
        staged._write_manifest()
    elif damage == "missing_manifest_receipt":
        del staged.manifest["source_receipts"][name]
        staged._write_manifest()
    else:
        output_name = pipeline_module.OUTPUT_NAMES[0]
        (staged.staged_outputs / output_name).write_text(
            "name,value\nCHANGED,2\n", encoding="utf-8"
        )

    monkeypatch.setattr(
        pipeline_module.TransactionalPipeline,
        "_validate",
        lambda self: None,
    )
    reviewed = pipeline_module.TransactionalPipeline.load_awaiting_review(
        staged.run_id
    )
    with pytest.raises((pipeline_module.ContractError, FileNotFoundError)):
        reviewed.promote_reviewed()

    persisted = json.loads((staged.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "awaiting_review"
    for target_name in pipeline_module.DERIVED_INPUT_NAMES:
        assert (inputs / target_name).read_text(encoding="utf-8") == (
            f"canonical-{target_name}\n"
        )
    for target_name in pipeline_module.OUTPUT_NAMES:
        assert (outputs / target_name).read_text(encoding="utf-8") == (
            f"canonical-{target_name}\n"
        )
    assert not (outputs / "run_manifest.json").exists()


def test_reviewed_promotion_rejects_catalog_change(monkeypatch, tmp_path):
    staged, inputs, outputs = _prepare_awaiting_review_run(monkeypatch, tmp_path)
    catalog_path = inputs.parent / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["datasets"]["tree_canopy.csv"]["authority"] = "Changed authority"
    catalog_path.write_text(json.dumps(catalog) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        pipeline_module.TransactionalPipeline,
        "_validate",
        lambda self: None,
    )

    reviewed = pipeline_module.TransactionalPipeline.load_awaiting_review(
        staged.run_id
    )
    with pytest.raises(pipeline_module.ContractError, match="catalog.json changed"):
        reviewed.promote_reviewed()

    assert (inputs / "tree_canopy.csv").read_text(encoding="utf-8") == (
        "canonical-tree_canopy.csv\n"
    )
    assert not (outputs / "run_manifest.json").exists()


def test_cli_supports_explicit_reviewed_promotion(monkeypatch, capsys):
    events = []

    class LoadedRun:
        def promote_reviewed(self):
            events.append("promoted")
            return Path("data/outputs/run_manifest.json")

    monkeypatch.setattr(
        pipeline_module.TransactionalPipeline,
        "load_awaiting_review",
        lambda run_id: events.append(run_id) or LoadedRun(),
    )

    pipeline_module.main(["--promote-run", "run-123"])

    assert events == ["run-123", "promoted"]
    assert "Run manifest: data/outputs/run_manifest.json" in capsys.readouterr().out
