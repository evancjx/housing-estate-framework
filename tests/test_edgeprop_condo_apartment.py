import argparse
import csv
from pathlib import Path

from scrapers import edgeprop_condo_apartment_playwright as condo


FIXTURE = Path(__file__).parent / "fixtures/edgeprop/condo_unit_transactions.txt"


def test_discover_project_links_keeps_condo_apartment_detail_pages_only():
    html = """
    <a href="/condo-apartment/all">All</a>
    <a href="/condo-apartment/treasure-at-tampines">TREASURE AT TAMPINES</a>
    <a href="/condo-apartment/treasure-at-tampines">Duplicate</a>
    <a href="/landed-house/kembangan-estate">Not condo</a>
    <a href="https://www.edgeprop.sg/condo-apartment/normanton-park">NORMANTON PARK</a>
    """

    links = condo.discover_project_links(html)

    assert [link.name for link in links] == ["TREASURE AT TAMPINES", "NORMANTON PARK"]
    assert links[0].url == "https://www.edgeprop.sg/condo-apartment/treasure-at-tampines"
    assert links[0].slug == "treasure-at-tampines"


def test_parse_condo_rendered_transaction_text():
    text = """
    Sales Transaction of TREASURE AT TAMPINES
    Date
    Area (sqft)
    Bedrooms
    Price (S$ psf)
    Price (S$)
    Type of Sale
    Address
    Type of Area
    Purchaser Address
    Source
    22 JUN 2026
    840
    3
    1,830
    1,536,500
    Resale
    55 TAMPINES LANE #06-XX
    Strata\tPrivate
    URA
    """

    rows = condo.parse_transaction_text(
        text,
        project_name="TREASURE AT TAMPINES",
        planning_area="Tampines",
        postal_district="18",
        property_type="Condominium",
        tenure="99 yrs from 29/11/2018",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["Project"] == "TREASURE AT TAMPINES"
    assert row["planning_area"] == "TAMPINES"
    assert row["Postal District"] == "18"
    assert row["Date of Sale"] == "22 Jun 2026"
    assert row["Address"] == "55 TAMPINES LANE #06-XX"
    assert row["Street"] == "55 TAMPINES LANE"
    assert row["unit_number"] == ""
    assert row["unit_number_status"] == "masked"
    assert row["unit_number_source"] == "edgeprop_address"
    assert row["Bedrooms"] == "3"
    assert row["Unit Price ($psf)"] == 1830
    assert row["Price ($)"] == 1536500
    assert row["Type"] == "Condominium"
    assert row["Tenure"] == "99 yrs from 29/11/2018"
    assert row["Sale Type"] == "Resale"
    assert row["Area (sqft)"] == 840
    assert row["Area (sqm)"] == 78.039
    assert row["Type of Area"] == "Strata"
    assert row["Purchaser Address"] == "Private"
    assert row["Source"] == "URA"


def test_parse_condo_transaction_text_with_separate_area_and_buyer_lines():
    text = """
    17 JUN 2026
    592
    2
    1,740
    1,030,000
    Resale
    15 TAMPINES LANE #11-XX
    Strata
    HDB
    URA
    """

    rows = condo.parse_transaction_text(text, project_name="TEST", property_type="Apartment")

    assert len(rows) == 1
    assert rows[0]["Type of Area"] == "Strata"
    assert rows[0]["Purchaser Address"] == "HDB"
    assert rows[0]["Source"] == "URA"


def test_advertised_sales_count_accepts_singular_and_plural_labels():
    assert condo.advertised_sales_count("ALL SALES TRANSACTIONS (935)") == 935
    assert condo.advertised_sales_count("ALL SALES TRANSACTION (0)") == 0
    assert condo.advertised_sales_count("No transaction table") is None


def test_unit_fixture_preserves_exact_values_and_marks_unavailable_units():
    text = FIXTURE.read_text(encoding="utf-8")

    rows = condo.parse_transaction_text(
        text,
        project_name="TEST RESIDENCES",
        planning_area="NOVENA",
        postal_district="11",
        property_type="Condominium",
        tenure="Freehold",
    )

    assert len(rows) == 4
    exact, masked, absent, unparseable = rows
    assert exact["unit_number"] == "#06-15"
    assert exact["unit_floor"] == "06"
    assert exact["unit_stack"] == "15"
    assert exact["unit_number_status"] == "exact"
    assert exact["unit_number_source"] == "edgeprop_address"
    assert exact["Street"] == "10 TEST ROAD"

    assert masked["unit_number"] == ""
    assert masked["unit_floor"] == ""
    assert masked["unit_stack"] == ""
    assert masked["unit_number_status"] == "masked"
    assert masked["unit_number_source"] == "edgeprop_address"
    assert masked["Address"].endswith("#06-XX")

    assert absent["unit_number"] == ""
    assert absent["unit_number_status"] == "not_present"
    assert absent["unit_number_source"] == ""

    assert unparseable["unit_number"] == ""
    assert unparseable["unit_number_status"] == "unparseable"
    assert unparseable["unit_number_source"] == "edgeprop_address"
    assert unparseable["Address"].endswith("#LEVEL")


def test_parse_saved_transactions_writes_stable_unit_schema(tmp_path):
    out = tmp_path / "units.csv"
    args = argparse.Namespace(
        html_file=[],
        text_file=[str(FIXTURE)],
        project_name="",
        planning_area="",
        postal_district="",
        property_type="Condominium/Apartment",
        tenure="",
        source_url="https://www.edgeprop.sg/condo-apartment/test-residences",
        source_slug="test-residences",
        out=str(out),
    )

    condo.parse_saved_transactions(args)

    with out.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == condo.UNIT_FIELDS
    assert len(rows) == 4
    assert rows[0]["Project"] == "TEST RESIDENCES"
    assert rows[0]["planning_area"] == "NOVENA"
    assert rows[0]["Postal District"] == "11"
    assert rows[0]["unit_number"] == "#06-15"
    assert rows[1]["unit_number_status"] == "masked"
    assert all(row["source_quality"] == "not_clean" for row in rows)
    assert all(row["source_slug"] == "test-residences" for row in rows)


def test_extract_unit_number_rejects_ambiguity_and_preserves_alphanumeric_tokens():
    ambiguous = condo.extract_unit_number("10 TEST ROAD #01-01 / #02-02")
    penthouse = condo.extract_unit_number("10 TEST ROAD #PH-01")
    basement = condo.extract_unit_number("10 TEST ROAD #B1-01")

    assert ambiguous["unit_number"] == ""
    assert ambiguous["unit_number_status"] == "unparseable"
    assert penthouse["unit_number"] == "#PH-01"
    assert penthouse["unit_floor"] == "PH"
    assert penthouse["unit_number_status"] == "exact"
    assert basement["unit_number"] == "#B1-01"
    assert basement["unit_floor"] == "B1"
    assert basement["unit_number_status"] == "exact"
