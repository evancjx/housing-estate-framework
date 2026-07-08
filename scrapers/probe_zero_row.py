#!/usr/bin/env python3
"""Probe why a condo project page yields 0 parsed transaction rows.

Loads the page like edgeprop_condo_apartment_playwright.scrape_project does,
captures evidence at each stage (initial text, advertised count, after-scroll
text), and reports where rows first become parseable.

Run:
    python3 scrapers/probe_zero_row.py the-jovell
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from edgeprop_condo_apartment_playwright import (  # noqa: E402
    BASE_URL,
    DEFAULT_USER_AGENT,
    advertised_sales_count,
    parse_transaction_text,
)
from playwright.async_api import async_playwright  # noqa: E402

PROBE_DIR = Path("data/raw/edgeprop/probe")


async def probe(slug: str) -> None:
    url = f"{BASE_URL}/condo-apartment/{slug}"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(user_agent=DEFAULT_USER_AGENT)
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(3_000)

        async def snapshot(stage: str) -> str:
            text = await page.locator("body").inner_text(timeout=15_000)
            rows = parse_transaction_text(text)
            count = advertised_sales_count(text)
            has_section = await page.locator("#SalesTransaction").count()
            print(f"[{stage}] parsed_rows={len(rows)} advertised={count} "
                  f"#SalesTransaction nodes={has_section} text_len={len(text)}")
            (PROBE_DIR / f"probe_{slug}_{stage}.txt").write_text(text, encoding="utf-8")
            return text

        await snapshot("initial")

        # scroll to the sales section (lazy-load hypothesis)
        section = page.locator("#SalesTransaction")
        if await section.count():
            await section.first.scroll_into_view_if_needed(timeout=10_000)
        else:
            await page.mouse.wheel(0, 20_000)
        await page.wait_for_timeout(4_000)
        await snapshot("after_scroll")

        # give lazy content generous extra time
        await page.wait_for_timeout(6_000)
        text = await snapshot("after_wait")

        # mark the section HTML for inspection
        if await section.count():
            html_text = await section.first.inner_html(timeout=10_000)
            (PROBE_DIR / f"probe_{slug}_section.html").write_text(html_text, encoding="utf-8")
            print(f"section html saved ({len(html_text)} chars)")
        title = await page.title()
        print("page title:", title)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(probe(sys.argv[1] if len(sys.argv) > 1 else "the-jovell"))
