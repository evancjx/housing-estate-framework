from __future__ import annotations

from datetime import date, datetime, timezone
import json
from pathlib import Path

import pytest

from sg_estate.contracts import (
    ContractError,
    SOURCE_RECEIPT,
    SOURCE_RECEIPT_FIELDS,
    SOURCE_RECEIPT_SCHEMA_VERSION,
)
from sg_estate import source_receipts


def _output(tmp_path: Path, content: bytes = b"estate,score\nALPHA,4\n") -> Path:
    output = tmp_path / "staged" / "scores.csv"
    output.parent.mkdir()
    output.write_bytes(content)
    return output


def _receipt(output: Path, **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "dataset_id": "scores",
        "authority": "Example Authority",
        "source_url": "https://data.example.test/scores.csv",
        "source_urls": None,
        "source_identity": "example-dataset-v1",
        "retrieved_at": "2026-08-13T00:15:00+00:00",
        "coverage_start": "2026-01-01",
        "coverage_end": "2026-06-30",
        "row_count": 1,
        "cache_state": "fresh",
        "fallback_state": "not_used",
        "validation_status": "passed",
    }
    values.update(overrides)
    return source_receipts.build_source_receipt(output, **values)  # type: ignore[arg-type]


def test_contract_accepts_explicit_unknown_provenance_without_inventing_dates(
    tmp_path: Path,
) -> None:
    output = _output(tmp_path)

    receipt = _receipt(
        output,
        source_url=None,
        source_identity="committed:data/inputs/scores.csv",
        retrieved_at=None,
        coverage_start=None,
        coverage_end=None,
        row_count=None,
        cache_state="offline",
        validation_status="unknown",
    )

    assert tuple(receipt) == SOURCE_RECEIPT_FIELDS
    assert receipt["schema_version"] == SOURCE_RECEIPT_SCHEMA_VERSION
    assert receipt["retrieved_at"] is None
    assert receipt["coverage_start"] is None
    assert receipt["coverage_end"] is None
    assert receipt["row_count"] is None
    assert receipt["sha256"] == source_receipts.sha256_file(output)


def test_builder_accepts_typed_dates_and_timezone_aware_timestamp(tmp_path: Path) -> None:
    output = _output(tmp_path)

    receipt = _receipt(
        output,
        retrieved_at=datetime(2026, 8, 13, 8, 30, tzinfo=timezone.utc),
        coverage_start=date(2026, 1, 1),
        coverage_end=date(2026, 6, 30),
    )

    assert receipt["retrieved_at"] == "2026-08-13T08:30:00+00:00"
    assert receipt["coverage_start"] == "2026-01-01"
    assert receipt["coverage_end"] == "2026-06-30"


@pytest.mark.parametrize(
    ("coverage_start", "coverage_end"),
    [
        ("2024", "2026"),
        ("2026-01", "2026-06"),
        ("2026-01-15", "2026-06-30"),
        ("2026", "2026-12-31"),
        ("2026-12", "2026"),
    ],
)
def test_coverage_preserves_annual_monthly_or_daily_source_precision(
    tmp_path: Path,
    coverage_start: str,
    coverage_end: str,
) -> None:
    receipt = _receipt(
        _output(tmp_path),
        coverage_start=coverage_start,
        coverage_end=coverage_end,
    )

    assert receipt["coverage_start"] == coverage_start
    assert receipt["coverage_end"] == coverage_end


def test_acquisition_modes_are_distinct(
    tmp_path: Path,
) -> None:
    output = _output(tmp_path)
    receipts = {
        "fresh": _receipt(output, cache_state="fresh", fallback_state="not_used"),
        "cached": _receipt(output, cache_state="cached", fallback_state="not_used"),
        "mixed": _receipt(output, cache_state="mixed", fallback_state="not_used"),
        "fallback": _receipt(output, cache_state="cached", fallback_state="used"),
        "offline": _receipt(
            output,
            cache_state="offline",
            fallback_state="not_used",
            retrieved_at=None,
        ),
        "derived": _receipt(
            output,
            source_url=None,
            source_identity="derived:committed-inputs-v1",
            cache_state="derived",
            fallback_state="not_used",
            retrieved_at=None,
        ),
    }

    assert {
        name: source_receipts.receipt_acquisition_mode(receipt)
        for name, receipt in receipts.items()
    } == {name: name for name in receipts}


def test_composite_acquisition_keeps_primary_and_all_source_urls(tmp_path: Path) -> None:
    output = _output(tmp_path)
    urls = [
        "https://api.example.test/current",
        "https://archive.example.test/history.csv",
    ]

    receipt = _receipt(
        output,
        authority="Example API + Example Archive",
        source_url=urls[0],
        source_urls=urls,
        source_identity="composite:current+history-v1",
        cache_state="mixed",
    )

    assert receipt["source_url"] == urls[0]
    assert receipt["source_urls"] == urls
    assert source_receipts.receipt_acquisition_mode(receipt) == "mixed"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"schema_version": 1}, "schema_version"),
        ({"schema_version": 2.0}, "schema_version"),
        ({"dataset_id": ""}, "dataset_id"),
        ({"source_url": None, "source_identity": None}, "requires source_url"),
        ({"source_url": "file:///tmp/source.csv"}, "absolute HTTP"),
        (
            {"source_url": "https://user:secret@example.test/scores.csv"},
            "must not contain credentials",
        ),
        (
            {"source_url": "https://example.test/scores.csv?api_key=secret"},
            "credential-bearing query fields",
        ),
        (
            {"source_url": "https://example.test/scores.csv?api%5Fkey=secret"},
            "credential-bearing query fields",
        ),
        ({"source_urls": []}, "non-empty JSON array"),
        (
            {
                "source_urls": [
                    "https://archive.example.test/history.csv",
                    "https://data.example.test/scores.csv",
                ]
            },
            "must list source_url first",
        ),
        (
            {
                "source_urls": [
                    "https://data.example.test/scores.csv",
                    "file:///tmp/source.csv",
                ]
            },
            "absolute HTTP",
        ),
        ({"retrieved_at": "2026-08-13"}, "timestamp with timezone"),
        ({"retrieved_at": "2026-08-13T08:00:00"}, "timestamp with timezone"),
        ({"coverage_start": "2026-02-30"}, "ISO precision"),
        ({"coverage_start": "2026-Q1"}, "ISO precision"),
        (
            {"coverage_start": "2026-07-01", "coverage_end": "2026-06-30"},
            "must not be after",
        ),
        ({"row_count": -1}, "non-negative integer"),
        ({"row_count": True}, "non-negative integer"),
        ({"sha256": "ABC"}, "lowercase SHA-256"),
        ({"cache_state": "network"}, "cache_state"),
        ({"fallback_state": False}, "fallback_state"),
        ({"validation_status": "valid"}, "validation_status"),
    ],
)
def test_malformed_receipts_fail_contract(
    tmp_path: Path,
    change: dict[str, object],
    message: str,
) -> None:
    receipt = _receipt(_output(tmp_path))
    receipt.update(change)

    with pytest.raises(ContractError, match=message):
        SOURCE_RECEIPT.validate(receipt)


def test_missing_or_unexpected_fields_fail_contract(tmp_path: Path) -> None:
    receipt = _receipt(_output(tmp_path))
    del receipt["retrieved_at"]
    receipt["retrieval_date"] = None

    with pytest.raises(ContractError, match="missing required fields.*retrieved_at"):
        SOURCE_RECEIPT.validate(receipt)

    complete = _receipt(tmp_path / "staged" / "scores.csv")
    complete["extra"] = "not versioned"
    with pytest.raises(ContractError, match="unexpected fields.*extra"):
        SOURCE_RECEIPT.validate(complete)


def test_write_is_atomic_and_receipt_is_bound_to_output(tmp_path: Path) -> None:
    output = _output(tmp_path)
    receipt = _receipt(output)

    receipt_path = source_receipts.write_source_receipt(output, receipt)

    assert receipt_path == output.with_name("scores.csv.receipt.json")
    assert receipt_path.parent == output.parent
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == receipt
    assert source_receipts.read_source_receipt(
        receipt_path, output_path=output
    ) == receipt
    assert not list(output.parent.glob(".scores.csv.receipt.json.*.tmp"))


def test_digest_mismatch_fails_before_creating_sidecar(tmp_path: Path) -> None:
    output = _output(tmp_path)
    receipt = _receipt(output)
    output.write_bytes(b"different bytes\n")

    with pytest.raises(ContractError, match="sha256 does not match"):
        source_receipts.write_source_receipt(output, receipt)

    assert not source_receipts.receipt_path_for(output).exists()


def test_failed_atomic_replace_preserves_existing_receipt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = _output(tmp_path)
    destination = source_receipts.write_source_receipt(output, _receipt(output))
    original = destination.read_bytes()
    replacement = _receipt(output, cache_state="cached")

    def fail_replace(source: object, target: object) -> None:
        raise OSError("simulated receipt replacement failure")

    monkeypatch.setattr(source_receipts.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated receipt replacement failure"):
        source_receipts.write_source_receipt(output, replacement)

    assert destination.read_bytes() == original
    assert not list(output.parent.glob(".scores.csv.receipt.json.*.tmp"))


def test_read_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.receipt.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ContractError, match="invalid source receipt JSON"):
        source_receipts.read_source_receipt(path)
