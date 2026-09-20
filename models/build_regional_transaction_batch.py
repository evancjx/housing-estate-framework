#!/usr/bin/env python3
"""Rebuild the local regional research batch from frozen URA exports.

No writes to canonical model inputs. No signature deduplication: identical
masked URA rows can represent different homes. Geography metadata uses a
separate, audited project crosswalk; every price comes from fresh URA CSVs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "data/runs/regional-property-analysis/2026-09-20"
URL = "https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch"
LATEST_START, LATEST_END = "2025-09", "2026-08"
PRIOR_START, PRIOR_END = "2024-09", "2025-08"
EXPECTED = [f"pmi_d{d}_2021-2026.csv" for d in ("10", "11", "14", "15", "16", "18", "21", "22", "23", "27")]
EXPECTED += [f"pmi_d{d}_executive_condo_2021-2026.csv" for d in ("18", "22", "27")]
RAW_COLUMNS = ["Project Name", "Transacted Price ($)", "Area (SQFT)", "Unit Price ($ PSF)", "Sale Date", "Street Name", "Type of Sale", "Type of Area", "Area (SQM)", "Unit Price ($ PSM)", "Nett Price($)", "Property Type", "Number of Units", "Tenure", "Postal District", "Market Segment", "Floor Level"]
COHORT_KEYS = ["project_name", "region", "subregion", "ec_origin", "tenure_group", "tenure", "sale_type", "size_band"]
SIZE_LABELS = ["≤50 sqm (≤538 sqft)", ">50–70 sqm (538–753 sqft)", ">70–100 sqm (753–1,076 sqft)", ">100–130 sqm (1,076–1,399 sqft)", ">130 sqm (>1,399 sqft)"]


def norm(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def numeric(series):
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")


def tenure_group(value):
    if "freehold" in value.lower():
        return "Freehold"
    m = re.search(r"(\d+)\s*(?:yrs|years)", value.lower())
    if not m:
        return "Other / unspecified"
    years = int(m.group(1))
    if years >= 900:
        return "999-year / long lease"
    if years == 99:
        return "99-year lease"
    return "Other lease"


def frame_records(frame):
    return json.loads(frame.to_json(orient="records", force_ascii=False))


def save_csv(frame, name):
    frame.to_csv(ROOT / name, index=False, encoding="utf-8", float_format="%.4f")


def load_scope(context):
    scope = pd.read_csv(ROOT / "scope_crosswalk.csv", keep_default_na=False, dtype=str)
    scope["key"] = scope.project_name.map(norm)
    assert scope.key.is_unique, "Project normalization collision in scope"
    overrides = ROOT / "scope_overrides.csv"
    if overrides.exists():
        extra = pd.read_csv(overrides, keep_default_na=False, dtype=str)
        extra["key"] = extra.project_name.map(norm)
        scope = pd.concat([scope.loc[~scope.key.isin(extra.key)], extra], ignore_index=True)
    # Primary-source named new launches without prior transactions remain visible.
    for item in context.get("projects", []) + context.get("upcoming_project_watchlist", []):
        key = norm(item["project_name"])
        if key in set(scope.key):
            continue
        region = item["region"].replace("Lakeside/Jurong", "Lakeside / Jurong")
        scope = pd.concat([scope, pd.DataFrame([{
            "key": key, "project_name": item["project_name"], "region": region,
            "subregion": "Sourced new project", "scope_status": "main",
            "ec_origin": str(item["ec_origin"]), "source_planning_area": "",
            "scope_basis": "Official developer/HDB project context",
            "source_reference": item.get("status_source", ""),
        }])], ignore_index=True)
    scope["ec_origin"] = scope.ec_origin.str.lower().eq("true")
    scope = scope.fillna("")
    assert scope.key.is_unique
    save_csv(scope, "project_scope.csv")
    return scope


def load_raw():
    parts, manifest = [], []
    for name in EXPECTED:
        path = ROOT / "raw" / "ura" / name
        encoding = "utf-8-sig"
        try:
            raw = pd.read_csv(path, encoding=encoding, dtype=str, keep_default_na=False)
        except UnicodeDecodeError:
            encoding = "cp1252"
            raw = pd.read_csv(path, encoding=encoding, dtype=str, keep_default_na=False)
        assert list(raw.columns) == RAW_COLUMNS, (name, raw.columns.tolist())
        assert len(raw) > 0
        dates = pd.to_datetime(raw["Sale Date"], format="%b-%y", errors="raise")
        assert dates.min() >= pd.Timestamp("2021-10-01")
        assert dates.max() <= pd.Timestamp("2026-09-01")
        expected_district = int(re.search(r"pmi_d(\d+)", name).group(1))
        assert set(numeric(raw["Postal District"])) == {expected_district}
        expected_types = {"Executive Condominium"} if "executive" in name else {"Apartment", "Condominium"}
        assert set(raw["Property Type"]) <= expected_types
        manifest.append({
            "file": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "encoding": encoding, "rows": len(raw), "distinct_public_signatures": len(raw.drop_duplicates()),
            "repeated_signature_occurrences_retained": int(raw.duplicated().sum()),
            "district": expected_district, "property_group": "EC" if "executive" in name else "Apartments/condominiums",
            "first_sale_month": dates.min().strftime("%Y-%m"), "last_sale_month": dates.max().strftime("%Y-%m"),
            "captured_date": "2026-09-20", "source_url": URL,
            "capture_note": "Reused same-day full district export from local LakeGarden batch" if expected_district == 22 and "executive" not in name else "Fresh public URA PMI browser CSV export",
        })
        raw["source_file"] = name
        raw["source_row"] = range(2, len(raw) + 2)  # CSV header is physical line 1.
        raw["sale_month"] = dates.dt.strftime("%Y-%m")
        raw["key"] = raw["Project Name"].map(norm)
        parts.append(raw)
    return pd.concat(parts, ignore_index=True), manifest


def cohort_table(period, previous=None):
    grouped = period.groupby(COHORT_KEYS, dropna=False, observed=True)
    out = grouped.agg(
        n=("price", "size"), median_price=("price", "median"),
        q1_price=("price", lambda x: x.quantile(.25)), q3_price=("price", lambda x: x.quantile(.75)),
        median_psf=("psf", "median"), q1_psf=("psf", lambda x: x.quantile(.25)), q3_psf=("psf", lambda x: x.quantile(.75)),
        min_sqft=("sqft", "min"), max_sqft=("sqft", "max"),
        latest_month=("sale_month", "max"), active_months=("sale_month", "nunique"),
    ).reset_index()
    if previous is not None:
        old = previous.groupby(COHORT_KEYS, dropna=False, observed=True).agg(prior_n=("price", "size"), prior_median_psf=("psf", "median")).reset_index()
        out = out.merge(old, on=COHORT_KEYS, how="left", validate="one_to_one")
    else:
        out["prior_n"], out["prior_median_psf"] = 0, float("nan")
    out["prior_n"] = out.prior_n.fillna(0).astype(int)
    out["median_psf_change_pct"] = ((out.median_psf / out.prior_median_psf - 1) * 100).where(out.n.ge(10) & out.prior_n.ge(10))
    out["evidence"] = out.n.map(lambda n: "Very thin (<5)" if n < 5 else "Small (5–19)" if n < 20 else "Descriptive (20–99)" if n < 100 else "100+ records; composition still matters")
    return out.sort_values(COHORT_KEYS).reset_index(drop=True)


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=ROOT)
    ROOT = parser.parse_args().batch.resolve()
    context_path = ROOT / "sourced_context.json"
    context = json.loads(context_path.read_text()) if context_path.exists() else {}
    scope = load_scope(context)
    raw, manifest = load_raw()
    mapped = raw.merge(scope[["key", "project_name", "region", "subregion", "scope_status", "ec_origin", "scope_basis"]], on="key", how="left", validate="many_to_one")
    mapped["scope_status"] = mapped.scope_status.fillna("unresolved")
    mapped["region"] = mapped.region.fillna("")
    save_csv(mapped.groupby(["Project Name", "Street Name", "Postal District", "scope_status", "region"], dropna=False).size().reset_index(name="raw_rows"), "scope_audit.csv")
    save_csv(mapped.loc[mapped.scope_status.eq("unresolved")], "unresolved_scope_rows.csv")
    kept = mapped.loc[mapped.scope_status.isin(["main", "context"])].copy()
    d = pd.DataFrame({
        "record_id": kept.source_file + ":" + kept.source_row.astype(str),
        "project_name": kept.project_name, "ura_project_name": kept["Project Name"],
        "region": kept.region, "subregion": kept.subregion, "scope_status": kept.scope_status,
        "ec_origin": kept.ec_origin.astype(bool), "property_type": kept["Property Type"],
        "sale_type": kept["Type of Sale"], "sale_month": kept.sale_month,
        "price": numeric(kept["Transacted Price ($)"]), "sqft": numeric(kept["Area (SQFT)"]),
        "sqm": numeric(kept["Area (SQM)"]), "psf": numeric(kept["Unit Price ($ PSF)"]),
        "tenure": kept.Tenure, "tenure_group": kept.Tenure.map(tenure_group),
        "floor_level": kept["Floor Level"], "street_name": kept["Street Name"],
        "postal_district": numeric(kept["Postal District"]), "market_segment": kept["Market Segment"],
        "number_of_units": numeric(kept["Number of Units"]), "type_of_area": kept["Type of Area"],
        "source_file": kept.source_file, "source_row": kept.source_row,
    })
    assert not d[["price", "sqm", "sqft", "psf", "number_of_units"]].isna().any().any()
    assert d.record_id.is_unique
    d["exclusion_reason"] = ""
    d.loc[d.number_of_units.ne(1), "exclusion_reason"] = "Multiple-unit transaction; price is not a single-home quantum"
    d.loc[d.type_of_area.ne("Strata"), "exclusion_reason"] += "; Land-area record; not comparable strata floor area"
    d.loc[d.price.le(0) | d.sqm.le(0) | d.psf.le(0), "exclusion_reason"] += "; Non-positive price/area"
    d["exclusion_reason"] = d.exclusion_reason.str.strip("; ")
    d["metric_eligible"] = d.exclusion_reason.eq("")
    d["size_band"] = pd.cut(d.sqm, [0, 50, 70, 100, 130, float("inf")], labels=SIZE_LABELS).astype(str)
    d["period"] = "Earlier history"
    d.loc[d.sale_month.between(PRIOR_START, PRIOR_END), "period"] = "Prior 12m"
    d.loc[d.sale_month.between(LATEST_START, LATEST_END), "period"] = "Latest 12m"
    d.loc[d.sale_month.gt(LATEST_END), "period"] = "Partial month"
    d = d.sort_values(["project_name", "sale_month", "source_file", "source_row"], kind="stable").reset_index(drop=True)
    save_csv(d, "transactions.csv")
    save_csv(kept[RAW_COLUMNS + ["source_file", "source_row", "scope_status"]], "transactions_original_fields.csv")
    save_csv(d.loc[~d.metric_eligible], "metric_exclusions.csv")
    eligible = d.loc[d.metric_eligible]
    recent = eligible.loc[eligible.sale_month.between(LATEST_START, LATEST_END)]
    previous = eligible.loc[eligible.sale_month.between(PRIOR_START, PRIOR_END)]
    two_years = eligible.loc[eligible.sale_month.between(PRIOR_START, LATEST_END)]
    cohorts = cohort_table(recent, previous)
    save_csv(cohorts, "cohorts.csv")
    save_csv(cohort_table(two_years), "cohorts_24m.csv")
    # Exact recorded area cohorts for analysts; never map area to an invented bedroom count.
    exact = recent.groupby(["project_name", "ec_origin", "tenure", "sale_type", "sqm"], observed=True).agg(n=("price", "size"), median_price=("price", "median"), median_psf=("psf", "median"), min_price=("price", "min"), max_price=("price", "max")).reset_index()
    save_csv(exact, "exact_area_cohorts.csv")
    context_map = {norm(x["project_name"]): x for x in context.get("projects", []) + context.get("upcoming_project_watchlist", [])}
    project_rows = []
    for item in scope.loc[scope.scope_status.isin(["main", "context"])].to_dict("records"):
        name = item["project_name"]
        all_rows = d.loc[d.project_name.eq(name)]
        r = recent.loc[recent.project_name.eq(name)]
        resale24 = two_years.loc[two_years.project_name.eq(name) & two_years.sale_type.eq("Resale")]
        resale = r.loc[r.sale_type.eq("Resale")]
        ctx = context_map.get(norm(name), {})
        note = ctx.get("note", "")
        if not len(all_rows):
            note = (note + " No rows in the fetched 60-month URA exports; not evidence of no development or no stock.").strip()
        if name in {"LAKESIDE APARTMENTS", "PARK VIEW MANSION", "BAGNALL COURT", "WATTEN ESTATE CONDOMINIUM"}:
            note += " Historical redevelopment predecessor; not a current-stock recommendation."
        project_rows.append({
            "project_name": name, "region": item["region"], "subregion": item["subregion"],
            "ec_origin": item["ec_origin"], "scope_status": item["scope_status"],
            "tenures": " | ".join(sorted(all_rows.tenure.unique())),
            "latest_month": all_rows.sale_month.max() if len(all_rows) else "",
            "total_n": len(all_rows), "recent_n": len(r),
            "new_n": int(r.sale_type.eq("New Sale").sum()), "sub_n": int(r.sale_type.eq("Sub Sale").sum()),
            "resale_n": len(resale), "resale_24m_n": len(resale24),
            "active_resale_months": resale.sale_month.nunique(),
            "latest_resale_month": resale24.sale_month.max() if len(resale24) else "",
            "development_status": ctx.get("development_status") or "Completion status not independently verified",
            "status_source": ctx.get("status_source", ""), "status_as_of": ctx.get("status_as_of", ""),
            "actual_top": ctx.get("actual_top") or "", "coverage_note": note.strip(),
            "scope_source": item.get("source_reference", ""),
        })
    projects = pd.DataFrame(project_rows).sort_values(["region", "project_name"])
    save_csv(projects, "projects.csv")
    # Regional tables remain segmented. These describe the observed mix, not location premiums.
    region_stats = recent.loc[recent.scope_status.eq("main")].groupby(["region", "ec_origin", "tenure_group", "sale_type", "size_band"], observed=True).agg(n=("price", "size"), projects=("project_name", "nunique"), median_price=("price", "median"), q1_price=("price", lambda x: x.quantile(.25)), q3_price=("price", lambda x: x.quantile(.75)), median_psf=("psf", "median")).reset_index()
    save_csv(region_stats, "regional_segments.csv")
    budget = recent.copy()
    budget["budget_band"] = pd.cut(budget.price, [0, 1e6, 1.5e6, 2e6, 2.5e6, 3e6, float("inf")], labels=["≤S$1m", "S$1–1.5m", "S$1.5–2m", "S$2–2.5m", "S$2.5–3m", ">S$3m"])
    b = budget.groupby(["region", "ec_origin", "tenure_group", "sale_type", "size_band", "budget_band"], observed=True).agg(n=("price", "size"), projects=("project_name", "nunique"), median_sqft=("sqft", "median")).reset_index()
    save_csv(b, "budget_size_matrix.csv")
    main_d = d.loc[d.scope_status.eq("main")]
    main_p = projects.loc[projects.scope_status.eq("main")]
    summary = {
        "raw_rows": len(raw), "transactions": len(main_d), "metric_transactions": int(main_d.metric_eligible.sum()),
        "projects": len(main_p), "projects_with_transactions": int(main_p.total_n.gt(0).sum()),
        "projects_recent": int(main_p.recent_n.gt(0).sum()), "ec_projects": int(main_p.ec_origin.sum()),
        "recent_transactions": int(recent.scope_status.eq("main").sum()),
        "partial_september_transactions": int((main_d.sale_month == "2026-09").sum()),
        "context_projects": int(projects.scope_status.eq("context").sum()),
        "context_transactions": int(d.scope_status.eq("context").sum()),
        "unresolved_scope_rows": int(mapped.scope_status.eq("unresolved").sum()),
        "out_of_scope_rows": int(mapped.scope_status.eq("excluded").sum()),
        "metric_exclusions_main": int((~main_d.metric_eligible).sum()),
    }
    limitations = [
        "Inventory covers identified historical and sourced new projects, not a certified census of every physical development. Zero-transaction and unrecognised generic names are documented; no prices are invented.",
        "All achieved prices use URA exports. EdgeProp supplies geography and EC-origin metadata only. Postal district is not a planning-area boundary.",
        "New Sale, Sub Sale and Resale, EC origin, tenure and size cohorts stay separate. New Sale is not proof of construction or completion status.",
        "Price metrics include single-unit strata transactions only. Bulk and land-area rows stay in the ledger with exclusion flags.",
        "September 2026 is partial. The headline 12 months are September 2025–August 2026; the prior period is September 2024–August 2025.",
        "An unchanged public signature can be a different transaction; every source row occurrence is retained. Sources are not concatenated across overlapping snapshots.",
        "Unit sizes are registered areas, not bedroom counts or usable internal floor areas. Different generations can use different area measurement conventions.",
        "Median PSF change requires at least 10 observations in both identical project/tenure/sale-type/size-band cohorts. It remains sensitive to floor, facing and size mix; it is not a repeat-sale return or forecast.",
        "Counts measure recorded transactions, not availability, selling time or turnover rate. URA resale/subsale caveats are voluntary and the source can be revised.",
        "No rental yields, net returns, taxes, loan affordability or unified liveability/value ranking are inferred from sale prices. TOP, defects, unit facing and asking prices are not comprehensively verified.",
        "EC origin does not establish present buyer eligibility. Completed ECs may remain within MOP. Apply the correct HDB land-tender cohort and check the particular unit.",
        "The wider Sembawang context is separate from the five requested regions. Bukit Timah includes 12 explicitly listed Upper Bukit Timah extensions; Lakeside/Jurong includes Jurong East and Jurong West.",
    ]
    metadata = {
        "captured_at": "2026-09-20 SGT", "source_url": URL, "source_updated": "2026-09-18",
        "history_start": "2021-10", "history_end": "2026-09",
        "latest_start": LATEST_START, "latest_end": LATEST_END, "prior_start": PRIOR_START, "prior_end": PRIOR_END,
        "scope_note": "Tampines and Bedok recorded planning areas; Canberra precinct; Jurong East/West; Bukit Timah plus explicitly listed Upper Bukit Timah extensions. Wider Sembawang context is optional.",
        "limitations": limitations,
    }
    payload = {"metadata": metadata, "summary": summary, "projects": frame_records(projects), "cohorts": frame_records(cohorts), "transactions": frame_records(d), "regional_segments": frame_records(region_stats), "context": context}
    (ROOT / "report_data.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    provenance = {"metadata": metadata, "sources": manifest, "summary": summary, "validation": {
        "expected_exports": len(EXPECTED), "validated_exports": len(manifest),
        "raw_row_reconciliation": len(raw) == summary["transactions"] + summary["context_transactions"] + summary["unresolved_scope_rows"] + summary["out_of_scope_rows"],
        "all_source_record_ids_unique": bool(d.record_id.is_unique),
        "recent_cohort_count_reconciliation": int(cohorts.n.sum()) == len(recent),
        "project_ledger_count_reconciliation": int(projects.total_n.sum()) == len(d),
        "raw_repeated_occurrences_retained": sum(x["repeated_signature_occurrences_retained"] for x in manifest),
    }}
    assert all(v for k, v in provenance["validation"].items() if k.endswith("reconciliation") or k == "all_source_record_ids_unique")
    for filename in ("scope_crosswalk.csv", "scope_overrides.csv", "sourced_context.json"):
        path = ROOT / filename
        if path.exists():
            provenance.setdefault("metadata_inputs", []).append({"file": filename, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (ROOT / "provenance.json").write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2))
    print("All source and cohort reconciliation checks passed.")


if __name__ == "__main__":
    main()
