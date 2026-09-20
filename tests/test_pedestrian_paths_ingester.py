"""Contract for the walking and cycling layers.

What each field can honestly carry, established 2026-09-20:

- `pcn_continuous_m` is MEASURED from the NParks Park Connector Loop GeoJSON
  on data.gov.sg (878 features, full LineString geometry, mean 37 vertices).
- `n_covered_linkway_segments_800m` is MEASURED from the committed
  covered_linkway.csv points.
- `dedicated_path_m_within_800m` is NOT measurable: OneMap's `cyclingpath`
  theme returns a representative point for most features (mean 1.14 vertices
  across 4,998), and LTA DataMall needs an account key this project lacks.
- `bike_parks_at_mrt` is NOT measurable: OneMap's `bicyclerack` theme returns
  "No result(s) found" at every extent tried.
- `pct_sheltered_to_mrt` is NOT measurable without route geometry.

Unmeasurable fields stay blank rather than 0, so a missing input can never be
read as a measured zero.
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "models"))

import ingest_pedestrian_paths as ingester  # noqa: E402


def _estates():
    return pd.DataFrame([
        {"estate": "ALPHA", "lat": 1.3500, "lon": 103.9400},
        {"estate": "BETA", "lat": 1.4500, "lon": 103.8200},
    ])


def _pcn_geojson(tmp_path):
    # A ~0.01 degree east-west line (~1.1 km) beside ALPHA, and one far away.
    payload = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"PCN_LOOP": "Near"},
             "geometry": {"type": "LineString",
                          "coordinates": [[103.9400, 1.3502], [103.9500, 1.3502]]}},
            {"type": "Feature", "properties": {"PCN_LOOP": "Far"},
             "geometry": {"type": "LineString",
                          "coordinates": [[103.6000, 1.2000], [103.6100, 1.2000]]}},
        ],
    }
    path = tmp_path / "pcn.geojson"
    path.write_text(json.dumps(payload))
    return path


def _linkways(tmp_path):
    path = tmp_path / "covered_linkway.csv"
    pd.DataFrame([
        {"lat": 1.3503, "lon": 103.9401},   # ~35 m from ALPHA
        {"lat": 1.3530, "lon": 103.9430},   # ~450 m from ALPHA
        {"lat": 1.3800, "lon": 103.9800},   # far from both
    ]).to_csv(path, index=False)
    return path


def test_pcn_metres_measured_within_the_buffer(tmp_path):
    frame = ingester.build_cycling(_estates(), _pcn_geojson(tmp_path), buffer_m=800)

    alpha = frame[frame.estate == "ALPHA"].iloc[0]
    beta = frame[frame.estate == "BETA"].iloc[0]
    # ~1.11 km of park connector sits inside ALPHA's buffer, none inside BETA's.
    assert 1000 < alpha.pcn_continuous_m < 1200
    assert beta.pcn_continuous_m == 0


def test_unmeasurable_cycling_fields_stay_blank_not_zero(tmp_path):
    frame = ingester.build_cycling(_estates(), _pcn_geojson(tmp_path), buffer_m=800)

    assert frame["dedicated_path_m_within_800m"].isna().all()
    assert frame["bike_parks_at_mrt"].isna().all()
    assert frame["provenance_note"].str.contains("pcn_continuous_m measured").all()


def test_covered_linkway_segments_counted_within_the_buffer(tmp_path):
    frame = ingester.build_walking(_estates(), _linkways(tmp_path), buffer_m=800)

    alpha = frame[frame.estate == "ALPHA"].iloc[0]
    beta = frame[frame.estate == "BETA"].iloc[0]
    assert alpha.n_covered_linkway_segments_800m == 2
    assert beta.n_covered_linkway_segments_800m == 0


def test_sheltered_share_stays_blank(tmp_path):
    frame = ingester.build_walking(_estates(), _linkways(tmp_path), buffer_m=800)

    assert frame["pct_sheltered_to_mrt"].isna().all()
    assert frame["provenance_note"].str.contains("pct_sheltered_to_mrt unmeasured").all()


def test_schema_and_estate_coverage_are_preserved(tmp_path):
    walking = ingester.build_walking(_estates(), _linkways(tmp_path), buffer_m=800)
    cycling = ingester.build_cycling(_estates(), _pcn_geojson(tmp_path), buffer_m=800)

    assert list(walking.columns) == ["estate", "pct_sheltered_to_mrt",
                                     "n_covered_linkway_segments_800m", "provenance_note"]
    assert list(cycling.columns) == ["estate", "dedicated_path_m_within_800m",
                                     "pcn_continuous_m", "bike_parks_at_mrt", "provenance_note"]
    assert walking.estate.tolist() == ["ALPHA", "BETA"]
    assert cycling.estate.tolist() == ["ALPHA", "BETA"]


def test_multilinestring_parts_are_all_measured(tmp_path):
    # Two ~556 m parts, one east and one west of ALPHA, both with midpoints
    # inside the buffer.
    payload = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature", "properties": {},
            "geometry": {"type": "MultiLineString",
                         "coordinates": [[[103.9400, 1.3502], [103.9450, 1.3502]],
                                         [[103.9400, 1.3502], [103.9350, 1.3502]]]},
        }],
    }
    path = tmp_path / "multi.geojson"
    path.write_text(json.dumps(payload))

    frame = ingester.build_cycling(_estates(), path, buffer_m=800)

    alpha = frame[frame.estate == "ALPHA"].iloc[0]
    assert 1000 < alpha.pcn_continuous_m < 1200


def test_a_segment_counts_only_when_its_midpoint_is_inside_the_buffer(tmp_path):
    # The midpoint rule is coarse by design: it keeps a long line from being
    # counted whole when one end merely clips the circle. Real PCN geometry
    # averages 37 vertices per feature, so segments are short.
    payload = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature", "properties": {},
            "geometry": {"type": "LineString",
                         "coordinates": [[103.9450, 1.3502], [103.9500, 1.3502]]},
        }],
    }
    path = tmp_path / "offset.geojson"
    path.write_text(json.dumps(payload))

    frame = ingester.build_cycling(_estates(), path, buffer_m=800)

    # Midpoint sits ~834 m east of ALPHA, so nothing counts.
    assert frame[frame.estate == "ALPHA"].iloc[0].pcn_continuous_m == 0
