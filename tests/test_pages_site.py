"""Checks for the static GitHub Pages report bundle."""

from html.parser import HTMLParser
from pathlib import Path


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
    assert len(report_links) == 19
    assert all((ROOT / href).is_file() for href in report_links)


def test_pages_workflow_packages_only_root_html_reports():
    workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")

    assert "find . -maxdepth 1 -type f -name '*.html'" in workflow
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
