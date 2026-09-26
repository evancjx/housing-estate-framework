"""Checks for the static GitHub Pages report bundle."""

from html.parser import HTMLParser
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from scripts import build_pages_site
from sg_estate.reporting.property_analysis import latest_property_analyses, parse_property_analysis


ROOT = Path(__file__).parent.parent


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


def test_pages_landing_page_links_only_to_existing_html_reports():
    parser = _LinkParser()
    parser.feed((ROOT / "index.html").read_text(encoding="utf-8"))
    report_links = [href for href in parser.hrefs if href.endswith(".html")]

    assert "poiz_east_resale_comparison.html" in report_links
    assert "poiz_east_unit_growth_transactions.html" in report_links
    assert "katong_condo_comparison.html" in report_links
    assert "condo_framework_comparison.html" in report_links
    assert "multi_condo_framework_comparison.html" in report_links
    assert "canberra_crescent_d27_deep_analysis.html" in report_links
    assert "home_loan_planner.html" in report_links
    assert "condo_loan_timeline_planner.html" in report_links
    assert "project_exit_comparison.html" in report_links
    assert "tampines_condo_school_mrt_area_guide_2026-08-08.html" in report_links
    for number, slug in (
        (1, "micro_location"),
        (2, "newness"),
        (3, "integration"),
        (4, "unit_matching"),
        (5, "sale_state"),
        (6, "planning_context"),
    ):
        assert f"canberra_strategy_{number}_{slug}.html" in report_links
    assert len(report_links) == 26
    assert all((ROOT / href).is_file() for href in report_links)


def test_report_catalog_covers_every_root_report():
    catalog = json.loads(
        (ROOT / "site" / "reports.json").read_text(encoding="utf-8")
    )
    paths = [report["path"] for report in catalog["reports"]]

    assert catalog["schema_version"] == 1
    assert len(paths) == len(set(paths))
    assert set(paths) == {
        path.name for path in ROOT.glob("*.html") if path.name != "index.html"
    }
    assert all(report["summary"].strip() for report in catalog["reports"])
    assert all(report["tags"] for report in catalog["reports"])


def test_pages_builder_packages_reports_catalog_and_assets(tmp_path):
    assets = tmp_path / "source-assets"
    assets.mkdir()
    (assets / "research-shell.css").write_text("body {}", encoding="utf-8")
    (assets / "research-shell.js").write_text("void 0;", encoding="utf-8")
    (assets / "estate-explorer.css").write_text("body {}", encoding="utf-8")
    (assets / "estate-comparison.js").write_text("void 0;", encoding="utf-8")
    (assets / "buyer-profile.css").write_text("body {}", encoding="utf-8")
    (assets / "buyer-profile.js").write_text("void 0;", encoding="utf-8")
    (assets / "mrt-comparison.css").write_text("body {}", encoding="utf-8")
    (assets / "mrt-comparison.js").write_text("void 0;", encoding="utf-8")
    (assets / "private-project-comparison.css").write_text(
        "body {}", encoding="utf-8"
    )
    (assets / "private-project-comparison.js").write_text(
        "void 0;", encoding="utf-8"
    )
    (assets / "home-loan-planner.js").write_text("void 0;", encoding="utf-8")
    (assets / "condo-loan-timeline-planner.js").write_text(
        "void 0;", encoding="utf-8"
    )
    (assets / "condo-loan-timeline-funding-v3.js").write_text(
        "void 0;", encoding="utf-8"
    )
    (assets / "project-exit-comparison.css").write_text(
        "body {}", encoding="utf-8"
    )
    (assets / "project-exit-comparison.js").write_text(
        "void 0;", encoding="utf-8"
    )
    (assets / "property-analysis.css").write_text("body {}", encoding="utf-8")
    transaction_assets = assets / "condo-transactions"
    transaction_assets.mkdir()
    (transaction_assets / "manifest.json").write_text(
        '{"schema":{"version":1}}', encoding="utf-8"
    )
    (transaction_assets / "shard-00.json").write_text(
        '{"projects":{}}', encoding="utf-8"
    )
    output = ROOT / f"_site-test-{tmp_path.name}-{os.getpid()}"
    try:
        count = build_pages_site.build_site(output, assets_dir=assets)

        source_count = len(build_pages_site.load_catalog()["reports"])
        analyses = build_pages_site.discover_property_analyses()
        assert count == source_count + len(analyses) + 1
        assert (output / "index.html").is_file()
        assert (output / "reports.json").is_file()
        assert (output / "projects.json").is_file()
        assert (output / "assets" / "research-shell.css").is_file()
        assert (output / "assets" / "estate-explorer.css").is_file()
        assert (output / "assets" / "estate-comparison.js").is_file()
        assert (output / "assets" / "buyer-profile.css").is_file()
        assert (output / "assets" / "buyer-profile.js").is_file()
        assert (output / "assets" / "mrt-comparison.css").is_file()
        assert (output / "assets" / "mrt-comparison.js").is_file()
        assert (output / "assets" / "home-loan-planner.js").is_file()
        assert (output / "assets" / "condo-loan-timeline-planner.js").is_file()
        assert (output / "assets" / "condo-loan-timeline-funding-v3.js").is_file()
        assert (output / "assets" / "project-exit-comparison.css").is_file()
        assert (output / "assets" / "project-exit-comparison.js").is_file()
        assert (output / "home_loan_planner.html").is_file()
        assert (output / "condo_loan_timeline_planner.html").is_file()
        assert (output / "project_exit_comparison.html").is_file()
        assert (
            output / "assets" / "condo-transactions" / "manifest.json"
        ).is_file()
        assert (
            output / "assets" / "condo-transactions" / "shard-00.json"
        ).is_file()
        assert (output / ".nojekyll").is_file()
        for analysis in analyses:
            assert (output / analysis.output_path).is_file()
        merged_catalog = json.loads(
            (output / "reports.json").read_text(encoding="utf-8")
        )
        assert len(merged_catalog["reports"]) == count
        property_entries = [
            report
            for report in merged_catalog["reports"]
            if report["kind"] == "property-analysis"
        ]
        assert {"Arc at Tampines", "Park Place Residences at PLQ"} <= {
            report["project_name"]
            for report in property_entries
        }
        assert {report["id"] for report in property_entries} == {
            analysis.report_id for analysis in analyses
        }
        assert {report["path"] for report in property_entries} == {
            analysis.output_path for analysis in analyses
        }
        landing = (output / "index.html").read_text(encoding="utf-8")
        assert build_pages_site.PROPERTY_CARDS_MARKER not in landing
        assert build_pages_site.PROPERTY_ROUTES_MARKER not in landing
        assert (
            '"ARC AT TAMPINES": '
            '"property-analysis-2026-09-20-arc-at-tampines.html"'
        ) in landing
        for project, slug in (
            ("PARKTOWN RESIDENCE", "parktown-residence"),
            ("PINERY RESIDENCES", "pinery-residences"),
            ("THE LAKEGARDEN RESIDENCES", "the-lakegarden-residences"),
            ("CANBERRA CRESCENT RESIDENCES", "canberra-crescent-residences"),
        ):
            assert (
                f'"{project}": "property-analysis-2026-09-20-{slug}.html"'
            ) in landing
        entries_by_id = {entry["id"]: entry for entry in property_entries}
        assert not entries_by_id["property-analysis-2026-07-26-arc-at-tampines"]["is_latest"]
        assert entries_by_id["property-analysis-2026-09-20-arc-at-tampines"]["is_latest"]
        assert entries_by_id["property-analysis-2026-09-20-canberra-crescent-residences"]["is_latest"]
        assert landing.index('"ONE AMBER"') < landing.index('"ARC AT TAMPINES"')
        assert "data-kind=\"analysis project\"" in landing
        latest_future = next(
            report for report in property_entries
            if report["project_slug"] == "bedok-rise-gls-future-condominium"
            and report["is_latest"]
        )
        directory = (output / "property-analyses.html").read_text(encoding="utf-8")
        future_row = next(
            line
            for line in directory.split("<li ")
            if f'href="{latest_future["path"]}"' in line
        )
        assert latest_future["market_stage"] == "future project"
        assert 'data-stage="future project"' in future_row
        assert 'data-stage="resale"' not in future_row
        assert landing.count('class="card property-analysis-card"') == 1
        assert directory.count('href="property-analysis-') == len(
            latest_property_analyses(analyses)
        )
        assert any(r["kind"] == "property-analysis-directory" for r in merged_catalog["reports"])
        projects = json.loads((output / "projects.json").read_text(encoding="utf-8"))["projects"]
        assert any("analysis" in p for p in projects)
        report = (output / "comparison_table.html").read_text(encoding="utf-8")
        assert report.count("assets/research-shell.css") == 1
        assert report.count("assets/research-shell.js") == 1
        buyer_report = (output / "buyer_profile_table.html").read_text(
            encoding="utf-8"
        )
        assert buyer_report.count("assets/research-shell.css") == 1
        assert buyer_report.count("assets/research-shell.js") == 1
        assert buyer_report.count("assets/estate-explorer.css") == 1
        assert buyer_report.count("assets/buyer-profile.css") == 1
        assert buyer_report.count("assets/buyer-profile.js") == 1
        mrt_report = (output / "mrt_comparison_table.html").read_text(
            encoding="utf-8"
        )
        assert mrt_report.count("assets/research-shell.css") == 1
        assert mrt_report.count("assets/research-shell.js") == 1
        assert mrt_report.count("assets/estate-explorer.css") == 1
        assert mrt_report.count("assets/mrt-comparison.css") == 1
        assert mrt_report.count("assets/mrt-comparison.js") == 1
    finally:
        if output.is_dir():
            for path in sorted(output.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            output.rmdir()


def test_generated_project_catalog_is_compact_and_routes_known_project():
    catalog = build_pages_site.build_project_catalog()
    projects = catalog["projects"]
    treasure = next(
        project for project in projects if project["slug"] == "treasure-at-tampines"
    )

    assert catalog["schema_version"] == 1
    assert len(projects) == 3477
    assert treasure == {
        "name": "TREASURE AT TAMPINES",
        "slug": "treasure-at-tampines",
        "district": "18",
    }
    assert all(set(project) <= {"name", "slug", "district"} for project in projects)


@pytest.fixture
def parsed_report(tmp_path):
    def create(project, slug, *, stage="future project", date="2026-09-20"):
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


def test_project_finder_adds_researched_projects_without_inventing_districts(parsed_report):
    reports = [
        parsed_report("Lucerne Grand", "lucerne-grand"),
        parsed_report("Canberra Drive EC GLS", "canberra-drive-ec-gls"),
    ]
    catalog = {
        "schema_version": 1,
        "projects": [{"name": "EXISTING PROJECT", "slug": "existing-project", "district": "18"}],
    }
    original = deepcopy(catalog)

    updated = build_pages_site.add_report_projects(catalog, reports)

    assert updated["projects"] == [
        original["projects"][0],
        {"name": "Lucerne Grand", "slug": "lucerne-grand"},
        {"name": "Canberra Drive EC GLS", "slug": "canberra-drive-ec-gls"},
    ]
    assert updated["schema_version"] == 1
    assert catalog == original
    assert updated["projects"][0] is not catalog["projects"][0]


def test_project_finder_keeps_existing_identity_and_adds_only_one_capture(parsed_report):
    catalog = {
        "projects": [{"name": "  LUCERNE   GRAND ", "slug": "directory-lucerne", "district": "18"}],
    }
    newest = parsed_report("Sample Project", "sample-project")
    older = parsed_report("Sample Project", "sample-project", date="2026-08-08")
    reports = [newest, parsed_report("Lucerne Grand", "lucerne-grand"), older]
    original_reports = list(reports)

    updated = build_pages_site.add_report_projects(catalog, reports)

    assert updated["projects"] == [
        catalog["projects"][0],
        {"name": "Sample Project", "slug": "sample-project"},
    ]
    assert reports == original_reports


def test_project_finder_does_not_treat_regional_reports_or_indexes_as_projects(parsed_report):
    catalog = {"schema_version": 1, "projects": []}
    reports = [
        parsed_report("Regional condo comparison", "regional-condo-comparison", stage="mixed market"),
        parsed_report("Individual project analyses", "individual-project-analyses", stage="mixed market"),
    ]

    assert build_pages_site.add_report_projects(catalog, reports) == catalog


def test_project_finder_preserves_old_named_project_when_report_slug_collides(parsed_report):
    catalog = {
        "projects": [{"name": "FLAMINGO VALLEY (OLD)", "slug": "flamingo-valley", "district": "15"}],
    }
    report = parsed_report("Flamingo Valley", "flamingo-valley", stage="resale")

    updated = build_pages_site.add_report_projects(catalog, [report])

    assert updated["projects"] == [
        catalog["projects"][0],
        {"name": "Flamingo Valley", "slug": "analysis-flamingo-valley"},
    ]
    assert report.project_slug == "flamingo-valley"
    assert (
        '"FLAMINGO VALLEY": "property-analysis-2026-09-20-flamingo-valley.html"'
    ) in build_pages_site._property_routes([report])


def test_project_finder_rejects_ambiguous_fallback_slug_without_mutating_catalog(parsed_report):
    catalog = {"projects": [
        {"name": "OLD SAMPLE", "slug": "sample-project"},
        {"name": "UNRELATED SAMPLE", "slug": "analysis-sample-project"},
    ]}
    original = deepcopy(catalog)
    report = parsed_report("Sample Project", "sample-project")

    with pytest.raises(ValueError, match="Ambiguous project-finder slug"):
        build_pages_site.add_report_projects(catalog, [report])
    assert catalog == original


def test_pages_builder_rejects_output_outside_repository(tmp_path):
    with pytest.raises(ValueError, match="inside the repository"):
        build_pages_site.build_site(tmp_path / "site")


def test_pages_builder_does_not_replace_unowned_directory(tmp_path):
    output = ROOT / f"_site-unowned-test-{tmp_path.name}-{os.getpid()}"
    output.mkdir()
    (output / "user-file.txt").write_text("keep", encoding="utf-8")
    try:
        with pytest.raises(ValueError, match="unowned non-empty"):
            build_pages_site.build_site(output)
        assert (output / "user-file.txt").read_text(encoding="utf-8") == "keep"
    finally:
        (output / "user-file.txt").unlink()
        output.rmdir()


def test_pages_link_validator_rejects_missing_local_asset(tmp_path):
    (tmp_path / "index.html").write_text(
        '<link rel="stylesheet" href="assets/missing.css">',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="assets/missing.css"):
        build_pages_site.validate_site_links(tmp_path)


def test_pages_workflow_uses_validated_site_builder():
    workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")

    assert "python scripts/build_pages_site.py --out _site" in workflow
    assert workflow.count("scripts/build_pages_site.py --out _site") == 1
    assert '- "property_analysis/**"' in workflow
    assert '- "sg_estate/reporting/**"' in workflow
    assert '- "site/**"' in workflow
    assert '- "models/gen_project_exit_comparison_html.py"' in workflow
    assert '- "data/inputs/ura_private.csv"' in workflow
    assert "edgeprop_condo_apartment_projects.csv" in workflow
    assert "actions/configure-pages@v5" in workflow
    assert "actions/upload-pages-artifact@v4" in workflow
    assert "actions/deploy-pages@v4" in workflow


def test_root_reports_have_no_broken_internal_html_links():
    broken = []
    for report in ROOT.glob("*.html"):
        parser = _LinkParser()
        parser.feed(report.read_text(encoding="utf-8"))
        for href in parser.hrefs:
            target = href.split("#", 1)[0].split("?", 1)[0]
            if target.endswith(".html") and "://" not in target:
                if not (ROOT / target).is_file():
                    broken.append(f"{report.name} -> {target}")

    assert broken == []


def test_analysis_links_are_added_to_matching_projects_only(parsed_report):
    catalog = {"projects": [
        {"name": "LUCERNE  GRAND", "slug": "lucerne-grand", "district": "18"},
        {"name": "OTHER", "slug": "other"},
    ]}
    older = parsed_report("Lucerne Grand", "lucerne-grand", date="2026-08-08")
    newest = parsed_report("Lucerne Grand", "lucerne-grand", date="2026-09-20")

    # Discovery order is newest first; latest_property_analyses keeps the first per slug.
    updated = build_pages_site.add_analysis_links(catalog, [newest, older])

    assert updated["projects"][0]["analysis"] == {
        "path": "property-analysis-2026-09-20-lucerne-grand.html", "date": "20 Sep 2026"}
    assert "analysis" not in updated["projects"][1]
    assert "analysis" not in catalog["projects"][0]


def test_home_library_gets_one_summary_card_not_one_card_per_analysis(parsed_report, tmp_path):
    index_copy = tmp_path / "index.html"
    index_copy.write_text((ROOT / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
    reports = [parsed_report("Alpha One", "alpha-one"), parsed_report("Beta Two", "beta-two")]

    build_pages_site.inject_property_library(index_copy, reports)
    landing = index_copy.read_text(encoding="utf-8")

    assert landing.count('class="card property-analysis-card"') == 1
    assert "Browse 2 project analyses by district" in landing
    assert 'href="property-analyses.html"' in landing
    assert 'href="property-analysis-2026-09-20-alpha-one.html"' not in landing
    assert '"ALPHA ONE": "property-analysis-2026-09-20-alpha-one.html"' in landing


def test_directory_path_collision_with_catalog_is_rejected():
    catalog = {"reports": [{"id": "x", "path": "property-analyses.html"}]}
    with pytest.raises(ValueError, match="property-analyses.html"):
        build_pages_site._prepare_property_publication(
            catalog, property_analysis_dir=ROOT / "property_analysis")


def test_library_has_no_property_analysis_chip():
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'data-filter="analysis"' not in source


def test_finder_offers_the_dated_analysis_and_district_directory():
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "Analysis · ${escapeMarkup(project.analysis.date)}" in source
    assert "Open the ${escapeMarkup(analysis.date)} analysis" in source
    assert 'property-analyses.html#d${district}' in source


def test_finder_tolerates_projects_without_analysis():
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "project.analysis ?" in source
    assert "project && project.analysis && project.analysis.path === " in source
    assert "p.analysis && " in source


def test_tampines_area_guide_is_an_ordinary_library_card():
    source = (ROOT / "index.html").read_text(encoding="utf-8")
    tag = next(line for line in source.splitlines()
               if 'href="tampines_condo_school_mrt_area_guide_2026-08-08.html"' in line)
    assert 'class="card"' in tag and "featured" not in tag
    last_featured = source.rindex('class="card featured"')
    assert source.index('href="tampines_condo_school_mrt_area_guide_2026-08-08.html"') > last_featured
    catalog = json.loads((ROOT / "site" / "reports.json").read_text(encoding="utf-8"))
    entry = next(r for r in catalog["reports"] if r["path"].startswith("tampines_condo"))
    assert not entry.get("featured")
