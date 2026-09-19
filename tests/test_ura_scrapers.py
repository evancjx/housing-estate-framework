import pandas as pd
from argparse import Namespace
import pytest

from scrapers import ingest_ura_raw, run_download
from scrapers.ura_pmi_api import flatten_project_transactions
from scrapers.ura_pmi_playwright import normalize_prop_types, raw_filename
from sg_estate import source_receipts
from sg_estate.contracts import ContractError


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
            },
        ]
    )

    deduped, dropped = ingest_ura_raw.dedupe_transactions(df)

    assert len(deduped) == 1
    assert dropped == 1


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


def test_run_writes_derived_receipt_with_emitted_sale_month_coverage(tmp_path):
    raw = tmp_path / "pmi_d15_2021-2026.csv"
    output = tmp_path / "renamed-output.csv"
    pd.DataFrame(
        {
            "Project": ["A", "B", "A"],
            "Type": ["Condominium"] * 3,
            "Postal District": ["15"] * 3,
            "Price ($)": ["1000000", "1200000", "1000000"],
            "Area (sqm)": ["80", "90", "80"],
            "Date of Sale": ["Jan-2025", "Mar-2026", "Jan-2025"],
            "Tenure": ["Freehold"] * 3,
        }
    ).to_csv(raw, index=False)

    ingest_ura_raw.run(
        Namespace(
            out=str(output),
            files=[str(raw)],
            raw_dir=str(tmp_path),
            merge=False,
            source_quality=None,
        )
    )

    receipt = source_receipts.read_source_receipt(
        source_receipts.receipt_path_for(output), output_path=output
    )
    assert receipt["dataset_id"] == "ura_private.csv"
    assert receipt["authority"] == "URA PMI"
    assert receipt["cache_state"] == "derived"
    assert receipt["retrieved_at"] is None
    assert receipt["coverage_start"] == "2025-01"
    assert receipt["coverage_end"] == "2026-03"
    assert receipt["row_count"] == 2
    assert receipt["validation_status"] == "not_run"
    assert str(tmp_path) not in receipt["source_identity"]
    assert "acquisition completeness not asserted" in receipt["source_identity"]


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


def test_ingest_preserves_unknown_sale_month_and_project_age(tmp_path):
    raw = tmp_path / "pmi_d15_2021-2026.csv"
    pd.DataFrame(
        {
            "Project": ["UNKNOWN EVIDENCE"],
            "Type": ["Condominium"],
            "Postal District": ["15"],
            "Price ($)": ["1000000"],
            "Area (sqm)": ["80"],
            "Tenure": ["Freehold"],
        }
    ).to_csv(raw, index=False)

    out = ingest_ura_raw.ingest_file(raw)

    assert pd.isna(out.iloc[0]["sale_month"])
    assert pd.isna(out.iloc[0]["project_age_years"])
    assert out.iloc[0]["sale_month_status"] == "unknown"
    assert out.iloc[0]["project_age_status"] == "unknown_no_completion_evidence"
    assert out.iloc[0]["property_type_group"] == "3"


def test_direct_canonical_ingest_is_rejected_before_write(tmp_path):
    raw = tmp_path / "pmi_d15_2021-2026.csv"
    raw.write_text("Price ($),Area (sqm)\n1000000,80\n", encoding="utf-8")
    canonical = ingest_ura_raw.CANONICAL_OUTPUT
    before = canonical.read_bytes()

    with pytest.raises(ContractError, match="Direct canonical URA writes are disabled"):
        ingest_ura_raw.run(
            Namespace(
                out=str(canonical),
                files=[str(raw)],
                raw_dir=str(tmp_path),
                merge=False,
                source_quality=None,
                attempt_manifest=None,
                promote_run=None,
            )
        )

    assert canonical.read_bytes() == before
