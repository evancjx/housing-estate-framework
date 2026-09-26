"""Unit ledger command line.

    python3 -m scrapers.unit_ledger run --project "CANBERRA CRESCENT RESIDENCES" \\
        [--chart-url URL] [--recent-sales FILE.csv]
    python3 -m scrapers.unit_ledger rebuild data/runs/unit-ledger/<slug>/<YYYY-MM-DD>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scrapers.unit_ledger import build


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m scrapers.unit_ledger", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="fetch every source and build a run directory")
    run.add_argument("--project", required=True, help="project name exactly as URA publishes it")
    run.add_argument("--chart-url", help="singmap agent-site unit chart, e.g. https://<project>.isaacyee.com/units")
    run.add_argument("--recent-sales", type=Path, help="CSV with columns date,unit (developer's recently sold list)")
    rebuild = commands.add_parser("rebuild", help="rebuild outputs offline from a run directory's raw/")
    rebuild.add_argument("run_dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            out = build.run(args.project, chart_url=args.chart_url, recent_sales=args.recent_sales)
        else:
            build.build_run(args.run_dir)
            out = args.run_dir
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print((out / "README.md").read_text(encoding="utf-8"))
    print(f"Page: {out / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
