import pandas as pd

import private_segment_value_model as psv


def test_filter_private_segment_splits_condo_and_landed_rows():
    df = pd.DataFrame({
        "property_type": [
            "Apartment",
            "Condominium",
            "Terrace House",
            "Semi-Detached House",
            "Detached House",
        ],
        "type_of_area": ["Strata", "Strata", "Land", "Land", "Land"],
    })

    condo = psv.filter_private_segment(df, "condo")
    landed = psv.filter_private_segment(df, "landed")

    assert list(condo["property_type"]) == ["Apartment", "Condominium"]
    assert list(landed["property_type"]) == [
        "Terrace House",
        "Semi-Detached House",
        "Detached House",
    ]


def test_filter_private_segment_rejects_unknown_segment():
    df = pd.DataFrame({"property_type": ["Apartment"], "type_of_area": ["Strata"]})
    try:
        psv.filter_private_segment(df, "shophouse")
    except ValueError as exc:
        assert "condo or landed" in str(exc)
    else:
        raise AssertionError("expected ValueError")
