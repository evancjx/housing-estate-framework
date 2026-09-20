#!/usr/bin/env python3
"""Package the reviewed frozen property evidence without local preview artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
DATE = "2026-09-20"


def selected_files(batch: Path) -> list[Path]:
    """Publish evidence and its provenance; leave browser caches and programs out."""
    files = []
    for path in sorted(batch.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(batch)
        if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            continue
        if any(marker in path.name.lower() for marker in ("storage-state", "storage_state", "credentials", "cookies", "token")):
            continue
        if len(relative.parts) == 1:
            include = path.suffix in {".csv", ".json"} and path.name not in {"report_data.json", "package_manifest.json"}
        else:
            include = (
                relative.parts[0] == "enrichment" and path.suffix in {".csv", ".json", ".md"}
                or relative.parts[0] in {"raw", "individual"} and path.suffix == ".csv"
            )
        if include:
            files.append(path)
    return files


def package(batch: Path, destination: Path) -> dict:
    files = selected_files(batch)
    required = {"transactions.csv", "transactions_original_fields.csv", "projects.csv", "cohorts.csv", "individual_report_manifest.json", "provenance.json", "enrichment/individual_editorial_notes.json", "enrichment/individual_project_profiles.json"}
    names = {path.relative_to(batch).as_posix() for path in files}
    if required - names:
        raise ValueError(f"Missing frozen evidence: {sorted(required - names)}")
    reports = json.loads((batch / "individual_report_manifest.json").read_text())
    if len(reports["reports"]) != 553 or len(reports["future_site_reports"]) != 4:
        raise ValueError("Unexpected individual project inventory")
    provenance = {"research_date": DATE, "projects": 553, "ec_origin_projects": 20, "future_sites": 4,
                  "note": "Frozen public-source evidence and derived research. Report sources and reproducible CLIs are committed separately in the repository.",
                  "files": [{"path": p.relative_to(batch).as_posix(), "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        def write(name, payload):
            entry = ZipInfo(name, date_time=(2026, 9, 20, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, payload, compresslevel=9)
        for path in files:
            write(path.relative_to(batch).as_posix(), path.read_bytes())
        write("package_manifest.json", json.dumps(provenance, indent=2).encode())
        write("README.md", ("# Frozen individual-property evidence\n\n"
                            "553 named projects, including 20 EC-origin developments, and four separately assessed future land sites.\n\n"
                            "All source-row occurrences are preserved. New Sale, Sub Sale, Resale, tenure and EC/private groups remain separate. Missing price, rent or completion evidence is not filled with a regional estimate.\n\n"
                            "See `package_manifest.json` for every file hash. See `docs/individual-property-research.md` in the repository for the reproducible offline commands and evidence limits.\n").encode())
    return {"files": len(files) + 2, "archive_bytes": destination.stat().st_size, "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=ROOT / f"data/runs/regional-property-analysis/{DATE}")
    parser.add_argument("--output", type=Path, default=ROOT / f"data/raw/property_research/{DATE}.zip")
    args = parser.parse_args()
    print(json.dumps(package(args.batch.resolve(), args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
