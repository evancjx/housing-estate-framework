import sys

import pandas as pd

import ingest_tree_canopy


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
