"""Static publication contract for the project exit comparison tool."""

from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path


ROOT = Path(__file__).parent.parent
PAGE = ROOT / "project_exit_comparison.html"
CATALOG = ROOT / "site" / "reports.json"

REQUIRED_IDS = {
    "project-exit-data",
    "decision-form",
    "project-slots",
    "project-options",
    "add-project",
    "target-area",
    "area-tolerance",
    "sale-state",
    "purchase-date",
    "planned-sale-date",
    "annual-growth",
    "selling-rate",
    "sale-costs",
    "comparison-results",
    "status-message",
    "form-error",
    "copy-view",
    "reset-view",
}


class _ContractParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = Counter()
        self.id_tags = {}
        self.id_attributes = {}
        self.stylesheets = []
        self.script_sources = []
        self.links = []
        self.vintages = []
        self.inline_handlers = []
        self._captures_data = False
        self.embedded_data_type = None
        self.embedded_data = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids[element_id] += 1
            self.id_tags[element_id] = tag
            self.id_attributes[element_id] = attributes
        for name, value in attrs:
            if name.lower().startswith("on"):
                self.inline_handlers.append((tag, name, value))
        if tag == "link" and "stylesheet" in attributes.get("rel", "").split():
            self.stylesheets.append(attributes.get("href"))
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])
        if tag == "time" and attributes.get("datetime"):
            self.vintages.append(attributes["datetime"])
        if tag == "script":
            source = attributes.get("src")
            if source:
                self.script_sources.append(source)
            if element_id == "project-exit-data":
                self._captures_data = True
                self.embedded_data_type = attributes.get("type")

    def handle_data(self, data):
        if self._captures_data:
            self.embedded_data.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self._captures_data:
            self._captures_data = False


def _parse_page():
    parser = _ContractParser()
    parser.feed(PAGE.read_text(encoding="utf-8"))
    return parser


def test_project_exit_page_exposes_stable_controls_and_valid_data():
    parser = _parse_page()

    assert REQUIRED_IDS <= set(parser.ids)
    assert all(parser.ids[element_id] == 1 for element_id in REQUIRED_IDS)
    assert parser.id_tags["project-exit-data"] == "script"
    assert parser.id_tags["decision-form"] == "form"
    assert parser.embedded_data_type == "application/json"
    assert isinstance(json.loads("".join(parser.embedded_data)), dict)


def test_project_exit_page_uses_external_assets_without_inline_handlers():
    parser = _parse_page()

    assert parser.stylesheets.count("assets/project-exit-comparison.css") == 1
    assert parser.script_sources.count("assets/project-exit-comparison.js") == 1
    assert parser.inline_handlers == []
    assert parser.id_attributes["comparison-results"]["aria-label"] == (
        "Comparison results"
    )
    assert "aria-live" not in parser.id_attributes["comparison-results"]
    assert "aria-labelledby" not in parser.id_attributes["comparison-results"]


def test_project_exit_page_attributes_official_evidence_and_generated_vintage():
    parser = _parse_page()
    payload = json.loads("".join(parser.embedded_data))

    assert (
        "https://eservice.ura.gov.sg/property-market-information/"
        "pmiResidentialTransactionSearch"
    ) in parser.links
    assert (
        "https://www.ura.gov.sg/eservices-info/maps/acceptance-grant-licence/"
    ) in parser.links
    assert payload["generated_as_of"] in parser.vintages


def test_project_exit_page_does_not_present_a_universal_verdict():
    page = PAGE.read_text(encoding="utf-8").lower()

    for phrase in (
        "best project",
        "overall rank",
        "project ranking",
        "universal rank",
        "winner",
    ):
        assert phrase not in page


def test_project_exit_tool_is_discoverable_as_a_tool():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    reports = [
        report
        for report in catalog["reports"]
        if report["id"] == "project-exit-comparison"
    ]

    assert len(reports) == 1
    assert reports[0]["path"] == "project_exit_comparison.html"
    assert reports[0]["category"] == "private-property"
    assert reports[0]["kind"] == "tool"
    assert reports[0]["featured"] is True
    assert 'href="project_exit_comparison.html"' in (
        ROOT / "index.html"
    ).read_text(encoding="utf-8")
