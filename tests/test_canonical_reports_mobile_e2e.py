"""Manifest-driven mobile release sweep for every published report."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import threading
import uuid

import pytest

from scripts import build_pages_site


ROOT = Path(__file__).resolve().parents[1]
MOBILE_VIEWPORT = {"width": 390, "height": 844}


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


@pytest.fixture(scope="module")
def canonical_mobile_site():
    """Build the real Pages catalog once and serve it to one cached browser."""

    playwright_api = pytest.importorskip("playwright.sync_api")
    with playwright_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except playwright_api.Error as error:
            pytest.skip(f"Chromium cannot launch in this environment: {error}")

        output = ROOT / (
            f".canonical-mobile-test-{os.getpid()}-{uuid.uuid4().hex}"
        )
        server = None
        thread = None
        context = None
        try:
            build_pages_site.build_site(output)
            catalog = json.loads(
                (output / "reports.json").read_text(encoding="utf-8")
            )
            reports = catalog["reports"]
            assert len(reports) > len(build_pages_site.load_catalog()["reports"])
            assert any(
                report.get("kind") == "property-analysis" for report in reports
            )

            handler = partial(_QuietHandler, directory=str(output))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            context = browser.new_context(
                viewport=MOBILE_VIEWPORT,
                reduced_motion="reduce",
            )
            page = context.new_page()
            page.set_default_timeout(7_000)
            base_url = f"http://127.0.0.1:{server.server_port}"
            yield page, base_url, reports
        finally:
            if context is not None:
                context.close()
            if server is not None:
                server.shutdown()
                server.server_close()
            if thread is not None:
                thread.join(timeout=2)
            browser.close()
            if output.is_dir():
                shutil.rmtree(output)


def _layout_diagnostics(page) -> dict:
    return page.evaluate(
        """
        () => {
          const root = document.documentElement;
          const viewportWidth = root.clientWidth;
          const scrollContainers = [];
          const uncontainedTables = [];
          const inaccessibleScrollContainers = [];

          const horizontalScroller = table => {
            for (let node = table; node && node !== document.body; node = node.parentElement) {
              const overflow = getComputedStyle(node).overflowX;
              if (
                ["auto", "scroll", "overlay"].includes(overflow)
                && node.scrollWidth > node.clientWidth + 1
              ) return node;
            }
            return null;
          };

          for (const [index, table] of [...document.querySelectorAll("table")].entries()) {
            const rect = table.getBoundingClientRect();
            const scroller = horizontalScroller(table);
            const isWide = rect.width > viewportWidth + 1;
            if (isWide && !scroller) {
              uncontainedTables.push({
                index,
                width: Math.round(rect.width),
                classes: table.className || "",
              });
            }
            if (!scroller || scrollContainers.includes(scroller)) continue;
            scrollContainers.push(scroller);
            const labelled = Boolean(
              scroller.getAttribute("aria-label")
              || scroller.getAttribute("aria-labelledby")
            );
            if (
              scroller.getAttribute("role") !== "region"
              || scroller.tabIndex < 0
              || !labelled
            ) {
              inaccessibleScrollContainers.push({
                tag: scroller.tagName.toLowerCase(),
                classes: scroller.className || "",
                role: scroller.getAttribute("role"),
                tabIndex: scroller.tabIndex,
                labelled,
              });
            }
          }

          return {
            clientWidth: viewportWidth,
            scrollWidth: root.scrollWidth,
            bodyScrollWidth: document.body.scrollWidth,
            uncontainedTables,
            inaccessibleScrollContainers,
          };
        }
        """
    )


def _skip_link_diagnostics(page) -> dict:
    return page.locator(".research-shell-skip").evaluate(
        """
        skip => {
          skip.focus();
          const href = skip.getAttribute("href") || "";
          const targetId = href.startsWith("#")
            ? decodeURIComponent(href.slice(1))
            : "";
          const target = targetId ? document.getElementById(targetId) : null;
          const rect = skip.getBoundingClientRect();
          const style = getComputedStyle(skip);
          return {
            href,
            targetExists: Boolean(target),
            focused: document.activeElement === skip,
            visible: rect.bottom > 0 && rect.right > 0
              && rect.left < document.documentElement.clientWidth
              && rect.top < document.documentElement.clientHeight,
            outlineStyle: style.outlineStyle,
            outlineWidth: parseFloat(style.outlineWidth) || 0,
          };
        }
        """
    )


def _menu_diagnostics(page) -> list[str]:
    failures = []
    toggle = page.locator(".research-shell-menu-toggle")
    links = page.locator(".research-shell-links")
    if toggle.count() != 1 or not toggle.is_visible():
        return ["mobile menu toggle is missing or hidden"]
    if toggle.get_attribute("aria-expanded") != "false":
        failures.append("mobile menu does not start collapsed")

    toggle.focus()
    focus = toggle.evaluate(
        """
        element => {
          const style = getComputedStyle(element);
          return {
            focused: document.activeElement === element,
            outlineStyle: style.outlineStyle,
            outlineWidth: parseFloat(style.outlineWidth) || 0,
          };
        }
        """
    )
    if (
        not focus["focused"]
        or focus["outlineStyle"] in {"none", "hidden"}
        or focus["outlineWidth"] < 2
    ):
        failures.append(f"menu toggle has no visible keyboard focus: {focus!r}")

    toggle.click()
    if toggle.get_attribute("aria-expanded") != "true" or not links.is_visible():
        failures.append("mobile menu cannot be opened")
        return failures
    if any(not link.is_visible() for link in links.locator("a, button").all()):
        failures.append("an open mobile-menu destination is hidden")

    page.keyboard.press("Escape")
    if toggle.get_attribute("aria-expanded") != "false" or links.is_visible():
        failures.append("Escape does not close the mobile menu")
    if not toggle.evaluate("element => document.activeElement === element"):
        failures.append("closing the mobile menu does not return focus")
    return failures


def test_every_canonical_report_passes_the_mobile_release_sweep(
    canonical_mobile_site,
) -> None:
    """Audit authored and generated reports without a hand-maintained URL list."""

    page, base_url, reports = canonical_mobile_site
    current_path = ""
    console_errors: list[tuple[str, str]] = []
    page_errors: list[tuple[str, str]] = []
    page.on(
        "console",
        lambda message: (
            console_errors.append((current_path, message.text))
            if message.type == "error"
            else None
        ),
    )
    page.on("pageerror", lambda error: page_errors.append((current_path, str(error))))

    failures: list[str] = []
    for report in reports:
        current_path = report["path"]
        before_console = len(console_errors)
        before_page_errors = len(page_errors)
        try:
            page.goto(
                f"{base_url}/{current_path}",
                wait_until="load",
                timeout=30_000,
            )
            page.locator(
                ".research-shell-nav[data-research-shell-enhanced='true']"
            ).wait_for(state="visible")
            page.wait_for_timeout(75)

            skip = _skip_link_diagnostics(page)
            if (
                not skip["targetExists"]
                or not skip["focused"]
                or not skip["visible"]
                or skip["outlineStyle"] in {"none", "hidden"}
                or skip["outlineWidth"] < 2
            ):
                failures.append(f"{current_path}: invalid skip link/focus {skip!r}")

            failures.extend(
                f"{current_path}: {message}" for message in _menu_diagnostics(page)
            )

            layout = _layout_diagnostics(page)
            if (
                layout["scrollWidth"] > layout["clientWidth"] + 1
                or layout["bodyScrollWidth"] > layout["clientWidth"] + 1
            ):
                failures.append(
                    f"{current_path}: document overflow "
                    f"{layout['scrollWidth']}/{layout['bodyScrollWidth']}px > "
                    f"{layout['clientWidth']}px"
                )
            if layout["uncontainedTables"]:
                failures.append(
                    f"{current_path}: uncontained wide tables "
                    f"{layout['uncontainedTables']!r}"
                )
            if layout["inaccessibleScrollContainers"]:
                failures.append(
                    f"{current_path}: inaccessible table scroll containers "
                    f"{layout['inaccessibleScrollContainers']!r}"
                )
        except Exception as error:  # keep the release matrix complete
            failures.append(f"{current_path}: sweep could not complete: {error}")

        report_console = console_errors[before_console:]
        report_page_errors = page_errors[before_page_errors:]
        if report_console:
            failures.append(f"{current_path}: console errors {report_console!r}")
        if report_page_errors:
            failures.append(f"{current_path}: page errors {report_page_errors!r}")

    assert not failures, "Mobile release sweep failures:\n" + "\n".join(failures)
