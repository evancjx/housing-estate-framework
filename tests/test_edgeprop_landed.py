import csv
import json

from scrapers import edgeprop_landed


def test_discover_project_links_keeps_landed_detail_pages_only():
    html = """
    <a href="/landed-house/all">All</a>
    <a href="/landed-house/kembangan-estate">Kembangan Estate</a>
    <a href="/landed-house/kembangan-estate">Kembangan Estate duplicate</a>
    <a href="/condo-apartment/foo">Not landed</a>
    <a href="https://www.edgeprop.sg/landed-house/serangoon-garden-estate">Serangoon Garden Estate</a>
    """

    links = edgeprop_landed.discover_project_links(html)

    assert [link.name for link in links] == ["Kembangan Estate", "Serangoon Garden Estate"]
    assert links[0].url == "https://www.edgeprop.sg/landed-house/kembangan-estate"
    assert links[0].slug == "kembangan-estate"


def test_parse_detail_page_extracts_public_next_metadata():
    next_data = {
        "props": {
            "pageProps": {
                "projectDetail": {
                    "id": "11963",
                    "ext_id": "8416",
                    "name": "KEMBANGAN ESTATE",
                    "alias": "kembangan-estate-11963",
                    "planning_area": "Bedok",
                    "lat": 1.3225,
                    "lon": 103.906,
                },
                "projectInfo": {
                    "district": "D14",
                    "property_type": ["Terrace House", "Semi-Detached House"],
                    "tenure": "Freehold",
                    "street_numbers": ["1 Jalan Test", "2 Jalan Test"],
                    "score": {
                        "indicative_price": "2178",
                        "indicative_price_range": "1415 - 2851",
                    },
                },
                "salesTransactionData": {},
            }
        }
    }
    html = (
        '<html><script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(next_data)}"
        "</script></html>"
    )

    row = edgeprop_landed.parse_detail_page(html, url="https://example.test/page")

    assert row["project_name"] == "KEMBANGAN ESTATE"
    assert row["project_id"] == "11963"
    assert row["planning_area"] == "Bedok"
    assert row["property_type"] == "Terrace House; Semi-Detached House"
    assert row["address_count"] == 2
    assert row["indicative_price_psf"] == "2178"
    assert row["has_public_next_data"] is True


def test_parse_transaction_text_writes_ingestor_compatible_rows(tmp_path):
    text = """
    Date
    Address
    Price (S$ psf)
    Price (S$)
    Property Type
    Tenure
    Type of Sale
    Area (sqft)
    Type of Area
    Purchaser Address
    Source
    7 OCT 2020
    XX JALAN KEMBANGAN
    965
    3,760,000
    Terrace House
    Freehold
    Resale
    3,895
    Land
    Private
    URA
    """

    rows = edgeprop_landed.parse_transaction_text(
        text,
        project_name="KEMBANGAN ESTATE",
        planning_area="Bedok",
        postal_district="14",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["Project"] == "KEMBANGAN ESTATE"
    assert row["planning_area"] == "BEDOK"
    assert row["Postal District"] == "14"
    assert row["Date of Sale"] == "7 Oct 2020"
    assert row["Street"] == "XX JALAN KEMBANGAN"
    assert row["Price ($)"] == 3760000
    assert row["Type"] == "Terrace House"
    assert row["Area (sqft)"] == 3895
    assert row["Area (sqm)"] == 361.857

    out = tmp_path / "edgeprop_kembangan.csv"
    edgeprop_landed.write_csv(out, rows)
    with out.open(newline="", encoding="utf-8") as handle:
        written = list(csv.DictReader(handle))
    assert written[0]["Price ($)"] == "3760000"


def test_parse_playwright_rendered_transaction_text_with_combined_area_and_buyer():
    text = """
    Sales Transaction of KEMBANGAN ESTATE
    Date
    Address
    Price (S$ psf)
    Price (S$)
    Property Type
    Tenure
    Type of Sale
    Area (sqft)
    Type of Area
    Purchaser Address
    Source
    17 APR 2026
    XX LORONG MARICAN
    2,851
    6,160,000
    Semi-Detached House
    Freehold
    New Sale
    2,160
    Land\tPrivate
    URA
    """

    rows = edgeprop_landed.parse_transaction_text(
        text,
        project_name="KEMBANGAN ESTATE",
        planning_area="Bedok",
        postal_district="14",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["Date of Sale"] == "17 Apr 2026"
    assert row["Unit Price ($psf)"] == 2851
    assert row["Price ($)"] == 6160000
    assert row["Type of Area"] == "Land"
    assert row["Purchaser Address"] == "Private"
