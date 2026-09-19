import csv

import pytest

from scrapers import edgeprop_condo_apartment_playwright as condo


def _write_log(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=condo.ATTEMPT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in condo.ATTEMPT_FIELDS})


@pytest.mark.parametrize(
    ("rows", "reason", "expected"),
    [
        ([{"x": 1}], "terminal_pagination", ("ok", "")),
        ([{"x": 1}], "from_year_boundary", ("ok", "")),
        ([], "terminal_pagination", ("failed", "zero_rows")),
        ([], "zero_rows", ("failed", "zero_rows")),
        ([{"x": 1}], "pagination_stalled", ("failed", "pagination_stalled")),
        ([{"x": 1}], "page_rows_missing", ("failed", "page_rows_missing")),
        ([{"x": 1}], "max_pages", ("failed", "max_pages")),
    ],
)
def test_condo_attempt_outcome_trusts_only_complete_non_empty_scrapes(rows, reason, expected):
    result = condo.ScrapeResult(rows=rows, completion_reason=reason)
    assert condo.attempt_outcome(result) == expected


def test_condo_resume_attempts_skips_only_complete_non_empty_urls(tmp_path):
    log = tmp_path / "attempts.csv"
    _write_log(log, [
        {"source_url": "ok", "row_count": "12", "status": "ok"},
        {"source_url": "legacy-zero", "row_count": "0", "status": "ok"},
        {"source_url": "partial", "row_count": "40", "status": "failed"},
        {"source_url": "error", "row_count": "0", "status": "error"},
    ])
    assert condo.read_succeeded_attempt_urls(log) == {"ok"}


def test_landed_attempt_outcome_and_resume(tmp_path):
    pytest.importorskip("playwright")
    from scrapers import edgeprop_landed_playwright as landed

    assert landed.attempt_outcome([{"x": 1}], "terminal_pagination") == ("ok", "")
    assert landed.attempt_outcome([], "terminal_pagination") == ("failed", "zero_rows")
    assert landed.attempt_outcome([{"x": 1}], "pagination_stalled") == ("failed", "pagination_stalled")
    assert landed.attempt_outcome([{"x": 1}], "max_pages") == ("failed", "max_pages")

    log = tmp_path / "attempts.csv"
    with log.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=landed.ATTEMPT_FIELDS)
        writer.writeheader()
        writer.writerow({"source_url": "ok", "row_count": 3, "status": "ok"})
        writer.writerow({"source_url": "legacy-zero", "row_count": 0, "status": "ok"})
        writer.writerow({"source_url": "partial", "row_count": 5, "status": "failed"})
    assert landed.read_succeeded_attempt_urls(log) == {"ok"}
