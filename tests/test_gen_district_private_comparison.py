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


def _unified(rows):
    return pd.DataFrame(rows, columns=gen.UNIFIED_COLUMNS)


def _u_row(project, year, psf, street="STREET A", ptype="Condominium",
           tenure="Freehold", source="ura_private", price=1_000_000, area=100.0):
    return [project, street, ptype, tenure, year, price, area, psf, "Resale", source]


def test_display_project_splits_generic_landed_by_street():
    assert gen.display_project("LANDED HOUSING DEVELOPMENT", "TOH CRESCENT") == \
        "LANDED HOUSING DEVELOPMENT (TOH CRESCENT)"
    assert gen.display_project("LOYANG VILLAS", "LOYANG RISE") == "LOYANG VILLAS"


def test_aggregate_projects_groups_and_computes_year_stats():
    df = _unified(
        [_u_row("ALPHA", 2021, 1000.0) for _ in range(3)]
        + [_u_row("ALPHA", 2023, 1100.0) for _ in range(3)]
        + [_u_row("ALPHA", 2022, 1050.0)]  # n=1 -> below MIN_YEAR_N
        + [_u_row("LANDED HOUSING DEVELOPMENT", 2021, 900.0, street="TOH CRESCENT")]
        + [_u_row("LANDED HOUSING DEVELOPMENT", 2021, 950.0, street="JALAN PERNAMA")]
    )
    rows = gen.aggregate_projects(df)
    names = [r["project"] for r in rows]
    assert names[0] == "ALPHA"  # most txns first
    assert "LANDED HOUSING DEVELOPMENT (TOH CRESCENT)" in names
    assert "LANDED HOUSING DEVELOPMENT (JALAN PERNAMA)" in names
    alpha = rows[0]
    assert alpha["n_total"] == 7
    assert alpha["year_stats"][2021] == (1000.0, 3)
    assert alpha["year_stats"][2019] == (None, 0)
    assert alpha["growth_pct"] == pytest.approx(((1100 / 1000) ** 0.5 - 1) * 100)
    assert (alpha["growth_from"], alpha["growth_to"]) == (2021, 2023)
    assert alpha["latest_year"] == 2023
    assert alpha["latest_median_psf"] == pytest.approx(1100.0)
    assert alpha["has_edgeprop_backfill"] is False


def test_aggregate_projects_flags_edgeprop_backfill():
    df = _unified([
        _u_row("BETA", 2019, 800.0, source="edgeprop_backfill"),
        _u_row("BETA", 2022, 1000.0),
    ])
    rows = gen.aggregate_projects(df)
    assert rows[0]["has_edgeprop_backfill"] is True


def test_district_summary_totals_and_growth_rankings():
    df = _unified(
        [_u_row("ALPHA", 2021, 1000.0) for _ in range(3)]
        + [_u_row("ALPHA", 2023, 1200.0) for _ in range(3)]
        + [_u_row("BETA", 2021, 1000.0) for _ in range(3)]
        + [_u_row("BETA", 2023, 900.0) for _ in range(3)]
        + [_u_row("GAMMA", 2021, 500.0)]  # no growth (single low-n year)
    )
    rows = gen.aggregate_projects(df)
    summary = gen.district_summary(df, rows)
    assert summary["total_txns"] == 13
    assert summary["yearly"][2021] == (1000.0, 7)
    assert summary["top_growth"][0]["project"] == "ALPHA"
    assert summary["bottom_growth"][0]["project"] == "BETA"
    growth_names = {r["project"] for r in summary["top_growth"] + summary["bottom_growth"]}
    assert "GAMMA" not in growth_names


def _full_fixture(tmp_path):
    """Canonical + edgeprop + ura_raw covering district 27."""
    canonical = _write_canonical(tmp_path)  # has 1 valid D27 row (THE SHAUGHNESSY 2023)
    edgeprop = _write_edgeprop(tmp_path, [_edgeprop_row()])  # SELETARIS 2019, D27
    raw_dir = _write_ura_raw(tmp_path, "27", [_ura_raw_row(**{"Postal District": "27"})])
    return canonical, edgeprop, raw_dir


def test_generate_writes_self_contained_page(tmp_path):
    canonical, edgeprop, raw_dir = _full_fixture(tmp_path)
    out_path, n_rows = gen.generate("27", canonical, edgeprop, raw_dir, tmp_path)
    assert out_path.name == "private_project_comparison_D27.html"
    assert out_path.exists()
    assert n_rows >= 3  # SHAUGHNESSY + SELETARIS + landed street group
    text = out_path.read_text(encoding="utf-8")
    assert "THE SHAUGHNESSY" in text
    assert "SELETARIS" in text
    assert "LANDED HOUSING DEVELOPMENT (JALAN PERNAMA)" in text
    assert "2019" in text and "2026" in text
    assert "EdgeProp" in text          # caveat banner mentions the backfill source
    assert "http://" not in text and "https://" not in text  # self-contained


def test_render_html_marks_low_n_years_and_backfill():
    year_stats = {y: (None, 0) for y in gen.YEARS}
    year_stats[2021] = (1000.0, 3)
    year_stats[2022] = (1050.0, 1)
    rows = [{
        "project": "ALPHA", "street": "S", "property_types": "Condominium",
        "tenure": "Freehold", "n_total": 4,
        "year_stats": year_stats,
        "growth_pct": None, "growth_from": None, "growth_to": None,
        "latest_year": 2022, "latest_median_psf": 1050.0, "latest_median_price": 1_000_000.0,
        "has_edgeprop_backfill": True,
    }]
    summary = {"total_txns": 4, "yearly": year_stats,
               "top_growth": [], "bottom_growth": []}
    html_text = gen.render_html("27", {"all": (rows, summary)}, {})
    assert "1,000" in html_text        # 2021 median shown (n>=3)
    assert "backfill" in html_text.lower()


import pathlib

ROOT = pathlib.Path(__file__).parent.parent


@pytest.mark.integration
def test_generate_real_d17_d27(tmp_path):
    for district, anchor in (("17", "LOYANG VILLAS"), ("27", "THE SHAUGHNESSY")):
        out_path, n_rows = gen.generate(
            district,
            ROOT / "data/ura_private.csv",
            ROOT / "data/edgeprop_condo_apartment_transactions_playwright_not_clean.csv",
            ROOT / "data/ura_raw",
            tmp_path,
        )
        assert n_rows > 20
        text = out_path.read_text(encoding="utf-8")
        assert anchor in text
        assert "2019" in text


def test_band_of_boundaries():
    assert gen.band_of(30.0) == "le50"
    assert gen.band_of(50.0) == "le50"
    assert gen.band_of(50.1) == "50to70"
    assert gen.band_of(70.0) == "50to70"
    assert gen.band_of(100.0) == "70to100"
    assert gen.band_of(130.0) == "100to130"
    assert gen.band_of(130.5) == "gt130"
    assert gen.band_of(500.0) == "gt130"
    assert gen.BAND_ORDER == ["all", "le50", "50to70", "70to100", "100to130", "gt130"]
    assert gen.BAND_LABELS["all"] == "All"
    assert gen.BAND_LABELS["gt130"] == ">130 sqm"


def test_bedroom_labels_mode_share_rule(tmp_path):
    rows = (
        # SELETARIS 116.1 sqm -> band 100to130; 3 rows, all "3" -> label (uses 2021+ rows too)
        [_edgeprop_row(**{"Date of Sale": "10 Jun 2021"}),
         _edgeprop_row(**{"Date of Sale": "10 Jun 2023"}),
         _edgeprop_row()]
        # EULER: only 2 rows -> no label
        + [_edgeprop_row(**{"Project": "EULER", "Bedrooms": "2", "Area (sqm)": "65"}) for _ in range(2)]
        # GAUSS: 3 rows split 2/1 -> share 0.67 < 0.7 -> no label
        + [_edgeprop_row(**{"Project": "GAUSS", "Bedrooms": "2", "Area (sqm)": "65"}),
           _edgeprop_row(**{"Project": "GAUSS", "Bedrooms": "2", "Area (sqm)": "66"}),
           _edgeprop_row(**{"Project": "GAUSS", "Bedrooms": "3", "Area (sqm)": "67"})]
        # NOETHER: unparseable bedrooms ignored entirely
        + [_edgeprop_row(**{"Project": "NOETHER", "Bedrooms": "-", "Area (sqm)": "80"}) for _ in range(3)]
    )
    path = _write_edgeprop(tmp_path, rows)
    labels = gen.load_edgeprop_bedroom_labels(path, "27")
    assert labels[("SELETARIS", "100to130")] == "≈3BR"
    assert ("EULER", "50to70") not in labels
    assert ("GAUSS", "50to70") not in labels
    assert not any(proj == "NOETHER" for proj, _ in labels)


def test_bedroom_labels_missing_file(tmp_path):
    assert gen.load_edgeprop_bedroom_labels(tmp_path / "nope.csv", "27") == {}

def _band_section(html_text, key):
    import re
    m = re.search(rf'<section id="band-{key}".*?</section>', html_text, re.S)
    assert m, f"missing section band-{key}"
    return m.group(0)


def test_generate_renders_band_tabs_and_membership(tmp_path):
    canonical, edgeprop, raw_dir = _full_fixture(tmp_path)
    out_path, _ = gen.generate("27", canonical, edgeprop, raw_dir, tmp_path)
    text = out_path.read_text(encoding="utf-8")
    for label in ("All", "≤50 sqm", "50–70 sqm", "70–100 sqm", "100–130 sqm", ">130 sqm"):
        assert label in text
    # canonical SHAUGHNESSY row is 100.0 sqm -> band 70to100 only
    assert "THE SHAUGHNESSY" in _band_section(text, "70to100")
    assert "THE SHAUGHNESSY" not in _band_section(text, "gt130")
    # ura_raw landed row is 335.8 sqm -> gt130 only
    assert "LANDED HOUSING DEVELOPMENT (JALAN PERNAMA)" in _band_section(text, "gt130")
    assert "LANDED HOUSING DEVELOPMENT (JALAN PERNAMA)" not in _band_section(text, "70to100")


def test_generate_shows_bedroom_label_in_band_table(tmp_path):
    canonical = _write_canonical(tmp_path)
    # 3 SELETARIS rows (116.1 sqm -> 100to130), all 3BR -> label ≈3BR
    edgeprop = _write_edgeprop(tmp_path, [
        _edgeprop_row(),
        _edgeprop_row(**{"Date of Sale": "16 Mar 2019"}),
        _edgeprop_row(**{"Date of Sale": "17 Mar 2019"}),
    ])
    raw_dir = tmp_path / "ura_raw"
    raw_dir.mkdir()
    out_path, _ = gen.generate("27", canonical, edgeprop, raw_dir, tmp_path)
    section = _band_section(out_path.read_text(encoding="utf-8"), "100to130")
    assert "≈3BR" in section
