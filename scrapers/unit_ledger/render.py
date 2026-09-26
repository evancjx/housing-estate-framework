"""Render the unit ledger's self-contained HTML page."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

TEMPLATE = Path(__file__).with_name("template.html")


def _records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records"))


def _embed(value) -> str:
    # "</" inside a <script> block would end it early; JSON allows the escaped form.
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def render(ledger: pd.DataFrame, units: pd.DataFrame, meta: dict) -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    for token, value in (("__META__", meta), ("__TRANSACTIONS__", _records(ledger)), ("__UNITS__", _records(units))):
        if html.count(token) != 1:
            raise ValueError(f"template must contain {token} exactly once")
        html = html.replace(token, _embed(value))
    return html
