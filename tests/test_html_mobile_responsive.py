"""Static guards for root-level HTML report responsiveness."""

from __future__ import annotations

import re
from pathlib import Path

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


def _report_ids() -> list[str]:
    return [path.name for path in REPORTS]


def test_root_reports_exist() -> None:
    assert REPORTS, "Expected at least one root-level HTML report"


@pytest.mark.parametrize("report", REPORTS, ids=_report_ids())
def test_root_report_declares_mobile_viewport(report: Path) -> None:
    assert VIEWPORT_RE.search(report.read_text(encoding="utf-8")), (
        f"{report.name} must declare width=device-width"
    )


@pytest.mark.parametrize("report", REPORTS, ids=_report_ids())
def test_root_report_does_not_use_fixed_width_page_shell(report: Path) -> None:
    html = report.read_text(encoding="utf-8")
    assert not FIXED_SHELL_RE.search(html), (
        f"{report.name} uses a fixed pixel width on a page shell"
    )


@pytest.mark.parametrize("report", REPORTS, ids=_report_ids())
def test_wide_tables_have_horizontal_scroll_strategy(report: Path) -> None:
    html = report.read_text(encoding="utf-8")
    if "<table" not in html.lower():
        pytest.skip("Report has no table")
    assert SCROLLABLE_TABLE_RE.search(html), (
        f"{report.name} must contain a scrollable table wrapper or table"
    )
