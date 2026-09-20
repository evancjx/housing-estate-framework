#!/usr/bin/env python3
"""Publish one evidence-led property analysis for every identified project.

The frozen September capture is the source. Reports do not invent live offers,
bedrooms, completion dates, rent, or a forecast for thinly observed homes.
Existing same-date authored reports are preserved, never overwritten.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import quote
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from models.regional_research_economics import bsd_residential, normalise_project_name
from sg_estate.reporting.property_analysis import discover_property_analyses, latest_property_analyses, parse_property_analysis

DATE = "2026-09-20"
START, END = "2025-09", "2026-08"
PUBLISHED = "https://evancjx.github.io/housing-estate-framework"
URA = "https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch"
API = "https://eservice.ura.gov.sg/maps/api/"
BSD = "https://www.iras.gov.sg/taxes/stamp-duty/for-property/buying-or-acquiring-property/buyer%27s-stamp-duty-%28bsd%29"
SSD = "https://www.iras.gov.sg/taxes/stamp-duty/for-property/selling-or-disposing-property/seller%27s-stamp-duty-%28ssd%29-for-residential-property"
EC_RULES = "https://www.hdb.gov.sg/buying-a-flat/executive-condominiums/conditions-after-buying-an-ec"


def slugify(name):
    value = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"['’]", "", value)
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def key(name):
    return re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().upper())


def maximum_entry(exit_price, target_gain=0, legal_allowance=5000, selling_rate=.025):
    """Invert current BSD and selling costs; no growth or holding period assumed."""
    values = [exit_price, target_gain, legal_allowance, selling_rate]
    if not all(math.isfinite(float(x)) for x in values):
        raise ValueError("Scenario inputs must be finite")
    if exit_price <= 0 or target_gain < 0 or legal_allowance < 0 or not 0 <= selling_rate < 1:
        raise ValueError("Invalid exit price, costs, target or selling rate")
    available = exit_price * (1 - selling_rate) - legal_allowance - target_gain
    if available <= 1:
        return 0.0
    low, high = 0.0, available
    for _ in range(70):
        middle = (low + high) / 2
        if middle + bsd_residential(middle) <= available:
            low = middle
        else:
            high = middle
    return low


def text(value, missing="Not verified in this capture"):
    if value is None or (isinstance(value, float) and math.isnan(value)) or str(value).strip() == "":
        return missing
    return str(value).strip().replace("|", "/").replace("\n", " ")


def money(value):
    return "—" if pd.isna(value) else f"S${value:,.0f}"


def psf(value):
    return money(value) + " psf" if pd.notna(value) else "—"


def signed(value):
    return ("−" if value < 0 else "+") + money(abs(value))


def fact_value(value):
    return value.get("value") if isinstance(value, dict) else value


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"] + ["| " + " | ".join(text(x, "—") for x in row) + " |" for row in rows])


def section(lines, heading, *paragraphs):
    lines.extend(["", f"## {heading}", ""])
    for paragraph in paragraphs:
        if paragraph:
            lines.extend([paragraph, ""])


def market_stage(project, profile, developer, recent):
    if "Historical redevelopment predecessor" in str(project.get("coverage_note", "")):
        return "historical project"
    status = str(fact_value(profile.get("status", {})) or project.get("development_status", "")).lower()
    if "bookings have not started" in status or "preview open" in status or "future site" in status:
        return "future project"
    top = profile.get("actual_top") or {}
    if project.get("ec_origin") and top.get("verified"):
        dates = re.findall(r"\d{4}-\d{2}-\d{2}", str(top.get("value", "")))
        if dates:
            # These existing ECs belong to the earlier tender cohort. Future
            # land sites with the newer ten-year rule are rendered separately.
            latest = max(datetime.strptime(d, "%Y-%m-%d") for d in dates)
            try:
                mop = latest.replace(year=latest.year + 5)
            except ValueError:
                mop = latest.replace(year=latest.year + 5, day=28)
            if mop.date().isoformat() > DATE:
                return "restricted ec"
    if status == "completed":
        return "resale"
    if any(s in status for s in ["under development", "under construction", "launched"]):
        return "new launch"
    if len(developer) and str(developer.ref_month.max()) == END:
        return "new launch"
    if len(recent) and recent.sale_type.isin(["Resale", "Sub Sale"]).any():
        return "resale" if recent.sale_type.eq("Resale").any() else "new launch"
    if len(recent) and recent.sale_type.eq("New Sale").any():
        return "new launch"
    return "unverified"


def cohort_order(cohorts):
    return cohorts.sort_values(["n", "sale_type", "tenure", "size_band"], ascending=[False, True, True, True])


def decision(project, recent, cohorts, peers, developer, editorial):
    name = project["project_name"].strip()
    if editorial.get("decision"):
        return editorial["decision"]
    if "Historical redevelopment predecessor" in str(project.get("coverage_note", "")):
        return f"{name} is a historical redevelopment predecessor. Do not treat its old transactions or bulk disposal price as a current individual-home purchase opportunity. Its replacement requires its own tenure, inventory and entry-price assessment."
    if not len(recent):
        latest = text(project.get("latest_month"), "no observed month")
        return f"No current entry-price recommendation is supported for {name}. There are no eligible single-home records in September 2025–August 2026; the latest captured transaction month is {latest}. Keep the property on a verification list until an executable offer, exact identity and sufficiently recent comparable evidence are available."
    anchor = cohort_order(cohorts).iloc[0]
    n = int(anchor.n)
    opening = f"For {name}, the most observed recent format is {anchor.size_band}, {anchor.sale_type}, with {n} records and a {money(anchor.median_price)} median."
    if n < 5:
        return opening + " This is an observed price reference, not a reliable buying band. A purchase needs direct checks of the offered unit and comparable transactions; the sample cannot establish a dependable exit price or justify a premium."
    comparable = peers.loc[peers.cohort_id.eq(anchor.cohort_id)] if len(peers) else peers
    if len(comparable):
        p = comparable.iloc[0]
        gap = p.unadjusted_psf_gap_pct
        conclusion = "Require a specific reason to pay the observed premium" if gap > 10 else "Use the owner-price comparison as an entry-discipline check"
        return opening + f" {conclusion}: the narrower subject sample is {gap:+.0f}% versus {p.peer_project.strip()} ({p.peer_sale_type}, N={int(p.peer_n)}). The gap is unadjusted for floor, condition, building age and layout, so it does not establish overvaluation or a guaranteed catch-up."
    if anchor.sale_type == "New Sale":
        return opening + f" Treat the entry as a product and holding-period decision: recovering purchase and selling friction alone requires about {money(anchor.break_even_sale)} at this historical median entry. A developer purchase is not supported by a demonstrated subject owner exit merely because the project has sold well."
    return opening + f" This supports a conditional own-stay comparison at the required area. At a hypothetical purchase at that median, capital-only break-even is {money(anchor.break_even_sale)} before holding costs. Rental support and the offered unit's condition must justify the investment case separately."


def render_project(project, transactions, cohorts, peers, rental, developer, profile, editorial, *, slug, display_name, captured_at, prior=None):
    eligible = transactions.loc[transactions.metric_eligible.eq(True)].copy() if len(transactions) else transactions.copy()
    recent = eligible.loc[eligible.sale_month.between(START, END)] if len(eligible) else eligible
    partial = eligible.loc[eligible.sale_month.eq("2026-09")] if len(eligible) else eligible
    history = eligible.loc[eligible.sale_month.le(END)] if len(eligible) else eligible
    cohorts = cohort_order(cohorts) if len(cohorts) else cohorts
    rent_current = rental.loc[rental.ref_quarter.eq("2026Q2")] if len(rental) else rental
    stage = market_stage(project, profile, developer, recent)
    verdict = decision(project, recent, cohorts, peers, developer, editorial)
    if re.search(r"\b60\s*(?:yrs|years|year)", str(project.get("tenures", "")), re.I):
        verdict = "The 60-year tenure is a defining constraint: a low entry price or higher gross yield must compensate for the shorter remaining lease, financing limits and future buyer pool. " + verdict
    name = project["project_name"].strip()
    streets = sorted(set(transactions.street_name.dropna())) if len(transactions) else []
    if not streets:
        streets = [str(x["value"]) for x in profile.get("identity", {}).get("streets", []) if x.get("value")]
    address = "; ".join(streets) or text(project.get("subregion"), project["region"])
    tx_url = f"{PUBLISHED}/research-data.html?path=research/2026-09-20/individual/{slug}/transactions.csv"
    lines = [f"# {display_name} — individual property purchase, valuation and exit analysis", "", f"Research captured: **{captured_at} SGT (UTC+08:00)**  ", f"Property: **{display_name}, {address}, Singapore**  ", "Analysis type: **individual project transactions, format selection, owner comparisons, rental fallback, supply and entry-cost analysis**  ", "Status: **point-in-time market snapshot**  ", f"Market stage: **{stage}**  ", f"Summary: **{verdict}**", "", "## Decision", "", f"**{verdict}**", ""]
    if stage == "historical project":
        lines[0] = f"# {display_name} — historical project and replacement analysis"
        replacements = {"BAGNALLCOURT": "Bagnall Haus", "LAKESIDEAPARTMENTS": "The LakeGarden Residences", "PARKVIEWMANSION": "Sora", "WATTENESTATECONDOMINIUM": "Watten House"}
        replacement = replacements.get(key(name))
        section(lines, "Historical transactions and interpretation", table(["Month", "Sale classification", "Total consideration", "Recorded units", "Recorded area SQM", "Metric exclusion"], [[x.sale_month, x.sale_type, money(x.price), x.number_of_units, x.sqm, x.exclusion_reason] for x in transactions.itertuples()]), "The aggregate disposal consideration is not an individual apartment price. It cannot be divided by the recorded unit count to value a home in the replacement project: land, redevelopment economics, new lease/product terms and unit mix differ.")
        if replacement:
            replacement_slug = slugify(replacement)
            section(lines, "Separate replacement project", f"The separately identified replacement is **{replacement}**. [Open its individual analysis]({PUBLISHED}/property-analysis-{DATE}-{replacement_slug}.html). The old project's record is not merged into that project's achieved prices or inventory.")
        section(lines, "Decision boundary", "This report does not present a live buying opportunity, current unit rent, owner exit forecast or cost scenario for the predecessor. Confirm the legal property identity in any offered title; an advertisement using an old site name must not be interpreted as current stock on this evidence.")
        section(lines, "Source records", f"[All captured predecessor rows]({tx_url}), [URA methodology]({URA}), [all individual reports]({PUBLISHED}/property-analysis-{DATE}-individual-project-analyses.html). Repeated rows and excluded bulk records remain visible; there is no artificial single-home valuation.")
        return "\n".join(lines)
    if len(cohorts):
        anchor = cohorts.iloc[0]
        lines.extend([f"At the {money(anchor.median_price)} historical entry illustration, an unchanged exit price loses {money(abs(anchor.profit_flat))}; a 10% higher exit leaves {signed(anchor.profit_up_10)} and a 10% lower exit leaves {signed(anchor.profit_down_10)} before financing, ongoing property tax, maintenance, renovation and rent. These are total price changes with no forecast date. Own-stay utility can justify a purchase, but it should not be presented as a demonstrated investment return.", ""])
        if pd.notna(anchor.gross_yield_median_pct):
            lines.extend([f"The subject's current-quarter project rent divided by this format's achieved sale PSF gives an aggregate gross-yield screen of about {anchor.gross_yield_median_pct:.1f}%. It combines different sale and rental homes; use an actual comparable lease and all recurring costs before relying on it.", ""])
        else:
            lines.extend(["The captured official 2026Q2 rental series does not establish a current subject rental median for this comparison. Rental fallback is unproven here; a missing statistic is neither zero rent nor a licence to substitute a neighbour's rent.", ""])
    if editorial.get("findings"):
        lines.extend(["\n".join(f"- {x}" for x in editorial["findings"]), ""])

    identity = [["Scheme / study location", f"{'EC-origin' if project['ec_origin'] else 'Private apartment / condominium'}; {project['region']}; {project['subregion']}"], ["Observed source tenures", text(project.get("tenures"))], ["Status and source date", text(fact_value(profile.get("status"))) + "; " + text(profile.get("status", {}).get("source_as_of") if isinstance(profile.get("status"), dict) else project.get("status_as_of"))], ["Actual TOP", text(fact_value(profile.get("actual_top")))], ["Expected milestone (not actual TOP)", text(fact_value(profile.get("proposed_completion"))) + "; " + text((profile.get("proposed_completion") or {}).get("kind"), "No verified expected date")], ["Official total homes", text(fact_value(profile.get("unit_count")))], ["Captured project rows", f"{len(transactions):,}; repeated public row occurrences retained"], ["Eligible single-home rows", f"{len(eligible):,}; {len(transactions)-len(eligible):,} excluded bulk/non-strata records retained in the ledger"], ["Recent / partial-September records", f"{len(recent):,} in Sep 2025–Aug 2026; {len(partial):,} in partial Sep 2026"]]
    section(lines, "Project identity and evidence", table(["Item", "Project evidence"], identity), "Market stage describes observed selling activity or a sourced development status. A resale classification is not an independent TOP certificate. A total-unit figure is not live inventory. Registered area is not a bedroom count or a measure of usable internal space.")
    if project.get("coverage_note") and not pd.isna(project["coverage_note"]):
        lines.extend([text(project["coverage_note"]), ""])
    if profile.get("source_note"):
        lines.extend([text(profile["source_note"]), ""])
    if prior:
        lines.extend([f"[Earlier individual analysis, {prior.date_label}]({PUBLISHED}/{prior.output_path}) contains the previous project-specific inspection of product, asks or unit formats. It retains its own capture date; earlier advertised stock is not assumed executable today.", ""])
    section(lines, "Achieved prices and format selection")
    if len(cohorts):
        rows = [[c.sale_type, c.tenure, c.size_band, int(c.n), money(c.median_price), f"{money(c.q1_price)}–{money(c.q3_price)}", psf(c.median_psf), int(c.active_months)] for c in cohorts.itertuples()]
        lines.extend([table(["Sale type", "Source tenure", "Registered area band", "N", "Median price", "Middle 50% of prices", "Median PSF", "Active months"], rows), "", "All rows above use September 2025–August 2026. Each tenure, size band and seller category is separate. A middle-50% range from fewer than five observations is not a stable valuation interval. The lowest PSF can reflect a larger or less usable registered area; it is not automatically the better home.", ""])
        for c in cohorts.head(4).itertuples():
            qualifier = "thin" if c.n < 5 else "small" if c.n < 20 else "more frequently observed"
            lines.extend([f"**{c.sale_type}, {c.size_band}:** {int(c.n)} observations across {int(c.active_months)} months make this a {qualifier} evidence cell. The median is {money(c.median_price)} ({psf(c.median_psf)}), while actual registered areas span {c.min_sqft:,.0f}–{c.max_sqft:,.0f} sqft. A quotation above {money(c.q3_price)} needs a unit-specific explanation relative to this historical distribution; that figure is not a universal offer ceiling. The cost-only recovery hurdle at the median entry is {money(c.break_even_sale)}.", ""])
        matched_changes = cohorts.loc[cohorts.median_psf_change_pct.notna()]
        if len(matched_changes):
            lines.extend(["### Change within the same source cohort", "", table(["Sale / area / tenure", "Prior N", "Recent N", "Prior median PSF", "Recent median PSF", "Median change"], [[f"{x.sale_type}; {x.size_band}; {x.tenure}", int(x.prior_n), int(x.n), psf(x.prior_median_psf), psf(x.median_psf), f"{x.median_psf_change_pct:+.1f}%"] for x in matched_changes.itertuples()]), "", "The prior window is September 2024–August 2025. Each side has at least ten records. These are composition-sensitive changes in separate groups of homes, not repeat-sale appreciation or an annual forecast.", ""])
    else:
        lines.extend(["There is no eligible recent cohort from which to form a current achieved-price band. Do not fill the gap with a regional median or treat an old transaction as a present offer.", ""])
    if len(recent):
        exact = recent.groupby(["sale_type", "tenure", "sqm"], dropna=False).agg(n=("record_id", "size"), median_price=("price", "median"), min_price=("price", "min"), max_price=("price", "max"), median_psf=("psf", "median")).reset_index()
        lines.extend(["### Exact registered-area evidence", "", table(["Sale type / tenure", "SQM / approx sqft", "N", "Median price", "Observed range", "Median PSF"], [[f"{x.sale_type}; {x.tenure}", f"{x.sqm:g} / {x.sqm*10.7639104167:,.0f}", int(x.n), money(x.median_price), f"{money(x.min_price)}–{money(x.max_price)}", psf(x.median_psf)] for x in exact.itertuples()]), "", "Equal registered area still does not establish equal layout, balcony/PES content, floor, facing or condition. No bedroom label is assigned without a verified plan. [URA floor-area harmonisation](https://www.ura.gov.sg/guidelines/circulars/dc22-09/) also means old and new area conventions need checking before pricing usable space.", ""])

    section(lines, "Sales history and exit liquidity")
    if len(history):
        annual = history.assign(year=history.sale_month.str[:4]).groupby(["year", "sale_type"]).agg(n=("record_id", "size"), min_price=("price", "min"), max_price=("price", "max"), median_psf=("psf", "median")).reset_index()
        lines.extend([table(["Year / coverage", "Sale category", "N", "Observed price range", "Unadjusted median PSF"], [[x.year + (" Oct–Dec" if x.year == "2021" else " Jan–Aug" if x.year == "2026" else ""), x.sale_type, int(x.n), f"{money(x.min_price)}–{money(x.max_price)}", psf(x.median_psf)] for x in annual.itertuples()]), "", "These yearly distributions mix sizes and floors, and the end years are incomplete. They show evidence depth and historical price dispersion; their difference is not a project return index.", ""])
    else:
        lines.extend(["No eligible individual-home history was captured for this project name. A missing record does not establish that the development or its owners do not exist.", ""])
    if len(recent):
        pace = recent.groupby(["sale_month", "sale_type"]).size().unstack(fill_value=0).reindex(pd.period_range(START, END, freq="M").astype(str), fill_value=0)
        lines.extend(["### Recent monthly activity", "", table(["Month", "New Sale", "Sub Sale", "Resale"], [[month, int(row.get("New Sale", 0)), int(row.get("Sub Sale", 0)), int(row.get("Resale", 0))] for month, row in pace.iterrows()]), ""])
        owners = recent.loc[recent.sale_type.isin(["Resale", "Sub Sale"])]
        owner_evidence = "These records provide observed owner pricing" if len(owners) else "No subject owner exit-price evidence is demonstrated in this recent window"
        lines.extend([f"There are {len(owners):,} recent owner-sale records across {owners.sale_month.nunique()} active months. {owner_evidence}. Counts do not establish days to sell or turnover: listing exposure and a consistently verified stock denominator are unavailable. {len(partial)} additional eligible records in September are excluded from the complete-month comparisons because the month is unfinished.", ""])

    section(lines, "Developer inventory and current purchase availability")
    if len(developer):
        latest = developer.sort_values("ref_month").iloc[-1]
        lines.extend([f"The latest captured official developer return is **{latest.ref_month}**: {int(latest.sold_to_date):,} sold out of {int(latest.units_avail):,} total homes, leaving {int(latest.unsold_total):,} unsold by official totals. Of those, {int(latest.launched_unsold):,} had been launched and {int(latest.unlaunched_units):,} had not. The distinction matters: unlaunched stock can reflect release policy and is not evidence that every home has been rejected by buyers.", "", table(["Month", "Sold in month", "Cumulative sold", "Launched", "Total unsold", "Monthly median PSF"], [[x.ref_month, int(x.sold_in_month), int(x.sold_to_date), int(x.launched_to_date), int(x.unsold_total), psf(x.median_psf) if pd.notna(x.median_psf) and x.median_psf > 0 else "Not published"] for x in developer.sort_values("ref_month").itertuples()]), ""])
        if latest.unsold_total > 0:
            lines.extend([f"For a buyer or eventual seller in {display_name}, the {int(latest.unsold_total):,}-home dated balance is a reason to compare the exact developer alternative, incentives and release terms. It is not a forecast of future selling time. Later bookings, cancellations and reporting revisions can change the position.", ""])
        else:
            lines.extend(["A zero balance in that official month closes the historical developer-stock comparison; it does not establish today's secondary listings, completion or purchaser eligibility.", ""])
        lines.extend(["The API's `units_avail` field is total project units, not available stock. Monthly sales are not forced to sum to cumulative sales. [Official API definitions](https://eservice.ura.gov.sg/maps/api/).", ""])
    else:
        lines.extend(["No project developer-sales return appears in this capture. This is not proof of full sell-out, completion or absence of available homes. No current seller or developer asking price has been verified for the unit a buyer would actually purchase.", ""])
    lines.extend(["URA's public New Sale transactions reflect developer OTP evidence; Resale and Sub Sale evidence is caveat-based. Neither dataset supplies full unit numbers or a reservable live inventory. Obtain a dated unit quotation before converting historical prices into an offer.", ""])

    section(lines, "Matched owner transactions and entry discipline")
    if len(peers):
        rows = [[f"{x.subject_sale_type}; {x.subject_min_sqm:g}–{x.subject_max_sqm:g} sqm; {x.subject_tenure}", f"{int(x.subject_n)} / {psf(x.subject_median_psf)}", f"{x.peer_project.strip()}; {x.peer_sale_type}; {x.peer_tenure}", f"{x.peer_min_sqm:g}–{x.peer_max_sqm:g} sqm / {int(x.peer_n)}", psf(x.peer_median_psf), f"{x.unadjusted_psf_gap_pct:+.0f}%", f"{x.distance_m:,.0f} m straight-line" if pd.notna(x.distance_m) else "Proximity unverified"] for x in peers.itertuples()]
        lines.extend([table(["Subject subset", "N / median PSF", "Owner control", "Peer area / N", "Peer median PSF", "Subject gap", "Location"], rows), "", "Both sides use the same area window, ±5% or 3 sqm around the subject cohort median, whichever is larger. The subject remains in its original cohort. Each side has at least five records; EC origin, region and tenure category match. Known lease commencements are within ten years, and known project distances are at most 2 km. Missing lease dates or geometry remain unverified. Floors, internal area, facing, building age, condition and incentives are not adjusted.", ""])
        hurdles = []
        for x in peers.itertuples():
            exit_value = x.peer_median_psf * x.subject_median_sqm * 10.7639104167
            entry = maximum_entry(exit_value)
            hurdles.append([f"{x.subject_min_sqm:g}–{x.subject_max_sqm:g} sqm; {x.subject_sale_type}", x.peer_project.strip(), money(x.subject_median_price), money(exit_value), money(entry), money(maximum_entry(exit_value, 500000))])
        lines.extend(["### What today's owner prices would require of entry", "", table(["Subject subset", "Owner-price scenario", "Observed subject median", "Hypothetical gross exit", "Maximum entry for cost-only recovery", "Maximum entry for S$500k gain"], hurdles), "", "This is an inverse cost test, not a valuation or an offer recommendation. It holds the subject's median registered area constant and assumes a hypothetical future exit at the peer's current median PSF. It includes current BSD, S$5,000 acquisition costs and 2.5% selling costs, but no holding expenses or rent. A lower calculated maximum entry exposes dependence on future price growth or a defensible product premium; it does not show that a seller will accept that price.", ""])
    else:
        lines.extend(["No owner comparison meets the captured rules for this project's recent subject cohorts: sufficient observations on both sides, the same tenure/EC group and area window, plus known lease and distance limits. A nearby launch price is not substituted as owner-exit support. Use the project's own exact-area history and obtain an independent unit comparison before paying a premium.", ""])

    section(lines, "Rental fallback")
    if len(rental):
        latest_rent = rental.sort_values("ref_quarter").iloc[-1]
        lines.extend([table(["Quarter", "25th percentile PSF/month", "Median PSF/month", "75th percentile PSF/month"], [[x.ref_quarter, f"S${x.psf25:.2f}", f"S${x.median_psf_pm:.2f}", f"S${x.psf75:.2f}"] for x in rental.sort_values("ref_quarter").tail(12).itertuples()]), ""])
        if len(rent_current):
            r = rent_current.iloc[0]
            lines.extend([f"The subject's official 2026Q2 median is **S${r.median_psf_pm:.2f} psf per month**, with a middle-50% range of S${r.psf25:.2f}–S${r.psf75:.2f}. These are project-level leases, not this sale unit's rent. URA publishes the statistic only where its quarterly contract threshold is met; do not infer a unit-specific rent from registered area alone.", ""])
        else:
            lines.extend([f"The latest available subject statistic is {latest_rent.ref_quarter}. There is no 2026Q2 subject median in this capture, so the older rent is historical context only and is not carried forward into a current yield.", ""])
    else:
        lines.extend(["No published subject rental observation appears in the captured official quarterly series. This leaves the rental fallback unverified. It does not establish zero rental demand; low contract count, project stage or coverage can explain absence.", ""])
    if len(cohorts):
        rows = [[f"{x.sale_type}; {x.size_band}; {x.tenure}", money(x.median_price), f"S${x.median_price*.035/12:,.0f}", f"S${x.median_price*.04/12:,.0f}", f"{x.gross_yield_median_pct:.1f}%" if pd.notna(x.gross_yield_median_pct) else "Unverified"] for x in cohorts.itertuples()]
        lines.extend([table(["Historical entry cohort", "Median entry", "Monthly rent needed for 3.5% gross", "For 4.0% gross", "Aggregate achieved-rent yield lens"], rows), "", "The required rents are arithmetic hurdles, not predicted leases. The aggregate yield lens divides the project rent PSF by the separate cohort sale PSF. It excludes vacancy, property tax, management fees, repairs, letting costs and financing. One vacant month removes one-twelfth of scheduled annual rent. For an EC, recorded rent does not override MOP or whole-unit rental restrictions.", ""])

    section(lines, "Purchase and exit economics")
    lines.extend(["The common scenario is a Singapore citizen's first residential purchase with no ABSD, entry price equal to dutiable market value, current BSD, S$5,000 acquisition allowance and 2.5% selling costs. Actual duty uses the higher of price and market value. The exit must be permitted and outside the applicable SSD period and any EC MOP. Loan interest, CPF obligations, renovation, ongoing property tax, maintenance, vacancy, rent and opportunity cost are excluded.", ""])
    if len(cohorts):
        rows = [[f"{x.sale_type}; {x.size_band}; {x.tenure}", money(x.median_price), money(x.scenario_bsd), f"{money(x.break_even_sale)} / {psf(x.break_even_psf)}", signed(x.profit_down_10), signed(x.profit_flat), signed(x.profit_up_10), f"{money(x.target_500k_sale)} / {psf(x.target_500k_psf)}"] for x in cohorts.itertuples()]
        lines.extend([table(["Historical cohort", "Entry", "BSD", "Cost-only break-even", "10% lower exit", "Unchanged exit", "10% higher exit", "Exit for S$500k capital-only gain"], rows), "", "These hypothetical entries combine the independent median price and median area, which need not describe the same home. Scenario PSF therefore differs from median transaction PSF. The S$500k hurdle is a common comparison, not a buyer objective or return forecast. A 10% change is a total price change with no assumed exit date.", ""])
        second = cohorts.loc[cohorts.sc_second_property_break_even_sale.notna()]
        if len(second):
            c = second.iloc[0]
            lines.extend([f"For illustration, at the {money(c.median_price)} entry above, a Singapore citizen's second-property purchase with 20% ABSD and no remission raises capital-only break-even to {money(c.sc_second_property_break_even_sale)}. This is a tax sensitivity, not a certification of purchaser eligibility. It is omitted for new-EC entries. [IRAS ABSD](https://www.iras.gov.sg/taxes/stamp-duty/for-property/buying-or-acquiring-property/additional-buyer%27s-stamp-duty-%28absd%29).", ""])
    else:
        lines.extend(["There is no current observed price anchor for a project-specific purchase scenario. Set the acquisition and exit assumptions only after obtaining a verified offer; a regional price would create false precision.", ""])
    lines.extend([f"A private-home acquisition in September 2026 falls under the four-year SSD regime for acquisitions from 4 July 2025. Selling at TOP does not itself establish that SSD has expired. Exact legal dates control. [BSD]({BSD}), [SSD]({SSD}).", ""])

    section(lines, "Location, competing supply and holding period")
    rail = profile.get("nearest_rail")
    if rail:
        distance = rail.get("straight_line_metres")
        lines.extend([f"The matched project point's nearest station marked open in the **{text(rail.get('station_status_as_of'))} station snapshot** is **{text(rail.get('name'))}**, approximately **{float(distance):,.0f} m straight-line** away. This is not the entrance-to-platform walking route, a sheltered-link claim or a school-distance certification. The source point is a project representative, not the offered block's gate. Check the actual block, crossings and any station changes after that snapshot.", ""])
    else:
        lines.extend(["A reliable project-to-operating-station distance is not established in this capture. No walkability, direct link or school-distance premium is assigned without a verified address and route.", ""])
    facts = profile.get("context_facts", [])
    if facts:
        rows = []
        for f in facts:
            sources = f.get("sources", [])
            links = []
            for s in sources:
                url = (s.get("url") or s.get("source_url")) if isinstance(s, dict) else s
                if url:
                    links.append(f"[Source]({url})" + (f" · {s.get('source_as_of')}" if isinstance(s, dict) and s.get('source_as_of') else ""))
            rows.append([f.get("claim", ""), f.get("status", ""), f.get("applicability", ""), f.get("limitation", ""), "; ".join(links)])
        lines.extend([table(["Dated context", "Delivered / future", "Relevance to this project", "Limit", "Evidence"], rows), ""])
    lines.extend([f"For {display_name}, a future transport or amenity benefit matters only if the household actually uses it and the holding period reaches delivery. Nearby new homes can add competing layouts and seller choices as well as amenities. No percentage appreciation is added from a regional plan, and land yields, launched inventory and unrestricted resale supply are not summed into one stock number.", ""])

    section(lines, "Ownership restrictions and project risks")
    if project["ec_origin"]:
        lines.extend([f"**{display_name} is EC-origin.** An older privatised EC, an EC between MOP and full privatisation, and a new EC have different purchaser and rental conditions. The current private/EC label in a transaction file does not certify eligibility. Confirm the actual project's tender cohort, block TOP date and applicable restrictions.", "", f"HDB distinguishes land tenders closing before 8 May 2026 from those on or after that date: the newer cohort has a ten-year MOP instead of five years, and a longer citizenship-restricted period. The existing EC's own dates control; a transaction does not prove that every unit is generally available. [HDB conditions]({EC_RULES}).", ""])
        if stage == "restricted ec":
            lines.extend(["The verified TOP evidence places this existing EC, or at least its latest recorded block, inside its original five-year MOP at this capture. An exceptional transaction does not establish general resale availability or whole-unit rental rights. Verify the offered block's legal dates and HDB conditions.", ""])
    risks = list(editorial.get("risks", []))
    if len(recent) < 10:
        risks.append(f"Only {len(recent)} eligible recent records are observed. Price dispersion and absence of a particular size may reflect very small samples rather than a market signal.")
    if not len(rent_current):
        risks.append("No current-quarter subject rental median supports the rental fallback in this capture.")
    if not profile.get("actual_top"):
        risks.append("Actual TOP is not independently verified here. An expected completion date or sale category does not resolve it.")
    if len(developer) and developer.sort_values("ref_month").iloc[-1].unsold_total > 0:
        d = developer.sort_values("ref_month").iloc[-1]
        risks.append(f"The {d.ref_month} developer return still has {int(d.unsold_total)} unsold homes; check current developer alternatives before paying an owner premium or forecasting an exit.")
    risks.extend(["The offered unit's floor plan, usable space, orientation, defects, major works and management-fund position are not established by a transaction record.", "Current listing exposure and executable seller terms are not captured consistently; asking stock is not inferred from past transactions."])
    lines.extend(["\n".join(f"- {x}" for x in risks), ""])
    section(lines, "Conditions for proceeding")
    conditions = list(editorial.get("entry_conditions", []))
    if len(cohorts):
        a = cohorts.iloc[0]
        conditions.append(f"Match the offered home to its own sale/tenure/area cell, starting with the {int(a.n)}-record {a.size_band} reference at {money(a.median_price)} only if that is the required format. Explain differences in floor, layout and condition before setting an offer.")
        conditions.append(f"Test the actual quotation against acquisition costs and a conservative exit. The selected historical entry needs {money(a.break_even_sale)} merely to recover the modeled purchase and selling costs; holding expenses raise that requirement.")
    else:
        conditions.append("Establish a current, unit-specific quotation and independently comparable owner evidence before assigning an entry band.")
    conditions.extend(["For own stay, verify the actual daily journey, space and holding horizon; for investment, obtain an achievable lease and calculate net carry after all costs.", "Confirm title, lease, current sale status and applicable purchaser/holding restrictions before treating any historical price as a buyable opportunity."])
    lines.extend(["\n".join(f"{i}. {x}" for i, x in enumerate(conditions, 1)), ""])

    section(lines, "Evidence register and downloads", f"This is a separate analysis of **{display_name}**. [Browse every captured project transaction]({tx_url}) or [download its source-row-preserving normalized ledger]({PUBLISHED}/research/2026-09-20/individual/{slug}/transactions.csv?download=1). The public data reports transaction months and floor bands, not full unit numbers. Every repeated source occurrence is retained. [All original URA fields]({PUBLISHED}/research-data.html?path=research/2026-09-20/transactions_original_fields.csv) remain separately available in the full capture.", f"[Project cohort and cost evidence]({PUBLISHED}/research-data.html?path=research/2026-09-20/individual/{slug}/cohorts.csv), [project owner comparisons]({PUBLISHED}/research-data.html?path=research/2026-09-20/individual/{slug}/peers.csv), [all individual reports]({PUBLISHED}/property-analysis-{DATE}-individual-project-analyses.html). The linked tables preserve the frozen source capture and do not refresh live offers.")
    source_rows = [["URA transactions", f"[Public source]({URA})", "Captured 20 Sep 2026; portal update 18 Sep; October 2021–partial September 2026"], ["URA quarterly rent and monthly developer returns", f"[API definitions]({API})", "Requested current rental quarter 2026Q2; developer snapshots retain each reference month"], ["Project scope identity", f"[Scope metadata]({project['scope_source']})" if project.get("scope_source") else "Unresolved", "Secondary geography metadata; no secondary sale price used"]]
    for label, field in [("Project status", "status"), ("Actual TOP", "actual_top"), ("Expected milestone", "proposed_completion"), ("Official unit count", "unit_count")]:
        f = profile.get(field)
        if isinstance(f, dict) and f.get("source_url"):
            source_rows.append([label, f"[Source]({f['source_url']})", text(f.get("source_as_of"), DATE)])
    for s in editorial.get("source_links", []):
        source_rows.append([s.get("title", "Project context"), f"[Source]({s['url']})", "Date/limitations stated beside the claim or in the linked earlier dossier"])
    if rail:
        for s in rail.get("station_sources", []):
            source_rows.append([s.get("title", "Station snapshot"), f"[Source]({s['source_url']})", text(s.get("source_as_of")) + "; existing repository snapshot"])
        source_rows.append(["Matched project representative point", "[OneMap search](https://www.onemap.gov.sg/apidocs/search)", "Existing geocoding snapshot; original retrieval date not recorded; no fresh-coordinate claim"])
    lines.extend([table(["Evidence", "Source", "Date and limit"], source_rows), "", "The calculation preserves the repository's distinction between objective Provision and person-relative Liveability. No unified estate/property score or predicted appreciation is assigned. The report's purchase conditions follow this project's evidence; missing inputs remain missing.", ""])
    return "\n".join(lines)


def render_future_site(site, cohorts, *, display_name, captured_at, prior=None):
    name = site["site_name"]
    is_ec = site["ec_origin"]
    verdict = (f"Wait for a licensed, unit-specific launch proposition at {name}. "
               "The current evidence supports a land-site watchlist decision, not a purchase price or investment return. "
               + ("A future EC here belongs to the newer tender cohort with a ten-year MOP, so it is unsuitable as a near-term resale or rental plan." if is_ec else "An award and potential housing yield do not establish final unit mix, price, completion or an executable offer."))
    lines = [f"# {display_name} — individual future-site and purchase-waiting analysis", "", f"Research captured: **{captured_at} SGT (UTC+08:00)**  ", f"Property: **{display_name}, {name}, Singapore**  ", "Analysis type: **individual future-site identity, supply, purchase alternatives and holding-period assessment**  ", "Status: **point-in-time market snapshot**  ", "Market stage: **future project**  ", f"Summary: **{verdict}**", "", "## Decision", "", f"**{verdict}**", ""]
    rows = []
    for label, field in [("Land status", "status"), ("Award date", "land_award_date"), ("Successful tenderer", "successful_tenderer"), ("Land tenure", "land_tenure"), ("Site area SQM", "site_area_sqm"), ("Potential housing yield", "potential_units"), ("Construction-scheme description", "construction_scheme_units")]:
        value = site.get(field)
        if isinstance(value, dict):
            rows.append([label, text(value.get("value")), text(value.get("kind"), "Official site fact"), f"[Source]({value['source_url']}) · {text(value.get('source_as_of'))}"])
    section(lines, "Identity and verified project stage", table(["Item", "Value", "Interpretation", "Dated source"], rows), site.get("identity_resolution", "The official land-site location is used as a descriptive identifier. A final condominium marketing name has not been verified."), "Final sales inventory, apartment mix, live price, launch date and actual TOP remain unverified. Potential yield is not licensed inventory and a construction contract description is not a sales schedule.")
    if prior:
        lines.extend([f"[Earlier site-specific analysis, {prior.date_label}]({PUBLISHED}/{prior.output_path}). Its assumptions remain dated; the verified facts above control this update.", ""])
    alternatives = ["1 CANBERRA", "THE BROWNSTONE", "THE VISIONAIRE"] if is_ec else (["GRANDEUR PARK RESIDENCES", "THE GLADES", "EAST MEADOWS"] if name in {"Bedok Rise", "New Upper Changi Road"} else ["BAYSHORE PARK", "THE BAYSHORE", "COSTA DEL SOL"])
    selected = cohorts.loc[cohorts.project_name.str.strip().isin(alternatives) & cohorts.sale_type.eq("Resale") & cohorts.n.ge(5)]
    section(lines, "The decision to wait versus buying an existing home")
    if len(selected):
        lines.extend([table(["Existing project", "Area / tenure", "N", "Achieved median", "Capital-only break-even at that entry"], [[x.project_name.strip(), f"{x.size_band}; {x.tenure}", int(x.n), money(x.median_price), money(x.break_even_sale)] for x in selected.itertuples()]), "", "These September 2025–August 2026 resale cohorts are alternative household budgets, not like-for-like valuations of an unlaunched development. Existing projects differ in lease age, layout, completion and access. The cost illustration uses current BSD, S$5,000 acquisition allowance and 2.5% selling costs; it excludes holding costs and rent.", ""])
    lines.extend([f"For an immediate housing need, compare an actual completed-home quotation with the cost of waiting for {name}: interim accommodation, an uncertain delivery date and the possibility that the eventual unit mix does not fit. Waiting is more defensible when the household has flexibility and the new project's verified product would solve a specific space or access problem.", ""])
    section(lines, "Pricing and rental case", "There are no achieved subject unit prices or rents in this evidence set. A developer land bid does not guarantee a resale price floor. No sale price, rental yield, break-even PSF or future gain is fabricated for the site. Once prices are released, start with the exact offered area and all acquisition/holding costs, then test the required exit against owner transactions in relevant completed projects.")
    section(lines, "Competing supply and buyer-pool risk", f"The potential {text(fact_value(site.get('potential_units')), 'unverified number of')} homes are future supply, not available apartments today. The eventual effect depends on launch timing, release policy, completion, unit mix and competing projects. The buyer should not pay an assumed infrastructure or integration premium twice, first in the future launch price and again as automatic resale appreciation.")
    if is_ec:
        section(lines, "EC holding-period constraint", f"The Canberra Drive tender is scheduled to close after 8 May 2026, so the new EC policy cohort applies if that timetable proceeds: ten-year MOP and a longer citizenship-restricted period. The MOP is not ten years from this research capture or land award; applicable completion and HDB conditions matter. Existing older EC resale alternatives follow their own earlier cohorts. [HDB conditions]({EC_RULES}).")
    section(lines, "Conditions for a purchase assessment", "1. Confirm the final developer-issued identity, licensed unit count, plans, sale conditions and expected possession.\n2. Obtain an executable quotation for a specific layout, floor and facing.\n3. Compare the required exit after BSD, selling costs and holding expenses with appropriately matched owner transactions.\n4. Verify actual routes and delivered amenities; separate future improvements from construction and competing stock.\n5. For ECs, confirm purchaser eligibility, the applicable MOP, rental restrictions and future buyer pool before assuming an exit.", f"[All individual project analyses]({PUBLISHED}/property-analysis-{DATE}-individual-project-analyses.html). This site is listed separately from the 553 named-project transaction inventory and is not counted as a launched condominium.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=ROOT / f"data/runs/regional-property-analysis/{DATE}")
    parser.add_argument("--captured-at")
    args = parser.parse_args()
    old_manifest = args.batch.resolve() / "individual_report_manifest.json"
    saved = json.loads(old_manifest.read_text()) if old_manifest.exists() else {}
    args.captured_at = args.captured_at or saved.get("captured_at") or datetime.now(ZoneInfo("Asia/Singapore")).strftime("%Y-%m-%d %H:%M:%S")
    if datetime.strptime(args.captured_at, "%Y-%m-%d %H:%M:%S").date().isoformat() != DATE:
        raise ValueError("Capture must use the frozen research date")
    batch = args.batch.resolve()
    enrichment = batch / "enrichment"
    projects = pd.read_csv(batch / "projects.csv", keep_default_na=False)
    projects = projects.loc[projects.scope_status.eq("main")]
    transactions = pd.read_csv(batch / "transactions.csv")
    cohorts = pd.read_csv(enrichment / "cohort_economics.csv")
    peers = pd.read_csv(enrichment / "matched_peers.csv")
    developer = pd.read_csv(enrichment / "developer_monthly.csv")
    rental = pd.read_csv(ROOT / "data/raw/ura/rental/pmi_api_rental_median_2q26.csv")
    profile_document = json.loads((enrichment / "individual_project_profiles.json").read_text())
    profiles = profile_document["profiles"]
    notes = json.loads((enrichment / "individual_editorial_notes.json").read_text())
    if "projects" in notes:
        notes = notes["projects"]
    notes = {key(name): value for name, value in notes.items()}
    analyses = discover_property_analyses()
    old_manifest = batch / "individual_report_manifest.json"
    previously_generated = {x["source"] for x in json.loads(old_manifest.read_text()).get("reports", []) if not x.get("reused")} if old_manifest.exists() else set()
    originals = [x for x in analyses if x.source_relative_path not in previously_generated and not x.analysis_type.startswith(("individual project transactions", "individual future-site identity"))]
    existing = {key(x.project_name): x for x in latest_property_analyses(originals)}
    occupied = {x.project_slug: key(x.project_name) for x in originals}
    records = []
    for project in projects.to_dict("records"):
        name = project["project_name"]
        prior = existing.get(key(name))
        slug = prior.project_slug if prior else slugify(name)
        if slug in occupied and occupied[slug] != key(name):
            raise ValueError(f"Slug collision for {name}: {slug}")
        occupied[slug] = key(name)
        display = prior.project_name if prior else name.strip().title()
        tx = transactions.loc[transactions.project_name.eq(name) & transactions.scope_status.eq("main")]
        c = cohorts.loc[cohorts.project_name.eq(name)]
        p = peers.loc[peers.project_name.eq(name)]
        d = developer.loc[developer.project_name.eq(name)]
        r = rental.loc[rental.project_name.map(normalise_project_name).eq(normalise_project_name(name))]
        if r.duplicated("ref_quarter").any():
            raise ValueError(f"Ambiguous rental evidence for {name}")
        output = batch / "individual" / slug
        output.mkdir(parents=True, exist_ok=True)
        for filename, frame in [("transactions", tx), ("cohorts", c), ("peers", p), ("developer_sales", d), ("rental", r)]:
            frame.to_csv(output / f"{filename}.csv", index=False)
        source = ROOT / "property_analysis" / f"{DATE}-{slug}.md"
        reuse = bool(prior and prior.source_path == source)
        if not reuse:
            content = render_project(project, tx, c, p, r, d, profiles[name], notes.get(key(name), {}), slug=slug, display_name=display, captured_at=args.captured_at, prior=prior)
            source.write_text(content, encoding="utf-8")
        parsed = parse_property_analysis(source)
        records.append({"project_name": name, "display_name": display, "region": project["region"], "ec_origin": bool(project["ec_origin"]), "slug": slug, "source": str(source.relative_to(ROOT)), "url": f"{PUBLISHED}/{parsed.output_path}", "recent_n": int(project["recent_n"]), "total_n": int(project["total_n"]), "cohorts": len(c), "peer_pairs": len(p), "has_current_rent": bool(r.ref_quarter.eq("2026Q2").any()), "market_stage": parsed.market_stage, "reused": reuse, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    future_records = []
    for site in profile_document.get("future_sites", []):
        if site["site_name"] == "Bedok Rise":
            prior = next((x for x in originals if x.project_slug == "bedok-rise-gls-future-condominium"), None)
        else:
            prior = None
        slug = prior.project_slug if prior else slugify(site["site_name"] + (" EC future site" if site["ec_origin"] else " GLS future condominium"))
        display = prior.project_name if prior else site["site_name"] + (" EC future site" if site["ec_origin"] else " GLS future condominium")
        path = ROOT / "property_analysis" / f"{DATE}-{slug}.md"
        path.write_text(render_future_site(site, cohorts, display_name=display, captured_at=args.captured_at, prior=prior))
        parsed = parse_property_analysis(path)
        future_records.append({"project_name": site["project_name"], "display_name": display, "region": site["region"], "ec_origin": site["ec_origin"], "source": str(path.relative_to(ROOT)), "url": f"{PUBLISHED}/{parsed.output_path}", "market_stage": "future project", "reused": False})
    index_path = ROOT / "property_analysis" / f"{DATE}-individual-project-analyses.md"
    index_capture = saved.get("index_captured_at") or (parse_property_analysis(index_path).captured_at.strftime("%Y-%m-%d %H:%M:%S") if index_path.exists() else args.captured_at)
    manifest = {"captured_at": args.captured_at, "index_captured_at": index_capture, "projects": len(records), "reports": records, "future_site_reports": future_records, "future_sites": profile_document.get("future_sites", [])}
    old_manifest.write_text(json.dumps(manifest, indent=2))
    index_lines = ["# Individual property analyses — every project in the requested areas", "", f"Research captured: **{args.captured_at} SGT (UTC+08:00)**  ", "Property: **Individual property analyses, Tampines / Bedok / Canberra / Lakeside-Jurong / Bukit Timah, Singapore**  ", "Analysis type: **directory of separate project purchase, valuation, rental and exit analyses**  ", "Status: **point-in-time market snapshot**  ", "Market stage: **mixed market**  ", "Summary: **Open a separate analysis for each of the 553 identified projects, including all 20 EC-origin developments. Each report has its own transactions, format choices, owner comparisons, rent, purchase costs, risks and conclusion; missing evidence stays explicit.**", "", "## Decision", "", "**Choose a project below to open its individual property analysis.** These are separate reports using the existing property-analysis format. The earlier regional comparison is supporting context; it does not substitute for these project reports.", "", "The captured inventory has 553 identified project names, including 20 EC-origin developments. It is not a certified census of every physical development. Historical predecessors and names with no recent transactions receive individual evidence-limit assessments rather than invented live valuations. The existing same-day Canberra Crescent analysis is preserved; older dated project reports remain accessible from their refreshed individual pages.", ""]
    for region in sorted(projects.region.unique()):
        selected = [x for x in records if x["region"] == region]
        section(index_lines, f"{region}: {len(selected)} individual reports", table(["Project analysis", "Category", "Recent transactions", "Current rent", "Report stage"], [[f"[{x['display_name']}]({x['url']})", "EC-origin" if x["ec_origin"] else "Private", x["recent_n"], "2026Q2 published" if x["has_current_rent"] else "Gap flagged", x["market_stage"]] for x in selected]))
    section(index_lines, "Four additional future land sites", "These have separate individual site assessments and are excluded from the 553 named-project count. Their final names, licensed inventory, home prices and TOP are not invented.", table(["Individual future-site analysis", "Area", "Category"], [[f"[{x['display_name']}]({x['url']})", x["region"], "Future EC site" if x["ec_origin"] else "Future private site"] for x in future_records]))
    index_lines[2] = f"Research captured: **{index_capture} SGT (UTC+08:00)**  "
    (ROOT / "property_analysis" / f"{DATE}-individual-project-analyses.md").write_text("\n".join(index_lines))
    print(json.dumps({"individual_projects": len(records), "new_reports": sum(not x["reused"] for x in records), "preserved_same_day_reports": sum(x["reused"] for x in records), "ec_reports": sum(x["ec_origin"] for x in records), "additional_future_sites": len(future_records)}, indent=2))


if __name__ == "__main__":
    main()
