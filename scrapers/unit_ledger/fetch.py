"""Network acquisition for the unit ledger. Writes raw captures only; never interprets them."""

from __future__ import annotations

import csv
import difflib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from scrapers import ura_pmi_api
from scrapers.unit_ledger import sources

ROOT = Path(__file__).resolve().parents[2]
EDGEPROP_SCRIPT = ROOT / "scrapers" / "edgeprop_condo_apartment_playwright.py"
EDGEPROP_PROJECTS = ROOT / "data" / "raw" / "edgeprop" / "edgeprop_condo_apartment_projects.csv"
PROPERTYNOOB_URL = "https://propertynoob.com/condo/{slug}/sales"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


class ProjectNotFound(ValueError):
    def __init__(self, project: str, closest: list[str]):
        super().__init__(f"{project!r} is not a project in the URA API result. "
                         f"Closest URA names: {', '.join(closest) or 'none'}")


def fetch_ura(project: str) -> list[dict]:
    """Every URA PMI_Resi_Transaction project record whose name equals ``project``."""
    key = ura_pmi_api.get_access_key()
    session = requests.Session()
    token = ura_pmi_api.generate_token(key, session)
    wanted = project.strip().upper()
    matches, names = [], set()
    for batch in ura_pmi_api.API_BATCHES:
        data = ura_pmi_api.fetch_transactions(key, token, batch, session)
        if data.get("Status") != "Success":
            raise RuntimeError(f"URA batch {batch} returned Status={data.get('Status')!r}")
        for record in data.get("Result") or []:
            name = str(record.get("project", "")).strip().upper()
            names.add(name)
            if name == wanted:
                matches.append(record)
        time.sleep(1)
    if not matches:
        raise ProjectNotFound(project, difflib.get_close_matches(wanted, sorted(names), n=5, cutoff=0))
    return matches


def _lookup(path: Path, project: str) -> dict | None:
    with path.open(newline="", encoding="utf-8") as handle:
        hits = [row for row in csv.DictReader(handle) if row["name"].strip().upper() == project.strip().upper()]
    return hits[0] if len(hits) == 1 else None


def find_edgeprop_project(project: str, projects_csv: Path, logs: Path) -> dict | None:
    """The EdgeProp project row (name, url, slug), discovering it when the cached list lacks it."""
    if projects_csv.exists():
        hit = _lookup(projects_csv, project)
        if hit:
            return hit
    out = logs / "edgeprop_projects.csv"
    subprocess.run([sys.executable, str(EDGEPROP_SCRIPT), "discover", "--match", project.strip().lower(),
                    "--out", str(out)], cwd=ROOT, capture_output=True, text=True)
    return _lookup(out, project) if out.exists() else None


def fetch_edgeprop(link: dict, out_csv: Path, logs: Path) -> str | None:
    """Scrape every EdgeProp transaction for one project. Returns an error message, or None on success."""
    listing = logs / "edgeprop_input.csv"
    with listing.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "url", "slug"])
        writer.writeheader()
        writer.writerow({k: link[k] for k in ("name", "url", "slug")})
    command = [sys.executable, str(EDGEPROP_SCRIPT), "scrape", "--input", str(listing), "--from-year", "1990",
               "--max-pages", "1000", "--out", str(out_csv), "--log", str(logs / "edgeprop_attempts.csv")]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    (logs / "edgeprop_scrape.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0 or not out_csv.exists():
        tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["no rows written"]
        return f"EdgeProp scrape did not complete ({tail[0]}); affected rows have no exact date, block or floor."
    return None


def fetch_page(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()
    return response.text


def fetch_all(project: str, raw: Path, logs: Path, *, chart_url: str | None = None,
              recent_sales: Path | None = None) -> dict:
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    info = {"project": project.strip().upper(), "fetched_at_utc": fetched_at, "sources": {}, "warnings": []}

    def warn(source, url, message):
        info["sources"][source] = {"url": url, "status": "missing", "error": message}
        info["warnings"].append(message)

    records = fetch_ura(project)
    (raw / "ura.json").write_text(json.dumps(records, indent=1), encoding="utf-8")
    info["sources"]["ura"] = {"url": "URA Data Service PMI_Resi_Transaction", "status": "ok"}

    link = find_edgeprop_project(project, EDGEPROP_PROJECTS, logs)
    if link is None:
        warn("edgeprop", "", f"EdgeProp has no project page named {project!r}; rows have no exact date, block or floor.")
    else:
        error = fetch_edgeprop(link, raw / "edgeprop.csv", logs)
        if error:
            warn("edgeprop", link["url"], error)
        else:
            info["sources"]["edgeprop"] = {"url": link["url"], "status": "ok"}

    pn_url = PROPERTYNOOB_URL.format(slug=link["slug"] if link else sources.slugify(project))
    try:
        html = fetch_page(pn_url)
        sources.load_propertynoob(html, source_url=pn_url, fetched_at_utc=fetched_at)
    except requests.RequestException as exc:
        warn("propertynoob", pn_url, f"PropertyNoob page unavailable ({exc}); no published unit numbers.")
    except ValueError as exc:
        if "found 0" not in str(exc) and "no transaction rows" not in str(exc):
            raise
        warn("propertynoob", pn_url, f"PropertyNoob has no sales table at {pn_url}; no published unit numbers.")
    else:
        (raw / "propertynoob.html").write_text(html, encoding="utf-8")
        info["sources"]["propertynoob"] = {"url": pn_url, "status": "ok"}

    if chart_url:
        try:
            html = fetch_page(chart_url)
        except requests.RequestException as exc:
            warn("chart", chart_url, f"Unit chart unavailable ({exc}); the site view is derived from sales.")
        else:
            sources.parse_chart(html)  # an unsupported template aborts the run
            (raw / "chart.html").write_text(html, encoding="utf-8")
            info["sources"]["chart"] = {"url": chart_url, "status": "ok"}

    if recent_sales:
        sources.load_recent_sales(pd.read_csv(recent_sales, dtype=str))
        shutil.copyfile(recent_sales, raw / "recent_sales.csv")
        info["sources"]["recent_sales"] = {"url": str(recent_sales), "status": "ok"}

    (raw / "fetch.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    return info
