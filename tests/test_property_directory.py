"""Property-analysis directory: district grouping, labels, escaping and the home summary card."""

import re
from pathlib import Path

import pytest

from sg_estate.reporting.property_analysis import parse_property_analysis
from sg_estate.reporting.property_directory import (
    DIRECTORY_PATH,
    DISTRICT_NAMES,
    directory_catalog_entry,
    directory_entries,
    render_directory_page,
    stage_label,
    summary_card,
)

ROOT = Path(__file__).parent.parent


@pytest.fixture
def analysis(tmp_path):
    def create(project, slug, *, stage="resale", date="2026-09-20"):
        source = tmp_path / f"{date}-{slug}.md"
        source.write_text(
            f"# {project} — property analysis\n\n"
            f"Research captured: **{date} 12:00:00 SGT (UTC+08:00)**  \n"
            f"Property: **{project}, Singapore**  \n"
            "Analysis type: **individual project evidence**  \n"
            "Status: **point-in-time market snapshot**  \n"
            f"Market stage: **{stage}**\n\n"
            "## Decision\n\nNo executable offer has been verified.\n",
            encoding="utf-8",
        )
        return parse_property_analysis(source)

    return create


def _catalog(*pairs):
    return {"projects": [{"name": n, "slug": n.lower().replace(" ", "-"), "district": d} for n, d in pairs]}


def test_stage_labels():
    assert stage_label("unverified") == "Stage not verified"
    assert stage_label("new launch") == "New launch"
    assert stage_label("resale") == "Resale"


def test_entries_take_district_from_the_project_index(analysis):
    entries = directory_entries(
        [analysis("Canberra Crescent Residences", "canberra-crescent-residences", stage="new launch")],
        _catalog(("CANBERRA  CRESCENT RESIDENCES", "27")),
    )
    assert entries == [{
        "name": "Canberra Crescent Residences",
        "path": "property-analysis-2026-09-20-canberra-crescent-residences.html",
        "stage": "new launch",
        "stage_label": "New launch",
        "date_label": "20 Sep 2026",
        "captured_iso": entries[0]["captured_iso"],
        "district": "27",
    }]


def test_directory_unknown_for_out_of_range_district(analysis):
    reports = [analysis("Alpha", "alpha"), analysis("Beta", "beta"), analysis("Gamma", "gamma")]
    entries = directory_entries(reports, _catalog(("ALPHA", ""), ("BETA", "29"), ("GAMMA", "0")))
    assert {e["district"] for e in entries} == {""}
    page = render_directory_page(entries)
    assert re.search(r'<details class="district" id="unknown">.*Alpha.*Beta.*Gamma.*</details>', page, re.S)


def test_page_groups_rows_by_district_in_numeric_order_with_counts(analysis):
    reports = [analysis("Zeta Park", "zeta-park"), analysis("Alpha Court", "alpha-court"),
               analysis("Beta Lodge", "beta-lodge"), analysis("Lost Place", "lost-place")]
    page = render_directory_page(directory_entries(
        reports, _catalog(("ZETA PARK", "27"), ("ALPHA COURT", "27"), ("BETA LODGE", "09"))))
    assert page.index('id="d09"') < page.index('id="d27"') < page.index('id="unknown"')
    d27 = page[page.index('id="d27"'):page.index("</details>", page.index('id="d27"'))]
    assert "D27 · Sembawang · Yishun" in d27 and '<span class="count">2</span>' in d27
    assert d27.index("Alpha Court") < d27.index("Zeta Park")
    assert 'id="d01"' not in page
    assert page.count('href="property-analysis-') == 4
    assert "<details" in page and " open" not in page.split("<main", 1)[1].split("<script", 1)[0]


def test_page_rows_carry_stage_and_date(analysis):
    page = render_directory_page(directory_entries(
        [analysis("Pinery Residences", "pinery-residences", stage="unverified", date="2026-08-08")],
        _catalog(("PINERY RESIDENCES", "20"))))
    assert 'data-stage="unverified"' in page
    assert ">Stage not verified<" in page
    assert ">08 Aug 2026<" in page
    assert 'data-stage="unverified" aria-pressed="false">Stage not verified <span>1</span>' in page


def test_directory_escapes_project_names():
    entry = {"name": 'Optima @ Tanah Merah & "Co" <x>', "path": "property-analysis-2026-09-20-optima.html",
             "stage": "resale", "stage_label": "Resale", "date_label": "20 Sep 2026",
             "captured_iso": "2026-09-20T12:00:00+08:00", "district": ""}
    page = render_directory_page([entry])
    assert "<x>" not in page
    assert "Optima @ Tanah Merah &amp; &quot;Co&quot; &lt;x&gt;" in page


def test_directory_keeps_same_named_analyses(analysis):
    entries = directory_entries(
        [analysis("Twin Tower", "twin-tower"), analysis("Twin Tower", "twin-tower-2")], {"projects": []})
    assert len(entries) == 2
    assert render_directory_page(entries).count(">Twin Tower<") == 2


def test_directory_script_guards_missing_hash_target():
    page = render_directory_page([])
    assert 'document.getElementById(location.hash.slice(1))' in page
    assert 'target && target.tagName === "DETAILS"' in page


def test_empty_directory_and_card():
    assert "No project analyses published yet" in render_directory_page([])
    card = summary_card([])
    assert "No project analyses published yet" in card
    assert f'href="{DIRECTORY_PATH}"' in card


def test_summary_card_counts_latest_and_links_directory(analysis):
    entries = directory_entries([analysis("A One", "a-one", date="2026-08-08"),
                                 analysis("B Two", "b-two", date="2026-09-26")], {"projects": []})
    card = summary_card(entries)
    assert card.count('<a class="card property-analysis-card"') == 1
    assert "Browse 2 project analyses by district" in card
    assert "Latest captured 26 Sep 2026. Each is a dated snapshot." in card
    assert 'data-kind="analysis project"' in card and "property analysis" in card


def test_catalog_entry_shape():
    entry = directory_catalog_entry()
    assert entry["path"] == DIRECTORY_PATH
    assert entry["kind"] == "property-analysis-directory"
    assert {"id", "path", "title", "category", "kind", "summary", "tags"} <= set(entry)


def test_python_district_names_match_index_html():
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    block = re.search(r"const DISTRICT_NAMES = \{(.*?)\};", source, re.S).group(1)
    js = dict(re.findall(r'"(\d{2})":"([^"]*)"', block))
    assert js == DISTRICT_NAMES


# --- Final-review fixes ------------------------------------------------------------------

def _entry(name, district, stage="resale"):
    return {"name": name, "path": f"property-analysis-2026-09-20-{name.lower().replace(' ', '-')}.html",
            "stage": stage, "stage_label": stage_label(stage), "date_label": "20 Sep 2026",
            "captured_iso": "2026-09-20T12:00:00+08:00", "district": district}


def test_search_text_is_name_and_district_name_only():
    page = render_directory_page([_entry("Parc Vista", "27", stage="new launch")])
    search = re.search(r'data-search="([^"]*)"', page).group(1)
    assert search == "parc vista sembawang · yishun"


def test_district_codes_match_whole_codes_not_substrings():
    page = render_directory_page([_entry("Alpha", "01"), _entry("Beta", "15")])
    assert 'data-district="01"' in page and 'data-district="15"' in page
    assert "row.dataset.district === want" in page
    assert 'code[1].padStart(2, "0")' in page


def test_district_sections_show_a_disclosure_marker():
    page = render_directory_page([_entry("Alpha", "01")])
    assert "details.district summary::before" in page
    assert "details.district[open] > summary::before" in page
    assert "list-style:none" in page
