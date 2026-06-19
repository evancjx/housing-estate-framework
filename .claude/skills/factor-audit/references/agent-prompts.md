# Agent-prompt templates for the three sweeps

Copy-paste these into the Agent tool (`subagent_type: general-purpose`). Send all three in a single message so they run in parallel.

The templates reference the source catalog. Paste the relevant `source-catalog.md` section *inline* into each agent prompt — subagents don't share your filesystem context cheaply, and giving them the curated list saves them rediscovery.

If the user has indicated WebSearch / WebFetch are unavailable in the environment, note that explicitly in each agent prompt so they fall back to training-data knowledge gracefully and tag their findings as "desk synthesis — needs live verification" rather than hallucinating dataset IDs. The skill's synthesis must then surface that caveat in §6 of the report.

---

## Sweep A — International / academic frameworks

```
You are researching for a Singapore-housing-estate scoring framework that I'm extending. The framework already measures 15 supply-side ("Provision") components per estate:

  conn, amen, green, sch, dens, hlth, mom, infra, env,
  childcare, community, sport, flood, hawker, noise

(Full definitions and weights in frameworks/1-provision-framework.md.)

Principled exclusions the framework enforces (do not propose factors that violate these):
- NO "social mix" component — flagged as class/income laundering
- Provision is supply-side; person-place relationships belong in the Liveability matrix, not Provision
- Components must declare honest provenance: MEASURED / PARTLY_MEASURED / JUDGED
- ±0.3 cross-grader noise floor — factors that won't shift estate scores by more than that are not worth adding

Your task: Survey these external neighborhood-quality / urban-liveability frameworks for dimensions the SG framework currently does NOT capture. Focus on supply-side, place-as-property factors that could become Provision components.

[Paste source-catalog.md section A here verbatim — Mercer, EIU, OECD How's Life regional, UK IMD, SEIFA / AURIN, CDC SVI, EPA EJScreen, MIT Place Pulse, Ewing-Handy, WHO Healthy Cities Phase VII, 15-minute city literature.]

If WebSearch/WebFetch are denied, fall back to your training-data knowledge of these frameworks' published indicator structures. Tag findings clearly as "desk synthesis" so the synthesis step knows to flag the provenance.

Deliverable (under 800 words): a categorised list of MISSING factors that pass the framework's principles, each with:
- Factor name + brief description
- Source framework(s) where it appears
- Why it might matter for Singapore specifically
- Provenance estimate (MEASURED / PARTLY_MEASURED / JUDGED)
- Honest discriminating-power assessment (will it actually differentiate SG estates, or saturate?)

Also list factors you considered and rejected because they hit one of the framework's principled exclusions — that negative space matters as much as the positive proposals. Skip factors the framework already covers.
```

---

## Sweep B — Singapore open data sources

```
You are researching Singapore-specific OPEN DATA sources that could feed new components into a housing-estate scoring framework, or upgrade currently-JUDGED ones to MEASURED.

Already ingested layers (do NOT re-suggest):
[Paste source-catalog.md section B "Already ingested" block here.]

Currently-JUDGED components that need MEASURED upgrades:
  mom (announced pipeline), hawker (reputation/fame)

Currently-PARTLY_MEASURED components that could move to MEASURED:
  dens (dwelling density yes; "feel" no), env (temp/flood yes; shade/noise/construction no)

Your task: identify SG-specific datasets that would unlock measurable new Provision components, or upgrade the JUDGED/PARTLY_MEASURED ones. Prioritise free-access feeds (data.gov.sg poll-download, OneMap themes with free token, LTA DataMall with free AccountKey) over gated ones.

Candidate sources to investigate:
[Paste source-catalog.md section B "NOT-yet-ingested" table here.]

If WebSearch/WebFetch are denied, fall back to training knowledge of the SG open-data catalogue. Tag dataset IDs you cannot freshly verify with "[verify]" so the synthesis step knows to re-check them before any code is written.

Deliverable (under 700 words): for each dataset, give:
- Dataset name + provider + URL or ID
- What Provision component(s) it could feed or upgrade
- API access method (data.gov.sg poll-download / OneMap theme / LTA token / manual)
- Update cadence
- Honest caveat (coverage gaps, lat/lon availability, licence)

Prioritise: (1) JUDGED → MEASURED upgrades, (2) genuinely new factors not in the 15 components, (3) datasets reachable without paid keys.
```

---

## Sweep C — Singapore home-buyer priorities

```
You are researching what Singapore home-buyers actually prioritise when choosing an estate / HDB town / private project. The framework already measures 15 supply-side components (conn, amen, green, sch, dens, hlth, mom, infra, env, childcare, community, sport, flood, hawker, noise).

What I want from you: factors REAL buyers (HDB and private) cite that ISN'T in those 15 components — and for each, an explicit classification.

Sources to survey:
[Paste source-catalog.md section C here — PropertyGuru CSS, 99.co, Stacked Homes, EdgeProp, ERA/OrangeTee/Huttons reports, IPS surveys, CLC reports, r/singapore housing threads.]

For EACH commonly-cited factor not in the 15 components, classify as ONE of:

  (P) Provision-side place attribute  → could become a Provision component
  (L) Liveability-side person-relationship  → belongs in the persona × horizon matrix, NOT Provision
  (V) Value-side cost factor  → handled by value_model.py / lease_risk_model.py, NOT Provision
  (U) Unit-level attribute  → out of estate-scoring scope entirely
  (R) Axiom-2 violation — social-mix / status-laundering  → principled rejection

The framework's most common Axiom-2 traps to watch for (flag explicitly):
- "atas" perception / address prestige / "good postal code"
- Foreign-worker dormitory proximity framed as safety/crowding concern
- Tenure-mix ratios (private-vs-HDB share)
- School ranking (MOE bans publishing these; buyers cite proxies)

If WebSearch/WebFetch are denied, fall back to training knowledge of these publications and r/singapore housing threads. Tag synthesis-only findings clearly.

Deliverable (under 600 words): a ranked list (by buyer-citation frequency) of factors NOT in the 15 components, each with: name, buyer language, classification letter (P/L/V/U/R), brief rationale. Be specific — "buyers care about flight noise" is useful; "buyers care about environment" is not.
```

---

## After the sweeps return

1. Read each agent's output.
2. Walk every candidate factor through Axioms 1–3 + Guardrails G1–G4 from `principled-rejections.md`. The first violation determines the report section.
3. Synthesise into the report template (see SKILL.md §"The proposal report").
4. Save to `factor_audit_reports/<YYYY-MM-DD>.md` (create the directory if needed).
5. Cite sources. If WebSearch was denied during sweeps, note that in §6 and flag the report as "desk synthesis — fresh verification needed on dataset IDs and weight-shift estimates".
