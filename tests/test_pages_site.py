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
    assert len(report_links) == 12
    assert all((ROOT / href).is_file() for href in report_links)


def test_pages_workflow_packages_only_root_html_reports():
    workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")

    assert "find . -maxdepth 1 -type f -name '*.html'" in workflow
    assert "actions/configure-pages@v5" in workflow
    assert "actions/upload-pages-artifact@v4" in workflow
    assert "actions/deploy-pages@v4" in workflow
