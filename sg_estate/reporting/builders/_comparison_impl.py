"""Internal estate-comparison renderer; execute through ``comparison.build``.

Reads committed Provision, Liveability, tenure-segmented Value, employment,
lease-risk and life-path outputs, then writes ``comparison_table.html``.
"""

from __future__ import annotations

from datetime import date
import math

import pandas as pd

from sg_estate.paths import REPOSITORY_ROOT as ROOT
from sg_estate.reporting.common import (
    atomic_write_text,
    html_json,
    optional_float,
    optional_value,
)


TEMPLATE = ROOT / "sg_estate/reporting/templates/comparison_table.html"
PRICE_SIGNAL_HIGH = 1.10
PRICE_SIGNAL_LOW = 0.90
VALUE_TRUST_THRESHOLD = 100


def _value(value):
    """Return ``None`` for framework-level missing values."""

    return optional_value(value)


def _float(value):
    return optional_float(value)


def _band(value):
    value = _value(value)
    return None if value is None else str(value)


def _text(value):
    """Preserve controlled statuses such as ``no_data`` and ``not_covered``."""

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def _multiplier(value_score, segment_base):
    value = _float(value_score)
    base = _float(segment_base)
    if value is None or base is None or base == 0:
        return None
    return round(value / base, 4)


def _gap(value):
    value = _float(value)
    return round(value, 2) if value is not None else None


def _integer(value):
    value = _float(value)
    return int(value) if value is not None else None


def _trusted_multiplier(multiplier, sample_count):
    """Hide decimal Value adjustments below the publication trust threshold."""

    if sample_count is None or sample_count < VALUE_TRUST_THRESHOLD:
        return None
    return multiplier


def _flags(row, hdb_multiplier, private_multiplier, disruption):
    flags: list[str] = []
    if str(row.get("archetype", "")).strip() == "X":
        return "nr"
    if disruption is not None and disruption < 1.0:
        flags.append("disruption")
    for segment, multiplier in (
        ("hdb", hdb_multiplier),
        ("private", private_multiplier),
    ):
        if multiplier is None:
            continue
        if multiplier >= PRICE_SIGNAL_HIGH:
            flags.append(f"{segment}_price_below_model")
        elif multiplier <= PRICE_SIGNAL_LOW:
            flags.append(f"{segment}_price_above_model")
    return ",".join(flags)


master = pd.read_csv(ROOT / "data/outputs/master_output.csv")
provision_components = pd.read_csv(
    ROOT / "data/outputs/provision_scores.csv"
)[["estate", "noise"]].set_index("estate")


def _employment(horizon: str, output_name: str) -> pd.DataFrame:
    return (
        pd.read_csv(ROOT / f"data/outputs/employment_scores_{horizon}.csv")
        [["estate", "emp_band"]]
        .rename(columns={"emp_band": output_name})
        .set_index("estate")
    )


employment_t0 = _employment("T0", "t0")
employment_t5 = _employment("T5", "t5")
employment_t15 = _employment("T15", "t15")

life_paths = pd.read_csv(ROOT / "data/outputs/life_paths.csv")
life_largest = life_paths.loc[
    life_paths.groupby("estate")["delta"].idxmax()
].set_index("estate")
life_smallest = life_paths.loc[
    life_paths.groupby("estate")["delta"].idxmin()
].set_index("estate")

rows: list[dict] = []
for _, source in master.iterrows():
    estate = str(source["estate"]).strip()
    archetype = _band(source.get("archetype")) or "?"
    disruption = _float(source.get("D_T0"))
    if disruption is None:
        disruption = 1.0

    public_provision = _float(source.get("provision_score"))
    private_provision = _float(source.get("provision_private"))
    hdb_sample = _integer(source.get("value_hdb_n"))
    private_sample = _integer(source.get("value_private_n"))
    hdb_multiplier = _trusted_multiplier(
        _multiplier(source.get("value_hdb_score"), public_provision),
        hdb_sample,
    )
    private_multiplier = _trusted_multiplier(
        _multiplier(source.get("value_private_score"), private_provision),
        private_sample,
    )

    noise_raw = (
        provision_components.loc[estate, "noise"]
        if estate in provision_components.index
        else None
    )
    noise = (
        int(noise_raw)
        if noise_raw is not None and not math.isnan(float(noise_raw))
        else None
    )

    largest_path = (
        life_largest.loc[estate] if estate in life_largest.index else None
    )
    smallest_path = (
        life_smallest.loc[estate] if estate in life_smallest.index else None
    )

    rows.append(
        {
            "estate": estate,
            "arch": archetype,
            "d": disruption,
            "prov": _band(source.get("provision_band")),
            "score": (
                round(public_provision, 2)
                if public_provision is not None
                else None
            ),
            "noise": noise,
            "yf0": _band(source.get("yf_T0_band")),
            "sp0": _band(source.get("sp_T0_band")),
            "ret0": _band(source.get("ret_T0_band")),
            "ls0": _band(source.get("ls_T0_band")),
            "ls5": _band(source.get("ls_T5_band")),
            "ls15": _band(source.get("ls_T15_band")),
            "gap_yf": _gap(source.get("gap_yf_T0")),
            "gap_yf_label": _text(source.get("gap_yf_T0_label")),
            "gap_sp": _gap(source.get("gap_sp_T0")),
            "gap_sp_label": _text(source.get("gap_sp_T0_label")),
            "gap_ret": _gap(source.get("gap_ret_T0")),
            "gap_ret_label": _text(source.get("gap_ret_T0_label")),
            "gap_ls": _gap(source.get("gap_ls_T0")),
            "gap_ls_label": _text(source.get("gap_ls_T0_label")),
            "hdb_b": _band(source.get("value_hdb_band")),
            "hdb_m": hdb_multiplier,
            "hdb_n": hdb_sample,
            "hdb_basis": _text(source.get("value_hdb_basis")),
            "hdb_status": _text(source.get("value_hdb_status")),
            "pvt_b": _band(source.get("value_private_band")),
            "pvt_m": private_multiplier,
            "pvt_n": private_sample,
            "pvt_basis": _text(source.get("value_private_basis")),
            "pvt_status": _text(source.get("value_private_status")),
            "emp0": (
                str(employment_t0.loc[estate, "t0"])
                if estate in employment_t0.index
                else None
            ),
            "emp5": (
                str(employment_t5.loc[estate, "t5"])
                if estate in employment_t5.index
                else None
            ),
            "emp15": (
                str(employment_t15.loc[estate, "t15"])
                if estate in employment_t15.index
                else None
            ),
            "lease": _band(source.get("lease_band")),
            "best": (
                str(largest_path["path"]) if largest_path is not None else None
            ),
            "best_delta": (
                round(float(largest_path["delta"]), 2)
                if largest_path is not None
                else None
            ),
            "worst": (
                str(smallest_path["path"]) if smallest_path is not None else None
            ),
            "worst_delta": (
                round(float(smallest_path["delta"]), 2)
                if smallest_path is not None
                else None
            ),
            "flag": _flags(
                dict(source), hdb_multiplier, private_multiplier, disruption
            ),
        }
    )

model_versions = sorted(
    {
        str(value).strip()
        for value in master.get("model_version", pd.Series(dtype=str)).dropna()
        if str(value).strip()
    }
)
model_version = ", ".join(model_versions) or "not recorded"


def render_html(*, generated_on: date | None = None) -> str:
    """Render the current committed estate outputs without writing a file."""

    generated_on = generated_on or date.today()
    html = TEMPLATE.read_text(encoding="utf-8")
    replacements = {
        "__ESTATE_COUNT__": str(len(rows)),
        "__MODEL_VERSION__": model_version,
        "__GENERATED_DATE_ISO__": generated_on.isoformat(),
        "__GENERATED_DATE_LABEL__": f"{generated_on.day} {generated_on:%b %Y}",
        "__ESTATE_DATA_JSON__": html_json(rows, indent=2),
    }
    for marker, value in replacements.items():
        html = html.replace(marker, value)

    unresolved = [marker for marker in replacements if marker in html]
    if unresolved:
        raise RuntimeError(f"Unresolved comparison template markers: {unresolved}")
    return html


def main() -> None:
    output = ROOT / "comparison_table.html"
    atomic_write_text(output, render_html())
    print(
        f"Written: {output} ({output.stat().st_size // 1024} KB, "
        f"{len(rows)} estates)"
    )


if __name__ == "__main__":
    main()
