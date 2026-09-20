#!/usr/bin/env python3
"""Build sourced identity and context for each project in the local research batch.

No TOP date, walking distance, unit inventory or infrastructure price effect is
inferred from transactions. The deterministic JSON keeps absent evidence null.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESEARCH_DATE = "2026-09-20"
URA_TRANSACTIONS = "https://eservice.ura.gov.sg/property-market-information/pmiResidentialTransactionSearch"
URA_API = "https://eservice.ura.gov.sg/maps/api/"
ONEMAP_SOURCE = "https://www.onemap.gov.sg/apidocs/search"
REGIONAL_FACTS = {
    "Tampines": ["TAM-01", "TAM-02"],
    "Bedok": ["BED-02", "BED-03"],
    "Canberra": ["CAN-02", "CAN-03"],
    "Lakeside/Jurong": ["JUR-02", "JUR-03"],
    "Bukit Timah": ["BT-02", "BT-03"],
}
# A comparison list is not an identity mapping. Only these facts disclose the
# subject project's own count; other named projects must not inherit that count.
OWN_PROJECT_FACTS = {
    "PARKTOWN RESIDENCE": "TAM-02", "PINERY RESIDENCES": "TAM-03",
    "AURELLE OF TAMPINES": "TAM-04", "RIVELLE TAMPINES": "TAM-05",
    "VELA BAY": "BED-04", "LUCERNE GRAND": "JUR-04",
    "THE LAKEGARDEN RESIDENCES": "JUR-05", "DUNEARN HOUSE": "BT-04",
    "THE RESERVE RESIDENCES": "BT-05",
}


def norm(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub("[^A-Z0-9]", "", value.upper())


def clean(value):
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return None
    return str(value).strip() or None


def sourced(value, url, as_of=None, evidence_class="primary-source fact", **extra):
    return {"value": value, "source_url": url, "source_as_of": as_of,
            "retrieved": RESEARCH_DATE, "evidence_class": evidence_class, **extra}


def distance_m(lat1, lon1, lat2, lon2):
    a, b = math.radians(lat1), math.radians(lat2)
    dl, dn = b - a, math.radians(lon2 - lon1)
    return 12_742_000 * math.asin(min(1.0, math.sqrt(
        math.sin(dl / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dn / 2) ** 2)))


def matched_locations(frame):
    result = {}
    valid = frame.loc[frame.match_status.eq("matched")].copy()
    valid["key"] = valid.project_name.map(norm)
    for key, rows in valid.groupby("key", sort=True):
        lat, lon = pd.to_numeric(rows.lat), pd.to_numeric(rows.lon)
        if not (lat.between(1.1, 1.6).all() and lon.between(103.5, 104.2).all()):
            continue
        centre = (float(lat.median()), float(lon.median()))
        spread = max(distance_m(*centre, float(x.lat), float(x.lon)) for x in rows.itertuples())
        if spread > 500:
            continue
        result[key] = {
            "lat": centre[0], "lon": centre[1], "source_url": ONEMAP_SOURCE,
            "source_as_of": None, "retrieved": None,
            "source_snapshot": "data/outputs/private_project_locations.csv",
            "basis": "OneMap matched project point; median point when multiple matched rows exist",
            "date_limit": "The input does not record the OneMap retrieval date; it is not labelled freshly geocoded.",
            "point_count": len(rows), "maximum_point_spread_m": round(spread, 1),
            "source_project_names": sorted(set(rows.project_name)),
            "addresses": sorted({str(v).strip() for v in rows.onemap_address if clean(v)}),
            "streets": sorted({str(v).strip() for v in rows.onemap_road if clean(v)}),
        }
    return result


def registry_source(registry, key):
    source = registry["sources"][key]
    return {
        "title": source["title"],
        "source_url": source.get("url") or source.get("download_url") or source.get("dataset_url"),
        "source_as_of": source.get("published_as_of") or source.get("accessed_as_of"),
        "retrieved": None,
        "basis": "Existing repository official-source snapshot; not a fresh download",
    }


def nearest_rail(location, stations, registry, mrt_only=False):
    if location is None:
        return None
    candidates = stations.loc[pd.to_numeric(stations.operational).eq(1)].copy()
    if mrt_only:
        candidates = candidates.loc[~candidates.line.str.contains("LRT", case=False)]
    # Published source identifiers must resolve; no unsupported point is used.
    candidates = candidates.loc[
        candidates.geometry_source.isin(registry["sources"])
        & candidates.network_status_source.isin(registry["sources"])
    ]
    if candidates.empty:
        return None
    candidates["distance"] = [
        distance_m(location["lat"], location["lon"], float(x.lat), float(x.lon))
        for x in candidates.itertuples()
    ]
    station = candidates.sort_values(["distance", "name", "stn_code"]).iloc[0]
    memberships = candidates.loc[candidates.name.eq(station["name"])]
    return {
        "name": station["name"], "codes": sorted(set(memberships.stn_code)),
        "lines": sorted(set(memberships.line)),
        "mode": "LRT" if "LRT" in station.line else "MRT",
        "status": "open in the station snapshot", "station_status_as_of": clean(station.status_as_of),
        "straight_line_metres": int(round(float(station.distance) / 10) * 10),
        "distance_basis": "Haversine distance from a matched project representative point to a derived station representative point; rounded to 10m",
        "limitation": "Not a walking route, gate-to-entrance distance or travel-time claim. Station status is dated to the supplied snapshot.",
        "station_geometry_basis": station.geometry_basis,
        "station_sources": [registry_source(registry, station.geometry_source),
                            registry_source(registry, station.network_status_source)],
        "location_source": {k: location[k] for k in ["source_url", "source_as_of", "source_snapshot", "date_limit"]},
    }


def context_for(name, region, context):
    # Scope CSVs preserve display spacing ("Lakeside / Jurong"), while the
    # research context uses "Lakeside/Jurong". Match identities, not typography.
    region_entry = next((r for r in context["regions"] if norm(r["region"]) == norm(region)), None)
    if region_entry is None:
        return []
    own_id = OWN_PROJECT_FACTS.get(name)
    regional_ids = REGIONAL_FACTS.get(region_entry["region"], [])
    selected = []
    for fact in region_entry["facts"]:
        direct = fact["id"] == own_id
        named = name in fact["named_projects"]
        regional = fact["id"] in regional_ids
        if not (direct or named or regional):
            continue
        sources = [{"title": context["sources"][key]["title"],
                    "source_url": context["sources"][key]["url"],
                    "source_as_of": context["sources"][key]["source_as_of"],
                    "retrieved": fact["retrieved"]} for key in fact["source_ids"]]
        applicability = ("Directly describes this project" if direct else
                         "Project named as a comparison or exposure to inspect" if named else
                         "Wider regional context only; project-specific exposure has not been established")
        entry = {
            "id": fact["id"], "title": fact["title"], "claim": fact["verified_claim"],
            "status": fact["status"], "sources": sources, "applicability": applicability,
            "direct_project_fact": direct,
            "limitation": "No automatic price uplift, view impact, school eligibility or walking access is assigned from this regional fact.",
            "decision_implication": fact["decision_implication"],
            "implication_evidence_class": "analyst inference; applicability must be checked for the offered unit",
        }
        if direct:
            # Keep disclosed launch dates and price guides machine-readable,
            # with the same primary sources as the direct project claim.
            for key in ["units", "units_kind", "preview_date", "scheduled_booking_date",
                        "price_evidence_class", "guide_prices"]:
                if key in fact:
                    entry[key] = fact[key]
        selected.append(entry)
    return sorted(selected, key=lambda f: (not f["direct_project_fact"], f["id"]))


def future_sites():
    """Dated official land facts, independently checked on 20 September 2026."""
    definitions = [
        ("BEDOK RISE LAND SITE", "Bedok Rise", "Bedok", False, "2025-12-02",
         "https://www.ura.gov.sg/news/media/pr25-66/", "Bellis Residential Pte. Ltd.",
         380, "https://www.ura.gov.sg/news/media/pr25-48/", "2025-09-18", 20_293.6),
        ("BAYSHORE DRIVE LAND SITE", "Bayshore Drive", "Bedok", False, "2026-07-20",
         "https://www.ura.gov.sg/news/media/pr26-55/", "Gemini Residential Pte. Ltd. and Gemini Trustee Pte. Ltd. (as trustee-manager of Gemini Mall Trust)",
         1280, "https://www.ura.gov.sg/news/media/pr26-23/", "2026-03-30", 57_460.6),
        ("NEW UPPER CHANGI ROAD LAND SITE", "New Upper Changi Road", "Bedok", False, "2026-09-04",
         "https://www.ura.gov.sg/news/media/pr26-64/", "United Venture Development (Daisy) Pte. Ltd. and CL Sapphire Pte. Ltd.",
         1010, "https://www.ura.gov.sg/news/media/pr26-38/", "2026-05-15", 30_769.0),
        ("CANBERRA DRIVE EC LAND SITE", "Canberra Drive", "Canberra", True, None,
         "https://www.hdb.gov.sg/hdb-pulse/news/2026/hdb-launches-tender-for-sale-site-at-canberra-drive", None,
         185, "https://www.hdb.gov.sg/hdb-pulse/news/2026/hdb-launches-tender-for-sale-site-at-canberra-drive", "2026-05-25", None),
    ]
    result = []
    for name, site, region, ec, awarded, url, tenderer, units, yield_url, yield_date, area in definitions:
        item = {
            "project_name": name, "site_name": site, "official_project_name": None,
            "name_basis": "Official land-site location; descriptive site identifier, not a confirmed condominium marketing name",
            "region": region, "ec_origin": ec,
            "status": sourced("Land awarded; no home-sales launch verified in this research" if awarded else
                               "Land tender open; scheduled close 1 October 2026", url, awarded or yield_date, verified=True),
            "land_award_date": sourced(awarded, url, awarded) if awarded else None,
            "successful_tenderer": sourced(tenderer, url, awarded) if tenderer else None,
            "land_tenure": sourced("99-year lease", url, awarded or yield_date),
            "site_area_sqm": sourced(area, url, awarded) if area is not None else None,
            "potential_units": sourced(units, yield_url, yield_date, kind="Official potential yield; not final licensed inventory"),
            "actual_top": None, "proposed_completion": None, "launch_date": None,
            "achieved_price_evidence": None, "rental_evidence": None,
            "buyer_limit": "An awarded or tendered site is not an executable home offer; licensed inventory, unit mix, prices and completion must be established separately.",
        }
        if name == "BEDOK RISE LAND SITE":
            item["construction_scheme_units"] = sourced(
                382, "https://isomer-user-content.by.gov.sg/338/e913f8bb-06d7-453b-8330-8f7ce707507e/free_pjt_list.pdf",
                "2026-04", kind="BCA awarded-contract description; not a final sales schedule",
                note="Five 12-storey condominium blocks in the April 2026 contract list.")
            item["identity_resolution"] = "Distinct from Vela Bay at Bayshore Walk, the Bayshore Drive site and the September 2026 New Upper Changi Road award. URA identifies a separate Bedok Rise parcel and tenderer."
            item["existing_dossier"] = "https://evancjx.github.io/housing-estate-framework/property-analysis-2026-07-30-bedok-rise-gls-future-condominium.html"
        if ec:
            item["scheduled_tender_close"] = sourced("2026-10-01", url, yield_date)
            item["ec_holding_period"] = sourced(
                "If the tender closes on the announced date, the project falls in the ten-year-MOP cohort; TOP has not occurred.",
                "https://www.hdb.gov.sg/buying-a-flat/executive-condominiums/conditions-after-buying-an-ec",
                None, evidence_class="conditional policy application to the announced tender date")
        result.append(item)
    return result


def build_profiles(batch, root=ROOT):
    batch, root = Path(batch), Path(root)
    paths = {
        "projects": batch / "projects.csv", "transactions": batch / "transactions.csv",
        "context": batch / "sourced_context.json", "regional": batch / "enrichment/regional_context.json",
        "developer": batch / "enrichment/developer_latest.csv", "batch_provenance": batch / "provenance.json",
        "locations": root / "data/outputs/private_project_locations.csv",
        "stations": root / "data/inputs/mrt_layer.csv", "station_sources": root / "data/inputs/mrt_source_registry.json",
    }
    projects = pd.read_csv(paths["projects"], keep_default_na=False)
    projects = projects.loc[projects.scope_status.eq("main")].sort_values("project_name")
    if not projects.project_name.is_unique:
        raise ValueError("Individual profile keys require unique exact project names")
    tx = pd.read_csv(paths["transactions"], keep_default_na=False)
    tx = tx.loc[tx.scope_status.eq("main")]
    raw_context = json.loads(paths["context"].read_text())
    regional = json.loads(paths["regional"].read_text())
    context = {p["project_name"]: p for key in ["projects", "upcoming_project_watchlist"] for p in raw_context.get(key, [])}
    facts = {f["id"]: f for r in regional["regions"] for f in r["facts"]}
    developer = pd.read_csv(paths["developer"], keep_default_na=False).set_index("project_name")
    if not developer.index.is_unique:
        raise ValueError("Developer snapshot contains duplicate project identities")
    source_date = json.loads(paths["batch_provenance"].read_text())["metadata"]["source_updated"]
    locations = matched_locations(pd.read_csv(paths["locations"], keep_default_na=False))
    stations = pd.read_csv(paths["stations"], keep_default_na=False)
    registry = json.loads(paths["station_sources"].read_text())
    profiles = {}
    for project in projects.itertuples():
        name = project.project_name
        records = tx.loc[tx.project_name.eq(name)]
        detail = context.get(name, {})
        location = locations.get(norm(name))
        identity = {}
        for field, column in [("streets", "street_name"), ("tenures", "tenure"), ("property_types", "property_type"), ("postal_districts", "postal_district")]:
            values = sorted({str(v).strip() for v in records[column] if clean(v)})
            identity[field] = [sourced(v, URA_TRANSACTIONS, source_date, "official transaction field",
                                      basis="Distinct values recorded in the retained URA transaction rows; not inferred from a project label") for v in values]
        identity["addresses"] = []
        if name == "LUCERNE GRAND":
            identity["streets"] = [sourced("LAKESIDE DRIVE", detail["status_source"], "2026-09-16",
                                          "developer project-location disclosure")]
        if clean(detail.get("address")):
            identity["addresses"].append(sourced(detail["address"], detail.get("geography_source") or detail.get("status_source"), detail.get("status_as_of")))
        if location:
            for address in location["addresses"]:
                identity["addresses"].append(sourced(address, ONEMAP_SOURCE, None, "matched OneMap address from existing snapshot",
                                                     retrieved=None, limitation=location["date_limit"]))
            if not identity["streets"]:
                identity["streets"] = [sourced(v, ONEMAP_SOURCE, None, "matched OneMap road from existing snapshot", retrieved=None) for v in location["streets"]]
        verified_status = bool(detail.get("development_status_verified") and clean(detail.get("development_status")))
        status = sourced(detail["development_status"] if verified_status else (clean(project.development_status) or "Completion status not independently verified"),
                         detail.get("status_source") if verified_status else (clean(project.status_source) or clean(project.scope_source)),
                         detail.get("status_as_of") if verified_status else clean(project.status_as_of),
                         "captured primary-source status" if verified_status else "unverified status / source metadata", verified=verified_status)
        top = None
        if verified_status and detail.get("actual_top"):
            top = sourced(detail["actual_top"], detail["status_source"], detail.get("status_as_of"),
                          verified=True, precision=detail.get("actual_top_precision", "as published"),
                          phases=detail.get("top_phases"), note=detail.get("note"))
        completion = detail.get("proposed_completion")
        proposed = sourced(completion["date"], completion["source"], detail.get("status_as_of"),
                           "developer expected milestone; not actual TOP", kind=completion["kind"]) if completion else None
        if name == "CANBERRA CRESCENT RESIDENCES":
            proposed = sourced(
                "2030-04-30", "https://www.canberra-crescent.com/", None,
                "developer expected milestone; not actual TOP", kind="expected vacant possession",
                expected_legal_completion="2033-04-30",
                note="Undated developer website footer; this disclosure does not verify current construction progress or an actual TOP.")
        units = None
        if name in developer.index:
            d = developer.loc[name]
            units = sourced(int(d.units_avail), URA_API, d.ref_month, "official monthly developer return",
                            kind="Total project units in the reported month; not currently available stock",
                            sold_to_date=int(d.sold_to_date), unsold_total=int(d.unsold_total),
                            launched_unsold=int(d.launched_unsold), unlaunched_units=int(d.unlaunched_units))
        elif name in OWN_PROJECT_FACTS and "units" in facts[OWN_PROJECT_FACTS[name]]:
            f = facts[OWN_PROJECT_FACTS[name]]
            s = regional["sources"][f["source_ids"][0]]
            units = sourced(f["units"], s["url"], s["source_as_of"], kind=f["units_kind"])
        missing = []
        for absent, message in [
            (not identity["streets"], "No verified street in the captured URA or matched OneMap records"),
            (not identity["addresses"], "No verified postal/block address in the supplied profile sources"),
            (not identity["tenures"], "No recorded tenure in the retained official transactions"),
            (not verified_status, "Current construction/completion status not independently verified"),
            (top is None, "Actual TOP not verified; transaction sale type is not a TOP certificate"),
            (units is None, "No official project unit total in the supplied source snapshots"),
            (location is None, "No unambiguous matched project point; no station distance calculated"),
        ]:
            if absent:
                missing.append(message)
        profiles[name] = {
            "project_name": name, "region": project.region, "subregion": project.subregion,
            "ec_origin": bool(project.ec_origin), "identity": identity,
            "scope_source": sourced(project.region, clean(project.scope_source), None,
                                    "project scope metadata; not a statutory address or TOP source"),
            "status": status, "actual_top": top, "proposed_completion": proposed,
            "unit_count": units, "location": location,
            "nearest_rail": nearest_rail(location, stations, registry),
            "nearest_mrt": nearest_rail(location, stations, registry, mrt_only=True),
            "context_facts": context_for(name, project.region, regional),
            "source_note": detail.get("note") or clean(project.coverage_note),
            "missing_evidence": missing,
        }
    future = future_sites()
    regions_with_facts = {norm(r["region"]) for r in regional["regions"] if r["facts"]}
    missing_context = [name for name, p in profiles.items()
                       if norm(p["region"]) in regions_with_facts and not p["context_facts"]]
    if missing_context:
        raise ValueError("Regional context unexpectedly absent for: " + ", ".join(missing_context))
    if any(p["project_name"] in profiles for p in future):
        raise ValueError("A future land site duplicates an existing exact project profile")
    return {
        "schema_version": 1, "research_date": RESEARCH_DATE,
        "scope": "Every main-scope identified project, plus separately named official future land sites; not a certified census of all physical developments",
        "date_rule": "source_as_of is null where a publication/capture date is absent; neither file modification time nor build time substitutes for it",
        "input_provenance": [{"role": key, "path": str(path.relative_to(root)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for key, path in paths.items()],
        "summary": {
            "profiles": len(profiles), "future_sites": len(future),
            "matched_project_points": sum(p["location"] is not None for p in profiles.values()),
            "nearest_rail_computed": sum(p["nearest_rail"] is not None for p in profiles.values()),
            "verified_status": sum(p["status"]["verified"] for p in profiles.values()),
            "verified_actual_top": sum(p["actual_top"] is not None for p in profiles.values()),
            "official_unit_totals": sum(p["unit_count"] is not None for p in profiles.values()),
            "profiles_with_context": sum(bool(p["context_facts"]) for p in profiles.values()),
            "context_coverage_by_region": {
                region: sum(p["region"] == region and bool(p["context_facts"]) for p in profiles.values())
                for region in sorted({p["region"] for p in profiles.values()})
            },
        },
        "profiles": profiles, "future_sites": future,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, default=ROOT / "data/runs/regional-property-analysis/2026-09-20")
    args = parser.parse_args()
    payload = build_profiles(args.batch.resolve())
    destination = args.batch / "enrichment/individual_project_profiles.json"
    destination.parent.mkdir(exist_ok=True, parents=True)
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    print(json.dumps(payload["summary"], indent=2))


if __name__ == "__main__":
    main()
