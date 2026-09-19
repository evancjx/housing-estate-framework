"""Review-gate tests for private-project coordinate consumers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import gen_district_pair_comparison_html as district_pair
from sg_estate.project_locations import (
    CURRENT_LOCATION_COLUMNS,
    LEGACY_LOCATION_COLUMNS,
    canonical_project_location_match_sha256,
    load_usable_project_locations,
    ProjectLocationContractError,
    usable_project_locations,
)


ROOT = Path(__file__).resolve().parents[1]
COMMITTED_LOCATIONS = ROOT / "data/outputs/private_project_locations.csv"


def _current_row(
    project: str,
    *,
    match_status: str = "matched",
    review_status: str = "approved_legacy",
    match_sha256: str = "a" * 64,
    reviewed_match_sha256: str = "a" * 64,
    reviewed_at: str = "2026-08-13T00:00:00Z",
) -> dict[str, object]:
    row: dict[str, object] = {
        "project_name": project,
        "street_name": f"{project} ROAD",
        "postal_district": "10",
        "planning_area": "BUKIT TIMAH",
        "lat": 1.3,
        "lon": 103.8,
        "match_status": match_status,
        "match_score": 105,
        "query_used": project,
        "onemap_building": project,
        "onemap_road": f"{project} ROAD",
        "onemap_address": f"1 {project} ROAD",
        "onemap_postal": "238800",
        "review_note": "project,street",
        "retrieved_at": "2026-08-13T00:00:00Z",
        "response_sha256": "b" * 64,
        "match_sha256": match_sha256,
        "retry_state": "complete",
        "attempt_count": 1,
        "last_error": "",
        "review_status": review_status,
        "reviewed_at": reviewed_at,
        "reviewed_match_sha256": reviewed_match_sha256,
        "review_decision_note": "fixture",
    }
    if match_sha256 == "canonical":
        row["match_sha256"] = canonical_project_location_match_sha256(row)
        row["reviewed_match_sha256"] = row["match_sha256"]
    return {column: row[column] for column in CURRENT_LOCATION_COLUMNS}


def test_committed_legacy_cache_accepts_2223_and_withholds_174() -> None:
    raw = pd.read_csv(COMMITTED_LOCATIONS)
    usable = load_usable_project_locations(COMMITTED_LOCATIONS)

    assert tuple(raw.columns) == LEGACY_LOCATION_COLUMNS
    assert len(raw) == 2_397
    assert len(usable) == 2_223
    assert len(raw) - len(usable) == 174
    assert set(usable["match_status"]) == {"matched"}
    assert set(usable["review_status"]) == {"approved_legacy"}


def test_current_approval_requires_timestamp_and_exact_match_hash_binding() -> None:
    frame = pd.DataFrame(
        [
            _current_row("BOUND", review_status="approved", match_sha256="canonical"),
            _current_row(
                "MISMATCH",
                review_status="approved",
                reviewed_match_sha256="c" * 64,
            ),
            _current_row(
                "NO REVIEW TIME",
                review_status="approved",
                reviewed_at="",
            ),
            _current_row(
                "NAIVE REVIEW TIME",
                review_status="approved",
                reviewed_at="2026-08-13T00:00:00",
            ),
            _current_row(
                "INVALID HASH",
                review_status="approved",
                match_sha256="not-a-hash",
                reviewed_match_sha256="not-a-hash",
            ),
            _current_row(
                "LEGACY APPROVAL",
                review_status="approved_legacy",
                match_sha256="canonical",
            ),
        ]
    )

    with pytest.raises(ProjectLocationContractError, match="invalid review/hash binding"):
        usable_project_locations(frame)

    usable = usable_project_locations(
        frame[frame["project_name"].isin(["BOUND", "LEGACY APPROVAL"])].copy()
    )
    assert list(usable["project_name"]) == ["BOUND", "LEGACY APPROVAL"]


def test_pending_changed_and_weak_match_states_never_expose_coordinates() -> None:
    rows = [
        _current_row("PENDING", review_status="pending_changed"),
        _current_row(
            "LOW", match_status="low_confidence", review_status="pending_low_confidence"
        ),
        _current_row(
            "REVIEW", match_status="needs_review", review_status="pending_low_confidence"
        ),
        _current_row("ERROR", match_status="error", review_status="pending_error"),
        _current_row("NO MATCH", match_status="no_match", review_status="pending_error"),
        {
            **_current_row("BAD COORDINATE", review_status="pending_changed"),
            "lat": "not-a-number",
        },
    ]
    frame = pd.DataFrame(rows, columns=CURRENT_LOCATION_COLUMNS)

    assert usable_project_locations(frame).empty


def test_nonlegacy_matched_rows_without_review_metadata_are_withheld() -> None:
    frame = pd.DataFrame(
        [
            {
                "project_name": "UNBOUND",
                "lat": 1.3,
                "lon": 103.8,
                "match_status": "matched",
            }
        ]
    )

    assert usable_project_locations(frame).empty


def test_current_approval_recomputes_digest_before_exposing_coordinates() -> None:
    row = _current_row("BOUND", review_status="approved", match_sha256="canonical")
    tampered = {**row, "lat": 1.3999}

    assert list(usable_project_locations(pd.DataFrame([row]))["project_name"]) == [
        "BOUND"
    ]
    with pytest.raises(ProjectLocationContractError, match="invalid review/hash binding"):
        usable_project_locations(pd.DataFrame([tampered]))


def test_approved_legacy_is_not_a_bypass_for_noncanonical_current_rows() -> None:
    minimal = pd.DataFrame(
        [
            {
                "project_name": "MINIMAL",
                "lat": 1.3,
                "lon": 103.8,
                "match_status": "matched",
                "review_status": "approved_legacy",
            }
        ]
    )
    invalid_current = pd.DataFrame(
        [_current_row("INVALID", review_status="approved_legacy")]
    )
    valid_current = pd.DataFrame(
        [
            _current_row(
                "VALID",
                review_status="approved_legacy",
                match_sha256="canonical",
            )
        ]
    )

    with pytest.raises(ProjectLocationContractError, match="column contract"):
        usable_project_locations(minimal)
    with pytest.raises(ProjectLocationContractError, match="invalid review/hash binding"):
        usable_project_locations(invalid_current)
    assert list(usable_project_locations(valid_current)["project_name"]) == ["VALID"]


def test_checkpoint_migrated_legacy_state_preserves_legacy_approval() -> None:
    row = _current_row(
        "MIGRATED",
        review_status="approved_legacy",
        match_sha256="",
        reviewed_match_sha256="",
        reviewed_at="",
    )
    row.update(
        {
            "retrieved_at": "",
            "response_sha256": "",
            "retry_state": "legacy",
            "attempt_count": 0,
            "last_error": "",
        }
    )

    usable = usable_project_locations(pd.DataFrame([row]))

    assert list(usable["project_name"]) == ["MIGRATED"]


def test_duplicate_full_identities_are_rejected() -> None:
    row = _current_row("DUPLICATE", review_status="pending_changed")

    with pytest.raises(ProjectLocationContractError, match="duplicate full identities"):
        usable_project_locations(pd.DataFrame([row, row]))


def test_district_reader_withholds_ambiguous_same_name_coordinates() -> None:
    locations = pd.DataFrame(
        [
            {"project_name": "DUPLICATE", "lat": 1.30, "lon": 103.80},
            {"project_name": "DUPLICATE", "lat": 1.31, "lon": 103.81},
        ]
    )
    mrt = pd.DataFrame(
        [
            {
                "name": "TEST MRT",
                "line": "Test Line",
                "lat": 1.30,
                "lon": 103.80,
                "operational": 1,
            }
        ]
    )

    assert district_pair.nearest_station_by_project(
        ["DUPLICATE"], locations, mrt
    ) == {}
