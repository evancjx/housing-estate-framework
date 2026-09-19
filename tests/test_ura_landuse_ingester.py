import io
import json
import os
from pathlib import Path
import urllib.error

import pytest

import pandas as pd

import ingest_ura_landuse


def _geojson_bytes(category="COMMERCIAL"):
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"LU_DESC": category},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[0, 0], [1, 0], [1, 1], [0, 0]]
                        ],
                    },
                }
            ],
        }
    ).encode()


def _cache_path(tmp_path):
    return tmp_path / f"{ingest_ura_landuse.DATASET_ID}.geojson"


def _stale(path: Path, monkeypatch, *, age_hours=2):
    os.utime(path, (0, 0))
    monkeypatch.setattr(
        ingest_ura_landuse.time, "time", lambda: age_hours * 3600
    )


def test_share_for_estate_computes_half_buffer_commercial_overlap():
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"LU_DESC": "COMMERCIAL"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [0.0, -0.05],
                            [0.05, -0.05],
                            [0.05, 0.05],
                            [0.0, 0.05],
                            [0.0, -0.05],
                        ]
                    ],
                },
            }
        ],
    }

    row = ingest_ura_landuse.rows_for_estates(
        pd.DataFrame({"estate": ["TEST"], "lat": [0.0], "lon": [0.0]}),
        geojson,
        buffer_km=2.0,
    )[0]

    assert row["estate"] == "TEST"
    assert row["commercial_share"] == pytest.approx(0.5, abs=1e-6)
    assert row["mixed_use_share"] == pytest.approx(0.5, abs=1e-6)
    assert row["white_share"] == 0.0
    assert row["business_park_share"] == 0.0
    assert row["buffer_km"] == 2.0


def test_empty_geojson_features_hard_fail():
    with pytest.raises(SystemExit) as exc:
        ingest_ura_landuse.rows_for_estates(
            pd.DataFrame({"estate": ["TEST"], "lat": [0.0], "lon": [0.0]}),
            {"type": "FeatureCollection", "features": []},
        )

    assert "URA land-use GeoJSON has zero features" in str(exc.value)


def test_http_helpers_delegate_to_shared_adapter(monkeypatch):
    calls = []

    def fake_json(url, **kwargs):
        calls.append(("json", url, kwargs))
        return {"status": "ok"}

    def fake_bytes(url, **kwargs):
        calls.append(("bytes", url, kwargs))
        return b"payload"

    monkeypatch.setattr(ingest_ura_landuse, "get_json", fake_json)
    monkeypatch.setattr(ingest_ura_landuse, "get_bytes", fake_bytes)

    assert ingest_ura_landuse._http_json("https://example.test/meta", 13) == {
        "status": "ok"
    }
    assert ingest_ura_landuse._http_bytes("https://example.test/file", 71) == b"payload"
    assert calls == [
        (
            "json",
            "https://example.test/meta",
            {
                "timeout": 13,
                "headers": {
                    "User-Agent": ingest_ura_landuse._UA,
                    "Accept": "application/json",
                },
            },
        ),
        (
            "bytes",
            "https://example.test/file",
            {
                "timeout": 71,
                "headers": {"User-Agent": ingest_ura_landuse._UA},
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
        return {"data": {"url": "https://example.test/landuse"}}

    monkeypatch.setattr(ingest_ura_landuse, "_http_json", fake_json)
    monkeypatch.setattr(
        ingest_ura_landuse, "_http_bytes", lambda url, timeout: _geojson_bytes()
    )
    monkeypatch.setattr(ingest_ura_landuse.time, "sleep", delays.append)

    payload = ingest_ura_landuse.poll_download_geojson()

    assert payload["features"]
    assert polls == 2
    assert delays == [5]


def test_fresh_valid_cache_avoids_download(tmp_path, monkeypatch):
    cache = _cache_path(tmp_path)
    cache.write_bytes(_geojson_bytes())
    monkeypatch.setattr(
        ingest_ura_landuse,
        "_http_json",
        lambda *_args, **_kwargs: pytest.fail("fresh cache must avoid network"),
    )

    payload = ingest_ura_landuse.poll_download_geojson(str(tmp_path))

    assert payload["features"]
    assert ingest_ura_landuse._LAST_CACHE_STATE == "cached"


def test_stale_online_cache_refreshes_atomically(tmp_path, monkeypatch, capsys):
    cache = _cache_path(tmp_path)
    old = _geojson_bytes()
    new = _geojson_bytes("WHITE")
    cache.write_bytes(old)
    _stale(cache, monkeypatch)
    monkeypatch.setattr(
        ingest_ura_landuse,
        "_http_json",
        lambda url, timeout: {"data": {"url": "https://example.test/landuse"}},
    )
    monkeypatch.setattr(
        ingest_ura_landuse, "_http_bytes", lambda url, timeout: new
    )

    payload = ingest_ura_landuse.poll_download_geojson(
        str(tmp_path), max_cache_age_hours=1
    )

    assert payload["features"][0]["properties"]["LU_DESC"] == "WHITE"
    assert cache.read_bytes() == new
    assert ingest_ura_landuse._LAST_CACHE_STATE == "fresh"
    stderr = capsys.readouterr().err
    assert "cache" in stderr and "stale" in stderr
    assert not list(tmp_path.glob(".*.tmp"))


def test_offline_stale_cache_warns_and_performs_zero_network(
    tmp_path, monkeypatch, capsys
):
    cache = _cache_path(tmp_path)
    cache.write_bytes(_geojson_bytes())
    _stale(cache, monkeypatch)

    def unexpected_network(*_args, **_kwargs):
        raise AssertionError("offline mode must not use network")

    monkeypatch.setattr(ingest_ura_landuse, "_http_json", unexpected_network)
    monkeypatch.setattr(ingest_ura_landuse, "_http_bytes", unexpected_network)

    payload = ingest_ura_landuse.poll_download_geojson(
        str(tmp_path), max_cache_age_hours=1, offline=True
    )

    assert payload["features"]
    assert ingest_ura_landuse._LAST_CACHE_STATE == "offline_stale"
    assert "using it because --offline was requested" in capsys.readouterr().err


@pytest.mark.parametrize("cache_bytes", [None, b"not-json"])
def test_offline_missing_or_invalid_cache_fails_without_network(
    tmp_path, monkeypatch, cache_bytes
):
    if cache_bytes is not None:
        _cache_path(tmp_path).write_bytes(cache_bytes)

    def unexpected_network(*_args, **_kwargs):
        raise AssertionError("offline mode must not use network")

    monkeypatch.setattr(ingest_ura_landuse, "_http_json", unexpected_network)
    monkeypatch.setattr(ingest_ura_landuse, "_http_bytes", unexpected_network)

    with pytest.raises(SystemExit, match="offline URA land-use cache.*(missing|invalid)"):
        ingest_ura_landuse.poll_download_geojson(str(tmp_path), offline=True)


def test_invalid_refresh_preserves_previous_cache(tmp_path, monkeypatch):
    cache = _cache_path(tmp_path)
    old = _geojson_bytes()
    cache.write_bytes(old)
    _stale(cache, monkeypatch)
    monkeypatch.setattr(
        ingest_ura_landuse,
        "_http_json",
        lambda url, timeout: {"data": {"url": "https://example.test/landuse"}},
    )
    monkeypatch.setattr(
        ingest_ura_landuse, "_http_bytes", lambda url, timeout: b"invalid"
    )

    with pytest.raises(SystemExit, match="downloaded URA land-use payload is invalid"):
        ingest_ura_landuse.poll_download_geojson(
            str(tmp_path), max_cache_age_hours=1
        )

    assert cache.read_bytes() == old


@pytest.mark.parametrize("failure_point", ["write", "replace"])
def test_cache_publish_failure_preserves_previous_bytes(
    tmp_path, monkeypatch, failure_point
):
    cache = _cache_path(tmp_path)
    old = _geojson_bytes()
    new = _geojson_bytes("WHITE")
    cache.write_bytes(old)
    _stale(cache, monkeypatch)
    monkeypatch.setattr(
        ingest_ura_landuse,
        "_http_json",
        lambda url, timeout: {"data": {"url": "https://example.test/landuse"}},
    )
    monkeypatch.setattr(
        ingest_ura_landuse, "_http_bytes", lambda url, timeout: new
    )

    def injected_failure(*_args, **_kwargs):
        raise OSError(f"injected {failure_point} failure")

    if failure_point == "write":
        monkeypatch.setattr(
            ingest_ura_landuse, "_write_staged_cache", injected_failure
        )
    else:
        monkeypatch.setattr(ingest_ura_landuse.os, "replace", injected_failure)

    with pytest.raises(OSError, match=f"injected {failure_point} failure"):
        ingest_ura_landuse.poll_download_geojson(
            str(tmp_path), max_cache_age_hours=1
        )

    assert cache.read_bytes() == old
    assert not list(tmp_path.glob(".*.tmp"))


def test_invalid_max_cache_age_fails_before_network(monkeypatch):
    monkeypatch.setattr(
        ingest_ura_landuse,
        "_http_json",
        lambda *_args, **_kwargs: pytest.fail("invalid policy must fail first"),
    )
    with pytest.raises(ValueError, match="max cache age"):
        ingest_ura_landuse.poll_download_geojson(max_cache_age_hours=0)
