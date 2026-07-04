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

    out = ingest_ura_raw.ingest_file(raw)

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
