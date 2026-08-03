"""Tests for the Canberra Crescent versus District 27 deep analysis."""

from datetime import date
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))

import gen_canberra_crescent_d27_html as canberra  # noqa: E402


def _raw(tmp_path):
    rows = []
    for sale_date, price in (("Jun-26", 1_000_000), ("Jun-26", 1_000_000), ("Jul-26", 1_100_000)):
        rows.append(
            {
                "Project Name": "CANBERRA CRESCENT RESIDENCES",
                "Transacted Price ($)": price,
                "Sale Date": sale_date,
                "Street Name": "CANBERRA CRESCENT",
                "Type of Sale": "New Sale",
                "Area (SQM)": 50,
                "Property Type": "Apartment",
                "Tenure": "99 yrs lease commencing from 2024",
                "Postal District": 27,
                "Floor Level": "01 to 05",
            }
        )
    path = tmp_path / "pmi_d27_2021-2026.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _edgeprop(tmp_path):
    rows = []
    for sale_date, price in (("02 Jun 2026", 1_000_000), ("02 Jul 2026", 1_100_000)):
        rows.append(
            {
                "Project": "CANBERRA CRESCENT RESIDENCES",
                "Date of Sale": sale_date,
                "Price ($)": price,
                "Area (sqft)": 538,
                "Area (sqm)": 50,
                "Address": "51 CANBERRA CRESCENT #03-XX",
                "Postal District": "27",
                "Bedrooms": "2",
                "Type": "Apartment",
                "Sale Type": "New Sale",
                "Tenure": "99 yrs from 2024",
            }
        )
    path = tmp_path / "edgeprop.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_official_transaction_multiplicity_is_preserved(tmp_path):
    txns = canberra.load_district_transactions(
        _raw(tmp_path),
        _edgeprop(tmp_path),
    )

    assert len(txns) == 3
    duplicates = txns[
        txns["sale_month"].eq("2026-06")
        & txns["price"].eq(1_000_000)
        & txns["area_sqm"].eq(50)
    ]
    assert len(duplicates) == 2
    assert txns["bedrooms"].astype(int).eq(2).all()
    assert txns["bedroom_source"].eq("edgeprop_exact").all()

    window = canberra.comparison_window(txns, date(2026, 7, 25))
    assert str(window["full_end"]) == "2026-06"
    assert str(window["partial"]) == "2026-07"


def test_transaction_diagnostics_keep_sale_states_and_cohort_breadth_visible():
    rows = [
        {
            "project_name": "LAUNCH",
            "year": 2026,
            "type_of_sale": "New Sale",
            "unit_key": "2",
            "psf": psf,
            "sqft": 700,
            "size_band_low": 700,
            "bedroom_source": "edgeprop_exact",
        }
        for psf in (1_900, 2_000, 2_100)
    ]
    rows.extend(
        [
            {
                "project_name": project,
                "year": 2026,
                "type_of_sale": "Resale",
                "unit_key": "2",
                "psf": psf,
                "sqft": 700,
                "size_band_low": 700,
                "bedroom_source": "edgeprop_exact",
            }
            for project, psf in (("RESALE A", 1_400), ("RESALE B", 1_600))
        ]
    )

    out = canberra.add_transaction_diagnostics(pd.DataFrame(rows))
    launch = out[out["project_name"].eq("LAUNCH")]
    resale = out[out["type_of_sale"].eq("Resale")]

    assert launch["cohort_project_n"].eq(1).all()
    assert launch["analysis"].str.contains("launch-position signal only").all()
    assert resale["cohort_project_n"].eq(2).all()
    assert resale["analysis"].str.contains("2 projects in cohort").all()


def test_canberra_mrt_uses_reviewed_ns12_coordinate_not_bad_legacy_point():
    locations = {
        canberra.SUBJECT: {
            "lat": 1.449921230269529,
            "lon": 103.8293971626456,
        },
        "THE COMMODORE": {
            "lat": 1.441213593738426,
            "lon": 103.8277840489972,
        },
    }
    mrt = pd.DataFrame(
        [
            {
                "lat": 1.44967,
                "lon": 103.82988,
                "name": "Canberra",
                "stn_code": "NS12",
                "operational": 1,
            }
        ]
    )

    subject = canberra.nearest_station(canberra.SUBJECT, locations, mrt)
    commodore = canberra.nearest_station("THE COMMODORE", locations, mrt)

    assert subject["station"] == "Canberra (NS12)"
    assert 740 <= subject["station_distance_m"] <= 755
    assert 290 <= commodore["station_distance_m"] <= 305
    assert commodore["station_distance_m"] < subject["station_distance_m"]
