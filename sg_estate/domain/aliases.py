"""Shared estate-name alias maps — single source of truth for all domains.

TWO DISTINCT concepts. Do NOT merge them:
  PIPELINE_NAME_ALIAS — pipeline/research benefiting-estate names -> canonical estate.
  ESTATE_TOWN_ALIAS   — estate -> HDB town, for joining resale transactions.
"""

PIPELINE_NAME_ALIAS = {
    "BIDADARI":       "WOODLEIGH",
    "MARSILING":      "WOODLANDS",
    "KAKI BUKIT":     "BEDOK",
    "EAST COAST":     "MARINE PARADE",
    "BOON LAY":       "JURONG WEST",    # town centre of Jurong West (momentum had JURONG EAST — wrong)
    "TAMAN JURONG":   "JURONG WEST",    # physically in Jurong West planning area
    "BUONA VISTA":    "QUEENSTOWN",     # Buona Vista is in Queenstown planning area (liveability had HOLLAND VILLAGE — wrong)
    "NOVENA":         "TOA PAYOH",
    "WEST COAST":     "CLEMENTI",
    "TAMPINES NORTH": "TAMPINES",
    "YEW TEE":        "CHOA CHU KANG",
    # JURONG WEST, KALLANG: now real estates in estates.csv — map to themselves (no stale fold).
}

ESTATE_TOWN_ALIAS = {
    "CANBERRA":        "SEMBAWANG",
    "BOON KENG":       "KALLANG/WHAMPOA",
    "KALLANG":         "KALLANG/WHAMPOA",
    "WOODLEIGH":       "TOA PAYOH",
    "DOVER":           "QUEENSTOWN",
    "TAMPINES WEST":   "TAMPINES",
    "TAMPINES EAST":   "TAMPINES",
    "LENTOR":          "ANG MO KIO",      # indicative proxy; lease_risk overrides via MANUAL_OVERRIDES
    "HOLLAND VILLAGE": "QUEENSTOWN",      # private-dominant; HDB proxy only
}

# Private-dominant estates must NOT borrow an HDB-resale residual.
PRIVATE_DOMINANT_PROXIES = {"HOLLAND VILLAGE", "LENTOR"}

# URA project name -> EdgeProp project name, both in build_private_bedrooms
# normalise_project_name form, keyed with the zero-padded postal district.
# ONLY for cases irreducible by normalisation (combined pages, renames).
# Used by build_private_bedrooms.py.
URA_EDGEPROP_PROJECT_ALIAS = {
    # ("<URA name_norm>", "<district>"): "<EdgeProp name_norm>",
    # URA annotates the en-bloc'd development; EdgeProp calls the same page "(OLD)".
    ("CHUAN PARK DEMOLISHED", "19"): "CHUAN PARK OLD",
    # SAINT vs ST — a token rule would wrongly merge EdgeProp's separate
    # ST THOMAS COURT and SAINT THOMAS COURT projects, so alias just this one.
    ("SKYLINE 360 AT SAINT THOMAS WALK", "09"): "SKYLINE 360 AT ST THOMAS WALK",
    # Spacing variant: URA MERAWOODS = EdgeProp "MERA WOODS" (Hillview Ave, D23).
    ("MERAWOODS", "23"): "MERA WOODS",
}


def canonicalise_pipeline_name(name):
    """Pipeline/research estate name -> canonical estate."""
    return PIPELINE_NAME_ALIAS.get(str(name).strip().upper(), str(name).strip().upper())


def estate_to_town(estate):
    """Estate -> HDB town for transaction joins."""
    return ESTATE_TOWN_ALIAS.get(str(estate).strip().upper(), str(estate).strip().upper())
