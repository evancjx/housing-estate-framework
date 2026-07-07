import pandas as pd
import pytest

import gen_district_private_comparison_html as gen


def _write_canonical(tmp_path):
    df = pd.DataFrame([
        {"planning_area": "SEMBAWANG", "transacted_price": 1_500_000, "area_sqm": 100.0,
         "property_type": "Condominium", "tenure": "99 yrs lease commencing from 2015",
         "project_age_years": 8, "sale_month": "2023-04", "project_name": "THE SHAUGHNESSY",
         "street_name": "MILTONIA CLOSE", "postal_district": "27",
         "market_segment": "Outside Central Region", "floor_level": "01-05",
         "type_of_sale": "Resale", "type_of_area": "Strata", "unit_price_psm": 15_000},
        {"planning_area": "PASIR RIS", "transacted_price": 1_200_000, "area_sqm": 90.0,
         "property_type": "Condominium", "tenure": "Freehold",
         "project_age_years": 20, "sale_month": "2022-01", "project_name": "LOYANG VILLAS",
         "street_name": "LOYANG RISE", "postal_district": "17",
         "market_segment": "Outside Central Region", "floor_level": "-",
         "type_of_sale": "Resale", "type_of_area": "Strata", "unit_price_psm": 13_000},
        {"planning_area": "SEMBAWANG", "transacted_price": 0, "area_sqm": 100.0,
         "property_type": "Condominium", "tenure": "Freehold",
         "project_age_years": 8, "sale_month": "2023-04", "project_name": "BAD ROW",
         "street_name": "X", "postal_district": "27",
         "market_segment": "Outside Central Region", "floor_level": "-",
         "type_of_sale": "Resale", "type_of_area": "Strata", "unit_price_psm": 15_000},
    ])
    path = tmp_path / "ura_private.csv"
    df.to_csv(path, index=False)
    return path


def test_normalise_district():
    assert gen.normalise_district("17") == "17"
    assert gen.normalise_district("7") == "07"
    assert gen.normalise_district(7) == "07"
    assert gen.normalise_district(" 27 ") == "27"


def test_load_canonical_filters_district_and_maps_schema(tmp_path):
    path = _write_canonical(tmp_path)
    out = gen.load_canonical(path, "27")
    assert list(out.columns) == gen.UNIFIED_COLUMNS
    assert set(out["project"]) == {"THE SHAUGHNESSY"}  # D17 row and zero-price row excluded
    row = out.iloc[0]
    assert row["sale_year"] == 2023
    assert row["source"] == "ura_private"
    assert row["psf"] == pytest.approx(15_000 / gen.SQM_TO_SQFT)
