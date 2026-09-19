"""Transactional cache tests for private-project OneMap geocoding."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.parse

import pytest

import geocode_private_projects as geocoder


def _row(
    project: str,
    *,
    street: str | None = None,
    district: str = "10",
    planning_area: str = "BUKIT TIMAH",
    status: str = "matched",
    lat: str = "1.3001",
    lon: str = "103.8001",
    score: int = 105,
) -> dict[str, object]:
    coordinates = status in geocoder.COORDINATE_MATCH_STATUSES
    return {
        "project_name": project,
        "street_name": street or f"{project} ROAD",
        "postal_district": district,
        "planning_area": planning_area,
        "lat": lat if coordinates else "",
        "lon": lon if coordinates else "",
        "match_status": status,
        "match_score": score,
        "query_used": f"{project} {street or f'{project} ROAD'}" if coordinates else "",
        "onemap_building": project if coordinates else "",
        "onemap_road": street or f"{project} ROAD" if coordinates else "",
        "onemap_address": f"1 {street or f'{project} ROAD'}" if coordinates else "",
        "onemap_postal": "238800" if coordinates else "",
        "review_note": "project,street" if coordinates else "OneMap returned no candidates",
    }


def _write_legacy(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=geocoder.LEGACY_OUT_COLUMNS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_private_input(path: Path, projects: list[dict[str, str]]) -> None:
    fieldnames = [
        "project_name",
        "street_name",
        "postal_district",
        "planning_area",
        "property_type",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for project in projects:
            writer.writerow({**project, "property_type": "Condominium"})


def _args(private: Path, out: Path, **overrides) -> argparse.Namespace:
    values = {
        "token": "test-token",
        "private": str(private),
        "out": str(out),
        "resume": True,
        "limit": None,
        "max_pages": 1,
        "max_cache_age_days": 30,
        "offline": False,
        "retry_transient": False,
        "sleep": 0,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _project(
    project: str,
    *,
    street: str | None = None,
    district: str = "10",
    planning_area: str = "BUKIT TIMAH",
) -> dict[str, str]:
    return {
        "project_name": project,
        "street_name": street or f"{project} ROAD",
        "postal_district": district,
        "planning_area": planning_area,
    }


def _match(
    project: str,
    *,
    street: str | None = None,
    response_sha256: str = "a" * 64,
    **updates: object,
) -> dict[str, object]:
    match = {
        key: value
        for key, value in _row(project, street=street).items()
        if key not in {
            "project_name",
            "street_name",
            "postal_district",
            "planning_area",
        }
    }
    match.update(updates)
    match["_response_sha256"] = response_sha256
    match["_retry_state"] = "complete"
    match["_last_error"] = ""
    return match


def _current_row(
    project: str,
    *,
    retrieved_at: datetime,
    street: str | None = None,
    prior: dict[str, str] | None = None,
    **updates: object,
) -> dict[str, str]:
    return geocoder.compose_attempt_row(
        _project(project, street=street),
        _match(project, street=street, **updates),
        prior=prior,
        retrieved_at=retrieved_at,
    )


def _approve(row: dict[str, str]) -> dict[str, str]:
    return geocoder.normalize_cache_row(
        {
            **row,
            "review_status": "approved",
            "reviewed_at": "2026-01-01T00:00:00Z",
            "reviewed_match_sha256": row["match_sha256"],
            "review_decision_note": "fixture approval",
        }
    )


def _candidate(
    project: str = "ALPHA",
    street: str = "ALPHA ROAD",
    *,
    lat: str = "1.3001",
    lon: str = "103.8001",
) -> dict[str, str]:
    return {
        "SEARCHVAL": project,
        "BUILDING": project,
        "ROAD_NAME": street,
        "ADDRESS": f"1 {street}",
        "POSTAL": "238800",
        "LATITUDE": lat,
        "LONGITUDE": lon,
    }


def test_load_existing_migrates_exact_legacy_header_without_losing_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "locations.csv"
    matched = _row("MATCHED PROJECT")
    low = _row("LOW PROJECT", status="low_confidence", score=35)
    _write_legacy(path, [matched, low])

    loaded = geocoder.load_existing(path)

    assert len(loaded) == 2
    matched_loaded = loaded[geocoder.key_for(matched)]
    assert list(matched_loaded) == geocoder.OUT_COLUMNS
    assert matched_loaded["review_status"] == "approved_legacy"
    assert matched_loaded["retry_state"] == "legacy"
    assert matched_loaded["retrieved_at"] == ""
    assert matched_loaded["review_note"] == "project,street"
    low_loaded = loaded[geocoder.key_for(low)]
    assert low_loaded["review_status"] == "pending_low_confidence"


@pytest.mark.parametrize(
    "header",
    [
        geocoder.LEGACY_OUT_COLUMNS[:-1],
        [*reversed(geocoder.LEGACY_OUT_COLUMNS)],
        [*geocoder.LEGACY_OUT_COLUMNS, "unexpected"],
    ],
)
def test_load_existing_rejects_missing_reordered_or_extra_headers(
    tmp_path: Path,
    header: list[str],
) -> None:
    path = tmp_path / "locations.csv"
    path.write_text(",".join(header) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid geocode cache header"):
        geocoder.load_existing(path)


def test_load_existing_rejects_duplicate_identity_instead_of_last_wins(
    tmp_path: Path,
) -> None:
    path = tmp_path / "locations.csv"
    row = _row("DUPLICATE PROJECT")
    _write_legacy(path, [row, {**row, "lat": "1.399"}])

    with pytest.raises(ValueError, match="duplicate geocode cache identity"):
        geocoder.load_existing(path)


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"project_name": ""}, "identity fields must be non-empty"),
        ({"postal_district": "north"}, "zero-padded two-digit"),
        ({"match_status": "accepted"}, "unsupported match_status"),
        ({"lat": "91"}, "valid coordinate range"),
        ({"lon": ""}, "both be present"),
        ({"lat": "", "lon": ""}, "require coordinates"),
    ],
)
def test_cache_row_validation_fails_closed(
    updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        geocoder.normalize_cache_row({**_row("INVALID PROJECT"), **updates})


def test_atomic_write_serialization_failure_preserves_previous_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "locations.csv"
    original = [_row("ALPHA"), _row("BETA")]
    geocoder.write_rows(path, original)
    previous = path.read_bytes()

    def fail_serialization(_handle, _rows) -> None:
        raise RuntimeError("injected serialization crash")

    with pytest.raises(RuntimeError, match="serialization crash"):
        geocoder.write_rows(
            path,
            [*original, _row("GAMMA")],
            serializer=fail_serialization,
        )

    assert path.read_bytes() == previous
    assert set(geocoder.load_existing(path)) == {
        geocoder.key_for(row) for row in original
    }
    assert list(tmp_path.glob(".locations.csv.*.tmp")) == []


def test_atomic_write_rejects_malformed_staging_before_replace(
    tmp_path: Path,
) -> None:
    path = tmp_path / "locations.csv"
    geocoder.write_rows(path, [_row("ALPHA"), _row("BETA")])
    previous = path.read_bytes()

    def malformed(handle, _rows) -> None:
        handle.write("wrong,header\n")

    with pytest.raises(ValueError, match="invalid geocode cache header"):
        geocoder.write_rows(path, [_row("CHANGED")], serializer=malformed)

    assert path.read_bytes() == previous


def test_atomic_write_replace_failure_preserves_previous_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "locations.csv"
    original = [_row("ALPHA"), _row("BETA")]
    geocoder.write_rows(path, original)
    previous = path.read_bytes()

    def fail_replace(_source, _destination) -> None:
        raise OSError("injected replace crash")

    with pytest.raises(OSError, match="replace crash"):
        geocoder.write_rows(
            path,
            [*original, _row("GAMMA")],
            replace=fail_replace,
        )

    assert path.read_bytes() == previous
    assert set(geocoder.load_existing(path)) == {
        geocoder.key_for(row) for row in original
    }
    assert list(tmp_path.glob(".locations.csv.*.tmp")) == []


def test_checkpoint_after_first_query_contains_all_existing_and_orphan_rows(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private.csv"
    output = tmp_path / "locations.csv"
    source_projects = [
        {
            "project_name": name,
            "street_name": f"{name} ROAD",
            "postal_district": "10",
            "planning_area": "BUKIT TIMAH",
        }
        for name in ("ALPHA", "BETA", "GAMMA")
    ]
    _write_private_input(private, source_projects)
    existing = [_row(name) for name in ("ALPHA", "BETA", "GAMMA", "ORPHAN")]
    _write_legacy(output, existing)
    expected_keys = {geocoder.key_for(row) for row in existing}
    checkpoints = 0

    def matcher(project, street, _token, _max_pages):
        match = {
            key: value
            for key, value in _row(project, street=street).items()
            if key not in {
                "project_name",
                "street_name",
                "postal_district",
                "planning_area",
            }
        }
        match.update({"lat": "1.3333", "lon": "103.8333"})
        return match

    def checkpoint_then_crash(path, rows) -> None:
        nonlocal checkpoints
        checkpoints += 1
        geocoder.write_rows(path, rows)
        assert set(geocoder.load_existing(path)) == expected_keys
        raise RuntimeError("injected process crash")

    with pytest.raises(RuntimeError, match="process crash"):
        geocoder.run(
            _args(private, output, resume=False, limit=1),
            matcher=matcher,
            checkpoint_writer=checkpoint_then_crash,
        )

    assert checkpoints == 1
    after_crash = geocoder.load_existing(output)
    assert set(after_crash) == expected_keys
    assert after_crash[geocoder.key_for(existing[0])]["lat"] == "1.3333"


def test_limit_and_resume_preserve_unvisited_and_orphan_rows(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private.csv"
    output = tmp_path / "locations.csv"
    source_projects = [
        {
            "project_name": name,
            "street_name": f"{name} ROAD",
            "postal_district": "10",
            "planning_area": "BUKIT TIMAH",
        }
        for name in ("ALPHA", "BETA", "GAMMA")
    ]
    _write_private_input(private, source_projects)
    alpha_error = _row("ALPHA", status="error", score=0)
    existing = [alpha_error, _row("BETA"), _row("GAMMA"), _row("ORPHAN")]
    _write_legacy(output, existing)

    calls: list[str] = []

    def matcher(project, street, _token, _max_pages):
        calls.append(project)
        row = _row(project, street=street)
        return {
            key: value
            for key, value in row.items()
            if key not in {
                "project_name",
                "street_name",
                "postal_district",
                "planning_area",
            }
        }

    geocoder.run(
        _args(private, output, resume=True, limit=1),
        matcher=matcher,
    )

    loaded = geocoder.load_existing(output)
    assert calls == ["ALPHA"]
    assert len(loaded) == 4
    assert set(loaded) == {geocoder.key_for(row) for row in existing}
    assert loaded[geocoder.key_for(existing[0])]["match_status"] == "matched"
    assert loaded[geocoder.key_for(existing[-1])]["project_name"] == "ORPHAN"


def test_atomic_output_is_deterministic_regardless_of_input_order(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    rows = [
        _row("ZULU", district="20"),
        _row("BETA", district="10"),
        _row("ALPHA", district="10"),
    ]

    geocoder.write_rows(first, rows)
    geocoder.write_rows(second, list(reversed(rows)))

    assert first.read_bytes() == second.read_bytes()
    assert [row[0] for row in geocoder.load_existing(first)] == [
        "ALPHA",
        "BETA",
        "ZULU",
    ]


def test_onemap_search_uses_shared_byte_adapter_and_preserves_paging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies = [
        json.dumps(
            {"found": 2, "results": [_candidate()]}, separators=(",", ":")
        ).encode(),
        json.dumps(
            {
                "found": 2,
                "results": [_candidate("BETA", "BETA ROAD")],
            },
            separators=(",", ":"),
        ).encode(),
    ]
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_get_bytes(url: str, **kwargs: object) -> bytes:
        calls.append((url, kwargs))
        return bodies[len(calls) - 1]

    monkeypatch.setattr(geocoder, "get_bytes", fake_get_bytes)

    results = geocoder.onemap_search("ALPHA ALPHA ROAD", "secret-token", 2)

    assert len(results) == 2
    assert len(calls) == 2
    for page, (url, kwargs) in enumerate(calls, start=1):
        parsed = urllib.parse.urlsplit(url)
        assert parsed.scheme == "https"
        assert parsed.netloc == "www.onemap.gov.sg"
        assert urllib.parse.parse_qs(parsed.query) == {
            "searchVal": ["ALPHA ALPHA ROAD"],
            "returnGeom": ["Y"],
            "getAddrDetails": ["Y"],
            "pageNum": [str(page)],
        }
        assert kwargs == {
            "timeout": 20,
            "headers": {"Authorization": "secret-token"},
        }
        assert "secret-token" not in url
    assert results.response_trace == [
        {
            "query": "ALPHA ALPHA ROAD",
            "page": page,
            "body_sha256": hashlib.sha256(body).hexdigest(),
        }
        for page, body in enumerate(bodies, start=1)
    ]


def test_response_hash_tracks_raw_bytes_while_match_hash_tracks_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate()
    bodies = [
        json.dumps({"found": 1, "results": [candidate]}).encode(),
        json.dumps(
            {"results": [dict(reversed(list(candidate.items())))], "found": 1},
            separators=(",", ":"),
        ).encode(),
    ]
    fixed = datetime(2026, 8, 13, tzinfo=timezone.utc)
    rows: list[dict[str, str]] = []
    for body in bodies:
        monkeypatch.setattr(geocoder, "get_bytes", lambda *_args, **_kwargs: body)
        attempt = geocoder.best_match("ALPHA", "ALPHA ROAD", "secret-token", 1)
        rows.append(
            geocoder.compose_attempt_row(
                _project("ALPHA"),
                attempt,
                prior=None,
                retrieved_at=fixed,
            )
        )

    assert rows[0]["response_sha256"] != rows[1]["response_sha256"]
    assert rows[0]["match_sha256"] == rows[1]["match_sha256"]
    assert "secret-token" not in json.dumps(rows)


def test_malformed_response_is_permanent_and_retains_raw_response_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b"{not-json"
    monkeypatch.setattr(
        geocoder,
        "get_bytes",
        lambda *_args, **_kwargs: body,
    )

    attempt = geocoder.best_match("ALPHA", "ALPHA ROAD", "token", 1)
    row = geocoder.compose_attempt_row(
        _project("ALPHA"),
        attempt,
        prior=None,
        retrieved_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )
    trace = [
        {
            "query": "ALPHA ALPHA ROAD",
            "page": 1,
            "body_sha256": hashlib.sha256(body).hexdigest(),
        }
    ]

    assert attempt["_retry_state"] == "permanent_failure"
    assert row["retry_state"] == "permanent_failure"
    assert row["response_sha256"] == geocoder.canonical_json_sha256(trace)
    assert row["review_status"] == "pending_error"
    assert "invalid JSON" in row["last_error"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            urllib.error.HTTPError(
                "https://example.test", 429, "rate limited", None, None
            ),
            "transient_failure",
        ),
        (
            urllib.error.HTTPError(
                "https://example.test", 503, "unavailable", None, None
            ),
            "transient_failure",
        ),
        (TimeoutError("timed out"), "transient_failure"),
        (
            urllib.error.HTTPError(
                "https://example.test", 404, "not found", None, None
            ),
            "permanent_failure",
        ),
        (geocoder.OneMapSchemaError("bad schema"), "permanent_failure"),
        (RuntimeError("unexpected"), "permanent_failure"),
    ],
)
def test_acquisition_failure_classification_is_explicit(
    error: BaseException,
    expected: str,
) -> None:
    assert geocoder.classify_acquisition_error(error) == expected


def test_no_match_is_an_explicit_not_found_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries: list[str] = []

    def no_results(query: str, _token: str, _max_pages: int):
        queries.append(query)
        return geocoder.OneMapSearchResults(
            [],
            [
                {
                    "query": query,
                    "page": 1,
                    "body_sha256": "0" * 64,
                }
            ],
        )

    monkeypatch.setattr(geocoder, "onemap_search", no_results)
    attempt = geocoder.best_match("ALPHA", "ALPHA ROAD", "token", 1)
    row = geocoder.compose_attempt_row(
        _project("ALPHA"),
        attempt,
        prior=None,
        retrieved_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )

    assert attempt["_retry_state"] == "not_found"
    assert row["match_status"] == "no_match"
    assert row["retry_state"] == "not_found"
    assert row["review_status"] == "pending_error"
    assert row["response_sha256"]
    assert row["match_sha256"]
    assert queries == ["ALPHA ALPHA ROAD", "ALPHA", "ALPHA ROAD"]


def test_retrieval_time_is_timezone_aware_and_canonical_utc() -> None:
    singapore_time = datetime(
        2026,
        8,
        13,
        16,
        30,
        tzinfo=timezone(timedelta(hours=8)),
    )
    row = _current_row("ALPHA", retrieved_at=singapore_time)

    assert row["retrieved_at"] == "2026-08-13T08:30:00Z"
    with pytest.raises(ValueError, match="timezone-aware"):
        _current_row("ALPHA", retrieved_at=datetime(2026, 8, 13, 8, 30))


def test_cache_age_treats_boundary_as_fresh_and_unknown_or_future_as_stale() -> None:
    now = datetime(2026, 8, 31, tzinfo=timezone.utc)
    boundary = _current_row(
        "ALPHA",
        retrieved_at=now - timedelta(days=30),
    )
    expired = _current_row(
        "BETA",
        retrieved_at=now - timedelta(days=30, seconds=1),
    )
    future = _current_row("GAMMA", retrieved_at=now + timedelta(seconds=1))
    unknown_age = geocoder.normalize_cache_row(_row("LEGACY"), legacy=True)

    assert not geocoder.cache_row_is_stale(
        boundary, now=now, max_cache_age_days=30
    )
    assert geocoder.cache_row_is_stale(expired, now=now, max_cache_age_days=30)
    assert geocoder.cache_row_is_stale(future, now=now, max_cache_age_days=30)
    assert geocoder.cache_row_is_stale(
        unknown_age, now=now, max_cache_age_days=30
    )


def test_unchanged_match_preserves_approval_and_changed_match_becomes_pending() -> None:
    first_time = datetime(2026, 8, 1, tzinfo=timezone.utc)
    later = datetime(2026, 8, 13, tzinfo=timezone.utc)
    approved = _approve(_current_row("ALPHA", retrieved_at=first_time))

    unchanged = _current_row(
        "ALPHA",
        retrieved_at=later,
        prior=approved,
        response_sha256="b" * 64,
    )
    changed = _current_row(
        "ALPHA",
        retrieved_at=later,
        prior=approved,
        lat="1.3999",
        response_sha256="c" * 64,
    )

    assert unchanged["review_status"] == "approved"
    assert unchanged["reviewed_at"] == approved["reviewed_at"]
    assert unchanged["reviewed_match_sha256"] == approved["match_sha256"]
    assert unchanged["match_sha256"] == approved["match_sha256"]
    assert unchanged["response_sha256"] != approved["response_sha256"]
    assert changed["review_status"] == "pending_changed"
    assert changed["match_sha256"] != approved["match_sha256"]
    assert changed["reviewed_match_sha256"] == approved["match_sha256"]
    assert changed["review_decision_note"] == "fixture approval"


def test_unchanged_first_refresh_preserves_legacy_approval() -> None:
    legacy = geocoder.normalize_cache_row(_row("ALPHA"), legacy=True)

    refreshed = _current_row(
        "ALPHA",
        retrieved_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
        prior=legacy,
    )

    assert refreshed["review_status"] == "approved_legacy"
    assert refreshed["match_sha256"] == geocoder.canonical_match_sha256(legacy)


def test_transient_refresh_failure_preserves_prior_valid_evidence() -> None:
    approved = _approve(
        _current_row(
            "ALPHA",
            retrieved_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )
    )
    failure = {
        "lat": "",
        "lon": "",
        "match_status": "error",
        "match_score": 0,
        "query_used": "ALPHA ALPHA ROAD",
        "onemap_building": "",
        "onemap_road": "",
        "onemap_address": "",
        "onemap_postal": "",
        "review_note": "TimeoutError: timed out",
        "_response_sha256": "f" * 64,
        "_retry_state": "transient_failure",
        "_last_error": "TimeoutError: timed out",
    }

    retained = geocoder.compose_attempt_row(
        _project("ALPHA"),
        failure,
        prior=approved,
        retrieved_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )

    changing_fields = {"retry_state", "attempt_count", "last_error"}
    assert {
        key: value for key, value in retained.items() if key not in changing_fields
    } == {key: value for key, value in approved.items() if key not in changing_fields}
    assert retained["retry_state"] == "transient_failure"
    assert retained["attempt_count"] == str(int(approved["attempt_count"]) + 1)
    assert retained["last_error"] == "TimeoutError: timed out"


def test_cache_validation_rejects_changed_semantics_without_new_match_hash() -> None:
    row = _current_row(
        "ALPHA",
        retrieved_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="canonical row semantics"):
        geocoder.normalize_cache_row({**row, "lat": "1.3999"})


def test_offline_reports_all_cache_states_without_token_requests_or_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private = tmp_path / "private.csv"
    output = tmp_path / "locations.csv"
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    projects = [_project(name) for name in ("FRESH", "STALE", "PENDING", "ERROR", "MISSING")]
    _write_private_input(private, projects)
    fresh = _approve(_current_row("FRESH", retrieved_at=now - timedelta(days=1)))
    stale = geocoder.normalize_cache_row(_row("STALE"), legacy=True)
    pending = _current_row("PENDING", retrieved_at=now - timedelta(days=1))
    error = geocoder.compose_attempt_row(
        _project("ERROR"),
        {
            **_match("ERROR"),
            "lat": "",
            "lon": "",
            "match_status": "error",
            "match_score": 0,
            "review_note": "HTTP 404",
            "_retry_state": "permanent_failure",
            "_last_error": "HTTP 404",
        },
        prior=None,
        retrieved_at=now,
    )
    orphan = _approve(_current_row("ORPHAN", retrieved_at=now))
    geocoder.write_rows(output, [fresh, stale, pending, error, orphan])
    previous = output.read_bytes()
    monkeypatch.delenv("ONEMAP_TOKEN", raising=False)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("offline mode attempted acquisition or write")

    geocoder.run(
        _args(private, output, token=None, offline=True),
        matcher=forbidden,
        checkpoint_writer=forbidden,
        clock=lambda: now,
    )

    assert output.read_bytes() == previous
    assert capsys.readouterr().out == (
        "Offline geocode cache: total=5 fresh=1 stale=1 missing=1 "
        "pending=1 error=1 orphans=1\n"
    )


def test_retry_transient_targets_only_transient_rows_and_preserves_others(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private.csv"
    output = tmp_path / "locations.csv"
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    _write_private_input(private, [_project(name) for name in ("ALPHA", "BETA", "GAMMA")])
    alpha = _approve(_current_row("ALPHA", retrieved_at=now))
    alpha = geocoder.normalize_cache_row(
        {
            **alpha,
            "retry_state": "transient_failure",
            "last_error": "HTTP 503",
        }
    )
    beta = _approve(_current_row("BETA", retrieved_at=now))
    beta = geocoder.normalize_cache_row(
        {
            **beta,
            "retry_state": "permanent_failure",
            "last_error": "HTTP 404",
        }
    )
    gamma = _approve(_current_row("GAMMA", retrieved_at=now))
    orphan = _approve(_current_row("ORPHAN", retrieved_at=now))
    geocoder.write_rows(output, [alpha, beta, gamma, orphan])
    before = geocoder.load_existing(output)
    calls: list[str] = []

    def matcher(project: str, street: str, token: str, max_pages: int):
        calls.append(project)
        assert token == "test-token"
        assert max_pages == 1
        return _match(project, street=street, response_sha256="d" * 64)

    geocoder.run(
        _args(private, output, retry_transient=True),
        matcher=matcher,
        clock=lambda: now,
    )

    after = geocoder.load_existing(output)
    assert calls == ["ALPHA"]
    assert set(after) == set(before)
    assert after[geocoder.key_for(_project("ALPHA"))]["retry_state"] == "complete"
    for project in ("BETA", "GAMMA", "ORPHAN"):
        key = geocoder.key_for(_project(project))
        assert after[key] == before[key]


def test_resume_uses_max_cache_age_to_refresh_only_stale_successes(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private.csv"
    output = tmp_path / "locations.csv"
    now = datetime(2026, 8, 13, tzinfo=timezone.utc)
    _write_private_input(private, [_project("FRESH"), _project("STALE")])
    fresh = _approve(
        _current_row("FRESH", retrieved_at=now - timedelta(days=29))
    )
    stale = _approve(
        _current_row("STALE", retrieved_at=now - timedelta(days=31))
    )
    geocoder.write_rows(output, [fresh, stale])
    calls: list[str] = []

    def matcher(project: str, street: str, _token: str, _max_pages: int):
        calls.append(project)
        return _match(project, street=street, response_sha256="e" * 64)

    geocoder.run(
        _args(private, output, max_cache_age_days=30),
        matcher=matcher,
        clock=lambda: now,
    )

    loaded = geocoder.load_existing(output)
    assert calls == ["STALE"]
    assert loaded[geocoder.key_for(_project("FRESH"))] == fresh
    assert loaded[geocoder.key_for(_project("STALE"))]["retrieved_at"] == (
        "2026-08-13T00:00:00Z"
    )
