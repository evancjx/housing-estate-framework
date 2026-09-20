#!/usr/bin/env python3
"""Add property-research evidence to the frozen regional transaction batch.

This produces analytical appendices, not a universal investment ranking or
hundreds of supposedly completed unit-underwriting reports. No source rows are
deduplicated. Official developer totals are never inferred from caveat counts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from models.regional_research_economics import enrich_cohorts

KEYS = ["project_name", "region", "subregion", "ec_origin", "tenure_group", "tenure", "sale_type", "size_band"]
LATER_START, LATER_END = "2025-09", "2026-08"


def norm(value):
    ascii_text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub("[^A-Z0-9]", "", ascii_text.upper())


def distance_m(a_lat, a_lon, b_lat, b_lon):
    lat1, lat2 = math.radians(a_lat), math.radians(b_lat)
    dlat, dlon = lat2 - lat1, math.radians(b_lon - a_lon)
    return 12742000 * math.asin(min(1, math.sqrt(math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)))


def lease_year(tenure):
    match = re.search(r"commencing from (\d{4})", str(tenure))
    return int(match.group(1)) if match else None


def project_locations():
    raw = pd.read_csv(ROOT / "data/outputs/private_project_locations.csv")
    raw = raw.loc[raw.match_status.eq("matched")].copy()
    raw["key"] = raw.project_name.map(norm)
    locations = {}
    for key, rows in raw.groupby("key"):
        lat, lon = rows.lat.median(), rows.lon.median()
        spread = max(distance_m(lat, lon, x.lat, x.lon) for x in rows.itertuples())
        if spread <= 500:
            locations[key] = {"lat": lat, "lon": lon, "source": "matched OneMap project points; median point if multiple"}
    return locations


def build_peer_matches(cohorts, recent, locations):
    """Match area, region, EC origin, tenure group and observable lease vintage.

    Resale and Sub Sale remain separate. No floor, facing, actual building age,
    layout or condition adjustment is claimed. Missing coordinates cause an
    explicitly regional-only comparison; known distances over 2km are rejected.
    """
    output = []
    owner = recent.loc[recent.sale_type.isin(["Resale", "Sub Sale"])].copy()
    for row in cohorts.loc[cohorts.n.ge(5)].itertuples():
        tolerance = max(3.0, row.median_sqm * .05)
        subject = recent.loc[
            recent.project_name.eq(row.project_name) & recent.tenure.eq(row.tenure)
            & recent.sale_type.eq(row.sale_type) & recent.size_band.eq(row.size_band)
            & recent.sqm.between(row.median_sqm - tolerance, row.median_sqm + tolerance)
        ]
        if len(subject) < 5:
            continue
        subject_psf = subject.psf.median()
        candidates = owner.loc[
            owner.region.eq(row.region) & owner.ec_origin.eq(row.ec_origin)
            & owner.tenure_group.eq(row.tenure_group) & owner.project_name.ne(row.project_name)
            & owner.sqm.between(row.median_sqm - tolerance, row.median_sqm + tolerance)
        ]
        potential = []
        for (name, tenure, state), records in candidates.groupby(["project_name", "tenure", "sale_type"]):
            if len(records) < 5:
                continue
            a_year, b_year = lease_year(row.tenure), lease_year(tenure)
            if row.tenure_group == "99-year lease" and a_year and b_year and abs(a_year - b_year) > 10:
                continue
            a, b = locations.get(norm(row.project_name)), locations.get(norm(name))
            distance = distance_m(a["lat"], a["lon"], b["lat"], b["lon"]) if a and b else None
            if distance is not None and distance > 2000:
                continue
            peer_psf = records.psf.median()
            potential.append({
                "cohort_id": row.cohort_id, "project_name": row.project_name, "subject_sale_type": row.sale_type,
                "subject_tenure": row.tenure, "subject_size_band": row.size_band,
                "subject_cohort_n": row.n, "subject_cohort_median_sqm": row.median_sqm,
                "subject_n": len(subject), "subject_median_sqm": subject.sqm.median(),
                "subject_min_sqm": subject.sqm.min(), "subject_max_sqm": subject.sqm.max(),
                "subject_median_price": subject.price.median(), "subject_median_psf": subject_psf,
                "region": row.region, "ec_origin": row.ec_origin, "peer_project": name,
                "peer_sale_type": state, "peer_tenure": tenure, "peer_n": len(records),
                "peer_min_sqm": records.sqm.min(), "peer_max_sqm": records.sqm.max(),
                "peer_median_price": records.price.median(), "peer_median_psf": peer_psf,
                "peer_q1_psf": records.psf.quantile(.25), "peer_q3_psf": records.psf.quantile(.75),
                "peer_max_psf": records.psf.max(), "distance_m": distance,
                "location_basis": "Within 2km by matched project points" if distance is not None else "Regional size match; proximity unverified",
                "lease_basis": "Lease commencement within 10 years" if a_year and b_year and row.tenure_group == "99-year lease" else "Same tenure category; building age not matched",
                "unadjusted_psf_gap_pct": (subject_psf / peer_psf - 1) * 100,
            })
        potential.sort(key=lambda x: (x["distance_m"] is None, x["distance_m"] if x["distance_m"] is not None else 9999, -x["peer_n"], x["peer_project"], x["peer_sale_type"]))
        output.extend(potential[:3])
    return pd.DataFrame(output)


def official_developer_evidence(batch, projects):
    files = sorted((batch / "enrichment/developer_sales").glob("*.csv"))
    assert len(files) == 1, "Select one non-overlapping developer-sales snapshot"
    raw = pd.read_csv(files[0], keep_default_na=False)
    raw["key"] = raw.project_name.map(norm)
    p = projects.copy()
    p["key"] = p.project_name.map(norm)
    mapping = p.set_index("key").to_dict("index")
    records = raw.loc[raw.key.isin(mapping)].copy()
    records["ura_project_name"] = records.project_name
    records["project_name"] = records.key.map(lambda x: mapping[x]["project_name"])
    records["region"] = records.key.map(lambda x: mapping[x]["region"])
    records["ec_origin"] = records.key.map(lambda x: mapping[x]["ec_origin"])
    assert not records.duplicated(["project_name", "ref_month"]).any()
    for col in ["units_avail", "launched_to_date", "sold_to_date", "sold_in_month"]:
        records[col] = pd.to_numeric(records[col], errors="raise")
    assert (records.sold_to_date <= records.units_avail).all()
    assert (records.sold_to_date <= records.launched_to_date).all()
    assert (records.launched_to_date <= records.units_avail).all()
    records["unsold_total"] = records.units_avail - records.sold_to_date
    records["launched_unsold"] = records.launched_to_date - records.sold_to_date
    records["unlaunched_units"] = records.units_avail - records.launched_to_date
    records["sold_pct"] = records.sold_to_date / records.units_avail * 100
    latest = records.sort_values("ref_month").groupby("project_name", sort=False).tail(1).copy()
    pace = records.loc[records.ref_month.between("2026-06", "2026-08")].groupby("project_name").agg(developer_sales_jun_aug=("sold_in_month", "sum"), months_reported_jun_aug=("ref_month", "nunique"))
    latest = latest.merge(pace, on="project_name", how="left")
    return records, latest


def write_register(projects, destination, captured):
    lines = [
        "# Regional project evidence register — project-level conclusions and research coverage", "",
        f"Research captured: **{captured} SGT (UTC+08:00)**  ",
        "Property: **Regional project evidence register, Tampines / Bedok / Canberra / Jurong / Bukit Timah, Singapore**  ",
        "Analysis type: **project evidence, market-state, rental and developer-inventory assessment register**  ",
        "Status: **point-in-time market snapshot**  ", "Market stage: **mixed market**", "", "## Decision", "",
        "**Use this register to decide which evidence can support a purchase assessment, not to treat every observed project as a completed investment recommendation.** Every identified project remains visible. Developer inventory, owner transaction evidence, rental coverage and missing evidence are distinguished; the companion regional report makes the comparative decisions where the evidence supports them.", "",
        "A current rental statistic or a resale record does not supply an exact TOP date, an executable asking price, the condition of a unit or a rent for its particular layout. No universal project ranking is created.", "",
        "## Reading the register", "",
        "Recent counts refer to eligible single-unit strata transactions in September 2025–August 2026. The developer balance is the latest reported monthly snapshot, and its date is always shown. Rental coverage means a published project-level URA median for 2026Q2; absence does not mean zero rent. The peer count concerns only the project's most frequently observed sale-type/tenure/size cohort, not all its homes.", "",
        "Rows marked transaction-supported or rental-supported are analytical evidence assessments, not full unit underwriting. An existing dated dossier is linked where available, and its original date remains visible.", "",
        "The price tables select each project's most frequently observed recent sale-type / exact-tenure / size-band cohort. They do not describe every format in that project. The median and middle 50% of achieved prices are historical evidence, not live offers. All other cohorts remain in the downloadable evidence.", "",
        "Capital-only break-even assumes a Singapore-citizen first-property purchase, current BSD, S$5,000 legal allowance and selling expenses of 2.5% of the exit price. It excludes loan interest, renovation, maintenance, property tax, accommodation, rent and opportunity cost. The median price is a synthetic scenario entry, not an executable home. The exit must be after the applicable SSD period and, for ECs, the applicable MOP and eligibility restrictions. A price rise to this hurdle does not establish an adequate total return.", "",
        "[Regional purchase decisions](https://evancjx.github.io/housing-estate-framework/property-analysis-2026-09-20-regional-condo-and-ec-comparison.html), [all sale cohorts and scenarios](https://evancjx.github.io/housing-estate-framework/research-data.html?path=research/2026-09-20/enrichment/cohort_economics.csv), [matched owner comparisons](https://evancjx.github.io/housing-estate-framework/research-data.html?path=research/2026-09-20/enrichment/matched_peers.csv), and [searchable project assessments](https://evancjx.github.io/housing-estate-framework/research-data.html?path=research/2026-09-20/enrichment/project_assessments.csv). These companion links open the published reports and frozen evidence tables.", "",
    ]
    for region, rows in projects.groupby("region", sort=True):
        lines.extend([f"## {region}", "", "### Achieved prices and entry-cost hurdles", "", "Private and EC-origin rows, sale types and source tenures remain labelled separately. This is not a pooled ranking. Price ranges show the cohort's 25th–75th percentiles; small cells do not establish a reliable valuation band.", "", "| Project / category | Selected sale type / tenure / area | N | Median price / middle 50% | Median PSF | Capital-only break-even |", "| --- | --- | ---: | --- | ---: | ---: |"])
        for x in rows.loc[rows.anchor_n.notna()].itertuples():
            category = "EC-origin" if x.ec_origin else "Private"
            selected = f"{x.anchor_sale_type}; {x.anchor_tenure}; {x.anchor_size_band}"
            price = f"S${x.anchor_median_price:,.0f} / S${x.anchor_q1_price:,.0f}–S${x.anchor_q3_price:,.0f}"
            values = [f"{x.project_name.strip()} · {category}", selected, int(x.anchor_n), price, f"S${x.anchor_median_psf:,.0f}", f"S${x.anchor_break_even_sale:,.0f}"]
            lines.append("| " + " | ".join(str(v).replace("|", "/") for v in values) + " |")
        lines.extend(["", "### Evidence, stock and purchase limits", "", "| Project | Category | Recent New / Sub / Resale | Evidence assessment | Latest developer balance | 2026Q2 project rent | Anchor peer cells | Action / limit |", "| --- | --- | --- | --- | --- | --- | --- | --- |"])
        for x in rows.itertuples():
            name = x.project_name.strip()
            if x.existing_dossier:
                name = f"[{name}]({x.existing_dossier}) · dossier {x.existing_dossier_date}"
            balance = f"{int(x.developer_unsold):,} / {int(x.developer_units):,} unsold · {x.developer_month}" if pd.notna(x.developer_units) else "No monthly return in this capture"
            rent = f"S${x.rent_median_psf_pm:.2f} psf/month" if pd.notna(x.rent_median_psf_pm) else "Not published in snapshot"
            values = [name, "EC-origin" if x.ec_origin else "Private", f"{x.new_n} / {x.sub_n} / {x.resale_n}", x.assessment, balance, rent, str(x.anchor_peer_cells), x.action]
            lines.append("| " + " | ".join(str(v).replace("|", "/") for v in values) + " |")
        lines.append("")
    lines.extend(["## Sources and reproduction", "", "[URA transaction methodology](https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch), [official developer-sales and rental API definitions](https://eservice.ura.gov.sg/maps/api/) and dated project dossiers linked above. The full ledger and frozen snapshots remain downloadable in the local research preview.", "", "Generated by `models/build_regional_property_evidence.py` from the frozen September 2026 research batch, the current-main official rental snapshot and newly fetched official monthly developer-sales returns. Project-specific source identity and data hashes are in `enrichment/provenance.json`. No positive conclusion is assigned from a missing price or rental statistic.", ""])
    destination.write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=ROOT / "data/runs/regional-property-analysis/2026-09-20")
    parser.add_argument("--captured-at", help="SGT research timestamp YYYY-MM-DD HH:MM:SS; otherwise preserve the existing enrichment capture")
    args = parser.parse_args()
    batch = args.batch.resolve()
    out = batch / "enrichment"
    out.mkdir(exist_ok=True)
    transactions = pd.read_csv(batch / "transactions.csv")
    projects = pd.read_csv(batch / "projects.csv", keep_default_na=False)
    projects = projects.loc[projects.scope_status.eq("main")].copy()
    source = transactions.loc[transactions.scope_status.eq("main") & transactions.metric_eligible].copy()
    recent = source.loc[source.sale_month.between(LATER_START, LATER_END)]
    cohorts = pd.read_csv(batch / "cohorts.csv")
    cohorts = cohorts.loc[cohorts.project_name.isin(projects.project_name)].copy()
    medians = recent.groupby(KEYS).agg(median_sqm=("sqm", "median"), median_sqft=("sqft", "median")).reset_index()
    cohorts = cohorts.merge(medians, on=KEYS, validate="one_to_one")
    cohorts["cohort_id"] = cohorts.apply(lambda row: hashlib.sha256(json.dumps([str(row[k]) for k in KEYS]).encode()).hexdigest()[:16], axis=1)
    assert cohorts.cohort_id.is_unique
    enriched = enrich_cohorts(cohorts)
    economics_provenance = enriched.attrs.get("economics_provenance", {})
    enriched.to_csv(out / "cohort_economics.csv", index=False)
    locations = project_locations()
    peers = build_peer_matches(cohorts, recent, locations)
    peers.to_csv(out / "matched_peers.csv", index=False)
    official, developer_latest = official_developer_evidence(batch, projects)
    official.to_csv(out / "developer_monthly.csv", index=False)
    developer_latest.to_csv(out / "developer_latest.csv", index=False)
    recent.groupby(["project_name", "sale_type", "sale_month"]).size().reset_index(name="records").to_csv(out / "monthly_transaction_pace.csv", index=False)
    rental = pd.read_csv(ROOT / "data/raw/ura/rental/pmi_api_rental_median_2q26.csv")
    rental["key"] = rental.project_name.map(norm)
    requested_keys = set(projects.project_name.map(norm))
    current_rent = rental.loc[rental.ref_quarter.eq("2026Q2") & rental.key.isin(requested_keys)].set_index("key")
    assert current_rent.index.is_unique
    devmap = developer_latest.set_index("project_name").to_dict("index")
    # Existing reports remain authored dossiers, not overwritten by automated screens.
    from sg_estate.reporting.property_analysis import discover_property_analyses, latest_property_analyses
    dossiers = {norm(x.project_name): x for x in latest_property_analyses([x for x in discover_property_analyses() if not x.analysis_type.startswith(("individual project transactions", "individual future-site identity"))])}
    additions = []
    for row in projects.itertuples():
        key = norm(row.project_name)
        d = devmap.get(row.project_name, {})
        has_rent = key in current_rent.index
        c = enriched.loc[enriched.project_name.eq(row.project_name)].sort_values(["n", "sale_type", "tenure", "size_band"], ascending=[False, True, True, True])
        anchor = c.iloc[0] if len(c) else None
        peer_n = int(peers.cohort_id.eq(anchor.cohort_id).sum()) if anchor is not None else 0
        if "Historical redevelopment predecessor" in row.coverage_note:
            assessment, action = "Historical predecessor", "Do not treat the old project record as purchasable replacement stock."
        elif row.total_n == 0:
            assessment, action = "No achieved-price evidence in window", "No valuation or return conclusion; establish project identity and current offer first."
        elif row.recent_n == 0:
            assessment, action = "No recent achieved-price evidence", "Use older evidence only with its date; no current price conclusion."
        elif row.resale_n == 0 and row.new_n > 0:
            assessment = "Developer-sale evidence; no recent owner resale"
            action = "Require an owner-exit comparison and stock check before paying the launch premium."
        elif row.resale_n >= 20 and has_rent:
            assessment = "Resale and rental evidence available"
            action = "Compare the exact offered unit to its cohort, then test net carry and condition."
        elif row.resale_n >= 20:
            assessment = "Resale evidence; rental gap"
            action = "Own-stay price comparison is supported; rental fallback needs separate evidence."
        else:
            assessment = "Thin or mixed owner evidence"
            action = "A price point is observable; the small sample does not establish a reliable exit band."
        if d and d["ref_month"] == "2026-08" and d["unsold_total"] > 0:
            action += f" Compare against {int(d['unsold_total'])} officially unsold homes at August end."
        if row.ec_origin:
            action += " Check the project's applicable MOP and purchaser eligibility."
        dossier = dossiers.get(key)
        anchor_fields = ["sale_type", "tenure", "size_band", "n", "median_price", "q1_price", "q3_price", "median_psf", "median_sqft", "break_even_sale", "target_500k_sale", "gross_yield_median_pct"]
        additions.append({
            "project_name": row.project_name, "assessment": assessment, "action": action,
            "rent_median_psf_pm": float(current_rent.loc[key, "median_psf_pm"]) if has_rent else None,
            "developer_month": d.get("ref_month", ""), "developer_units": d.get("units_avail"),
            "developer_unsold": d.get("unsold_total"), "developer_sold": d.get("sold_to_date"),
            "anchor_peer_cells": peer_n, "anchor_cohort_id": anchor.cohort_id if anchor is not None else "",
            "existing_dossier": f"https://evancjx.github.io/housing-estate-framework/{dossier.output_path}" if dossier else "",
            "existing_dossier_date": dossier.date_label if dossier else "",
            **{f"anchor_{field}": anchor[field] if anchor is not None else None for field in anchor_fields},
        })
    register = projects.merge(pd.DataFrame(additions), on="project_name", validate="one_to_one")
    register.to_csv(out / "project_assessments.csv", index=False)
    previous = json.loads((out / "provenance.json").read_text()) if (out / "provenance.json").exists() else {}
    captured = args.captured_at or previous.get("captured_at") or datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M:%S")
    capture_date = datetime.strptime(captured, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
    if capture_date != batch.name:
        raise ValueError("Research capture date must match the frozen batch directory; supply --captured-at explicitly")
    write_register(register, ROOT / f"property_analysis/{capture_date}-regional-project-evidence-register.md", captured)
    summary = {
        "projects": len(register), "cohorts": len(enriched), "peer_cells": len(peers),
        "cohorts_with_peers": peers.cohort_id.nunique(), "projects_with_peers": peers.project_name.nunique(),
        "rental_q2_projects": int(register.rent_median_psf_pm.notna().sum()),
        "official_developer_projects": developer_latest.project_name.nunique(),
        "official_august_projects": int(developer_latest.ref_month.eq("2026-08").sum()),
        "existing_authored_dossiers": int(register.existing_dossier.ne("").sum()),
        "assessment_counts": register.assessment.value_counts().to_dict(),
    }
    provenance = {"captured_at": captured, "base_commit": "601c81a", "summary": summary, "economics": economics_provenance,
                  "peer_rule": "Same region, EC/private and tenure group. Both sides restricted to area within max(3sqm,5%) of the original subject cohort median; subject also stays in its original cohort. Minimum five records on both sides. Known 99-year lease starts within ten years; known project distances at most 2km. Missing geometry is explicitly regional-only. Up to three controls by proximity, then sample depth when geometry is missing. Resale and Sub Sale stay separate. Floor, facing, layout, building age and condition are not adjusted."}
    files = [batch / "transactions.csv", batch / "cohorts.csv", batch / "projects.csv", ROOT / "data/raw/ura/rental/pmi_api_rental_median_2q26.csv", ROOT / "data/outputs/private_project_locations.csv"] + list((out / "developer_sales").glob("*.csv"))
    provenance["inputs"] = [{"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    (out / "provenance.json").write_text(json.dumps(provenance, indent=2, default=str))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
