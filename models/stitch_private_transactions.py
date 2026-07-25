"""
Stitch URA PMI transactions with EdgeProp scrape rows into ONE clean
per-transaction table for private condominiums/apartments.

Both datasets describe the same underlying URA caveats, but each side carries
columns the other lacks:
  URA-only:      floor_level band, market_segment, tenure (canonical),
                 planning_area, project_age
  EdgeProp-only: exact Date of Sale, unit address (with floor), Bedrooms

Matching is per (project, district): rows are grouped by
(sale_month, price, area_sqft) — a group's URA and EdgeProp rows are paired
1:1, preferring pairs whose EdgeProp unit floor falls inside the URA floor
band. Rows without a partner are kept and flagged (`sources` column):
  both            matched pair (one output row, columns merged)
  ura_only        URA row with no EdgeProp partner
  edgeprop_only   EdgeProp row with no URA partner (e.g. months newer than
                  the committed URA extract, or option-vs-exercise date drift)

Cleaning applied: landed + Executive Condominium excluded, per-source dedup,
numeric coercion, uppercase project names, deterministic sort.

Run (pilot, one project):
  python3 models/stitch_private_transactions.py \
      --project "CANBERRA CRESCENT RESIDENCES" --out data/outputs/stitched_ccr.csv
Run (all URA condo/apartment projects):
  python3 models/stitch_private_transactions.py --all \
      --out data/outputs/private_transactions_stitched.csv

INPUT CONTRACT
  --private   data/inputs/ura_private.csv (see build_private_bedrooms)
  --edgeprop  data/raw/edgeprop/edgeprop_condo_apartment_transactions_playwright_not_clean.csv
  Output columns: project_name, postal_district, planning_area, property_type,
    tenure, sale_date (YYYY-MM-DD, blank for ura_only), sale_month, type_of_sale,
    price, area_sqft, area_sqm, unit_price_psf, floor_level, unit_floor,
    address, bedrooms, sources, match_method
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from aliases import URA_EDGEPROP_PROJECT_ALIAS  # noqa: E402
from build_private_bedrooms import (  # noqa: E402
    DEFAULT_EDGEPROP,
    DEFAULT_PRIVATE,
    SQM_TO_SQFT,
    load_edgeprop,
    load_ura,
    build_name_mapping,
)

ROOT = pathlib.Path(__file__).parent.parent
FLOOR_RE = re.compile(r"#(\d{2,3})-")


def unit_floor(address) -> int | None:
    m = FLOOR_RE.search(str(address))
    return int(m.group(1)) if m else None


def floor_in_band(floor: int | None, band) -> bool | None:
    """URA floor_level bands look like '01 to 05' (also accepts '01-05')."""
    if floor is None or pd.isna(floor):
        return None
    m = re.match(r"^(\d{2})\s*(?:to|-)\s*(\d{2})$", str(band).strip(), re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1)) <= int(floor) <= int(m.group(2))


def stitch_project(ura: pd.DataFrame, ep: pd.DataFrame) -> list[dict]:
    """Pair one project's URA and EdgeProp rows 1:1 within
    (sale_month, price, area_sqft) groups, floor-consistent pairs first."""
    ura = ura.copy()
    ep = ep.copy()
    ura["area_sqft_key"] = (ura["area_sqm"] * SQM_TO_SQFT).round(0)
    ep["area_sqft_key"] = pd.to_numeric(ep["Area (sqft)"], errors="coerce").round(0)
    ep["unit_floor"] = ep["Address"].map(unit_floor)

    out: list[dict] = []
    key_cols = ["sale_month", "price_key", "area_sqft_key"]
    ura["price_key"] = ura["price_int"].astype("Int64")
    ep["price_key"] = ep["price_int"].astype("Int64")

    ep_used = set()
    ep_groups = {k: list(g.index) for k, g in ep.groupby(key_cols, dropna=False)}

    def emit(u_row=None, e_row=None, method=""):
        src = "both" if (u_row is not None and e_row is not None) else \
              "ura_only" if u_row is not None else "edgeprop_only"
        sqft = float(u_row["area_sqft_key"]) if u_row is not None else float(e_row["area_sqft_key"])
        sqm = float(u_row["area_sqm"]) if u_row is not None else float(e_row["ep_sqm"])
        price = int(u_row["price_int"]) if u_row is not None else int(e_row["price_int"])
        out.append({
            "project_name": (u_row["project_name"] if u_row is not None else e_row["project_upper"]),
            "postal_district": (u_row["district"] if u_row is not None else e_row["district"]),
            "planning_area": (u_row.get("planning_area", "") if u_row is not None
                              else e_row.get("planning_area", "")),
            "property_type": (u_row["property_type"] if u_row is not None else e_row["Type"]),
            "tenure": (u_row["tenure"] if u_row is not None else e_row["Tenure"]),
            "sale_date": (e_row["sale_dt"].strftime("%Y-%m-%d") if e_row is not None else ""),
            "sale_month": (u_row["sale_month"] if u_row is not None else e_row["sale_month"]),
            "type_of_sale": (u_row["type_of_sale"] if u_row is not None else e_row["Sale Type"]),
            "price": price,
            "area_sqft": sqft,
            "area_sqm": round(sqm, 1),
            "unit_price_psf": round(price / sqft) if sqft else None,
            "floor_level": (u_row.get("floor_level", "") if u_row is not None else ""),
            "unit_floor": (e_row["unit_floor"] if e_row is not None else None),
            "address": (e_row["Address"] if e_row is not None else ""),
            "bedrooms": (int(e_row["bedrooms"]) if e_row is not None and pd.notna(e_row["bedrooms"])
                         else None),
            "sources": src,
            "match_method": method,
        })

    for _, u in ura.iterrows():
        key = (u["sale_month"], u["price_key"], u["area_sqft_key"])
        candidates = [i for i in ep_groups.get(key, []) if i not in ep_used]
        chosen, method = None, ""
        # prefer a candidate whose unit floor sits inside the URA floor band
        for i in candidates:
            if floor_in_band(ep.loc[i, "unit_floor"], u.get("floor_level")) is True:
                chosen, method = i, "group+floor"
                break
        if chosen is None and candidates:
            chosen, method = candidates[0], "group"
        if chosen is not None:
            ep_used.add(chosen)
            emit(u, ep.loc[chosen], method)
        else:
            emit(u, None, "ura_only")

    for i in ep.index:
        if i not in ep_used:
            emit(None, ep.loc[i], "edgeprop_only")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Stitch URA + EdgeProp private transactions")
    ap.add_argument("--private", default=str(DEFAULT_PRIVATE))
    ap.add_argument("--edgeprop", default=str(DEFAULT_EDGEPROP))
    ap.add_argument("--project", action="append",
                    help="URA project name (repeatable); omit with --all for every project")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    if not args.all and not args.project:
        ap.error("pass --project NAME (repeatable) or --all")

    ura = load_ura(pathlib.Path(args.private))
    ep = load_edgeprop(pathlib.Path(args.edgeprop))
    mapping = build_name_mapping(ura, ep)
    ura["match_name"] = [mapping.get(k, k[0]) for k in zip(ura["name_norm"], ura["district"])]

    if args.project:
        wanted = {p.strip().upper() for p in args.project}
        ura = ura[ura["project_name"].isin(wanted)]
        if ura.empty:
            sys.exit(f"ERROR: no URA rows for {sorted(wanted)}")

    rows: list[dict] = []
    for (match_name, district), u_grp in ura.groupby(["match_name", "district"]):
        e_grp = ep[(ep["name_norm"] == match_name) & (ep["district"] == district)]
        rows.extend(stitch_project(u_grp, e_grp))

    out = pd.DataFrame(rows)
    out["bedrooms"] = out["bedrooms"].astype("Int64")
    out["unit_floor"] = out["unit_floor"].astype("Int64")
    out = out.sort_values(["project_name", "sale_month", "sale_date", "price", "area_sqft"],
                          kind="stable").reset_index(drop=True)
    out.to_csv(args.out, index=False)

    total = len(out)
    print(f"Written: {args.out} ({total:,} rows, {out['project_name'].nunique()} projects)")
    print(out["sources"].value_counts().to_string())
    both = out[out["sources"] == "both"]
    if len(both):
        print(f"bedrooms filled on matched rows: {both['bedrooms'].notna().mean()*100:.1f}%")
        fb = [floor_in_band(f, b) for f, b in zip(both["unit_floor"], both["floor_level"])]
        checked = [x for x in fb if x is not None]
        if checked:
            print(f"floor-band consistency on checkable pairs: "
                  f"{sum(checked)/len(checked)*100:.1f}% ({len(checked)} checkable)")


if __name__ == "__main__":
    main()
