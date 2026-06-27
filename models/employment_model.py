#!/usr/bin/env python3
"""
Employment Accessibility Model  (Option A — station-count approximation)
=========================================================================
Scores each estate by transit commute time to 5 major employment nodes,
weighted by node employment size.

Methodology:
  - Travel times hand-estimated via MRT station counts + transfer penalties
  - ~2 min per station in-train, +8 min per interchange, +10 min door overhead
  - Accuracy: ±10 min. Good for band-level scoring, not trip planning.
  - Node weights reflect current (T0) employment concentration.
    JLD weight increases at T5/T15 as 100k jobs materialise.

Employment nodes:
  CBD          Raffles Place (EW14/NS26)     weight 45%  ~500k+ jobs
  JLD          Jurong East (EW24/NS1)        weight 20%  growing; 100k by 2040-50
  ONE_NORTH    one-north stn (CC23/EW23)     weight 15%  ~50k biomedical/tech
  CHANGI       Expo (EW29/CG1)              weight 10%  ~30k CBP/airport
  WOODLANDS    Woodlands stn (NS9/TE2)       weight 10%  ~20k regional centre

Score function:
  ≤15 min → 5.0  (excellent — within 45-min city target with headroom)
  16-25  → 4.5
  26-35  → 4.0
  36-45  → 3.0
  46-55  → 2.0
  >55    → 1.0

Sources:
  - MOT parliamentary statement Oct 2024 (Tengah→CBD 55→40 min post-JRL)
  - Rome2rio + station count: Jurong East→RP ~27-30 min
  - Zhu & Liu 2004 (corridor-specificity of MRT accessibility gains)
  - LTA LTMP 2040 (45-minute city target)
"""

import os

import pandas as pd
import numpy as np

# ── Node weights (T0) ──────────────────────────────────────────────────────
NODES = ["cbd", "jld", "one_north", "changi", "woodlands_rc"]
NODE_LABELS = {
    "cbd":          "CBD (Raffles Pl)",
    "jld":          "JLD (Jurong East)",
    "one_north":    "one-north",
    "changi":       "Changi/Expo",
    "woodlands_rc": "Woodlands RC",
}
WEIGHTS_T0  = {"cbd": 0.45, "jld": 0.20, "one_north": 0.15, "changi": 0.10, "woodlands_rc": 0.10}
WEIGHTS_T5  = {"cbd": 0.40, "jld": 0.25, "one_north": 0.15, "changi": 0.10, "woodlands_rc": 0.10}
WEIGHTS_T15 = {"cbd": 0.35, "jld": 0.30, "one_north": 0.15, "changi": 0.10, "woodlands_rc": 0.10}

# ── Travel time matrix (minutes, door-to-door ±10 min) ────────────────────
# Columns: cbd, jld, one_north, changi, woodlands_rc
# T0 = current. TENGAH: no MRT, bus to Jurong East (55 min to CBD per MOT).
# Post-JRL (T5): Tengah→CBD 40 min, Tengah→JLD 15 min (direct JRL).
TRAVEL_TIMES_T0 = {
  # estate            CBD  JLD  ONE  CHG  WRC
  "WOODLANDS":       ( 45,  62,  55,  62,   8),
  "CANBERRA":        ( 40,  60,  52,  58,  12),
  "SEMBAWANG":       ( 42,  62,  54,  60,  14),
  "YISHUN":          ( 37,  57,  48,  54,  20),
  "ANG MO KIO":      ( 30,  52,  42,  50,  28),
  "BISHAN":          ( 25,  48,  30,  45,  33),
  "TOA PAYOH":       ( 22,  50,  32,  47,  35),
  "SERANGOON":       ( 25,  50,  35,  35,  40),
  "HOUGANG":         ( 30,  55,  40,  32,  43),
  "SENGKANG":        ( 35,  58,  45,  30,  47),
  "PUNGGOL":         ( 40,  62,  50,  28,  52),
  "TAMPINES":        ( 32,  50,  42,  15,  55),
  "TAMPINES EAST":   ( 35,  53,  45,  18,  57),
  "TAMPINES WEST":   ( 30,  48,  40,  20,  53),
  "BEDOK":           ( 22,  42,  35,  27,  50),
  "PASIR RIS":       ( 40,  55,  47,  12,  62),
  "MARINE PARADE":   ( 18,  38,  28,  32,  50),
  "GEYLANG":         ( 15,  38,  25,  30,  47),
  "BOON KENG":       ( 18,  43,  35,  35,  42),
  "WOODLEIGH":       ( 22,  47,  38,  35,  42),
  "QUEENSTOWN":      ( 12,  22,  15,  42,  50),
  "DOVER":           ( 15,  18,  12,  45,  50),
  "CLEMENTI":        ( 22,  12,  12,  42,  48),
  "JURONG EAST":     ( 30,   5,  18,  52,  52),
  "CHOA CHU KANG":   ( 40,  22,  30,  57,  28),
  "BUKIT PANJANG":   ( 37,  22,  28,  55,  37),
  "BUKIT BATOK":     ( 33,  15,  22,  52,  30),
  "BUKIT TIMAH":     ( 28,  25,  20,  48,  45),
  "BUKIT MERAH":     ( 12,  30,  20,  38,  48),
  "LENTOR":          ( 28,  52,  38,  50,  18),
  "TENGAH":          ( 55,  40,  48,  65,  58),   # bus-dependent T0; JRL not open
  "CENTRAL AREA":    (  0,  30,  15,  35,  45),   # exits pipeline — shown for reference only
  # New estates added 2026-06 (§ missing estates)
  "JURONG WEST":     ( 35,  15,  22,  55,  55),   # Boon Lay area; EWL direct; JLD 3 stops
  "KALLANG":         ( 20,  38,  28,  28,  42),   # Old Airport Rd / Kallang River; CCL+EWL
  "HOLLAND VILLAGE": ( 22,  22,  12,  45,  48),   # CC21; one-north 2 stops; JLD via Buona Vista
}

# T5 (2031): JRL open mid-2028. Tengah times improve significantly.
# Other deltas: Tampines East gets TEL direct to CBD improvement, etc.
TRAVEL_TIMES_T5 = {k: list(v) for k, v in TRAVEL_TIMES_T0.items()}
TRAVEL_TIMES_T5["TENGAH"]          = [40, 15, 30, 60, 55]   # JRL open: CBD 55→40, JLD bus→15 min direct
TRAVEL_TIMES_T5["JURONG WEST"]     = [28, 10, 18, 52, 52]   # JRL opens ~2028: Boon Lay+Jurong West stations direct to JLD

# T15 (2041): West Coast Extension (-15 min conservative, vs max -20 min published)
TRAVEL_TIMES_T15 = {k: list(v) for k, v in TRAVEL_TIMES_T5.items()}
WCE_ESTATES = ["JURONG EAST","CHOA CHU KANG","BUKIT PANJANG","BUKIT BATOK","BUKIT TIMAH","CLEMENTI","DOVER","QUEENSTOWN","TENGAH"]
for e in WCE_ESTATES:
    t = list(TRAVEL_TIMES_T15[e])
    t[0] = max(10, t[0] - 15)
    TRAVEL_TIMES_T15[e] = t


# ── Scoring ───────────────────────────────────────────────────────────────
def time_to_score(t: float) -> float:
    if t <= 15: return 5.0
    if t <= 25: return 4.5
    if t <= 35: return 4.0
    if t <= 45: return 3.0
    if t <= 55: return 2.0
    return 1.0

BAND_EDGES = [(4.5,"A"),(4.0,"B+"),(3.5,"B"),(3.0,"C"),(2.5,"D"),(0,"F")]
def band(x):
    for edge, b in BAND_EDGES:
        if x >= edge: return b
    return "F"

def compute(times_dict, weights):
    rows = []
    for estate, times in times_dict.items():
        if estate == "CENTRAL AREA":
            continue
        cbd, jld, one, chg, wrc = times
        node_times  = {"cbd": cbd, "jld": jld, "one_north": one, "changi": chg, "woodlands_rc": wrc}
        node_scores = {n: time_to_score(t) for n, t in node_times.items()}
        weighted    = sum(weights[n] * node_scores[n] for n in NODES)
        best_node   = min(node_times, key=node_times.get)
        worst_node  = max(node_times, key=node_times.get)
        rows.append({
            "estate":         estate,
            "emp_score":      round(weighted, 2),
            "emp_band":       band(weighted),
            "t_cbd":          cbd,
            "t_jld":          jld,
            "t_one_north":    one,
            "t_changi":       chg,
            "t_woodlands_rc": wrc,
            "best_node":      best_node,
            "worst_node":     worst_node,
            "s_cbd":          node_scores["cbd"],
            "s_jld":          node_scores["jld"],
            "s_one_north":    node_scores["one_north"],
            "s_changi":       node_scores["changi"],
            "s_woodlands_rc": node_scores["woodlands_rc"],
        })
    return pd.DataFrame(rows).sort_values("emp_score", ascending=False)

if __name__ == "__main__":
    print("=" * 72)
    print("EMPLOYMENT ACCESSIBILITY SCORES — T0 (current)")
    print("Weights: CBD 45% | JLD 20% | one-north 15% | Changi 10% | WRC 10%")
    print("Times in minutes door-to-door (±10 min accuracy)")
    print("=" * 72)

    df0 = compute(TRAVEL_TIMES_T0, WEIGHTS_T0)
    show = ["estate","emp_band","emp_score","t_cbd","t_jld","t_one_north","t_changi","t_woodlands_rc","best_node","worst_node"]
    print(df0[show].to_string(index=False))

    print("\n" + "=" * 72)
    print("T5 (2031) — JRL open, Tengah upgraded")
    print("=" * 72)
    df5 = compute(TRAVEL_TIMES_T5, WEIGHTS_T5)
    print(df5[show].to_string(index=False))

    print("\n" + "=" * 72)
    print("T15 (2041) — West Coast Extension (-15 min west estates to CBD)")
    print("=" * 72)
    df15 = compute(TRAVEL_TIMES_T15, WEIGHTS_T15)
    print(df15[show].to_string(index=False))

    # ── Delta table ──
    merged = df0[["estate","emp_score","emp_band"]].merge(
        df5[["estate","emp_score","emp_band"]], on="estate", suffixes=("_T0","_T5")
    ).merge(df15[["estate","emp_score","emp_band"]], on="estate").rename(
        columns={"emp_score":"emp_score_T15","emp_band":"emp_band_T15"}
    )
    merged["delta_T5"]  = (merged["emp_score_T5"]  - merged["emp_score_T0"]).round(2)
    merged["delta_T15"] = (merged["emp_score_T15"] - merged["emp_score_T0"]).round(2)
    merged = merged.sort_values("emp_score_T0", ascending=False)

    print("\n" + "=" * 72)
    print("TRAJECTORY SUMMARY")
    print("=" * 72)
    print(merged[["estate","emp_band_T0","emp_score_T0","emp_band_T5","emp_score_T5","delta_T5",
                  "emp_band_T15","emp_score_T15","delta_T15"]].to_string(index=False))

    # Write outputs — __file__-relative so it works from any cwd (matches build_master/lease_risk).
    _D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    df0.to_csv(os.path.join(_D, "employment_scores_T0.csv"), index=False)
    df5.to_csv(os.path.join(_D, "employment_scores_T5.csv"), index=False)
    df15.to_csv(os.path.join(_D, "employment_scores_T15.csv"), index=False)
    merged.to_csv(os.path.join(_D, "employment_trajectory.csv"), index=False)
    print("\nWritten: employment_scores_T0/T5/T15.csv + employment_trajectory.csv")

# ======================================================================
# INPUT CONTRACT
# ======================================================================
# No external inputs — travel times are hard-coded from MRT station counts.
# To update: edit TRAVEL_TIMES_T0 dict (values = tuple of 5 ints in
# order: cbd, jld, one_north, changi, woodlands_rc).
# Methodology note: ±10 min accuracy. Sufficient for band scoring.
# Do NOT use this for trip planning.
# ======================================================================
