import argparse

import pandas as pd

from scrapers import ingest_ura_raw, run_download
from scrapers.ura_pmi_api import flatten_project_transactions
from scrapers.ura_pmi_playwright import normalize_prop_types, raw_filename


def test_landed_property_type_aliases_and_raw_filenames():
    assert normalize_prop_types(["landed", "strata-landed", "landed"]) == ["1", "2"]
    assert raw_filename("15", "2021", "2026", "landed") == (
        "pmi_d15_landed_non_strata_2021-2026.csv"
    )
    assert raw_filename("15", "2021", "2026", "strata_landed") == (
        "pmi_d15_strata_landed_2021-2026.csv"
    )

    # Existing apartment/condo downloads keep the legacy filename.
    assert raw_filename("15", "2021", "2026", "apt_condo") == "pmi_d15_2021-2026.csv"


def test_ingest_landed_pmi_file_preserves_property_type_and_schema(tmp_path):
    raw = tmp_path / "pmi_d15_landed_non_strata_2021-2026.csv"
    pd.DataFrame(
        {
            "Project": ["LANDED TEST"],
            "Street": ["TEST ROAD"],
            "Type": ["Terrace House"],
            "Postal District": ["15"],
            "Price ($)": ["3,200,000"],
            "Area (sqm)": ["210"],
            "Date of Sale": ["Jan-2025"],
            "Tenure": ["Freehold"],
            "Sale Type": ["Resale"],
            "Type of Area": ["Land"],
            "Market Segment": ["Outside Central Region"],
        }
    ).to_csv(raw, index=False)

    out = ingest_ura_raw.ingest_file(raw, source_quality="not_clean")

    assert list(out.columns[:7]) == [
        "planning_area",
        "transacted_price",
        "area_sqm",
        "property_type",
        "tenure",
        "project_age_years",
        "sale_month",
    ]
    row = out.iloc[0]
    assert row["planning_area"] == "MARINE PARADE"
    assert row["property_type"] == "Terrace House"
    assert row["type_of_area"] == "Land"
    assert row["market_segment"] == "Outside Central Region"
    assert row["transacted_price"] == 3200000
    assert row["area_sqm"] == 210
    assert row["sale_month"] == "2025-01"


def test_ingest_edgeprop_style_file_converts_sqft_and_preserves_context(tmp_path):
    raw = tmp_path / "edgeprop_kembangan.csv"
    pd.DataFrame(
        {
            "Project": ["KEMBANGAN ESTATE"],
            "planning_area": ["BEDOK"],
            "Postal District": ["14"],
            "Date of Sale": ["7 Oct 2020"],
            "Street": ["XX JALAN KEMBANGAN"],
            "Unit Price ($psf)": ["965"],
            "Price ($)": ["3,760,000"],
            "Type": ["Terrace House"],
            "Tenure": ["Freehold"],
            "Sale Type": ["Resale"],
            "Area (sqft)": ["3,895"],
            "Type of Area": ["Land"],
            "Purchaser Address": ["Private"],
            "Source": ["URA"],
        }
    ).to_csv(raw, index=False)

    out = ingest_ura_raw.ingest_file(raw, source_quality="not_clean")

    row = out.iloc[0]
    assert row["planning_area"] == "BEDOK"
    assert row["project_name"] == "KEMBANGAN ESTATE"
    assert row["street_name"] == "XX JALAN KEMBANGAN"
    assert row["property_type"] == "Terrace House"
    assert row["transacted_price"] == 3760000
    assert round(row["area_sqm"], 3) == 361.857
    assert row["unit_price_psf"] == 965
    assert row["type_of_area"] == "Land"
    assert row["purchaser_address"] == "Private"
    assert row["source"] == "URA"
    assert row["source_quality"] == "not_clean"
    assert row["sale_month"] == "2020-10"


def test_ingest_edgeprop_unit_schema_preserves_exact_unit_provenance(tmp_path):
    raw = tmp_path / "edgeprop_condo_units.csv"
    pd.DataFrame(
        {
            "Project": ["TEST RESIDENCES"],
            "planning_area": ["NOVENA"],
            "Postal District": ["11"],
            "Date of Sale": ["22 Jun 2026"],
            "Address": ["10 TEST ROAD #06-15"],
            "Street": ["10 TEST ROAD"],
            "unit_number": ["#06-15"],
            "unit_floor": ["06"],
            "unit_stack": ["15"],
            "unit_number_status": ["exact"],
            "unit_number_source": ["edgeprop_address"],
            "Unit Price ($psf)": ["1,830"],
            "Price ($)": ["1,536,500"],
            "Type": ["Condominium"],
            "Tenure": ["Freehold"],
            "Sale Type": ["Resale"],
            "Area (sqft)": ["840"],
            "Type of Area": ["Strata"],
            "Purchaser Address": ["Private"],
            "Source": ["URA"],
            "source_quality": ["not_clean"],
        }
    ).to_csv(raw, index=False)

    out = ingest_ura_raw.ingest_file(raw)

    assert len(out) == 1
    row = out.iloc[0]
    assert row["address"] == "10 TEST ROAD #06-15"
    assert row["street_name"] == "10 TEST ROAD"
    assert row["unit_number"] == "#06-15"
    assert str(row["unit_floor"]).zfill(2) == "06"
    assert str(row["unit_stack"]).zfill(2) == "15"
    assert row["unit_number_status"] == "exact"
    assert row["unit_number_source"] == "edgeprop_address"


def test_api_project_records_flatten_to_ingestor_schema():
    rows = flatten_project_transactions([
        {
            "project": "API LANDED TEST",
            "street": "TEST ROAD",
            "marketSegment": "RCR",
            "transaction": [
                {
                    "propertyType": "Strata Terrace",
                    "district": "3",
                    "price": "3210000",
                    "area": "188",
                    "contractDate": "0125",
                    "tenure": "Freehold",
                    "typeOfSale": "3",
                    "typeOfArea": "Strata",
                    "noOfUnits": "1",
                }
            ],
        }
    ])

    assert rows == [
        {
            "project_name": "API LANDED TEST",
            "street_name": "TEST ROAD",
            "property_type": "Strata Terrace House",
            "postal_district": "03",
            "market_segment": "RCR",
            "floor_level": "",
            "transacted_price": "3210000",
            "area_sqm": "188",
            "sale_month": "2025-01",
            "tenure": "Freehold",
            "type_of_sale": "3",
            "type_of_area": "Strata",
            "n_units": "1",
        }
    ]


def test_dedupe_transactions_runs_without_merge_mode():
    df = pd.DataFrame(
        [
            {
                "planning_area": "QUEENSTOWN",
                "transacted_price": 3210000,
                "area_sqm": 188,
                "sale_month": "2025-01",
                "property_type": "Terrace House",
                "project_name": "A",
                "street_name": "TEST ROAD",
                "floor_level": "",
                "_source_file": "pmi_d03_2021-2026.csv",
            },
            {
                "planning_area": "QUEENSTOWN",
                "transacted_price": 3210000,
                "area_sqm": 188,
                "sale_month": "2025-01",
                "property_type": "Terrace House",
                "project_name": "A",
                "street_name": "TEST ROAD",
                "floor_level": "",
                "_source_file": "pmi_d03_2024-2026.csv",
            },
        ]
    )

    deduped, dropped = ingest_ura_raw.dedupe_transactions(df)

    assert len(deduped) == 1
    assert dropped == 1


PMI_UNIT = {
    "planning_area": "BEDOK",
    "transacted_price": 2358000,
    "area_sqm": 108,
    "sale_month": "2025-01",
    "property_type": "Apartment",
    "project_name": "SCENECA RESIDENCE",
    "street_name": "TANAH MERAH KECHIL LINK",
    "floor_level": "01 to 05",
    "type_of_area": "Strata",
}


def test_dedupe_keeps_identical_units_within_one_export():
    # URA PMI rows carry no unit number: two units sold on identical terms
    # in one export are two transactions, not a duplicate.
    source = "pmi_d16_2021-2026.csv"
    df = pd.DataFrame([{**PMI_UNIT, "_source_file": source}] * 2)

    deduped, dropped = ingest_ura_raw.dedupe_transactions(df)

    assert len(deduped) == 2
    assert dropped == 0


def test_dedupe_keeps_most_repeats_seen_in_any_single_export():
    other = {**PMI_UNIT, "transacted_price": 1750000, "area_sqm": 70}
    df = pd.DataFrame(
        [{**PMI_UNIT, "_source_file": "pmi_d16_2021-2026.csv"}] * 2
        + [{**other, "_source_file": "pmi_d16_2021-2026.csv"}]
        + [{**PMI_UNIT, "_source_file": "pmi_d16_2024-2026.csv"}]
        + [{**other, "_source_file": "pmi_d16_2024-2026.csv"}]
    )

    deduped, dropped = ingest_ura_raw.dedupe_transactions(df)

    assert (deduped["transacted_price"] == 2358000).sum() == 2
    assert (deduped["transacted_price"] == 1750000).sum() == 1
    assert dropped == 2
    assert "_source_file" not in deduped.columns


def test_dedupe_merge_restores_units_collapsed_in_existing_output():
    # Rows read back from an existing ura_private.csv have no source file.
    df = pd.DataFrame(
        [PMI_UNIT]
        + [{**PMI_UNIT, "_source_file": "pmi_d16_2025-2026.csv"}] * 2
    )

    deduped, dropped = ingest_ura_raw.dedupe_transactions(df)

    assert len(deduped) == 2
    assert dropped == 1


def test_dedupe_legacy_blank_rows_only_match_as_many_typed_rows():
    blank = {**PMI_UNIT, "type_of_area": pd.NA}
    df = pd.DataFrame(
        [blank] * 2
        + [{**PMI_UNIT, "_source_file": "pmi_d16_2025-2026.csv"}]
    )

    deduped, dropped = ingest_ura_raw.dedupe_transactions(df)

    assert len(deduped) == 2
    assert (deduped["type_of_area"] == "Strata").sum() == 1
    assert dropped == 1


def test_run_keeps_identical_units_and_drops_overlapping_exports(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    pmi_row = {
        "Project Name": "SCENECA RESIDENCE",
        "Transacted Price ($)": "2,358,000",
        "Area (SQFT)": "1,162.51",
        "Unit Price ($ PSF)": "2,028",
        "Sale Date": "Jan-25",
        "Street Name": "TANAH MERAH KECHIL LINK",
        "Type of Sale": "New Sale",
        "Type of Area": "Strata",
        "Area (SQM)": "108",
        "Property Type": "Apartment",
        "Number of Units": "1",
        "Tenure": "99 yrs lease commencing from 2021",
        "Postal District": "16",
        "Market Segment": "Outside Central Region",
        "Floor Level": "01 to 05",
    }
    other_row = {**pmi_row, "Transacted Price ($)": "1,750,000", "Area (SQM)": "70"}
    for name in ("pmi_d16_2021-2026.csv", "pmi_d16_2024-2026.csv"):
        pd.DataFrame([pmi_row, pmi_row, other_row]).to_csv(raw_dir / name, index=False)
    out = tmp_path / "ura_private.csv"

    ingest_ura_raw.run(
        argparse.Namespace(
            files=None, raw_dir=str(raw_dir), out=str(out), merge=False,
            source_quality=None,
        )
    )

    written = pd.read_csv(out)
    assert (written["transacted_price"] == 2358000).sum() == 2
    assert (written["transacted_price"] == 1750000).sum() == 1
    assert not {"_source_file", "_occurrence"} & set(written.columns)


def test_dedupe_keeps_distinct_exact_condo_units_apart():
    common = {
        "planning_area": "NOVENA",
        "transacted_price": 1536500,
        "area_sqm": 78.039,
        "sale_month": "2026-06",
        "property_type": "Condominium",
        "project_name": "TEST RESIDENCES",
        "street_name": "10 TEST ROAD",
    }
    df = pd.DataFrame(
        [
            {**common, "address": "10 TEST ROAD #06-15", "unit_number": "#06-15"},
            {**common, "address": "10 TEST ROAD #07-15", "unit_number": "#07-15"},
        ]
    )

    deduped, dropped = ingest_ura_raw.dedupe_transactions(df)

    assert len(deduped) == 2
    assert dropped == 0


def test_dedupe_keeps_land_and_strata_landed_apart():
    df = pd.DataFrame(
        [
            {
                "planning_area": "MARINE PARADE",
                "transacted_price": 3210000,
                "area_sqm": 188,
                "sale_month": "2025-01",
                "property_type": "Terrace House",
                "type_of_area": "Land",
                "project_name": "A",
                "street_name": "TEST ROAD",
                "floor_level": "",
            },
            {
                "planning_area": "MARINE PARADE",
                "transacted_price": 3210000,
                "area_sqm": 188,
                "sale_month": "2025-01",
                "property_type": "Terrace House",
                "type_of_area": "Strata",
                "project_name": "A",
                "street_name": "TEST ROAD",
                "floor_level": "",
            },
        ]
    )

    deduped, dropped = ingest_ura_raw.dedupe_transactions(df)

    assert len(deduped) == 2
    assert dropped == 0


def test_dedupe_matches_legacy_blank_type_of_area_to_populated_row():
    df = pd.DataFrame(
        [
            {
                "planning_area": "MARINE PARADE",
                "transacted_price": 3210000,
                "area_sqm": 188,
                "sale_month": "2025-01",
                "property_type": "Terrace House",
                "type_of_area": pd.NA,
                "project_name": "A",
                "street_name": "TEST ROAD",
                "floor_level": "",
            },
            {
                "planning_area": "MARINE PARADE",
                "transacted_price": 3210000,
                "area_sqm": 188,
                "sale_month": "2025-01",
                "property_type": "Terrace House",
                "type_of_area": "Strata",
                "project_name": "A",
                "street_name": "TEST ROAD",
                "floor_level": "",
            },
        ]
    )

    deduped, dropped = ingest_ura_raw.dedupe_transactions(df)

    assert len(deduped) == 1
    assert dropped == 1
    assert deduped.iloc[0]["type_of_area"] == "Strata"


def test_run_download_api_subprocess_passes_selected_districts(monkeypatch, tmp_path):
    captured = {}

    class Result:
        returncode = 0

    def fake_run(cmd):
        captured["cmd"] = cmd
        return Result()

    monkeypatch.setattr(run_download.subprocess, "run", fake_run)

    assert run_download.run_api_subprocess(tmp_path, ["3"], ["15", "16"])

    cmd = captured["cmd"]
    assert "--districts" in cmd
    district_pos = cmd.index("--districts")
    assert cmd[district_pos:district_pos + 3] == ["--districts", "15", "16"]


def _ingest_args(raw, out, **overrides):
    import argparse

    values = dict(
        files=[str(raw)], raw_dir=None, out=str(out), merge=False,
        source_quality=None, allow_coverage_loss=False,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def _write_pmi(path, rows):
    path.write_text(
        "Project,Street,Type,Postal District,Market Segment,Tenure,Sale Type,"
        "No. of Units,Price ($),Area (sqm),Unit Price ($psm),Date of Sale,Floor\n"
        + "".join(
            f"P{i},S,{kind},{district},OCR,Freehold,Resale,1,1000000,100,10000,Jan-25,01-05\n"
            for i, (district, kind) in enumerate(rows)
        ),
        encoding="utf-8",
    )


def test_rebuild_refuses_to_drop_existing_district_type_groups(tmp_path):
    import pytest

    out = tmp_path / "ura_private.csv"
    full = tmp_path / "full.csv"
    _write_pmi(full, [("15", "Condominium"), ("16", "Condominium"), ("16", "Detached House")])
    ingest_ura_raw.run(_ingest_args(full, out))
    before = out.read_bytes()

    partial = tmp_path / "partial.csv"
    _write_pmi(partial, [("15", "Condominium")])
    with pytest.raises(SystemExit, match="drop 2 location/property-type"):
        ingest_ura_raw.run(_ingest_args(partial, out))
    assert out.read_bytes() == before

    ingest_ura_raw.run(_ingest_args(partial, out, allow_coverage_loss=True))
    assert len(ingest_ura_raw.pd.read_csv(out)) == 1


def test_file_without_sale_date_is_skipped_not_backfilled(tmp_path):
    raw = tmp_path / "no_date.csv"
    raw.write_text(
        "Project,Postal District,Type,Price ($),Area (sqm)\nP,15,Condominium,1000000,100\n",
        encoding="utf-8",
    )
    assert ingest_ura_raw.ingest_file(raw).empty


def test_write_csv_atomic_leaves_no_temp_files(tmp_path):
    out = tmp_path / "x.csv"
    ingest_ura_raw.write_csv_atomic(ingest_ura_raw.pd.DataFrame({"a": [1]}), out)
    assert [p.name for p in tmp_path.iterdir()] == ["x.csv"]
