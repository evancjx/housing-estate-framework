import pytest

import pandas as pd

import ingest_ura_landuse


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
