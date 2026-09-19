import sys

import pandas as pd

import ingest_hdb_density
from sg_estate import source_receipts


def test_http_json_uses_shared_resilient_helper(monkeypatch):
    sentinel_opener = object()
    calls = []

    def fake_get_json(url, **kwargs):
        calls.append((url, kwargs))
        return {"data": {"url": "https://example.test/hdb.csv"}}

    monkeypatch.setattr(ingest_hdb_density, "get_json", fake_get_json)
    monkeypatch.setattr(
        ingest_hdb_density.urllib.request,
        "urlopen",
        sentinel_opener,
    )

    result = ingest_hdb_density._http_json("https://example.test/poll", timeout=9)

    assert result["data"]["url"].endswith("hdb.csv")
    assert calls == [
        (
            "https://example.test/poll",
            {
                "timeout": 9,
                "headers": {
                    "User-Agent": ingest_hdb_density._UA,
                    "Accept": "application/json",
                },
                "opener": sentinel_opener,
            },
        )
    ]


def test_fetch_csv_uses_resilient_text_helper(monkeypatch):
    sentinel_opener = object()
    calls = []
    monkeypatch.setattr(
        ingest_hdb_density,
        "_http_json",
        lambda _url: {"data": {"url": "https://example.test/hdb.csv"}},
    )
    monkeypatch.setattr(
        ingest_hdb_density.urllib.request,
        "urlopen",
        sentinel_opener,
    )

    def fake_get_text(url, **kwargs):
        calls.append((url, kwargs))
        return "residential,bldg_contract_town\nY,AMK\n"

    monkeypatch.setattr(ingest_hdb_density, "get_text", fake_get_text)

    result = ingest_hdb_density.fetch_csv(cache_dir=None)

    assert result.startswith("residential")
    assert calls == [
        (
            "https://example.test/hdb.csv",
            {
                "timeout": 120,
                "headers": {"User-Agent": ingest_hdb_density._UA},
                "opener": sentinel_opener,
            },
        )
    ]


def test_main_writes_fresh_digest_bound_source_receipt(tmp_path, monkeypatch):
    estates = tmp_path / "estates.csv"
    out = tmp_path / "hdb_density.csv"
    pd.DataFrame(
        {"estate": ["ANG MO KIO"], "lat": [1.37], "lon": [103.85]}
    ).to_csv(estates, index=False)
    csv_text = (
        "residential,bldg_contract_town,total_dwelling_units,year_completed,max_floor_lvl\n"
        "Y,AMK,100,2001,12\n"
    )
    monkeypatch.setattr(ingest_hdb_density, "fetch_csv", lambda _cache_dir: csv_text)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_hdb_density.py",
            "--estates",
            str(estates),
            "--out",
            str(out),
        ],
    )

    ingest_hdb_density.main()

    receipt = source_receipts.read_source_receipt(
        source_receipts.receipt_path_for(out), output_path=out
    )
    assert receipt["dataset_id"] == "hdb_density.csv"
    assert receipt["cache_state"] == "fresh"
    assert receipt["fallback_state"] == "not_used"
    assert receipt["retrieved_at"] is not None
    assert receipt["coverage_start"] == "2001"
    assert receipt["coverage_end"] == "2001"
    assert receipt["row_count"] == 1


def test_main_does_not_invent_retrieval_time_for_legacy_cache(tmp_path, monkeypatch):
    estates = tmp_path / "estates.csv"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    out = tmp_path / "hdb_density.csv"
    pd.DataFrame(
        {"estate": ["ANG MO KIO"], "lat": [1.37], "lon": [103.85]}
    ).to_csv(estates, index=False)
    (cache_dir / f"{ingest_hdb_density.DATASET_ID}.csv").write_text(
        "residential,bldg_contract_town,total_dwelling_units,year_completed,max_floor_lvl\n"
        "Y,AMK,100,2001,12\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_hdb_density.py",
            "--estates",
            str(estates),
            "--out",
            str(out),
            "--cache-dir",
            str(cache_dir),
        ],
    )

    ingest_hdb_density.main()

    receipt = source_receipts.read_source_receipt(
        source_receipts.receipt_path_for(out), output_path=out
    )
    assert receipt["cache_state"] == "cached"
    assert receipt["retrieved_at"] is None
