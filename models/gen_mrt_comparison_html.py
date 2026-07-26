#!/usr/bin/env python3
"""Compatibility entry point for the canonical MRT-comparison builder."""

from pathlib import Path
import sys

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> None:
    from sg_estate.reporting.builders.mrt_comparison import main as canonical_main

    canonical_main()


if __name__ == "__main__":
    main()
