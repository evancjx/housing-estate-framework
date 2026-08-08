#!/usr/bin/env python3
"""Compatibility entry point for the verified official-source rail ingester.

The former implementation geocoded station names through OneMap and silently
collapsed interchange memberships by name.  Keep this filename for existing
operator workflows, but delegate to :mod:`models.ingest_lta_rail`, which
preserves one output row per code-line membership and validates the result.

Importing this module performs no network or filesystem writes.  Running it
accepts the same arguments as ``models/ingest_lta_rail.py``; use ``--help`` for
local-archive and validate-only options.
"""

from __future__ import annotations

import sys

try:
    from models.ingest_lta_rail import main
except ModuleNotFoundError:  # Direct execution from the models/ directory.
    from ingest_lta_rail import main


if __name__ == "__main__":
    print(
        "onemap_geocode_mrt.py is deprecated; delegating to ingest_lta_rail.py.",
        file=sys.stderr,
    )
    sys.exit(main())
