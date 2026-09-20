"""URA PMI exports are not always UTF-8.

data/raw/ura/pmi_d11_2021-2026.csv is Latin-1: the D11 project ENCHANTÉ
carries byte 0xC9 in 25 rows. scrapers/ingest_ura_raw.py already falls back,
but the district report generator read raw exports as UTF-8 and would die on
any district whose project names carry an accent.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "models"))

import gen_canberra_crescent_d27_html as generator  # noqa: E402
from scrapers import ingest_ura_raw  # noqa: E402

COMMITTED_D11 = ROOT / "data" / "raw" / "ura" / "pmi_d11_2021-2026.csv"


def _latin1_export(path, district="11"):
    pd.DataFrame([{
        "Project Name": "ENCHANTÉ",
        "Transacted Price ($)": "2,000,000",
        "Area (SQFT)": "1,076.39",
        "Unit Price ($ PSF)": "1,858",
        "Sale Date": "Aug-26",
        "Street Name": "EVELYN ROAD",
        "Type of Sale": "Resale",
        "Type of Area": "Strata",
        "Area (SQM)": "100",
        "Unit Price ($ PSM)": "20,000",
        "Nett Price($)": "-",
        "Property Type": "Apartment",
        "Number of Units": "1",
        "Tenure": "Freehold",
        "Postal District": district,
        "Market Segment": "Rest of Central Region",
        "Floor Level": "06 to 10",
    }]).to_csv(path, index=False, encoding="latin-1")


def test_committed_d11_export_is_latin1_not_utf8():
    raw = COMMITTED_D11.read_bytes()
    with pytest.raises(UnicodeDecodeError):
        raw.decode("utf-8")
    assert "ENCHANTÉ" in raw.decode("latin-1")


def test_ingester_reads_a_latin1_export(tmp_path):
    path = tmp_path / "pmi_d11_2021-2026.csv"
    _latin1_export(path)

    out = ingest_ura_raw.ingest_file(path, "11")

    assert out["project_name"].tolist() == ["ENCHANTÉ"]


def test_district_report_generator_reads_a_latin1_export(tmp_path):
    # The generator reports District 27; the point here is the Latin-1 bytes.
    raw = tmp_path / "pmi_d27_2021-2026.csv"
    _latin1_export(raw, district="27")
    edgeprop = tmp_path / "edgeprop.csv"
    pd.DataFrame(columns=["Project", "Street", "Type", "Postal District", "Date of Sale",
                          "Price ($)", "Area (sqm)", "Bedrooms"]).to_csv(edgeprop, index=False)

    txns = generator.load_district_transactions(raw, edgeprop)

    assert "ENCHANTÉ" in set(txns["project_name"])
