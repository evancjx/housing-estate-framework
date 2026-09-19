import io
import json
import os
from pathlib import Path
import urllib.error

import pytest

import ingest_moh_hospitals


def _facility_payload(name="Singapore General Hospital"):
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "HCI_NAME": name,
                        "ADDRESS": "1 Hospital Road",
                    },
                    "geometry": None,
                }
            ],
        }
    ).encode()


def _stale(path: Path, monkeypatch, *, age_hours=2):
    os.utime(path, (0, 0))
    monkeypatch.setattr(
        ingest_moh_hospitals.time, "time", lambda: age_hours * 3600
    )


def test_ae_allowlist_flags_only_curated_24h_emergency_hospitals():
    assert ingest_moh_hospitals.has_ae_24h("Singapore General Hospital")
    assert ingest_moh_hospitals.has_ae_24h("KK Women's and Children's Hospital")
    assert not ingest_moh_hospitals.has_ae_24h("Alexandra Hospital")
    assert not ingest_moh_hospitals.has_ae_24h("Jurong Community Hospital")


def test_min_expected_acute_guard_hard_fails_below_threshold():
    rows = [
        {"name": f"Acute {i}", "tier": "acute", "lat": 1.3, "lon": 103.8}
        for i in range(7)
    ]

    with pytest.raises(SystemExit) as exc:
        ingest_moh_hospitals.require_min_acute(rows, "data/inputs/hospitals.csv")

    assert "only 7 acute public hospitals resolved/geocoded" in str(exc.value)
    assert "refusing to write data/inputs/hospitals.csv" in str(exc.value)


def test_http_helpers_delegate_to_shared_adapter(monkeypatch):
    calls = []

    def fake_json(url, **kwargs):
        calls.append(("json", url, kwargs))
        return {"status": "ok"}

    def fake_bytes(url, **kwargs):
        calls.append(("bytes", url, kwargs))
        return b"payload"

    monkeypatch.setattr(ingest_moh_hospitals, "get_json", fake_json)
    monkeypatch.setattr(ingest_moh_hospitals, "get_bytes", fake_bytes)

    assert ingest_moh_hospitals._http_json("https://example.test/meta", 13) == {
        "status": "ok"
    }
    assert ingest_moh_hospitals._http_bytes("https://example.test/file", 71) == b"payload"
    assert calls == [
        (
            "json",
            "https://example.test/meta",
            {
                "timeout": 13,
                "headers": {
                    "User-Agent": ingest_moh_hospitals._UA,
                    "Accept": "application/json",
                },
            },
        ),
        (
            "bytes",
            "https://example.test/file",
            {
                "timeout": 71,
                "headers": {"User-Agent": ingest_moh_hospitals._UA},
            },
        ),
    ]


def test_poll_download_keeps_source_specific_429_loop(monkeypatch):
    polls = 0
    delays = []

    def fake_json(url, timeout):
        nonlocal polls
        polls += 1
        if polls == 1:
            raise urllib.error.HTTPError(
                url, 429, "limited", {"Retry-After": "0"}, io.BytesIO()
            )
        return {"data": {"url": "https://example.test/facilities"}}

    monkeypatch.setattr(ingest_moh_hospitals, "_http_json", fake_json)
    monkeypatch.setattr(
        ingest_moh_hospitals,
        "_http_bytes",
        lambda url, timeout: _facility_payload(),
    )
    monkeypatch.setattr(ingest_moh_hospitals.time, "sleep", delays.append)

    assert ingest_moh_hospitals.poll_download("dataset", retries=2) == _facility_payload()
    assert polls == 2
    assert delays == [5]


def test_fresh_valid_cache_avoids_download(tmp_path, monkeypatch):
    cache = tmp_path / "dataset.raw"
    cache.write_bytes(_facility_payload())
    monkeypatch.setattr(
        ingest_moh_hospitals, "discover_collection_dataset_ids", lambda: ["dataset"]
    )
    monkeypatch.setattr(
        ingest_moh_hospitals,
        "poll_download",
        lambda *_args, **_kwargs: pytest.fail("fresh cache must avoid download"),
    )

    rows = ingest_moh_hospitals.fetch_health_facility_rows(str(tmp_path))

    assert [row["name"] for row in rows] == ["Singapore General Hospital"]
    assert ingest_moh_hospitals._LAST_CACHE_STATE == "cached"


def test_stale_online_cache_refreshes_atomically(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "dataset.raw"
    old = _facility_payload()
    new = _facility_payload("Changi General Hospital")
    cache.write_bytes(old)
    _stale(cache, monkeypatch)
    monkeypatch.setattr(
        ingest_moh_hospitals, "discover_collection_dataset_ids", lambda: ["dataset"]
    )
    monkeypatch.setattr(ingest_moh_hospitals, "poll_download", lambda _dataset: new)

    rows = ingest_moh_hospitals.fetch_health_facility_rows(
        str(tmp_path), max_cache_age_hours=1
    )

    assert [row["name"] for row in rows] == ["Changi General Hospital"]
    assert cache.read_bytes() == new
    assert ingest_moh_hospitals._LAST_CACHE_STATE == "fresh"
    assert "cache is stale" in capsys.readouterr().err
    assert not list(tmp_path.glob(".*.tmp"))


def test_offline_stale_cache_warns_and_performs_zero_network(
    tmp_path, monkeypatch, capsys
):
    cache = tmp_path / "dataset.raw"
    cache.write_bytes(_facility_payload())
    _stale(cache, monkeypatch)

    def unexpected_network(*_args, **_kwargs):
        raise AssertionError("offline mode must not discover or download")

    monkeypatch.setattr(
        ingest_moh_hospitals, "discover_collection_dataset_ids", unexpected_network
    )
    monkeypatch.setattr(ingest_moh_hospitals, "poll_download", unexpected_network)

    rows = ingest_moh_hospitals.fetch_health_facility_rows(
        str(tmp_path), max_cache_age_hours=1, offline=True
    )

    assert rows
    assert ingest_moh_hospitals._LAST_CACHE_STATE == "offline_stale"
    assert "using it because --offline was requested" in capsys.readouterr().err


@pytest.mark.parametrize("cache_bytes", [None, b"not-json-or-csv"])
def test_offline_missing_or_invalid_cache_fails_without_network(
    tmp_path, monkeypatch, cache_bytes
):
    if cache_bytes is not None:
        (tmp_path / "dataset.raw").write_bytes(cache_bytes)

    def unexpected_network(*_args, **_kwargs):
        raise AssertionError("offline mode must not use network")

    monkeypatch.setattr(
        ingest_moh_hospitals, "discover_collection_dataset_ids", unexpected_network
    )
    monkeypatch.setattr(ingest_moh_hospitals, "poll_download", unexpected_network)

    with pytest.raises(RuntimeError, match="offline MOH cache.*(missing|no valid)"):
        ingest_moh_hospitals.fetch_health_facility_rows(
            str(tmp_path), offline=True
        )


def test_invalid_refresh_preserves_previous_cache(tmp_path, monkeypatch):
    cache = tmp_path / "dataset.raw"
    old = _facility_payload()
    cache.write_bytes(old)
    _stale(cache, monkeypatch)
    monkeypatch.setattr(
        ingest_moh_hospitals, "discover_collection_dataset_ids", lambda: ["dataset"]
    )
    monkeypatch.setattr(
        ingest_moh_hospitals, "poll_download", lambda _dataset: b"invalid"
    )

    with pytest.raises(RuntimeError, match="no public hospital rows found"):
        ingest_moh_hospitals.fetch_health_facility_rows(
            str(tmp_path), max_cache_age_hours=1
        )

    assert cache.read_bytes() == old


@pytest.mark.parametrize("failure_point", ["write", "replace"])
def test_cache_publish_failure_preserves_previous_bytes(
    tmp_path, monkeypatch, failure_point
):
    cache = tmp_path / "dataset.raw"
    old = _facility_payload()
    new = _facility_payload("Changi General Hospital")
    cache.write_bytes(old)
    _stale(cache, monkeypatch)
    monkeypatch.setattr(
        ingest_moh_hospitals, "discover_collection_dataset_ids", lambda: ["dataset"]
    )
    monkeypatch.setattr(ingest_moh_hospitals, "poll_download", lambda _dataset: new)

    def injected_failure(*_args, **_kwargs):
        raise OSError(f"injected {failure_point} failure")

    if failure_point == "write":
        monkeypatch.setattr(
            ingest_moh_hospitals, "_write_staged_cache", injected_failure
        )
    else:
        monkeypatch.setattr(ingest_moh_hospitals.os, "replace", injected_failure)

    with pytest.raises(OSError, match=f"injected {failure_point} failure"):
        ingest_moh_hospitals.fetch_health_facility_rows(
            str(tmp_path), max_cache_age_hours=1
        )

    assert cache.read_bytes() == old
    assert not list(tmp_path.glob(".*.tmp"))


def test_invalid_max_cache_age_fails_before_discovery(monkeypatch):
    monkeypatch.setattr(
        ingest_moh_hospitals,
        "discover_collection_dataset_ids",
        lambda: pytest.fail("invalid policy must fail before network"),
    )
    with pytest.raises(ValueError, match="max cache age"):
        ingest_moh_hospitals.fetch_health_facility_rows(
            max_cache_age_hours=0
        )
