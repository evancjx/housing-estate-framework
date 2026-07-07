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


def _edgeprop_row(**over):
    row = {"Project": "SELETARIS", "planning_area": "SEMBAWANG", "Postal District": "27",
           "Date of Sale": "15 Mar 2019", "Address": "X #05-XX", "Street": "SEMBAWANG ROAD",
           "Bedrooms": "3", "Unit Price ($psf)": "800", "Price ($)": "1000000",
           "Type": "Condominium", "Tenure": "Freehold", "Sale Type": "Resale",
           "Area (sqft)": "1250", "Area (sqm)": "116.1", "Type of Area": "Strata",
           "Purchaser Address": "Private", "Source": "URA", "source_quality": "not_clean",
           "source_url": "u", "source_slug": "s"}
    row.update(over)
    return row


def _write_edgeprop(tmp_path, rows):
    path = tmp_path / "edgeprop.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_edgeprop_backfill_keeps_only_2019_2020(tmp_path):
    path = _write_edgeprop(tmp_path, [
        _edgeprop_row(),
        _edgeprop_row(**{"Date of Sale": "10 Jun 2020", "Price ($)": "1100000"}),
        _edgeprop_row(**{"Date of Sale": "10 Jun 2021", "Price ($)": "1200000"}),
        _edgeprop_row(**{"Date of Sale": "10 Jun 2018", "Price ($)": "900000"}),
    ])
    out = gen.load_edgeprop_backfill(path, "27")
    assert list(out.columns) == gen.UNIFIED_COLUMNS
    assert sorted(out["sale_year"]) == [2019, 2020]
    assert set(out["source"]) == {"edgeprop_backfill"}


def test_edgeprop_backfill_dedupes_and_drops_bad_rows(tmp_path):
    dup = _edgeprop_row()
    path = _write_edgeprop(tmp_path, [
        dup, dict(dup),                                    # exact duplicate
        _edgeprop_row(**{"Price ($)": "", "Date of Sale": "16 Mar 2019"}),   # missing price
        _edgeprop_row(**{"Area (sqm)": "0", "Date of Sale": "17 Mar 2019"}), # bad area
    ])
    out = gen.load_edgeprop_backfill(path, "27")
    assert len(out) == 1


def test_edgeprop_backfill_derives_psf_when_missing(tmp_path):
    path = _write_edgeprop(tmp_path, [_edgeprop_row(**{"Unit Price ($psf)": ""})])
    out = gen.load_edgeprop_backfill(path, "27")
    expected = 1_000_000 / (116.1 * gen.SQM_TO_SQFT)
    assert out.iloc[0]["psf"] == pytest.approx(expected, rel=1e-6)


def test_edgeprop_backfill_missing_file_returns_empty(tmp_path):
    out = gen.load_edgeprop_backfill(tmp_path / "nope.csv", "27")
    assert list(out.columns) == gen.UNIFIED_COLUMNS
    assert out.empty


def _ura_raw_row(**over):
    row = {"Project Name": "LANDED HOUSING DEVELOPMENT", "Transacted Price ($)": "4,653,000",
           "Area (SQFT)": "3,614.55", "Unit Price ($ PSF)": "1,287", "Sale Date": "Jun-19",
           "Street Name": "JALAN PERNAMA", "Type of Sale": "Resale", "Type of Area": "Land",
           "Area (SQM)": "335.8", "Unit Price ($ PSM)": "13,856", "Nett Price($)": "-",
           "Property Type": "Semi-Detached House", "Number of Units": "1", "Tenure": "Freehold",
           "Postal District": "17", "Market Segment": "Outside Central Region", "Floor Level": "-"}
    row.update(over)
    return row


def _write_ura_raw(tmp_path, district, rows):
    raw_dir = tmp_path / "ura_raw"
    raw_dir.mkdir(exist_ok=True)
    path = raw_dir / f"pmi_d{district}_landed_non_strata_2019-2026.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return raw_dir


def test_ura_raw_backfill_parses_commas_and_dates(tmp_path):
    raw_dir = _write_ura_raw(tmp_path, "17", [_ura_raw_row()])
    out = gen.load_ura_raw_backfill(raw_dir, "17")
    assert len(out) == 1
    row = out.iloc[0]
    assert row["price"] == pytest.approx(4_653_000)
    assert row["area_sqm"] == pytest.approx(335.8)
    assert row["psf"] == pytest.approx(1287)
    assert row["sale_year"] == 2019
    assert row["source"] == "ura_raw_backfill"


def test_ura_raw_backfill_keeps_only_2019_2020(tmp_path):
    raw_dir = _write_ura_raw(tmp_path, "17", [
        _ura_raw_row(),
        _ura_raw_row(**{"Sale Date": "Dec-20"}),
        _ura_raw_row(**{"Sale Date": "Jan-21"}),
        _ura_raw_row(**{"Sale Date": "Jun-26"}),
    ])
    out = gen.load_ura_raw_backfill(raw_dir, "17")
    assert sorted(out["sale_year"]) == [2019, 2020]


def test_ura_raw_backfill_missing_files_warns_and_returns_empty(tmp_path, capsys):
    empty_dir = tmp_path / "ura_raw"
    empty_dir.mkdir()
    out = gen.load_ura_raw_backfill(empty_dir, "17")
    assert out.empty
    assert list(out.columns) == gen.UNIFIED_COLUMNS
    assert "WARN" in capsys.readouterr().out


def test_annualised_growth_uses_first_and_last_qualifying_years():
    stats = {2019: (1000.0, 5), 2021: (900.0, 2), 2023: (1200.0, 4)}
    rate, y0, y1 = gen.annualised_growth(stats)
    assert (y0, y1) == (2019, 2023)  # 2021 skipped: n < MIN_YEAR_N
    assert rate == pytest.approx((1200.0 / 1000.0) ** (1 / 4) - 1)


def test_annualised_growth_none_when_fewer_than_two_qualifying_years():
    assert gen.annualised_growth({2019: (1000.0, 5)}) is None
    assert gen.annualised_growth({2019: (1000.0, 2), 2020: (1100.0, 2)}) is None
    assert gen.annualised_growth({}) is None


def test_annualised_growth_ignores_none_medians():
    stats = {2019: (None, 5), 2020: (1000.0, 3), 2022: (1210.0, 3)}
    rate, y0, y1 = gen.annualised_growth(stats)
    assert (y0, y1) == (2020, 2022)
    assert rate == pytest.approx(0.1)
