"""Property-analysis parsing, rendering and publication safety checks."""

from pathlib import Path

import pytest

from scripts import build_pages_site
from sg_estate.reporting.property_analysis import (
    discover_property_analyses,
    latest_property_analyses,
    parse_property_analysis,
    render_markdown,
    render_property_analysis_page,
)


ROOT = Path(__file__).parent.parent
ANALYSIS_DIR = ROOT / "property_analysis"
TANAH_MERAH_PORTFOLIO = {
    "2026-07-30-bedok-court.md": "Bedok Court",
    "2026-07-30-bedok-rise-gls-future-condominium.md": (
        "Bedok Rise GLS future condominium"
    ),
    "2026-07-30-casa-flora.md": "Casa Flora",
    "2026-07-30-casa-merah.md": "Casa Merah",
    "2026-07-30-east-meadows.md": "East Meadows",
    "2026-07-30-east-village.md": "East Village",
    "2026-07-30-eco.md": "eCO",
    "2026-07-30-grandeur-park-residences.md": "Grandeur Park Residences",
    "2026-07-30-limau-park.md": "Limau Park",
    "2026-07-30-optima-at-tanah-merah.md": "Optima @ Tanah Merah",
    "2026-07-30-palmwoods.md": "Palmwoods",
    "2026-07-30-sceneca-residence.md": "Sceneca Residence",
    "2026-07-30-stratford-court.md": "Stratford Court",
    "2026-07-30-tanah-merah-mansion.md": "Tanah Merah Mansion",
    "2026-07-30-tanamera-crest.md": "Tanamera Crest",
    "2026-07-30-the-glades.md": "The Glades",
    "2026-07-30-the-tanamera.md": "The Tanamera",
    "2026-07-30-urban-vista.md": "Urban Vista",
}


def _write_analysis(
    directory: Path,
    *,
    date: str = "2026-07-26",
    time: str = "12:00:00",
    slug: str = "sample-project",
    project: str = "Sample Project",
    metadata: str = "",
    decision: str = "The evidence supports a disciplined purchase.",
    remainder: str = "",
) -> Path:
    path = directory / f"{date}-{slug}.md"
    metadata_block = f"\n{metadata.strip()}" if metadata.strip() else ""
    path.write_text(
        (
            f"# {project} — resale inventory and quantum analysis\n\n"
            f"Research captured: **{date} {time} SGT (UTC+08:00)**  \n"
            f"Property: **{project}, 1 Sample Road, Singapore**  \n"
            "Analysis type: **property resale inventory, valuation and "
            "investment analysis**  \n"
            f"Status: **point-in-time market snapshot**{metadata_block}\n\n"
            "## Decision\n\n"
            f"{decision}\n\n"
            f"{remainder}\n"
        ),
        encoding="utf-8",
    )
    return path


def test_real_property_analyses_are_discovered_newest_first():
    analyses = discover_property_analyses(ANALYSIS_DIR)

    by_project = {analysis.project_name: analysis for analysis in analyses}
    assert {
        "144A Lorong Sarina",
        "Arc at Tampines",
        "Canberra Crescent Residences",
        "Park Place Residences at PLQ",
        "The LakeGarden Residences",
    } <= by_project.keys()
    assert (
        by_project["144A Lorong Sarina"].captured_iso
        == "2026-07-27T21:45:49+08:00"
    )
    assert by_project["Arc at Tampines"].captured_iso == "2026-07-26T12:46:23+08:00"
    assert (
        by_project["Park Place Residences at PLQ"].captured_iso
        == "2026-07-26T12:25:08+08:00"
    )
    assert (
        by_project["The LakeGarden Residences"].captured_iso
        == "2026-08-03T22:21:00+08:00"
    )
    assert (
        by_project["Canberra Crescent Residences"].captured_iso
        == "2026-08-03T22:54:43+08:00"
    )
    assert by_project["Canberra Crescent Residences"].market_stage == "new launch"
    assert by_project["The LakeGarden Residences"].market_stage == "new launch"
    assert [analysis.captured_at for analysis in analyses] == sorted(
        (analysis.captured_at for analysis in analyses), reverse=True
    )
    assert all(analysis.summary for analysis in analyses)


def test_tanah_merah_property_analysis_portfolio_is_complete():
    sources = {
        path.name: parse_property_analysis(path).project_name
        for path in ANALYSIS_DIR.glob("2026-07-30-*.md")
    }

    assert TANAH_MERAH_PORTFOLIO.items() <= sources.items()


@pytest.mark.parametrize(
    "source_name",
    (
        "2026-07-26-arc-at-tampines.md",
        "2026-07-26-park-place-residences-at-plq.md",
        "2026-07-27-144a-lorong-sarina.md",
        "2026-08-03-canberra-crescent-residences.md",
        "2026-08-03-the-lakegarden-residences.md",
        *TANAH_MERAH_PORTFOLIO,
    ),
)
def test_real_analysis_renders_semantic_responsive_html(source_name):
    analysis = parse_property_analysis(ANALYSIS_DIR / source_name)
    page = render_property_analysis_page(analysis)

    assert page.count("<h1>") == 1
    assert page.count('class="tbl-wrap pa-table-wrap"') >= 1
    assert page.count('class="tbl-wrap pa-table-wrap"') == page.count("<table>")
    assert '<th scope="col"' in page
    assert "<strong>" in page
    assert "<ol>" in page
    assert 'href="https://' in page
    assert 'href="assets/property-analysis.css"' in page
    assert 'type="application/ld+json"' in page
    assert 'rel="canonical"' in page
    assert "<script>alert" not in page
    assert render_property_analysis_page(analysis) == page


def test_landed_analysis_has_generic_private_property_catalog_tags():
    analysis = parse_property_analysis(
        ANALYSIS_DIR / "2026-07-27-144a-lorong-sarina.md"
    )
    tags = analysis.catalog_entry(is_latest=True)["tags"]

    assert "private property" in tags
    assert "resale" in tags
    assert "condominium" not in tags


def test_future_gls_analysis_is_not_catalogued_as_resale(tmp_path):
    source = _write_analysis(
        tmp_path,
        slug="sample-gls-future-condominium",
        project="Sample GLS future condominium",
        metadata="Market stage: **future project**",
    )
    entry = parse_property_analysis(source).catalog_entry(is_latest=True)
    tags = entry["tags"]

    assert entry["market_stage"] == "future project"
    assert "future project" in tags
    assert "resale" not in tags


def test_new_launch_analysis_is_not_catalogued_as_resale_or_future(tmp_path):
    source = _write_analysis(
        tmp_path,
        slug="sample-launched-condominium",
        project="Sample Launched Condominium",
        metadata="Market stage: **new launch**",
    )
    entry = parse_property_analysis(source).catalog_entry(is_latest=True)
    tags = entry["tags"]

    assert entry["market_stage"] == "new launch"
    assert "new launch" in tags
    assert "resale" not in tags
    assert "future project" not in tags


def test_real_lakegarden_card_and_page_show_new_launch_stage():
    analysis = parse_property_analysis(
        ANALYSIS_DIR / "2026-08-03-the-lakegarden-residences.md"
    )
    entry = analysis.catalog_entry(is_latest=True)
    card = build_pages_site._property_cards([analysis])
    page = render_property_analysis_page(analysis)

    assert entry["market_stage"] == "new launch"
    assert " new launch " in card
    assert " resale " not in card
    assert "Property analysis · New Launch · 03 Aug 2026" in card
    assert "<dt>Market stage</dt>" in page
    assert "<dd>new launch</dd>" in page
    assert 'id="september-2026-one-bedroom-owner-exit-analysis"' in page
    assert "S$44,551" in page
    assert "S$53,326" in page


def test_real_canberra_card_and_page_show_new_launch_quantum_analysis():
    analysis = parse_property_analysis(
        ANALYSIS_DIR / "2026-08-03-canberra-crescent-residences.md"
    )
    entry = analysis.catalog_entry(is_latest=True)
    card = build_pages_site._property_cards([analysis])
    page = render_property_analysis_page(analysis)

    assert entry["market_stage"] == "new launch"
    assert " new launch " in card
    assert "Property analysis · New Launch · 03 Aug 2026" in card
    assert "<dt>Market stage</dt>" in page
    assert "<dd>new launch</dd>" in page
    assert 'id="capital-potential-model"' in page
    assert "S$2,625,498" in page
    assert "S$3,344,916" in page
    assert "~748m" in page


def test_parse_rejects_unknown_market_stage(tmp_path):
    source = _write_analysis(
        tmp_path,
        metadata="Market stage: **planned someday**",
    )

    with pytest.raises(ValueError, match="Market stage must be one of"):
        parse_property_analysis(source)


def test_parse_rejects_filename_and_capture_date_mismatch(tmp_path):
    source = _write_analysis(tmp_path, date="2026-07-26")
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "2026-07-26 12:00:00", "2026-07-25 12:00:00"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="date does not match"):
        parse_property_analysis(source)


def test_parse_rejects_missing_required_metadata(tmp_path):
    source = _write_analysis(tmp_path)
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "Status: **point-in-time market snapshot**\n", ""
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing metadata: Status"):
        parse_property_analysis(source)


def test_render_escapes_raw_html_and_metadata(tmp_path):
    source = _write_analysis(
        tmp_path,
        project="Sample <Unsafe> Project",
        decision="<script>alert('unsafe')</script> The evidence remains readable.",
    )
    analysis = parse_property_analysis(source)
    page = render_property_analysis_page(analysis)

    assert "Sample &lt;Unsafe&gt; Project" in page
    assert "&lt;script&gt;alert('unsafe')&lt;/script&gt;" in page
    assert "<script>alert('unsafe')</script>" not in page


def test_markdown_cannot_inject_link_or_layout_attributes(tmp_path):
    source = _write_analysis(
        tmp_path,
        decision=(
            "[Source](https://example.com){target=_blank rel=opener}\n\n"
            "A normal paragraph.\n"
            '{style="position:fixed;inset:0;background:red;z-index:999999"}'
        ),
    )
    page = render_property_analysis_page(parse_property_analysis(source))

    assert 'target="_blank"' not in page
    assert 'rel="opener"' not in page
    assert '<p style="position:fixed' not in page


@pytest.mark.parametrize(
    "link",
    (
        "[unsafe](javascript:alert(1))",
        "[unsafe](JaVaScRiPt:alert(1))",
        "[unsafe](javascript&#58;alert(1))",
        "[unsafe](//example.com/path)",
    ),
)
def test_render_rejects_unsafe_links(tmp_path, link):
    source = _write_analysis(tmp_path, decision=f"Evidence link: {link}")
    analysis = parse_property_analysis(source)

    with pytest.raises(ValueError, match="unsafe|protocol-relative"):
        render_markdown(analysis)


def test_newest_capture_becomes_latest_without_removing_history(tmp_path):
    _write_analysis(
        tmp_path,
        date="2026-07-25",
        time="23:59:59",
        decision="Older evidence.",
    )
    newest_path = _write_analysis(
        tmp_path,
        date="2026-07-26",
        time="00:00:01",
        decision="Newer evidence.",
    )

    analyses = discover_property_analyses(tmp_path)
    latest = latest_property_analyses(analyses)

    assert len(analyses) == 2
    assert len(latest) == 1
    assert latest[0].source_path == newest_path.resolve()


def test_same_slug_cannot_split_history_across_display_names(tmp_path):
    _write_analysis(tmp_path, date="2026-07-25", project="Sample Project")
    _write_analysis(tmp_path, date="2026-07-26", project="Renamed Sample Project")

    with pytest.raises(ValueError, match="inconsistent names"):
        discover_property_analyses(tmp_path)


def test_new_property_analysis_route_overrides_legacy_project_route(tmp_path):
    source = _write_analysis(
        tmp_path,
        slug="the-poiz-residences",
        project="THE POIZ RESIDENCES",
    )
    index_copy = tmp_path / "index.html"
    index_copy.write_text(
        (ROOT / "index.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    build_pages_site.inject_property_library(
        index_copy, [parse_property_analysis(source)]
    )
    rendered = index_copy.read_text(encoding="utf-8")

    legacy = '"THE POIZ RESIDENCES": "poiz_east_resale_comparison.html"'
    generated = (
        '"THE POIZ RESIDENCES": '
        '"property-analysis-2026-07-26-the-poiz-residences.html"'
    )
    assert rendered.index(legacy) < rendered.index(generated)
