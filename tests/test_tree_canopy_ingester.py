import sys

import pandas as pd
import pytest

import ingest_tree_canopy
from sg_estate import source_receipts


def test_http_json_uses_shared_resilient_helper(monkeypatch):
    sentinel_opener = object()
    calls = []

    def fake_get_json(url, **kwargs):
        calls.append((url, kwargs))
        return {"metadata": {"stations": []}, "items": []}

    monkeypatch.setattr(ingest_tree_canopy, "get_json", fake_get_json)
    monkeypatch.setattr(
        ingest_tree_canopy.urllib.request,
        "urlopen",
        sentinel_opener,
    )

    result = ingest_tree_canopy._http_json("https://example.test/mss", timeout=11)

    assert result["items"] == []
    assert calls == [
        (
            "https://example.test/mss",
            {
                "timeout": 11,
                "headers": {
                    "User-Agent": ingest_tree_canopy._UA,
                    "Accept": "application/json",
                },
                "opener": sentinel_opener,
            },
        )
    ]


def test_tree_canopy_uses_mss_fallback_when_station_fetches_fail(tmp_path, monkeypatch):
    estates = tmp_path / "estates.csv"
    parks = tmp_path / "parks.csv"
    out = tmp_path / "tree_canopy.csv"

    pd.DataFrame({"estate": ["TEST"], "lat": [1.35], "lon": [103.8]}).to_csv(estates, index=False)
    pd.DataFrame({"name": ["TEST PARK"], "lat": [1.35], "lon": [103.8]}).to_csv(parks, index=False)
    pd.DataFrame(
        {
            "estate": ["TEST"],
            "ndvi_proxy": [0.1],
            "canopy_cover_pct": [10.0],
            "mss_station": ["S999"],
            "annual_mean_temp_c": [28.12],
            "uhi_delta_c": [0.45],
        }
    ).to_csv(out, index=False)

    monkeypatch.setattr(ingest_tree_canopy, "fetch_station_means", lambda cache_dir: {})
    monkeypatch.setattr(ingest_tree_canopy, "canopy_proxy", lambda lat, lon, parks_df: (0.42, 42.0))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_tree_canopy.py",
            "--estates", str(estates),
            "--parks", str(parks),
            "--out", str(out),
            "--mss-fallback", str(out),
        ],
    )

    ingest_tree_canopy.main()

    result = pd.read_csv(out)
    row = result.iloc[0]
    assert row["ndvi_proxy"] == 0.42
    assert row["canopy_cover_pct"] == 42.0
    assert row["mss_station"] == "S999"
    assert row["annual_mean_temp_c"] == 28.12
    assert row["uhi_delta_c"] == 0.45
    receipt = source_receipts.read_source_receipt(
        source_receipts.receipt_path_for(out), output_path=out
    )
    assert receipt["dataset_id"] == "tree_canopy.csv"
    assert receipt["fallback_state"] == "used"
    assert receipt["cache_state"] == "offline"
    assert receipt["retrieved_at"] is None
    assert receipt["coverage_start"] is None
    assert receipt["coverage_end"] is None
    assert receipt["row_count"] == 1
    assert receipt["source_identity"] == (
        "committed MSS fallback:tree_canopy.csv; parks input:parks.csv"
    )
    assert str(tmp_path) not in str(receipt)


@pytest.mark.parametrize(
    ("sample_modes", "expected_state", "has_retrieval"),
    [
        (["fresh", "fresh"], "fresh", True),
        (["cached", "cached"], "cached", False),
        (["cached", "fresh"], "mixed", True),
    ],
)
def test_main_records_successful_mss_acquisition_modes(
    tmp_path,
    monkeypatch,
    sample_modes,
    expected_state,
    has_retrieval,
):
    estates = tmp_path / "estates.csv"
    parks = tmp_path / "parks.csv"
    out = tmp_path / "tree_canopy.csv"
    pd.DataFrame({"estate": ["TEST"], "lat": [1.35], "lon": [103.8]}).to_csv(
        estates, index=False
    )
    pd.DataFrame({"name": ["TEST PARK"], "lat": [1.35], "lon": [103.8]}).to_csv(
        parks, index=False
    )

    def fake_fetch(_cache_dir):
        ingest_tree_canopy._LAST_SUCCESSFUL_SAMPLE_DATES = [
            "2026-06-15",
            "2026-07-15",
        ]
        ingest_tree_canopy._LAST_SUCCESSFUL_SAMPLE_MODES = sample_modes
        return {"S24": (1.36, 103.9, "Changi", 27.5)}

    monkeypatch.setattr(ingest_tree_canopy, "fetch_station_means", fake_fetch)
    monkeypatch.setattr(
        ingest_tree_canopy,
        "canopy_proxy",
        lambda lat, lon, parks_df: (0.42, 42.0),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest_tree_canopy.py",
            "--estates",
            str(estates),
            "--parks",
            str(parks),
            "--out",
            str(out),
        ],
    )

    ingest_tree_canopy.main()

    receipt = source_receipts.read_source_receipt(
        source_receipts.receipt_path_for(out), output_path=out
    )
    assert receipt["cache_state"] == expected_state
    assert (receipt["retrieved_at"] is not None) is has_retrieval
    assert receipt["coverage_start"] == "2026-06-15"
    assert receipt["coverage_end"] == "2026-07-15"
    assert receipt["source_urls"] == [
        ingest_tree_canopy.MSS_URL.format(d="2026-06-15"),
        ingest_tree_canopy.MSS_URL.format(d="2026-07-15"),
    ]
