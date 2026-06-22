#!/usr/bin/env python3
"""
Build aggregate master outputs from the canonical pipeline CSVs.

Outputs:
  data/life_paths.csv
  data/master_output.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

try:
    from framework_config import DATA_DIR
except ImportError:  # pragma: no cover - supports package-style imports
    from models.framework_config import DATA_DIR


PATHS: Dict[str, Tuple[str, str]] = {
    "forming_family": ("sp_T0", "yf_T5"),
    "downsizing": ("yf_T0", "ret_T5"),
    "settling_single": ("ls_T0", "sp_T5"),
    "ageing_in_place": ("ret_T0", "ret_T5"),
}


def arrow(delta: float) -> str:
    if delta > 0.1:
        return "up"
    if delta < -0.1:
        return "down"
    return "flat"


def band_column(score_col: str) -> str:
    persona, horizon = score_col.split("_", 1)
    return f"{persona}_{horizon}_band"


def build_life_paths(liveability: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in liveability.iterrows():
        estate = row["estate"]
        path_defs = dict(PATHS)
        path_defs["upgrader"] = (
            "sp_T0",
            "yf_T5" if row["yf_T5"] >= row["ls_T5"] else "ls_T5",
        )

        for path, (start_col, end_col) in path_defs.items():
            start_score = float(row[start_col])
            end_score = float(row[end_col])
            start_band = row[band_column(start_col)]
            end_band = row[band_column(end_col)]
            delta = round(end_score - start_score, 3)
            rows.append({
                "estate": estate,
                "path": path,
                "start_score": round(start_score, 3),
                "start_band": start_band,
                "end_score": round(end_score, 3),
                "end_band": end_band,
                "delta": delta,
                "arrow": arrow(delta),
                "band_shift": f"{start_band}->{end_band}",
            })
    return pd.DataFrame(rows)


def value_summary(path: Path, prefix: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = ["estate", "value_band", "mult", "n"]
    out = df[cols].copy()
    return out.rename(columns={
        "value_band": f"{prefix}_band",
        "mult": f"{prefix}_mult",
        "n": f"{prefix}_n",
    })


def notes_for(row: pd.Series) -> str:
    notes = []
    if row.get("D_T0", 1.0) < 1.0:
        notes.append(f"Active disruption: D={row['D_T0']:.2f}")
    mult = row.get("value_prov_mult")
    if pd.notna(mult):
        if mult < 0.90:
            notes.append("Overpriced vs provision")
        elif mult > 1.10:
            notes.append("Underpriced vs provision")
    if row["estate"] == "CENTRAL AREA":
        notes.append("Exits pipeline (N/R)")
    return "; ".join(notes)


def build_master(data_dir: Path) -> pd.DataFrame:
    provision = pd.read_csv(data_dir / "provision_scores.csv")
    liveability = pd.read_csv(data_dir / "liveability_matrix.csv")
    archetypes = pd.read_csv(data_dir / "archetype_assignments.csv")
    value_prov = value_summary(data_dir / "value_output.csv", "value_prov")
    value_yf = value_summary(data_dir / "value_live_yf.csv", "value_live_yf")
    value_sp = value_summary(data_dir / "value_live_sp.csv", "value_live_sp")
    value_ret = value_summary(data_dir / "value_live_ret.csv", "value_live_ret")
    value_ls = value_summary(data_dir / "value_live_ls.csv", "value_live_ls")
    employment_t0 = pd.read_csv(data_dir / "employment_scores_T0.csv")
    employment_traj = pd.read_csv(data_dir / "employment_trajectory.csv")
    lease = pd.read_csv(data_dir / "lease_risk.csv")

    private_frames = []
    for filename in ["value_private_d15_d16.csv", "value_private_d5_d21_d27.csv"]:
        path = data_dir / filename
        if path.exists():
            private_frames.append(pd.read_csv(path))
    if private_frames:
        private_value = pd.concat(private_frames, ignore_index=True)
        private_value = private_value[["estate", "value_band", "mult", "n"]].rename(columns={
            "value_band": "value_private_band",
            "mult": "value_private_mult",
            "n": "value_private_n",
        })
    else:
        private_value = pd.DataFrame(columns=[
            "estate", "value_private_band", "value_private_mult", "value_private_n"
        ])

    life_paths = build_life_paths(liveability)
    life_paths.to_csv(data_dir / "life_paths.csv", index=False)
    best_paths = (
        life_paths.sort_values(["estate", "end_score", "delta"], ascending=[True, False, False])
        .drop_duplicates("estate")
        [["estate", "path", "end_band"]]
        .rename(columns={"path": "best_lifepath_name", "end_band": "best_lifepath_end_band"})
    )
    worst_paths = (
        life_paths.sort_values(["estate", "end_score", "delta"], ascending=[True, True, True])
        .drop_duplicates("estate")
        [["estate", "path", "end_score"]]
        .rename(columns={
            "path": "worst_lifepath_name",
            "end_score": "worst_lifepath_end_score",
        })
    )

    master = archetypes[["estate", "archetype"]].merge(
        provision[["estate", "provision", "band", "noise"]],
        on="estate",
        how="right",
    )
    master = master.rename(columns={
        "provision": "provision_score",
        "band": "provision_band",
        "noise": "noise_score",
    })

    liveability_cols = [
        "estate", "D_T0",
        "yf_T0", "yf_T0_band", "yf_T5", "yf_T5_band", "yf_T15", "yf_T15_band",
        "sp_T0", "sp_T0_band", "sp_T5", "sp_T5_band", "sp_T15", "sp_T15_band",
        "ret_T0", "ret_T0_band", "ret_T5", "ret_T5_band", "ret_T15", "ret_T15_band",
        "ls_T0", "ls_T0_band", "ls_T5", "ls_T5_band", "ls_T15", "ls_T15_band",
        "gap_yf_T0", "gap_yf_T5", "gap_yf_T15",
        "gap_sp_T0", "gap_sp_T5", "gap_sp_T15",
        "gap_ret_T0", "gap_ret_T5", "gap_ret_T15",
        "gap_ls_T0", "gap_ls_T5", "gap_ls_T15",
    ]
    master = master.merge(liveability[liveability_cols], on="estate", how="left")

    for value_df in [value_prov, value_yf, value_sp, value_ret, value_ls]:
        master = master.merge(value_df, on="estate", how="left")

    master = master.merge(best_paths, on="estate", how="left")
    master = master.merge(worst_paths, on="estate", how="left")

    master = master.merge(private_value, on="estate", how="left")
    emp_cols = [
        "estate", "emp_score_T0", "emp_band_T0",
        "emp_score_T5", "emp_band_T5", "emp_score_T15", "emp_band_T15",
    ]
    master = master.merge(employment_traj[emp_cols], on="estate", how="left")
    master = master.merge(
        employment_t0[["estate", "best_node", "worst_node"]],
        on="estate",
        how="left",
    )
    master = master.merge(
        lease[["estate", "lease_score", "lease_band"]],
        on="estate",
        how="left",
    )
    master["notes"] = master.apply(notes_for, axis=1)
    master["notes"] = master["notes"].replace("", np.nan)

    columns = [
        "estate", "archetype", "provision_score", "provision_band", "D_T0",
        "yf_T0", "yf_T0_band", "yf_T5", "yf_T5_band", "yf_T15", "yf_T15_band",
        "sp_T0", "sp_T0_band", "sp_T5", "sp_T5_band", "sp_T15", "sp_T15_band",
        "ret_T0", "ret_T0_band", "ret_T5", "ret_T5_band", "ret_T15", "ret_T15_band",
        "ls_T0", "ls_T0_band", "ls_T5", "ls_T5_band", "ls_T15", "ls_T15_band",
        "gap_yf_T0", "gap_yf_T5", "gap_yf_T15",
        "gap_sp_T0", "gap_sp_T5", "gap_sp_T15",
        "gap_ret_T0", "gap_ret_T5", "gap_ret_T15",
        "gap_ls_T0", "gap_ls_T5", "gap_ls_T15",
        "value_prov_band", "value_prov_mult", "value_prov_n",
        "value_live_yf_band", "value_live_sp_band", "value_live_ret_band",
        "value_live_ls_band", "value_live_ls_mult",
        "best_lifepath_name", "best_lifepath_end_band",
        "worst_lifepath_name", "worst_lifepath_end_score",
        "notes",
        "value_private_band", "value_private_mult", "value_private_n",
        "emp_score_T0", "emp_band_T0", "best_node", "worst_node",
        "emp_score_T5", "emp_band_T5", "emp_score_T15", "emp_band_T15",
        "lease_score", "lease_band", "noise_score",
    ]
    return master[columns]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build aggregate master output")
    parser.add_argument("--data-dir", default=str(DATA_DIR), help="Directory containing pipeline CSVs")
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    master = build_master(data_dir)
    master.to_csv(data_dir / "master_output.csv", index=False)
    print(f"Wrote {len(master)} rows -> {data_dir / 'master_output.csv'}")
    print(f"Wrote {len(master) * 5} rows -> {data_dir / 'life_paths.csv'}")


if __name__ == "__main__":
    main()
