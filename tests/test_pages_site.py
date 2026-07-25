"""Checks for the static GitHub Pages report bundle."""

from html.parser import HTMLParser
import json
from pathlib import Path

import pytest

from scripts import build_pages_site


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
    assert "canberra_crescent_d27_deep_analysis.html" in report_links
    for number, slug in (
        (1, "micro_location"),
        (2, "newness"),
        (3, "integration"),
        (4, "unit_matching"),
        (5, "sale_state"),
        (6, "planning_context"),
    ):
        assert f"canberra_strategy_{number}_{slug}.html" in report_links
    assert len(report_links) == 20
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
    output = ROOT / "_site-test"
    try:
        count = build_pages_site.build_site(output, assets_dir=assets)

        assert count == len(build_pages_site.load_catalog()["reports"])
        assert (output / "index.html").is_file()
        assert (output / "reports.json").is_file()
        assert (output / "projects.json").is_file()
        assert (output / "assets" / "research-shell.css").is_file()
        assert (output / ".nojekyll").is_file()
        report = (output / "comparison_table.html").read_text(encoding="utf-8")
        assert report.count("assets/research-shell.css") == 1
        assert report.count("assets/research-shell.js") == 1
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


def test_pages_builder_rejects_output_outside_repository(tmp_path):
    with pytest.raises(ValueError, match="inside the repository"):
        build_pages_site.build_site(tmp_path / "site")


def test_pages_builder_does_not_replace_unowned_directory():
    output = ROOT / "_site-unowned-test"
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

    assert "python3 scripts/build_pages_site.py --out _site" in workflow
    assert '- "site/**"' in workflow
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
