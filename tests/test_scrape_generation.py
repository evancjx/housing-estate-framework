from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import stat

import pytest

from sg_estate.contracts import (
    ContractError,
    SCRAPE_GENERATION,
    SCRAPE_GENERATION_ARTIFACT_FIELDS,
    SCRAPE_GENERATION_ATTEMPT_FIELDS,
    SCRAPE_GENERATION_FIELDS,
    SCRAPE_GENERATION_PARTITION_FIELDS,
    SCRAPE_GENERATION_SCOPE_FIELDS,
    SCRAPE_GENERATION_SCOPE_PARTITION_FIELDS,
    SCRAPE_GENERATION_SUMMARY_FIELDS,
)
from sg_estate import scrape_generation


START = datetime(2026, 8, 13, 1, 0, tzinfo=timezone.utc)


def _scope(*partition_ids: str) -> dict[str, object]:
    return {
        "project_catalog": {
            "name": "projects.csv",
            "sha256": "a" * 64,
        },
        "partitions": [
            {
                "partition_id": partition_id,
                "name": f"Project {partition_id.upper()}",
                "source_url": f"https://example.test/project/{partition_id}",
                "source_slug": partition_id,
            }
            for partition_id in partition_ids
        ],
        "parameters": {
            "artifact_schema": "edgeprop-condo-unit.v1",
            "from_year": 2019,
            "max_pages": 250,
        },
    }


def _write_new(
    tmp_path: Path,
    *,
    source: str = "edgeprop_condo_apartment",
    scope: dict[str, object] | None = None,
) -> tuple[Path, dict[str, object]]:
    path = tmp_path / "generation-one" / "checkpoint.json"
    manifest = scrape_generation.new_generation(
        source,
        scope or _scope("p1", "p2"),
        generation_id="generation-one",
        now=START,
    )
    scrape_generation.write_generation(path, manifest)
    return path, manifest


def _artifact(path: Path, partition_id: str, rows: int = 1) -> Path:
    destination = path.parent / "artifacts" / f"{partition_id}.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    values = ["value"] + [f"{partition_id}-{index}" for index in range(rows)]
    destination.write_text("\n".join(values) + "\n", encoding="utf-8")
    return destination


def _success(
    path: Path,
    partition_id: str,
    *,
    offset: int,
    artifact: Path | None = None,
    rows: int = 1,
) -> dict[str, object]:
    artifact = artifact or _artifact(path, partition_id, rows=rows)
    return scrape_generation.record_attempt(
        path,
        partition_id,
        method="playwright",
        status="succeeded",
        started_at=START + timedelta(minutes=offset),
        retrieved_at=START + timedelta(minutes=offset, seconds=30),
        completed_at=START + timedelta(minutes=offset + 1),
        artifact_path=artifact,
        source_reported_row_count=rows,
        observations={"pages_scraped": 1, "completion_reason": "terminal_page"},
        attempt_id=f"attempt-{partition_id}-{offset}",
        now=START + timedelta(minutes=offset + 1),
    )


def test_new_generation_has_exact_normalized_contract_and_stable_scope_digest() -> None:
    scope = _scope("p2", "p1")
    reordered = copy.deepcopy(scope)
    reordered["partitions"] = list(reversed(reordered["partitions"]))
    reordered["parameters"] = {
        "max_pages": 250,
        "from_year": 2019,
        "artifact_schema": "edgeprop-condo-unit.v1",
    }

    manifest = scrape_generation.new_generation(
        "edgeprop_condo_apartment",
        scope,
        generation_id="generation-one",
        now="2026-08-13T09:00:00+08:00",
    )

    assert tuple(manifest) == SCRAPE_GENERATION_FIELDS
    assert set(manifest["requested_scope"]) == set(SCRAPE_GENERATION_SCOPE_FIELDS)
    assert [
        partition["partition_id"] for partition in manifest["requested_scope"]["partitions"]
    ] == ["p1", "p2"]
    assert all(
        set(partition) == set(SCRAPE_GENERATION_SCOPE_PARTITION_FIELDS)
        for partition in manifest["requested_scope"]["partitions"]
    )
    assert all(
        set(partition) == set(SCRAPE_GENERATION_PARTITION_FIELDS)
        for partition in manifest["partitions"]
    )
    assert set(manifest["summary"]) == set(SCRAPE_GENERATION_SUMMARY_FIELDS)
    assert manifest["started_at"] == "2026-08-13T01:00:00Z"
    assert manifest["scope_sha256"] == scrape_generation.canonical_scope_sha256(
        reordered
    )
    assert manifest["summary"] == {
        "requested": 2,
        "selected": 0,
        "succeeded": 0,
        "confirmed_empty": 0,
        "failed": 0,
        "pending": 2,
    }

    changed = copy.deepcopy(scope)
    changed["parameters"]["from_year"] = 2020
    assert scrape_generation.canonical_scope_sha256(changed) != manifest["scope_sha256"]


def test_exact_schema_scope_hash_and_utc_timestamp_are_fail_closed() -> None:
    manifest = scrape_generation.new_generation(
        "edgeprop_condo_apartment",
        _scope("p1"),
        generation_id="generation-one",
        now=START,
    )

    extra = copy.deepcopy(manifest)
    extra["unversioned"] = True
    with pytest.raises(ContractError, match="unexpected fields"):
        SCRAPE_GENERATION.validate(extra)

    bad_scope = copy.deepcopy(manifest)
    bad_scope["requested_scope"]["parameters"]["max_pages"] = 1
    with pytest.raises(ContractError, match="scope_sha256"):
        SCRAPE_GENERATION.validate(bad_scope)

    naive = copy.deepcopy(manifest)
    naive["updated_at"] = "2026-08-13T01:00:00"
    with pytest.raises(ContractError, match="canonical UTC"):
        SCRAPE_GENERATION.validate(naive)

    with pytest.raises(ValueError, match="timezone"):
        scrape_generation.new_generation(
            "edgeprop_condo_apartment",
            _scope("p1"),
            now=datetime(2026, 8, 13, 1, 0),
        )


@pytest.mark.parametrize(
    ("duplicate", "message"),
    [
        ("partition_id", "duplicate partition IDs"),
        ("source_url", "duplicate source URLs"),
        ("source_slug", "duplicate source slugs"),
    ],
)
def test_requested_partition_identity_fields_must_be_unique(
    duplicate: str,
    message: str,
) -> None:
    scope = _scope("p1", "p2")
    scope["partitions"][1][duplicate] = scope["partitions"][0][duplicate]

    with pytest.raises(ContractError, match=message):
        scrape_generation.new_generation("edgeprop_condo_apartment", scope)


@pytest.mark.parametrize(
    "source_slug",
    ["mdis-residence@stirling", "THE-LINQ-@-BEAUTY-WORLD"],
)
def test_real_edgeprop_source_slugs_are_preserved_exactly(source_slug: str) -> None:
    scope = _scope("p1")
    scope["partitions"][0]["source_slug"] = source_slug

    manifest = scrape_generation.new_generation(
        "edgeprop_condo_apartment",
        scope,
        generation_id="generation-one",
        now=START,
    )

    assert manifest["requested_scope"]["partitions"][0]["source_slug"] == source_slug


@pytest.mark.parametrize(
    "source_slug",
    [
        "",
        ".",
        "..",
        "bad/slug",
        r"bad\slug",
        "bad slug",
        "bad\tslug",
        "bad\nslug",
        "bad%2",
        "bad?query",
        "bad#fragment",
    ],
)
def test_source_slug_rejects_unsafe_or_non_segment_text(source_slug: str) -> None:
    scope = _scope("p1")
    scope["partitions"][0]["source_slug"] = source_slug

    with pytest.raises(ContractError, match="source_slug"):
        scrape_generation.new_generation("edgeprop_condo_apartment", scope)


def test_failed_partition_retries_and_successful_partition_resumes_exactly_once(
    tmp_path: Path,
) -> None:
    path, _manifest = _write_new(tmp_path)
    failed = scrape_generation.record_attempt(
        path,
        "p1",
        method="playwright",
        status="failed",
        started_at=START + timedelta(minutes=1),
        completed_at=START + timedelta(minutes=2),
        error_code="navigation_timeout",
        error_message="timed out",
        observations={"pages_scraped": 0},
        attempt_id="attempt-p1-failed",
        now=START + timedelta(minutes=2),
    )

    assert scrape_generation.successful_partition_ids(path) == set()
    assert scrape_generation.pending_partition_ids(path) == {"p1", "p2"}
    assert failed["summary"]["failed"] == 1

    retried = _success(path, "p1", offset=3)

    assert scrape_generation.successful_partition_ids(path) == {"p1"}
    assert scrape_generation.pending_partition_ids(path) == {"p2"}
    partition = retried["partitions"][0]
    assert [attempt["status"] for attempt in partition["attempts"]] == [
        "failed",
        "succeeded",
    ]
    assert partition["selected_attempt_id"] == "attempt-p1-3"
    assert retried["summary"] == {
        "requested": 2,
        "selected": 1,
        "succeeded": 1,
        "confirmed_empty": 0,
        "failed": 0,
        "pending": 1,
    }
    selected = scrape_generation.selected_artifacts(path)
    assert [(item.partition_id, item.row_count) for item in selected] == [("p1", 1)]


def test_edgeprop_zero_rows_and_confirmed_empty_never_become_complete(
    tmp_path: Path,
) -> None:
    path, _manifest = _write_new(tmp_path, scope=_scope("p1"))
    zero = _artifact(path, "p1", rows=0)
    before = path.read_bytes()

    with pytest.raises(ContractError, match="positive-row artifact"):
        scrape_generation.record_attempt(
            path,
            "p1",
            method="playwright",
            status="succeeded",
            started_at=START + timedelta(minutes=1),
            retrieved_at=START + timedelta(minutes=1, seconds=30),
            completed_at=START + timedelta(minutes=2),
            artifact_path=zero,
            source_reported_row_count=0,
            attempt_id="zero-row",
            now=START + timedelta(minutes=2),
        )
    with pytest.raises(ContractError, match="cannot confirm an empty EdgeProp"):
        scrape_generation.record_attempt(
            path,
            "p1",
            method="playwright",
            status="confirmed_empty",
            started_at=START + timedelta(minutes=1),
            retrieved_at=START + timedelta(minutes=1, seconds=30),
            completed_at=START + timedelta(minutes=2),
            source_reported_row_count=0,
            attempt_id="claimed-empty",
            now=START + timedelta(minutes=2),
        )

    assert path.read_bytes() == before
    assert scrape_generation.pending_partition_ids(path) == {"p1"}


def test_ura_can_select_explicit_confirmed_empty_without_reusing_acquisition_contract(
    tmp_path: Path,
) -> None:
    scope = _scope("d03-p3")
    scope["project_catalog"] = None
    path, _manifest = _write_new(tmp_path, source="ura_pmi", scope=scope)

    manifest = scrape_generation.record_attempt(
        path,
        "d03-p3",
        method="playwright",
        status="confirmed_empty",
        started_at=START + timedelta(minutes=1),
        retrieved_at=START + timedelta(minutes=1, seconds=30),
        completed_at=START + timedelta(minutes=2),
        source_reported_row_count=0,
        observations={"portal_no_data": True},
        attempt_id="ura-empty",
        now=START + timedelta(minutes=2),
    )

    assert manifest["source"] == "ura_pmi"
    assert manifest["summary"]["confirmed_empty"] == 1
    assert scrape_generation.successful_partition_ids(path) == {"d03-p3"}
    assert scrape_generation.selected_artifacts(path) == ()


@pytest.mark.parametrize("mutation", ["missing", "tampered", "row_count"])
def test_resume_rehashes_and_recounts_selected_artifacts(
    tmp_path: Path,
    mutation: str,
) -> None:
    path, _manifest = _write_new(tmp_path, scope=_scope("p1"))
    artifact = _artifact(path, "p1")
    _success(path, "p1", offset=1, artifact=artifact)

    if mutation == "missing":
        artifact.unlink()
        message = "missing"
    elif mutation == "tampered":
        artifact.write_text("value\nchanged\n", encoding="utf-8")
        message = "byte_count|sha256"
    else:
        artifact.write_text("value\np1-0\np1-1\n", encoding="utf-8")
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["partitions"][0]["attempts"][0]["artifact"]["sha256"] = (
            scrape_generation.sha256_file(artifact)
        )
        manifest["partitions"][0]["attempts"][0]["artifact"]["byte_count"] = (
            artifact.stat().st_size
        )
        path.write_text(json.dumps(manifest), encoding="utf-8")
        message = "row_count"

    with pytest.raises(ContractError, match=message):
        scrape_generation.load_generation(path)
    with pytest.raises(ContractError, match=message):
        scrape_generation.successful_partition_ids(path)


def test_scope_source_generation_and_unsafe_artifacts_reject_mixed_evidence(
    tmp_path: Path,
) -> None:
    path, _manifest = _write_new(tmp_path, scope=_scope("p1"))
    _success(path, "p1", offset=1)

    with pytest.raises(ContractError, match="expected source"):
        scrape_generation.load_generation(path, expected_source="edgeprop_landed")
    with pytest.raises(ContractError, match="generation_id"):
        scrape_generation.load_generation(path, expected_generation_id="generation-two")
    with pytest.raises(ContractError, match="requested_scope"):
        scrape_generation.load_generation(path, expected_scope=_scope("different"))

    manifest = json.loads(path.read_text(encoding="utf-8"))
    attempt = manifest["partitions"][0]["attempts"][0]
    attempt["generation_id"] = "generation-two"
    with pytest.raises(ContractError, match="does not match the generation"):
        SCRAPE_GENERATION.validate(manifest)

    attempt["generation_id"] = "generation-one"
    attempt["artifact"]["relative_path"] = "../generation-two/p1.csv"
    with pytest.raises(ContractError, match="safe canonical relative path"):
        SCRAPE_GENERATION.validate(manifest)


def test_duplicate_attempt_and_artifact_selection_are_rejected(
    tmp_path: Path,
) -> None:
    path, _manifest = _write_new(tmp_path)
    artifact = _artifact(path, "shared")
    _success(path, "p1", offset=1, artifact=artifact)
    before = path.read_bytes()

    with pytest.raises(ContractError, match="duplicate attempt artifacts"):
        _success(path, "p2", offset=3, artifact=artifact)
    assert path.read_bytes() == before

    manifest = json.loads(path.read_text(encoding="utf-8"))
    duplicate = copy.deepcopy(manifest["partitions"][0]["attempts"][0])
    duplicate["status"] = "failed"
    duplicate["artifact"] = None
    duplicate["retrieved_at"] = None
    duplicate["source_reported_row_count"] = None
    duplicate["error_code"] = "retry_failed"
    duplicate["error_message"] = "failed"
    manifest["partitions"][1]["attempts"].append(duplicate)
    with pytest.raises(ContractError, match="duplicate attempt IDs"):
        SCRAPE_GENERATION.validate(manifest)


def test_manifest_can_never_be_a_partition_artifact_or_final_output(
    tmp_path: Path,
) -> None:
    path, _manifest = _write_new(tmp_path, scope=_scope("p1"))
    before = path.read_bytes()

    with pytest.raises(ContractError, match="manifest itself"):
        scrape_generation.record_attempt(
            path,
            "p1",
            method="playwright",
            status="succeeded",
            started_at=START + timedelta(minutes=1),
            retrieved_at=START + timedelta(minutes=1, seconds=30),
            completed_at=START + timedelta(minutes=2),
            artifact_path=path,
            observations={"completion_reason": "terminal_page"},
            attempt_id="attempt-manifest-self",
            now=START + timedelta(minutes=2),
        )
    assert path.read_bytes() == before

    _success(path, "p1", offset=1)
    before = path.read_bytes()
    with pytest.raises(ContractError, match="manifest itself"):
        scrape_generation.finalize_generation(
            path, path, now=START + timedelta(minutes=3)
        )
    assert path.read_bytes() == before


def test_write_generation_validates_new_artifact_before_manifest_switch(
    tmp_path: Path,
) -> None:
    path, manifest = _write_new(tmp_path, scope=_scope("p1"))
    artifact = _artifact(path, "p1")
    before = path.read_bytes()
    updated = copy.deepcopy(manifest)
    attempt = {
        "attempt_id": "attempt-p1-direct",
        "generation_id": "generation-one",
        "method": "playwright",
        "status": "succeeded",
        "started_at": "2026-08-13T01:01:00Z",
        "completed_at": "2026-08-13T01:02:00Z",
        "retrieved_at": "2026-08-13T01:01:30Z",
        "artifact": {
            "relative_path": "artifacts/p1.csv",
            "sha256": scrape_generation.sha256_file(artifact),
            "byte_count": artifact.stat().st_size,
            "row_count": 1,
        },
        "source_reported_row_count": 1,
        "error_code": None,
        "error_message": None,
        "observations": {"completion_reason": "terminal_page"},
    }
    updated["partitions"][0]["attempts"].append(attempt)
    updated["partitions"][0]["selected_attempt_id"] = attempt["attempt_id"]
    updated["updated_at"] = "2026-08-13T01:02:00Z"
    updated["summary"] = {
        "requested": 1,
        "selected": 1,
        "succeeded": 1,
        "confirmed_empty": 0,
        "failed": 0,
        "pending": 0,
    }
    artifact.write_text("value\ntampered-and-longer\n", encoding="utf-8")

    with pytest.raises(ContractError, match="byte_count|sha256"):
        scrape_generation.write_generation(path, updated)

    assert path.read_bytes() == before
    assert scrape_generation.pending_partition_ids(path) == {"p1"}


def test_complete_requires_all_partitions_and_binds_immutable_output_bytes(
    tmp_path: Path,
) -> None:
    path, _manifest = _write_new(tmp_path)
    _success(path, "p1", offset=1)
    candidate = path.parent / "candidate.csv"
    candidate.write_text("value\np1-0\n", encoding="utf-8")

    with pytest.raises(ContractError, match="remain pending"):
        scrape_generation.finalize_generation(
            path, candidate, now=START + timedelta(minutes=3)
        )

    _success(path, "p2", offset=3)
    candidate.write_text("value\np1-0\np2-0\n", encoding="utf-8")
    complete = scrape_generation.finalize_generation(
        path, candidate, now=START + timedelta(minutes=5)
    )

    assert complete["status"] == "complete"
    assert complete["completed_at"] == "2026-08-13T01:05:00Z"
    assert set(complete["output"]) == set(SCRAPE_GENERATION_ARTIFACT_FIELDS)
    assert complete["output"]["row_count"] == 2
    assert scrape_generation.load_generation(path) == complete
    assert [item.partition_id for item in scrape_generation.selected_artifacts(path)] == [
        "p1",
        "p2",
    ]

    candidate.write_text("value\nchanged\n", encoding="utf-8")
    with pytest.raises(ContractError, match="byte_count|sha256"):
        scrape_generation.load_generation(path)
    with pytest.raises(ContractError, match="byte_count|sha256"):
        scrape_generation.finalize_generation(path, candidate)


def test_attempt_history_is_append_only_and_complete_generation_is_immutable(
    tmp_path: Path,
) -> None:
    path, _manifest = _write_new(tmp_path, scope=_scope("p1"))
    _success(path, "p1", offset=1)
    manifest = scrape_generation.load_generation(path)
    rewritten = copy.deepcopy(manifest)
    rewritten["partitions"][0]["attempts"] = []
    rewritten["partitions"][0]["selected_attempt_id"] = None
    rewritten["summary"] = {
        "requested": 1,
        "selected": 0,
        "succeeded": 0,
        "confirmed_empty": 0,
        "failed": 0,
        "pending": 1,
    }
    rewritten["updated_at"] = "2026-08-13T01:03:00Z"
    with pytest.raises(ContractError, match="append-only"):
        scrape_generation.write_generation(path, rewritten)

    candidate = path.parent / "candidate.csv"
    candidate.write_text("value\np1-0\n", encoding="utf-8")
    complete = scrape_generation.finalize_generation(
        path, candidate, now=START + timedelta(minutes=3)
    )
    changed = copy.deepcopy(complete)
    changed["updated_at"] = "2026-08-13T01:04:00Z"
    changed["completed_at"] = "2026-08-13T01:04:00Z"
    with pytest.raises(ContractError, match="immutable"):
        scrape_generation.write_generation(path, changed)


@pytest.mark.parametrize("failure", ["fsync", "replace"])
def test_atomic_checkpoint_failure_preserves_prior_manifest_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    path, _manifest = _write_new(tmp_path, scope=_scope("p1"))
    artifact = _artifact(path, "p1")
    before = path.read_bytes()

    def injected_failure(*_args, **_kwargs):
        raise OSError(f"injected {failure} failure")

    monkeypatch.setattr(
        scrape_generation.os,
        "fsync" if failure == "fsync" else "replace",
        injected_failure,
    )
    with pytest.raises(OSError, match=failure):
        _success(path, "p1", offset=1, artifact=artifact)

    assert path.read_bytes() == before
    assert not list(path.parent.glob(f".{path.name}.*.tmp"))


def test_atomic_switch_fsyncs_file_then_parent_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, _manifest = _write_new(tmp_path, scope=_scope("p1"))
    artifact = _artifact(path, "p1")
    real_fsync = scrape_generation.os.fsync
    modes: list[str] = []

    def observing_fsync(descriptor: int) -> None:
        modes.append("directory" if stat.S_ISDIR(scrape_generation.os.fstat(descriptor).st_mode) else "file")
        real_fsync(descriptor)

    monkeypatch.setattr(scrape_generation.os, "fsync", observing_fsync)
    _success(path, "p1", offset=1, artifact=artifact)

    assert modes[-2:] == ["file", "directory"]


def test_manifest_writes_do_not_treat_legacy_csv_as_checkpoint_evidence(
    tmp_path: Path,
) -> None:
    legacy = tmp_path / "legacy.csv"
    legacy.write_text(
        "source_url,status,row_count\nhttps://example.test/project/p1,error,0\n",
        encoding="utf-8",
    )

    with pytest.raises(ContractError, match="invalid scrape-generation JSON"):
        scrape_generation.load_generation(legacy)


def test_attempt_and_artifact_nested_shapes_are_exact(tmp_path: Path) -> None:
    path, _manifest = _write_new(tmp_path, scope=_scope("p1"))
    manifest = _success(path, "p1", offset=1)
    attempt = manifest["partitions"][0]["attempts"][0]

    assert set(attempt) == set(SCRAPE_GENERATION_ATTEMPT_FIELDS)
    assert set(attempt["artifact"]) == set(SCRAPE_GENERATION_ARTIFACT_FIELDS)

    extra_attempt = copy.deepcopy(manifest)
    extra_attempt["partitions"][0]["attempts"][0]["pages"] = 1
    with pytest.raises(ContractError, match="unexpected schema"):
        SCRAPE_GENERATION.validate(extra_attempt)
