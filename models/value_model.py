#!/usr/bin/env python3
"""
Singapore Estate Value Residual Model  (Document 2, Section 3)
==============================================================
Computes the VALUE score: is an estate cheap or dear RELATIVE TO what its
liveability/provision predicts? (Not "is it expensive" — that punishes good
estates for being good.)

    ValueResidual(a,g) = median regression residual of ln(price_psm) within
                         subzone a, segment g, after controlling for the
                         provision/liveability score + dwelling + tenure + month.
    ValueScore(a,g)    = LiveabilityOrProvision(a) * exp(-ValueResidual(a,g))

NEGATIVE residual  -> cheaper than predicted -> GOOD value (score lifts)
POSITIVE residual  -> dearer than predicted  -> POOR value (score drops)

Hard rules from the framework (do not remove):
  * HDB and PRIVATE are SEPARATE universes -> modelled as separate segments,
    never blended. (HDB resale = HDB/data.gov.sg; private = URA.)
  * Hierarchical shrinkage: thin subzone samples are pulled toward their
    town/segment mean so a handful of odd transactions can't swing the score.
  * Adjustment multiplier capped to [0.75, 1.25] until calibrated.
  * Output is a BAND unless the sample is large enough to trust a decimal.

RUN:
    pip install pandas numpy statsmodels --break-system-packages
    python value_model.py --hdb hdb_resale.csv --private ura_private.csv \
                          --scores provision_scores.csv
All three CSVs are optional individually; supply whichever segment you have.
See INPUT CONTRACT at the bottom of this file for exact column names.
"""

import argparse, sys, json
import numpy as np
import pandas as pd
from aliases import ESTATE_TOWN_ALIAS, PRIVATE_DOMINANT_PROXIES

# ----------------------------------------------------------------------
# 1. CONFIG — the only knobs. Documented so a future run can challenge them.
# ----------------------------------------------------------------------
CFG = {
    "adj_cap_low": 0.75,        # min Value adjustment multiplier (framework lock)
    "adj_cap_high": 1.25,       # max Value adjustment multiplier
    "shrink_min_n": 30,         # below this many txns, shrink subzone toward town mean
    "shrink_strength": 30.0,    # k in James-Stein-style pull: w = n/(n+k)
    "trust_decimal_n": 100,     # below this, report BAND only, not a decimal
    "band_edges": [(4.5,"A"),(4.0,"B+"),(3.5,"B"),(3.0,"C"),(2.5,"D"),(0,"F")],
}

def band(x):
    for edge,b in CFG["band_edges"]:
        if x >= edge: return b
    return "F"


def build_formula(df, controls, month_col):
    """RHS = within-segment quality controls only. Provision score is NEVER here."""
    ctrl_terms = []
    for c in controls:
        if c in df.columns:
            ctrl_terms.append(f"C({c})" if df[c].dtype == object else c)
    if month_col in df.columns:
        ctrl_terms.append(f"C({month_col})")
    rhs = " + ".join(ctrl_terms) if ctrl_terms else "1"
    return f"_lnpsm ~ {rhs}"

def clean_psm(df, price_col, area_col):
    """Compute price-per-sqm and drop non-finite / non-positive rows (incl. area==0)."""
    df = df.copy()
    df["_psm"] = df[price_col] / df[area_col]
    df = df[(df[area_col] > 0) & np.isfinite(df["_psm"]) & (df["_psm"] > 0)]
    df["_lnpsm"] = np.log(df["_psm"])
    return df

# ----------------------------------------------------------------------
# 2. SEGMENT MODELS — controls differ by tenure (framework §3 table)
# ----------------------------------------------------------------------
SEGMENTS = {
    "hdb_resale": {
        "price_col": "resale_price",
        "area_col":  "floor_area_sqm",
        "controls":  ["flat_type", "storey_band", "remaining_lease_years"],
        "month_col": "month",
        "area_key":  "town",          # geographic rollup key in the file
    },
    "private_resale": {
        "price_col": "transacted_price",
        "area_col":  "area_sqm",
        "controls":  ["property_type", "tenure", "project_age_years"],
        "month_col": "sale_month",
        "area_key":  "planning_area",
    },
    "private_rental": {
        "price_col": "monthly_rent",
        "area_col":  "area_sqm",
        "controls":  ["property_type", "project_age_years"],
        "month_col": "lease_month",
        "area_key":  "planning_area",
    },
}

# ----------------------------------------------------------------------
# 3. CORE — fit ln(price_psm) ~ controls + C(month), take residuals
# ----------------------------------------------------------------------
def fit_segment(df, seg_name, scores):
    import statsmodels.formula.api as smf
    s = SEGMENTS[seg_name]
    df = df.copy()

    # price per sqm, logged
    n_before = len(df)
    df = clean_psm(df, s["price_col"], s["area_col"])
    dropped = n_before - len(df)
    if dropped:
        print(f"  [{seg_name}] dropped {dropped} rows with non-finite/zero psm")

    # Expand scores: for each alias whose target town has no score yet,
    # inject a shadow row using the alias estate's score so the regression
    # includes that town's transactions (residual is later attributed back).
    extra = []
    for alias_estate, target_town in ESTATE_TOWN_ALIAS.items():
        if target_town not in scores["estate"].values:
            alias_row = scores[scores["estate"] == alias_estate]
            if not alias_row.empty:
                shadow = alias_row.iloc[0].copy()
                shadow["estate"] = target_town
                extra.append(shadow)
    if extra:
        scores = pd.concat([scores, pd.DataFrame(extra)], ignore_index=True)

    # For private segments, prefer score_private (W_PRIVATE weights) if present
    if seg_name in ("private_resale", "private_rental") and "score_private" in scores.columns:
        scores = scores.assign(score=scores["score_private"])

    # attach the estate score (provision or liveability) by area key
    df = df.merge(scores.rename(columns={"estate": s["area_key"], "score": "_score"}),
                  on=s["area_key"], how="left")
    df = df.dropna(subset=["_score"])
    if df.empty:
        return None

    # build controls-only formula: lnpsm ~ controls + C(month)
    # NOTE: provision _score is deliberately NOT a regressor — it is the Value
    # multiplier base (value_scores). Putting it here partials out the provision
    # premium then multiplies it back, double-counting provision.
    model_formula = build_formula(df, s["controls"], s["month_col"])
    model = smf.ols(model_formula, data=df).fit()
    df["_resid"] = model.resid

    # ----- per-subzone/town residual with hierarchical shrinkage -----
    key = s["area_key"]
    seg_mean = df["_resid"].mean()
    out = []
    for area, g in df.groupby(key):
        n = len(g)
        raw = g["_resid"].median()
        w = n / (n + CFG["shrink_strength"])          # trust grows with n
        shrunk = w * raw + (1 - w) * seg_mean          # pull thin samples to mean
        out.append({"estate": area, "segment": seg_name, "n": n,
                    "resid_raw": raw, "resid_shrunk": shrunk,
                    "trust": "decimal" if n >= CFG["trust_decimal_n"] else "band_only"})
    return pd.DataFrame(out)

def value_scores(resid_df, scores, original_estate_names):
    # shadow towns (alias targets that aren't real estate names) must be dropped from output
    shadow_towns = {target for alias, target in ESTATE_TOWN_ALIAS.items()
                    if target not in original_estate_names}

    df = resid_df.merge(scores, on="estate", how="left")
    # drop shadow town rows — they exist only to anchor the regression
    df = df[~df["estate"].isin(shadow_towns)]

    # ValueScore = score * exp(-residual), capped multiplier
    mult = np.exp(-df["resid_shrunk"]).clip(CFG["adj_cap_low"], CFG["adj_cap_high"])
    df["value_score"] = (df["score"] * mult)
    df["value_band"]  = df["value_score"].apply(band)
    df["mult"] = mult
    df["value_basis"] = "direct"
    # honesty: blank the decimal where sample is thin
    df["reported"] = np.where(df["trust"]=="decimal",
                              df["value_score"].round(2).astype(str),
                              df["value_band"] + " (band only, n<%d)" % CFG["trust_decimal_n"])
    # inject synthetic rows for aliased estates (e.g. CANBERRA → SEMBAWANG)
    # uses alias target's price residual but the aliased estate's own provision score
    alias_rows = []
    for alias_estate, target_town in ESTATE_TOWN_ALIAS.items():
        alias_score_row = scores[scores["estate"] == alias_estate]
        target_resid_row = resid_df[resid_df["estate"] == target_town]
        if alias_score_row.empty or target_resid_row.empty:
            continue
        alias_score = float(alias_score_row["score"].iloc[0])

        if alias_estate in PRIVATE_DOMINANT_PROXIES:
            # invariant 2: never attribute an HDB residual to a private-dominant estate
            alias_rows.append(pd.Series({
                "estate": alias_estate, "segment": target_resid_row.iloc[0]["segment"],
                "n": 0, "resid_raw": np.nan, "resid_shrunk": np.nan,
                "trust": "band_only", "score": alias_score,
                "value_score": np.nan, "mult": np.nan, "value_band": "N/A",
                "value_basis": "no_hdb_segment",
                "reported": "no private-segment match",
            }))
            continue

        row = target_resid_row.iloc[0].copy()
        row["estate"] = alias_estate
        row["score"] = alias_score
        m = float(np.clip(np.exp(-row["resid_shrunk"]),
                          CFG["adj_cap_low"], CFG["adj_cap_high"]))
        row["mult"] = m
        row["value_score"] = alias_score * m
        row["value_band"] = band(row["value_score"])
        row["value_basis"] = f"proxy_from:{target_town}"   # non-independent: shares parent n
        row["reported"] = (str(round(row["value_score"], 2))
                           if row["trust"] == "decimal"
                           else row["value_band"] + " (band only, n<%d)" % CFG["trust_decimal_n"])
        alias_rows.append(row)
    if alias_rows:
        df = pd.concat([df, pd.DataFrame(alias_rows)], ignore_index=True)
    return df.sort_values("value_score", ascending=False, na_position="last")

# ----------------------------------------------------------------------
# 4. CLI
# ----------------------------------------------------------------------
def load_scores(path):
    sc = pd.read_csv(path)
    assert {"estate","score"} <= set(sc.columns), "scores csv needs columns: estate,score"
    return sc

def load_liveability_scores(path: str, persona: str) -> pd.DataFrame:
    """Extract per-estate T0 score for a given persona from liveability_matrix.csv."""
    PREFIX = {"yf": "yf", "sp": "sp", "ret": "ret", "ls": "ls",
              "youngfam": "yf", "singlepro": "sp", "retiree": "ret", "lifestyle": "ls"}
    pre = PREFIX.get(persona.lower())
    if pre is None:
        sys.exit(f"Unknown persona '{persona}'. Use: yf, sp, ret, ls")
    lv = pd.read_csv(path)
    score_col = f"{pre}_T0"
    if score_col not in lv.columns:
        sys.exit(f"Column '{score_col}' not found in {path}.")
    return lv[["estate", score_col]].rename(columns={score_col: "score"})

def main():
    ap = argparse.ArgumentParser(description="Singapore Estate Value Residual Model")
    ap.add_argument("--scores", help="CSV: estate,score  (provision scores)")
    ap.add_argument("--liveability", help="liveability_matrix.csv — uses persona T0 score as base (overrides --scores)")
    ap.add_argument("--persona", default="ls", help="Persona for liveability base: yf, sp, ret, ls (default: ls)")
    ap.add_argument("--hdb", help="HDB resale CSV (data.gov.sg schema)")
    ap.add_argument("--private", help="URA private resale CSV")
    ap.add_argument("--rental", help="URA private rental CSV")
    ap.add_argument("--out", default="value_output.csv")
    a = ap.parse_args()

    if not a.scores and not a.liveability:
        sys.exit("Provide --scores or --liveability.")
    if a.liveability:
        scores = load_liveability_scores(a.liveability, a.persona)
        print(f"Using liveability base scores (persona={a.persona}, T0)")
    else:
        scores = load_scores(a.scores)
    original_estate_names = set(scores["estate"])
    frames = []
    jobs = [("hdb_resale", a.hdb), ("private_resale", a.private), ("private_rental", a.rental)]
    for seg, path in jobs:
        if not path: continue
        df = pd.read_csv(path)
        r = fit_segment(df, seg, scores)
        if r is not None:
            frames.append(value_scores(r, scores, original_estate_names).assign(segment=seg))

    if not frames:
        sys.exit("No segment produced output. Check inputs against the INPUT CONTRACT.")

    result = pd.concat(frames, ignore_index=True)
    result.to_csv(a.out, index=False)
    # console summary
    show = ["estate","segment","n","reported","value_band","mult","trust"]
    print(result[show].to_string(index=False))
    print(f"\nWritten: {a.out}")
    print("Reminder: HDB and private rows are SEPARATE segments — never rank across them.")

if __name__ == "__main__":
    main()

# ======================================================================
# INPUT CONTRACT  — how to pass data in the future
# ======================================================================
# You pass THREE kinds of CSV. Supply whichever segments you have.
#
# (1) --scores  scores.csv   [ALWAYS required]
#       columns: estate,score
#       'estate' must match the geographic key in the transaction files
#       (HDB 'town' OR URA 'planning_area'). 'score' is the Provision band's
#       decimal (or Liveability cell) from Documents 1/2.
#       e.g.   estate,score
#              BISHAN,4.47
#              TAMPINES,4.00
#              TENGAH,2.96
#
# (2) --hdb  hdb_resale.csv   [HDB segment]   source: data.gov.sg "Resale Flat Prices"
#       required columns: town, resale_price, floor_area_sqm, flat_type,
#                         storey_band, remaining_lease_years, month
#       (data.gov.sg ships 'storey_range' and 'remaining_lease' as text —
#        pre-map storey_range->storey_band and parse remaining_lease to years,
#        or tell me to add a cleaner step.)
#
# (3) --private  ura_private.csv   [private resale]   source: URA REALIS / caveats
#       required: planning_area, transacted_price, area_sqm, property_type,
#                 tenure, project_age_years, sale_month
#
# (4) --rental  ura_rental.csv   [private rental]   source: URA rental contracts
#       required: planning_area, monthly_rent, area_sqm, property_type,
#                 project_age_years, lease_month
#
# EXAMPLE RUN:
#   python value_model.py --scores scores.csv --hdb hdb_resale.csv
#   python value_model.py --scores scores.csv --hdb hdb.csv --private ura.csv
#
# WHAT YOU GET:
#   value_output.csv with per-estate, per-segment: n, residual (raw+shrunk),
#   Value score, Value band, and a 'reported' field that HIDES the decimal
#   when n < 100 (shows band only) — enforcing the framework's no-false-precision rule.
# ======================================================================
