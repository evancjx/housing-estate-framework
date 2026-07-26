#!/usr/bin/env python3
"""Compatibility entry point for :mod:`sg_estate.application.master`."""

from pathlib import Path
import sys

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sg_estate.application.master import *  # noqa: F401,F403,E402

if __name__ == "__main__":
    main()
