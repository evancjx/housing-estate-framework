"""The MOH hospital list now comes from the OneMap `moh_hospitals` theme.

The previous data.gov.sg discovery path is dead: collection 521 and the dataset
search API both return 403. The theme is owner-published by MINISTRY OF HEALTH
and carries coordinates per facility, so the layer no longer needs the OneMap
Search geocoder — which returns "SGH BLK 4 (TAXI STAND)" for Singapore General
Hospital and an unrelated GP clinic for Woodlands Health.
"""
import json
import os

import pytest

import ingest_moh_hospitals as ingest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAYLOAD = os.path.join(ROOT, "data", "raw", "onemap", "moh_hospitals.json")


def _payload():
    with open(PAYLOAD, encoding="utf-8") as f:
        return json.load(f)


def _boom(*_args, **_kwargs):
    raise AssertionError("theme coordinates must be used; geocoding must not run")


# ------------------------------------------------------------------ parsing

def test_parse_theme_reads_name_and_coordinates():
    rows = ingest.parse_theme_rows(_payload())
    by_name = {r["name"]: r for r in rows}

    sgh = by_name["SINGAPORE GENERAL HOSPITAL"]
    assert sgh["lat"] == pytest.approx(1.27964383975506)
    assert sgh["lon"] == pytest.approx(103.835541765111)
    assert sgh["address"] == "OUTRAM ROAD"


def test_parse_theme_skips_the_metadata_header():
    """SrchResults[0] is a FeatCount/Theme_Name header, not a facility."""
    rows = ingest.parse_theme_rows(_payload())
    assert len(rows) == _payload()["SrchResults"][0]["FeatCount"]
    assert all(r["name"] for r in rows)
    assert not any("FeatCount" in r for r in rows)


@pytest.mark.parametrize("bad", ["", "not-a-pair", "1.3", "abc,def", None])
def test_parse_theme_drops_unusable_coordinates(bad):
    payload = {"SrchResults": [{"FeatCount": 1}, {"NAME": "X HOSPITAL", "LatLng": bad}]}
    assert ingest.parse_theme_rows(payload) == []


def test_parse_theme_rejects_an_empty_payload():
    assert ingest.parse_theme_rows({"SrchResults": []}) == []
    assert ingest.parse_theme_rows({}) == []


# --------------------------------------------------------------- retention

def test_theme_retains_the_public_acute_hospitals():
    rows = ingest.build_hospital_rows(ingest.parse_theme_rows(_payload()),
                                      geocode_func=_boom)
    acute = {r["name"] for r in rows if r["tier"] == "acute"}

    assert acute == {
        "Alexandra Hospital",
        "Changi General Hospital",
        "KK Women's and Children's Hospital",
        "Khoo Teck Puat Hospital",
        "National University Hospital",
        "Ng Teng Fong General Hospital",
        "Sengkang General Hospital",
        "Singapore General Hospital",
        "Tan Tock Seng Hospital",
        "Woodlands Health",
    }
    assert len(acute) >= ingest.MIN_EXPECTED_ACUTE


def test_theme_drops_private_hospitals():
    """The provision layer measures public-system access, not private capacity."""
    rows = ingest.build_hospital_rows(ingest.parse_theme_rows(_payload()),
                                      geocode_func=_boom)
    kept = {r["name"].upper() for r in rows}
    for private in ("GLENEAGLES HOSPITAL", "MOUNT ELIZABETH HOSPITAL",
                    "RAFFLES HOSPITAL", "FARRER PARK HOSPITAL",
                    "PARKWAY EAST HOSPITAL", "THOMSON MEDICAL CENTRE"):
        assert private not in kept


def test_theme_drops_non_hospital_facilities():
    """Specialist centres and care hubs are not acute hospitals."""
    rows = ingest.build_hospital_rows(ingest.parse_theme_rows(_payload()),
                                      geocode_func=_boom)
    kept = {r["name"].upper() for r in rows}
    for other in ("TTSH INTEGRATED CARE HUB", "NATIONAL HEART CENTRE SINGAPORE",
                  "CHANGI MEDICAL FACILITY"):
        assert other not in kept


def test_theme_coordinates_are_used_verbatim_without_geocoding():
    rows = ingest.build_hospital_rows(ingest.parse_theme_rows(_payload()),
                                      geocode_func=_boom)
    sgh = next(r for r in rows if r["name"] == "Singapore General Hospital")
    assert sgh["lat"] == pytest.approx(1.27964383975506)
    assert sgh["lon"] == pytest.approx(103.835541765111)


def test_ae_flag_survives_the_theme_source():
    rows = ingest.build_hospital_rows(ingest.parse_theme_rows(_payload()),
                                      geocode_func=_boom)
    by_name = {r["name"]: r for r in rows}
    assert by_name["Singapore General Hospital"]["has_ae"] is True
    assert by_name["Alexandra Hospital"]["has_ae"] is False


# ------------------------------------------------------------------- token

def test_fetch_requires_a_token_and_says_so():
    with pytest.raises(RuntimeError) as exc:
        ingest.fetch_theme_payload(token="")
    assert "ONEMAP_TOKEN" in str(exc.value)
