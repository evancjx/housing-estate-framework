import json
import math
import os

import numpy as np

import provision_model as p

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data", "inputs")


def test_jtc_missing_returns_nan():
    s, meta = p.score_jtc_industrial({})
    assert np.isnan(s)
    assert "missing" in meta["note"]
    assert np.isnan(p.score_jtc_industrial({"nearest_industrial_m": np.nan})[0])


def test_jtc_heavy_and_none_use_A_JTC():
    # A_JTC: <=500->1, <=1500->2, <=3000->3, <=5000->4, else 5
    assert p.score_jtc_industrial({"nearest_industrial_m": 400, "intensity_tag": "HEAVY"})[0] == 1.0
    assert p.score_jtc_industrial({"nearest_industrial_m": 6000, "intensity_tag": "NONE"})[0] == 5.0
    assert p.score_jtc_industrial({"nearest_industrial_m": 400})[0] == 1.0  # tag defaults to NONE


def test_jtc_light_uses_looser_anchors():
    # light table: <=250->2, <=800->3, <=2000->4, else 5
    assert p.score_jtc_industrial({"nearest_industrial_m": 250, "intensity_tag": "LIGHT"})[0] == 2.0
    assert p.score_jtc_industrial({"nearest_industrial_m": 400, "intensity_tag": "LIGHT"})[0] == 3.0


def test_air_quality_missing_returns_nan():
    s, meta = p.score_air_quality({})
    assert np.isnan(s)
    assert np.isnan(p.score_air_quality({"pm25_annual_mean": np.nan})[0])


def test_air_quality_anchors_and_additive_correction():
    # A_PM25: <=8->5, <=12->4, <=16->3, <=20->2, else 1 (lower PM is better)
    assert p.score_air_quality({"pm25_annual_mean": 7})[0] == 5.0
    s, meta = p.score_air_quality({"pm25_annual_mean": 7, "road_buffer_correction": 2})
    assert s == 4.0  # 7+2=9 -> band 4
    assert meta["pm25_adjusted"] == 9.0


def test_air_quality_none_correction_coalesces_to_zero():
    assert p.score_air_quality({"pm25_annual_mean": 10, "road_buffer_correction": None})[0] == 4.0


def test_stewardship_none_json_and_no_mapping_return_nan():
    assert np.isnan(p.score_stewardship("BISHAN", None)[0])
    tc = {"town_councils": [{"name": "T", "estates": ["Bishan"], "scc_arrears": "GREEN",
          "lift": "GREEN", "cleanliness": "GREEN", "estate_maintenance": "GREEN"}]}
    s, meta = p.score_stewardship("NOWHERE", tc)
    assert np.isnan(s)
    assert "no TC mapping" in meta["note"]


def test_stewardship_kpi_average_and_close_rate_bump():
    tc = {"town_councils": [{"name": "BTP", "estates": ["Bishan"], "scc_arrears": "GREEN",
          "lift": "GREEN", "cleanliness": "GREEN", "estate_maintenance": "GREEN",
          "oneservice_close_rate_pct": 95}]}
    assert p.score_stewardship("BISHAN", tc)[0] == 5.0  # mean 5 + 0.3, clamped to 5
    tc2 = {"town_councils": [{"name": "X", "estates": ["Foo"], "scc_arrears": "RED",
           "lift": "AMBER", "cleanliness": "GREEN", "estate_maintenance": "AMBER",
           "oneservice_close_rate_pct": 75}]}
    assert p.score_stewardship("FOO", tc2)[0] == 2.7  # mean(1,3,5,3)=3 -0.3


def test_stewardship_real_data_in_range():
    tc = json.load(open(os.path.join(DATA, "town_council_kpi.json")))
    s, _ = p.score_stewardship("JURONG EAST", tc)
    assert 1.0 <= s <= 5.0
