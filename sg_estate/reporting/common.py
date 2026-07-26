"""Shared value handling and safe publication helpers for HTML reports."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any

MISSING_TEXT = frozenset(
    {
        "",
        "nan",
        "NaN",
        "None",
        "N/A",
        "N/R",
        "no_data",
        "not_covered",
    }
)


def optional_value(value: Any) -> Any | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if str(value).strip() in MISSING_TEXT:
        return None
    return value


def optional_float(value: Any) -> float | None:
    value = optional_value(value)
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def html_json(value: Any, *, indent: int | None = None) -> str:
    """Serialize embedded data without allowing a value to close a script tag."""

    return json.dumps(value, indent=indent, ensure_ascii=False).replace("</", "<\\/")


def atomic_write_text(path: str | Path, content: str) -> Path:
    """Write a complete report before replacing its public path."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


__all__ = [
    "MISSING_TEXT",
    "atomic_write_text",
    "html_json",
    "optional_float",
    "optional_value",
]
