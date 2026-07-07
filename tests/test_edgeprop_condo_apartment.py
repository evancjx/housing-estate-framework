from scrapers import edgeprop_condo_apartment_playwright as condo


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
