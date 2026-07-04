import pandas as pd

import gen_buyer_profile_html as htmlgen


def _rows():
    return [
        {
            "profile_id": "family",
            "estate": "ALPHA",
            "tenure": "hdb",
            "eligible": True,
            "rank": 1,
            "profile_score": 4.1,
            "soft_weight_covered": 1.0,
            "filter_reasons": "",
            "persona": "YoungFam",
            "horizon": "T5",
            "life_path": "forming_family",
            "liveability_score": 4.0,
            "liveability_band": "B+",
            "value_score": 4.2,
            "value_band": "B+",
            "value_basis": "direct",
            "value_n": 100,
            "employment_score": 3.5,
            "employment_band": "B",
            "lease_score": 4.0,
            "lease_band": "B+",
            "provision_score": 3.8,
            "provision_band": "B",
            "archetype": "B",
            "measured_only": False,
        },
        {
            "profile_id": "landed",
            "estate": "BETA",
            "tenure": "landed",
            "eligible": False,
            "rank": None,
            "profile_score": 3.2,
            "soft_weight_covered": 0.8,
            "filter_reasons": "value_below:C",
            "persona": "Lifestyle",
            "horizon": "T5",
            "life_path": "upgrader",
            "liveability_score": 3.4,
            "liveability_band": "C",
            "value_score": None,
            "value_band": "no_data",
            "value_basis": "no_data",
            "value_n": None,
            "employment_score": 3.0,
            "employment_band": "C",
            "lease_score": None,
            "lease_band": "",
            "provision_score": 3.6,
            "provision_band": "",
            "archetype": "C",
            "measured_only": False,
        },
    ]


def test_render_html_has_filters_and_embedded_segments():
    html = htmlgen.render_html(_rows(), "2026-07-04")

    assert "Buyer Profile Evaluation" in html
    assert 'id="profileFilter"' in html
    assert 'id="tenureFilter"' in html
    assert 'id="eligibleFilter"' in html
    assert 'id="minScore"' in html
    assert '"tenure": "landed"' in html
    assert '"filter_reasons": "value_below:C"' in html
    assert "function renderRows()" in html


def test_load_rows_requires_buyer_profile_columns(tmp_path):
    path = tmp_path / "bad.csv"
    pd.DataFrame({"estate": ["ALPHA"]}).to_csv(path, index=False)

    try:
        htmlgen.load_rows(path)
    except SystemExit as exc:
        assert "missing required columns" in str(exc)
    else:
        raise AssertionError("expected SystemExit")


def test_profile_summary_uses_top_eligible_choice():
    summary = htmlgen.profile_summary(_rows())
    family = [row for row in summary if row["profile_id"] == "family"][0]
    landed = [row for row in summary if row["profile_id"] == "landed"][0]

    assert family["eligible"] == 1
    assert family["top_estate"] == "ALPHA"
    assert landed["eligible"] == 0
    assert landed["top_estate"] == ""
