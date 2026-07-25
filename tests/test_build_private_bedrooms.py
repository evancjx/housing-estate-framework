"""Tests for models/build_private_bedrooms.py — normalisation, join hierarchy,
provenance, and exclusion rules, on tiny synthetic fixtures."""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"))

import build_private_bedrooms as bpb  # noqa: E402

URA_COLUMNS = ["project_name", "street_name", "postal_district", "property_type",
               "tenure", "project_age_years", "sale_month", "planning_area",
               "market_segment", "floor_level", "type_of_sale", "type_of_area",
               "transacted_price", "area_sqm", "unit_price_psf", "unit_price_psm"]
EP_COLUMNS = ["Project", "planning_area", "Postal District", "Date of Sale", "Address",
              "Street", "Bedrooms", "Unit Price ($psf)", "Price ($)", "Type", "Tenure",
              "Sale Type", "Area (sqft)", "Area (sqm)", "Type of Area",
              "Purchaser Address", "Source", "source_quality", "source_url", "source_slug"]


def _ura_row(project="ALPHA GRAND", district="10", month="2023-05", price=1_500_000,
             sqm=85.0, ptype="Condominium"):
    return {"project_name": project, "street_name": "X ROAD", "postal_district": district,
            "property_type": ptype, "tenure": "99 yrs", "project_age_years": 5,
            "sale_month": month, "planning_area": "AREA", "market_segment": "RCR",
            "floor_level": "10-15", "type_of_sale": "Resale", "type_of_area": "Strata",
            "transacted_price": price, "area_sqm": sqm,
            "unit_price_psf": 0, "unit_price_psm": 0}


def _ep_row(project="Alpha Grand", district="10", date="15 May 2023", price=1_500_000,
            sqm=85.0, bedrooms="3", ptype="Condominium", address="X ROAD #10-01"):
    return {"Project": project, "planning_area": "AREA", "Postal District": district,
            "Date of Sale": date, "Address": address, "Street": "X ROAD",
            "Bedrooms": bedrooms, "Unit Price ($psf)": 1000, "Price ($)": price,
            "Type": ptype, "Tenure": "99 yrs", "Sale Type": "Resale",
            "Area (sqft)": round(sqm * bpb.SQM_TO_SQFT), "Area (sqm)": sqm,
            "Type of Area": "Strata", "Purchaser Address": "HDB", "Source": "URA",
            "source_quality": "not_clean", "source_url": "u", "source_slug": "s"}


def _build(tmp_path, ura_rows, ep_rows, mix_rows=None):
    ura_path = tmp_path / "ura.csv"
    ep_path = tmp_path / "ep.csv"
    mix_path = tmp_path / "mix.csv"
    pd.DataFrame(ura_rows, columns=URA_COLUMNS).to_csv(ura_path, index=False)
    pd.DataFrame(ep_rows, columns=EP_COLUMNS).to_csv(ep_path, index=False)
    if mix_rows is not None:
        pd.DataFrame(mix_rows).to_csv(mix_path, index=False)
    return bpb.build(ura_path, ep_path, mix_path)


def _mix_row(norm="ALPHA GRAND", district="10", bedrooms=2, lo=400, hi=800):
    return {"project_name_norm": norm, "postal_district": district, "bedrooms": bedrooms,
            "min_sqft": lo, "max_sqft": hi, "source_url": "https://example.com",
            "retrieved_date": "2026-07-10", "note": ""}


# ---------- normalisation ----------

def test_normalise_project_name_cases():
    assert bpb.normalise_project_name("J'DEN") == "JDEN"
    assert bpb.normalise_project_name("SKYE @ HOLLAND") == "SKYE AT HOLLAND"
    assert bpb.normalise_project_name("The Continuum") == "CONTINUUM"
    assert bpb.normalise_project_name("PARC ESTA II") == "PARC ESTA 2"
    assert bpb.normalise_project_name("Meadows @ Peirce") == "MEADOWS AT PEIRCE"
    assert bpb.normalise_project_name("ENCHANTÉ") == "ENCHANTE"  # transliterate, don't drop
    n = bpb.normalise_project_name
    for name in ("J'DEN", "SKYE @ HOLLAND", "THE BROOKS I & II"):
        assert n(n(name)) == n(name)  # idempotent


def test_aggressive_key_strips_suffix_only_as_fallback():
    assert bpb.aggressive_key("KOVAN RESIDENCES") == "KOVAN"
    assert bpb.aggressive_key("THE BALMORAL CONDOMINIUM") == "BALMORAL"
    # never strips a lone token to nothing
    assert bpb.aggressive_key("RESIDENCES") == "RESIDENCES"


def test_aggressive_fallback_rejected_on_district_collision(tmp_path):
    # two EdgeProp projects in D10 share aggressive key BALMORAL -> no mapping
    out = _build(tmp_path,
                 [_ura_row(project="BALMORAL", price=2_000_000, sqm=100.0)],
                 [_ep_row(project="Balmoral Residences", price=2_000_000, sqm=100.0),
                  _ep_row(project="Balmoral Condominium", price=2_000_000, sqm=100.0,
                          address="Y ROAD #01-01")])
    row = out[out["data_source"] == "ura_private"].iloc[0]
    assert row["bedroom_source"] == "unknown"
    assert pd.isna(row["bedrooms"])


def test_aggressive_fallback_accepted_when_unique(tmp_path):
    out = _build(tmp_path,
                 [_ura_row(project="THE LUMOS")],
                 [_ep_row(project="Lumos Residences")])
    row = out[out["data_source"] == "ura_private"].iloc[0]
    assert row["bedroom_source"] == "edgeprop_exact"
    assert row["bedrooms"] == 3


# ---------- join hierarchy ----------

def test_exact_match_wins_over_label_and_mix(tmp_path):
    ep = [_ep_row(bedrooms="3"),
          _ep_row(bedrooms="2", price=999, address="A"),   # band-label noise
          _ep_row(bedrooms="2", price=998, address="B")]
    out = _build(tmp_path, [_ura_row()], ep,
                 mix_rows=[_mix_row(bedrooms=1, lo=100, hi=2000)])
    row = out[out["data_source"] == "ura_private"].iloc[0]
    assert row["bedroom_source"] == "edgeprop_exact"
    assert row["bedrooms"] == 3


def test_exact_modal_on_duplicate_key(tmp_path):
    ep = [_ep_row(bedrooms="3", address="A"), _ep_row(bedrooms="3", address="B"),
          _ep_row(bedrooms="2", address="C")]
    out = _build(tmp_path, [_ura_row()], ep)
    assert out[out["data_source"] == "ura_private"].iloc[0]["bedrooms"] == 3


def test_exact_tie_falls_to_band_label(tmp_path):
    # exact key candidates tie 3 vs 2 -> tier 1 refuses; band 70-100 sqm has
    # 3 more rows agreeing on 3 => label 3 (share 3/5 >= 0.6 incl. tie rows)
    ep = [_ep_row(bedrooms="3", address="A"), _ep_row(bedrooms="2", address="B"),
          _ep_row(bedrooms="3", price=1, sqm=90.0, address="C"),
          _ep_row(bedrooms="3", price=2, sqm=91.0, address="D"),
          _ep_row(bedrooms="3", price=3, sqm=92.0, address="E")]
    out = _build(tmp_path, [_ura_row()], ep)
    row = out[out["data_source"] == "ura_private"].iloc[0]
    assert row["bedroom_source"] == "edgeprop_band_label"
    assert row["bedrooms"] == 3


def test_band_label_requires_min_n_and_share(tmp_path):
    # single EdgeProp row in the band (n=1 < MIN_LABEL_N) and no exact match
    ep = [_ep_row(bedrooms="3", price=999_999)]
    out = _build(tmp_path, [_ura_row()], ep)
    assert out[out["data_source"] == "ura_private"].iloc[0]["bedroom_source"] == "unknown"


def test_unit_mix_inclusive_boundaries_and_overlap(tmp_path):
    # 85 sqm = 914.93 sqft. Inclusive bounds hit at exactly the computed sqft.
    sqft = 85.0 * bpb.SQM_TO_SQFT
    hit_lo = [_mix_row(bedrooms=2, lo=sqft, hi=sqft + 100)]
    hit_hi = [_mix_row(bedrooms=2, lo=sqft - 100, hi=sqft)]
    miss = [_mix_row(bedrooms=2, lo=sqft + 0.01, hi=sqft + 100)]
    overlap = [_mix_row(bedrooms=2, lo=800, hi=1000), _mix_row(bedrooms=3, lo=900, hi=1100)]
    for mix, expected in [(hit_lo, "research_unit_mix"), (hit_hi, "research_unit_mix"),
                          (miss, "unknown"), (overlap, "unknown")]:
        out = _build(tmp_path, [_ura_row()], [_ep_row(project="Other", district="09")], mix)
        assert out[out["data_source"] == "ura_private"].iloc[0]["bedroom_source"] == expected


# ---------- exclusions & provenance ----------

def test_placeholder_stays_unknown(tmp_path):
    out = _build(tmp_path,
                 [_ura_row(project="RESIDENTIAL APARTMENTS")],
                 [_ep_row(project="Residential Apartments")],
                 mix_rows=[_mix_row(norm="RESIDENTIAL APARTMENTS", lo=100, hi=2000)])
    row = out[out["data_source"] == "ura_private"].iloc[0]
    assert row["bedroom_source"] == "unknown"
    assert pd.isna(row["bedrooms"])


def test_executive_condominium_rows_excluded(tmp_path):
    ep = [_ep_row(ptype="Executive Condominium", date="15 May 2019")]
    out = _build(tmp_path, [_ura_row()], ep)
    assert (out[out["data_source"] == "ura_private"]["bedroom_source"] == "unknown").all()
    assert (out["data_source"] == "edgeprop_backfill").sum() == 0


def test_landed_ura_rows_excluded(tmp_path):
    out = _build(tmp_path,
                 [_ura_row(), _ura_row(project="LANDED VILLA", ptype="Terrace House")],
                 [_ep_row()])
    assert "LANDED VILLA" not in set(out["project_name"])


def test_dash_bedrooms_never_matches(tmp_path):
    out = _build(tmp_path, [_ura_row()], [_ep_row(bedrooms="-")])
    assert out[out["data_source"] == "ura_private"].iloc[0]["bedroom_source"] == "unknown"


def test_repeated_edgeprop_header_row_is_excluded(tmp_path):
    shifted_header = _ep_row(
        project="Tenure",
        district="",
        date="17 Jun 2020",
        ptype="Bedrooms",
        address="Resale",
    )
    shifted_header["Tenure"] = "Type of Sale"
    out = _build(tmp_path, [_ura_row()], [shifted_header])
    assert "TENURE" not in set(out["project_name"])
    assert (out["data_source"] == "edgeprop_backfill").sum() == 0


def test_no_bedrooms_without_source_and_vice_versa(tmp_path):
    out = _build(tmp_path,
                 [_ura_row(), _ura_row(project="NOMATCH TOWERS", price=42)],
                 [_ep_row(), _ep_row(project="Backfill Court", date="10 Jan 2019",
                                     bedrooms="2", address="Z")])
    known = out["bedroom_source"] != "unknown"
    assert out.loc[known, "bedrooms"].notna().all()
    assert out.loc[~known, "bedrooms"].isna().all()


# ---------- backfill window ----------

def test_backfill_only_2019_2020(tmp_path):
    ep = [_ep_row(project="Old Court", date="10 Jan 2019", address="A"),
          _ep_row(project="Old Court", date="10 Jun 2020", address="B"),
          _ep_row(project="Old Court", date="10 Jun 2021", address="C")]
    out = _build(tmp_path, [_ura_row()], ep)
    bf = out[out["data_source"] == "edgeprop_backfill"]
    assert len(bf) == 2
    assert set(bf["sale_month"]) == {"2019-01", "2020-06"}
    assert (bf["bedroom_source"] == "edgeprop_exact").all()


# ---------- determinism ----------

def test_deterministic_output(tmp_path):
    ura = [_ura_row(), _ura_row(project="BETA VIEW", price=800_000, sqm=60.0)]
    ep = [_ep_row(), _ep_row(project="Beta View", price=800_000, sqm=60.0,
                             bedrooms="2", address="B"),
          _ep_row(project="Gamma Park", date="05 Mar 2019", bedrooms="1", address="C")]
    a = _build(tmp_path, ura, ep)
    b = _build(tmp_path, ura, ep)
    pd.testing.assert_frame_equal(a, b)


# ---------- real data gate (slow; guards the 95% target + reproducibility) ----------

@pytest.mark.integration
@pytest.mark.skipif(not bpb.DEFAULT_OUT.exists(),
                    reason="private_transactions_bedrooms.csv not yet committed")
def test_committed_data_attribution_target():
    out = bpb.build(bpb.DEFAULT_PRIVATE, bpb.DEFAULT_EDGEPROP, bpb.DEFAULT_UNIT_MIX)
    committed = pd.read_csv(bpb.DEFAULT_OUT, dtype={"postal_district": str})
    rebuilt = out.copy()
    rebuilt["postal_district"] = rebuilt["postal_district"].astype(str)
    # regenerating from committed inputs must reproduce the committed dataset
    assert len(rebuilt) == len(committed)
    pd.testing.assert_series_equal(
        rebuilt["bedroom_source"].reset_index(drop=True),
        committed["bedroom_source"].reset_index(drop=True), check_names=False)
    attributed = (out["bedroom_source"] != "unknown").mean()
    print(out["bedroom_source"].value_counts().to_string())
    assert attributed >= 0.95, f"attribution {attributed:.2%} below 95% target"
