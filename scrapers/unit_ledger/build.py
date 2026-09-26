"""Assemble a unit-ledger run directory: offline from raw/, or after a fresh fetch."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

from scrapers.unit_ledger import layout, match, sources
from scrapers.unit_ledger.render import render

ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = ROOT / "data" / "runs" / "unit-ledger"


def _readme(meta: dict) -> str:
    c = meta["counts"]
    lines = [
        f"# {meta['project']}: unit ledger", "",
        f"Fetched {meta['fetched_at_utc']}. Research output, not a model input. Unit numbers come from "
        "third-party sources and are not official. Open `index.html` for the table and site view.", "",
        "| Measure | Count |", "| --- | ---: |",
        f"| Transactions | {c['transactions']} |",
        f"| From the URA API (last five years) | {c['ura']} |",
        f"| Older, not verified against the URA API | {c['pre_window']} |",
        f"| With an exact date | {c['dated']} |",
        f"| With a unit number | {c['with_unit']} |",
        f"| Ambiguous | {c['ambiguous']} |",
        f"| Not found | {c['not_found']} |",
    ]
    if c["uniquely_located"] is not None:
        lines.append(f"| URA rows whose block, floor and size alone fix the unit | {c['uniquely_located']} |")
    lines += ["", "## How units were matched", "", "| Rule | Rows |", "| --- | ---: |"]
    lines += [f"| {rule} | {n} |" for rule, n in sorted(c["unit_source"].items())]
    lines += ["", "## Warnings", ""] + ([f"- {w}" for w in meta["warnings"]] or ["None."])
    return "\n".join(lines) + "\n"


def build_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    raw = run_dir / "raw"
    fetch_info = json.loads((raw / "fetch.json").read_text(encoding="utf-8"))
    warnings = list(fetch_info.get("warnings", []))

    ura = sources.load_ura(json.loads((raw / "ura.json").read_text(encoding="utf-8")))
    ep = sources.load_edgeprop([pd.read_csv(p, dtype=str, keep_default_na=False)
                                for p in sorted(raw.glob("edgeprop*.csv"))])
    chart, chart_as_of = (sources.parse_chart((raw / "chart.html").read_text(encoding="utf-8"))
                          if (raw / "chart.html").exists() else (None, ""))
    pn = (sources.load_propertynoob((raw / "propertynoob.html").read_text(encoding="utf-8"),
                                    source_url=fetch_info["sources"]["propertynoob"]["url"],
                                    fetched_at_utc=fetch_info["fetched_at_utc"])
          if (raw / "propertynoob.html").exists() else sources.empty_propertynoob())
    recent = (sources.load_recent_sales(pd.read_csv(raw / "recent_sales.csv", dtype=str))
              if (raw / "recent_sales.csv").exists() else sources.empty_recent_sales())
    has_chart = chart is not None

    result = match.match_all(ura, ep, pn, chart, recent)
    ledger = result.ledger
    units = layout.summarise_units(result.units, ledger, recent, has_chart)

    no_edgeprop = int(((ledger.origin == "URA") & (ledger.sale_date == "")).sum())
    if no_edgeprop:
        warnings.append(f"{no_edgeprop} URA transactions have no matching EdgeProp record, "
                        "so they have no exact date, block or floor.")
    if result.unmatched_edgeprop:
        warnings.append(f"{result.unmatched_edgeprop} EdgeProp rows inside the URA window match no URA transaction.")
    if result.unmatched_propertynoob:
        warnings.append(f"{result.unmatched_propertynoob} PropertyNoob rows inside the URA window match no "
                        "transaction (for example a lapsed booking, or a sale URA has not published).")

    counts = {
        "transactions": len(ledger),
        "ura": int((ledger.origin == "URA").sum()),
        "pre_window": int((ledger.origin == "Pre-window").sum()),
        "dated": int((ledger.sale_date != "").sum()),
        "with_unit": int((ledger.unit != "").sum()),
        "ambiguous": int(ledger.unit_source.str.startswith("Ambiguous").sum()),
        "not_found": int((ledger.unit_source == "Not found").sum()),
        "uniquely_located": match.uniquely_located_count(ledger, chart) if has_chart else None,
        "unit_source": {k: int(v) for k, v in ledger.unit_source.str.split(":").str[0].value_counts().items()},
    }
    meta = {"project": fetch_info["project"], "fetched_at_utc": fetch_info["fetched_at_utc"],
            "chart_as_of": chart_as_of, "has_chart": has_chart, "warnings": warnings, "counts": counts}

    ledger.to_csv(run_dir / "transactions.csv", index=False)
    units.to_csv(run_dir / "units.csv", index=False)
    (run_dir / "index.html").write_text(render(ledger, units, meta), encoding="utf-8")
    provenance = {**fetch_info, "warnings": warnings, "counts": counts, "chart_as_of": chart_as_of,
                  "raw_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(raw.iterdir()) if p.is_file()}}
    (run_dir / "provenance.json").write_text(json.dumps(provenance, indent=1), encoding="utf-8")
    (run_dir / "README.md").write_text(_readme(meta), encoding="utf-8")
    return meta


def run(project: str, *, chart_url: str | None = None, recent_sales: Path | None = None,
        runs_root: Path = RUNS_ROOT, today: str | None = None) -> Path:
    """Fetch and build into a partial directory; replace the day's run only once everything succeeded."""
    from scrapers.unit_ledger import fetch  # network dependencies load only when fetching

    today = today or date.today().isoformat()
    final = Path(runs_root) / sources.slugify(project) / today
    work = final.with_name(f".{today}.partial")
    shutil.rmtree(work, ignore_errors=True)
    (work / "raw").mkdir(parents=True)
    (work / "logs").mkdir()
    try:
        fetch.fetch_all(project, work / "raw", work / "logs", chart_url=chart_url, recent_sales=recent_sales)
        build_run(work)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    if final.exists():
        shutil.rmtree(final)
    work.rename(final)
    return final
