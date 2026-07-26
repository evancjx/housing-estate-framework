#!/usr/bin/env python3
"""Compatibility export for :mod:`sg_estate.domain.aliases`."""

from pathlib import Path
import sys

_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from sg_estate.domain.aliases import *  # noqa: F401,F403,E402
