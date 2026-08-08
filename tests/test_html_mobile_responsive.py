"""Static guards for root-level HTML report responsiveness."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
REPORTS = sorted(ROOT.glob("*.html"))

VIEWPORT_RE = re.compile(
    r"<meta\s+name=[\"']viewport[\"']\s+"
    r"content=[\"'][^\"']*width=device-width[^\"']*[\"']",
    re.IGNORECASE,
)
FIXED_SHELL_RE = re.compile(
    r"(?:^|,)\s*(?:body|main|\.page|\.shell|\.container)\s*"
    r"\{[^}]*(?<!-)\bwidth\s*:\s*\d{3,}px\b",
    re.IGNORECASE | re.MULTILINE,
)
SCROLLABLE_TABLE_RE = re.compile(
    r"(?:"
    r"\.[\w-]*(?:wrap|scroll|responsive)[\w-]*"
    r"|table(?:\.[\w-]+)?"
    r")\s*\{[^}]*\boverflow(?:-x)?\s*:\s*(?:auto|scroll)\b",
    re.IGNORECASE | re.DOTALL,
)
STYLESHEET_RE = re.compile(
    r"<link\b[^>]*\bhref=[\"']([^\"']+\.css(?:\?[^\"']*)?)[\"'][^>]*>",
    re.IGNORECASE,
)


def _report_ids() -> list[str]:
    return [path.name for path in REPORTS]


def _responsive_source(report: Path) -> str:
    """Return authored HTML plus local linked CSS used by the Pages build."""

    html = report.read_text(encoding="utf-8")
    sources = [html]
    for reference in STYLESHEET_RE.findall(html):
        parsed = urlsplit(reference)
        if parsed.scheme or parsed.path.startswith("/") or ".." in Path(parsed.path).parts:
            continue
        stylesheet = ROOT / parsed.path
        if not stylesheet.is_file() and parsed.path.startswith("assets/"):
            stylesheet = ROOT / "site" / parsed.path
        if stylesheet.is_file():
            sources.append(stylesheet.read_text(encoding="utf-8"))
    return "\n".join(sources)


def test_root_reports_exist() -> None:
    assert REPORTS, "Expected at least one root-level HTML report"


@pytest.mark.parametrize("report", REPORTS, ids=_report_ids())
def test_root_report_declares_mobile_viewport(report: Path) -> None:
    assert VIEWPORT_RE.search(report.read_text(encoding="utf-8")), (
        f"{report.name} must declare width=device-width"
    )


@pytest.mark.parametrize("report", REPORTS, ids=_report_ids())
def test_root_report_does_not_use_fixed_width_page_shell(report: Path) -> None:
    source = _responsive_source(report)
    assert not FIXED_SHELL_RE.search(source), (
        f"{report.name} uses a fixed pixel width on a page shell"
    )


@pytest.mark.parametrize("report", REPORTS, ids=_report_ids())
def test_wide_tables_have_horizontal_scroll_strategy(report: Path) -> None:
    html = report.read_text(encoding="utf-8")
    if "<table" not in html.lower():
        pytest.skip("Report has no table")
    assert SCROLLABLE_TABLE_RE.search(_responsive_source(report)), (
        f"{report.name} must contain a scrollable table wrapper or table"
    )
