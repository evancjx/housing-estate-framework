import pandas as pd
import pytest

import gen_two_district_comparison_html as gen


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _write_ura(tmp_path):
    """Two districts (18, 26), condo/apartment + one landed row that must be dropped."""
    rows = [
        # District 18 - condo/apartment
        {"planning_area": "TAMPINES", "transacted_price": 1_000_000, "area_sqm": 60.0,
         "property_type": "Condominium", "tenure": "99 yrs", "project_age_years": 5,
         "sale_month": "2023-04", "project_name": "COCO PALMS", "street_name": "PASIR RIS GROVE",
         "postal_district": "18", "unit_price_psm": 15_000, "type_of_sale": "Resale"},
        {"planning_area": "TAMPINES", "transacted_price": 1_400_000, "area_sqm": 100.0,
         "property_type": "Apartment", "tenure": "Freehold", "project_age_years": 5,
         "sale_month": "2023-05", "project_name": "COCO PALMS", "street_name": "PASIR RIS GROVE",
         "postal_district": "18", "unit_price_psm": 14_000, "type_of_sale": "Resale"},
        # District 18 - landed (MUST be excluded)
        {"planning_area": "TAMPINES", "transacted_price": 4_000_000, "area_sqm": 300.0,
         "property_type": "Terrace House", "tenure": "Freehold", "project_age_years": 20,
         "sale_month": "2023-05", "project_name": "SOME TERRACE", "street_name": "X",
         "postal_district": "18", "unit_price_psm": 13_000, "type_of_sale": "Resale"},
        # District 26 - condo/apartment
        {"planning_area": "ANG MO KIO", "transacted_price": 1_600_000, "area_sqm": 65.0,
         "property_type": "Condominium", "tenure": "99 yrs", "project_age_years": 1,
         "sale_month": "2023-06", "project_name": "LENTOR MODERN", "street_name": "LENTOR CENTRAL",
         "postal_district": "26", "unit_price_psm": 23_000, "type_of_sale": "New Sale"},
        {"planning_area": "ANG MO KIO", "transacted_price": 2_200_000, "area_sqm": 95.0,
         "property_type": "Apartment", "tenure": "99 yrs", "project_age_years": 1,
         "sale_month": "2023-07", "project_name": "LENTOR MODERN", "street_name": "LENTOR CENTRAL",
         "postal_district": "26", "unit_price_psm": 23_500, "type_of_sale": "New Sale"},
        # Bad row (price 0) must be dropped by the shared loader
        {"planning_area": "ANG MO KIO", "transacted_price": 0, "area_sqm": 80.0,
         "property_type": "Condominium", "tenure": "99 yrs", "project_age_years": 1,
         "sale_month": "2023-07", "project_name": "BAD ROW", "street_name": "Y",
         "postal_district": "26", "unit_price_psm": 0, "type_of_sale": "Resale"},
    ]
    path = tmp_path / "ura_private.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _write_edgeprop(tmp_path):
    """EdgeProp rows: 2019-2020 backfill + bedroom labels (>=2 units per project+band)."""
    rows = []
    for i in range(3):  # 3x 2BR COCO PALMS in the 50-70 band -> modal label 2
        rows.append({"Project": "COCO PALMS", "Street": "PASIR RIS GROVE", "Postal District": "18",
                     "Date of Sale": "10 Jun 2019", "Type": "Condominium", "Tenure": "99 yrs",
                     "Sale Type": "Resale", "Price ($)": 900_000 + i, "Area (sqm)": 60.0,
                     "Area (sqft)": 646.0, "Unit Price ($psf)": 1400, "Bedrooms": 2})
    for i in range(2):  # 2x 3BR LENTOR MODERN in the 70-100 band -> modal label 3
        rows.append({"Project": "LENTOR MODERN", "Street": "LENTOR CENTRAL", "Postal District": "26",
                     "Date of Sale": "11 Jun 2020", "Type": "Apartment", "Tenure": "99 yrs",
                     "Sale Type": "New Sale", "Price ($)": 1_900_000 + i, "Area (sqm)": 95.0,
                     "Area (sqft)": 1022.0, "Unit Price ($psf)": 1850, "Bedrooms": 3})
    path = tmp_path / "edgeprop.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _write_locations(tmp_path):
    rows = [
        {"project_name": "COCO PALMS", "street_name": "PASIR RIS GROVE", "postal_district": "18",
         "planning_area": "TAMPINES", "lat": 1.3721, "lon": 103.9474, "match_status": "exact",
         "match_score": 90},
        {"project_name": "LENTOR MODERN", "street_name": "LENTOR CENTRAL", "postal_district": "26",
         "planning_area": "ANG MO KIO", "lat": 1.3846, "lon": 103.8360, "match_status": "exact",
         "match_score": 92},
    ]
    path = tmp_path / "locations.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _write_mrt(tmp_path):
    rows = [
        {"lat": 1.3730, "lon": 103.9492, "name": "Pasir Ris", "stn_code": "EW1",
         "line": "East West Line", "operational": 1},
        {"lat": 1.3849, "lon": 103.8352, "name": "Lentor", "stn_code": "TE5",
         "line": "Thomson-East Coast Line", "operational": 1},
        # A future station placed right on top of COCO PALMS -> should win only when future included
        {"lat": 1.3721, "lon": 103.9474, "name": "Future Halt", "stn_code": "XX1",
         "line": "Cross Island Line", "operational": 0},
    ]
    path = tmp_path / "mrt.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_load_unified_excludes_landed(tmp_path):
    ura = _write_ura(tmp_path)
    edge = _write_edgeprop(tmp_path)
    df = gen.load_unified(ura, edge, "18")
    assert not df.empty
    # landed "Terrace House" and the price-0 row are gone
    assert not df["property_type"].str.contains("House", case=False).any()
    assert (df["price"] > 0).all()
    # URA 2023 rows + EdgeProp 2019 backfill both present
    assert set(df["source"].unique()) == {"ura_private", "edgeprop_backfill"}


def test_size_breakdown_bands(tmp_path):
    ura = _write_ura(tmp_path)
    edge = _write_edgeprop(tmp_path)
    df = gen.load_unified(ura, edge, "18")
    size = gen.size_breakdown(df)
    assert size["all"]["n"] == len(df)
    # the 100 sqm apartment lands in 70-100 band
    assert size["70to100"]["n"] >= 1
    assert size["50to70"]["n"] >= 1


def test_bedroom_breakdown_uses_edgeprop_labels(tmp_path):
    ura = _write_ura(tmp_path)
    edge = _write_edgeprop(tmp_path)
    labels = gen.load_edgeprop_bedroom_counts(edge, "18")
    assert labels[("COCO PALMS", "50to70")] == 2
    df = gen.load_unified(ura, edge, "18")
    br = gen.bedroom_breakdown(df, labels)
    # the 60 sqm COCO PALMS units get the 2BR label; others fall to Unknown
    assert br["br2"]["n"] >= 1
    total = sum(br[k]["n"] for k in gen.BEDROOM_ORDER)
    assert total == len(df)


def test_mrt_breakdown_operational_vs_future(tmp_path):
    ura = _write_ura(tmp_path)
    edge = _write_edgeprop(tmp_path)
    coords = gen.load_project_coords(_write_locations(tmp_path), "18")
    all_st, op_st = gen.load_stations(_write_mrt(tmp_path))
    df = gen.load_unified(ura, edge, "18")
    m = gen.mrt_breakdown(df, coords, all_st, op_st)
    assert m["n_projects_geocoded"] == 1  # only COCO PALMS geocoded in D18
    # future "Future Halt" sits on COCO PALMS -> closer than operational Pasir Ris
    assert m["any_median_m"] < m["op_median_m"]
    assert m["future_improves"], "future station should improve the nearest for COCO PALMS"


def test_load_project_coords_filters_by_district(tmp_path):
    coords18 = gen.load_project_coords(_write_locations(tmp_path), "18")
    coords26 = gen.load_project_coords(_write_locations(tmp_path), "26")
    assert set(coords18) == {"COCO PALMS"}
    assert set(coords26) == {"LENTOR MODERN"}


def test_generate_writes_html(tmp_path):
    out, a, b = gen.generate(
        "18", "26",
        _write_ura(tmp_path), _write_edgeprop(tmp_path),
        _write_locations(tmp_path), _write_mrt(tmp_path), tmp_path,
    )
    assert out.exists()
    text = out.read_text()
    assert "Size (floor-area bands)" in text
    assert "Bedrooms (EdgeProp labels)" in text
    assert "MRT distance" in text
    assert a["district"] == "18" and b["district"] == "26"


def test_main_requires_exactly_two_districts(monkeypatch, tmp_path):
    argv = ["prog", "--district", "18",
            "--private", str(_write_ura(tmp_path)),
            "--edgeprop", str(_write_edgeprop(tmp_path)),
            "--locations", str(_write_locations(tmp_path)),
            "--mrt", str(_write_mrt(tmp_path)),
            "--out-dir", str(tmp_path)]
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit):
        gen.main()


def test_main_rejects_duplicate_district(monkeypatch, tmp_path):
    argv = ["prog", "--district", "18", "--district", "18",
            "--private", str(_write_ura(tmp_path)),
            "--edgeprop", str(_write_edgeprop(tmp_path)),
            "--locations", str(_write_locations(tmp_path)),
            "--mrt", str(_write_mrt(tmp_path)),
            "--out-dir", str(tmp_path)]
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit):
        gen.main()
