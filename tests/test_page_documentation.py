"""Coverage and link checks for per-HTML-report documentation."""

import json
from pathlib import Path
import re


ROOT = Path(__file__).parent.parent
GUIDES = ROOT / "docs" / "html-pages"
REQUIRED_HEADINGS = {
    "## Purpose",
    "## Data & Scope",
    "## Comparison Framework",
    "## Controls & Outputs",
    "## Interpretation Limits",
    "## Rebuild",
}
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _catalog():
    return json.loads((ROOT / "site" / "reports.json").read_text(encoding="utf-8"))


def test_every_catalogued_html_report_has_exactly_one_guide():
    expected = {
        Path(report["path"]).with_suffix(".md").name
        for report in _catalog()["reports"]
    }
    expected.add("index.md")
    actual = {path.name for path in GUIDES.glob("*.md")} - {"README.md"}

    assert actual == expected


def test_page_guides_follow_the_documentation_contract():
    reports = [{"path": "index.html"}, *_catalog()["reports"]]
    for report in reports:
        guide = GUIDES / Path(report["path"]).with_suffix(".md").name
        source = guide.read_text(encoding="utf-8")
        lines = source.splitlines()

        assert lines[0].startswith("# ")
        assert lines[1] == ""
        assert lines[2].startswith("> ") and len(lines[2]) > 2
        assert REQUIRED_HEADINGS <= set(lines)
        assert f"(../../{report['path']})" in source


def test_page_documentation_has_no_broken_local_markdown_links():
    broken = []
    for guide in GUIDES.glob("*.md"):
        source = guide.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(source):
            path = target.split("#", 1)[0]
            if not path or "://" in path:
                continue
            if not (guide.parent / path).resolve().exists():
                broken.append(f"{guide.name} -> {target}")

    assert broken == []


def test_removed_historical_documentation_is_not_referenced():
    references = []
    removed_directory = "docs/" + "superpowers"
    ignored_parts = {
        ".git",
        ".pytest_cache",
        ".superpowers",
        "__pycache__",
        "_site",
    }
    for path in ROOT.rglob("*"):
        if (
            path.is_file()
            and not ignored_parts.intersection(path.parts)
            and path != Path(__file__)
            and (
                path.suffix
                in {".md", ".json", ".py", ".yml", ".yaml", ".toml", ".ini"}
                or path.name == "Makefile"
            )
        ):
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if removed_directory in source:
                references.append(str(path.relative_to(ROOT)))

    assert references == []
