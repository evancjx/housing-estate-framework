# Principled rejections — the framework's standing exclusions

These are not stylistic preferences. They are *constitutional* — encoded in `frameworks/1-provision-framework.md` Appendix C and tested through v0.1–v0.9 iterations. A new component proposal that violates any of them is rejected, and the rejection is *documented in the audit report*, not silently dropped.

The audit must list these factors in section §4 of the report so future audits do not re-litigate the same rejections.

---

## Axiom 1: Provision is supply-side. Person-relationships go in Liveability.

**Rule.** A Provision component must measure a property of *the place*. The moment a factor requires "for whom" to interpret, it is Liveability, not Provision.

**Worked examples (auto-reject as Provision; route to Liveability matrix instead):**

- *Distance to parents / in-laws.* Cannot be answered without the buyer's existing address. → Liveability persona delta (especially YoungFam, Retiree).
- *Commute to my job.* Already captured anchor-relative in `employment_model.py` and Doc 2 §P9.4 — a single estate has different connectivity scores per job anchor. → Liveability.
- *School-choice fit.* MOE policy lets a parent pick within distance bands; the same MOE-school list scores differently per child's age and ECA preference. → Liveability YoungFam.
- *Mature-vs-new "feel".* Resolves to amenity-completeness + block age + tree canopy, all of which are place properties — but the *feel* itself is a person-place report. Component the underlying place attributes; do not score "feel".
- *"Atas" perception / address prestige.* This is a *report of status by an observer*, not a place attribute. See Axiom 2.

**The boundary test.** If two people standing at the same estate's centre point can disagree on the answer with neither being wrong, it's Liveability.

---

## Axiom 2: No class/income laundering. No status proxies.

**Rule.** A "social mix" score launders demographic sorting under a neutral label. Any factor that ends up scoring "more affluent residents = better estate" is rejected, regardless of how it's framed.

**Worked examples (auto-reject; flag in §4):**

- *Social-mix / diversity index.* The named-and-rejected canonical case. Permanently excluded.
- *Median household income by planning area.* Same factor, different name.
- *Address prestige / "good postal code" / D9-D10-D11 premium.* Buyer-cited but is verbatim status-laundering. Reject.
- *Foreign-worker dormitory proximity (as a negative).* Buyers cite "crowding/safety"; the operative signal is class-coded. Reject as Provision input. (If actual environmental noise or specific safety incidents exist, those measure as *noise* and *crime-event* respectively — measure those directly, not "dormitories nearby".)
- *Private-vs-HDB ratio in a planning area.* Same trap, dressed as "tenure mix".
- *School ranking (PSLE T-score cohort, IB percentages).* MOE explicitly bans publishing school rankings. Buyer-cited but the framework respects the policy.

**The acceptable substitute.** *Stewardship* — observable upkeep, lighting, vandalism, void-deck maintenance, lift-breakdown frequency. These measure what the *place* gets, not who *lives* there. Stewardship is admissible in principle but requires actual measurement (HDB Town Council KPIs, SPF graffiti reports), not analyst impression.

**The discrimination test.** If the factor's variance across SG estates correlates >0.7 with median income of residents, it's almost certainly laundering. Demand a separate signal-vs-noise argument.

---

## Axiom 3: Honest provenance. JUDGED is fine; pretending-MEASURED is not.

**Rule.** Every component carries one of three provenance tags:

- **MEASURED** — computed from a public, joinable dataset with a clean spatial join. Reproducible by another analyst from the same inputs.
- **PARTLY_MEASURED** — has a real data feed for *part* of the construct, but a substantive piece still depends on analyst judgement. Example: `env` measures temperature and flood from data; shade/noise/construction remain judgement.
- **JUDGED** — admittedly opinion. Used only when no dataset exists *and* the construct is too important to drop. Examples in v1.1: `mom`, `hawker`.

**Rejection trigger.** A proposed factor whose "measurement" is:

- "scrape a website and read it" → JUDGED, not MEASURED
- "use a CV model on Street View images" → JUDGED unless the model is open, versioned, and class-laundering-audited; otherwise PARTLY_MEASURED at best
- "ask the analyst to score 1–5 based on impressions" → JUDGED — declare it; don't dress it as MEASURED
- "average of TripAdvisor / Google reviews" → JUDGED + a review-bias laundering risk

**Why this matters.** The framework reports BANDS, not decimals, partly because too many components are JUDGED and the noise is real. Adding a MEASURED-looking-but-actually-JUDGED component falsely tightens the band — the same construct-validity failure that drove the v0.8 → v0.9 rewrite.

---

## Secondary guardrails (not axioms, but binding)

### G1: ±0.3 cross-grader noise floor

A factor that won't move estate scores by more than ~0.3 across reasonable analyst variation is not worth adding. Most mature SG estates have crossed the provision threshold and saturate the existing 15 components — adding another saturating component costs complexity without gaining discrimination.

**The discrimination probe.** For a proposed factor, name three SG estates that would visibly differ on it and three that would not. If you can't fill both lists, the factor is either saturated or universally low — neither merits inclusion.

### G2: D-multiplier holds losses only

The D multiplier in `provision_model.py` and `liveability_model.py` is reserved for *losses/disruptions*, not future-positive items. A forward-looking factor (e.g., "planned MRT line") must route through:

- `mom` (S7 momentum) for the Provision side, or
- Liveability T5/T15 horizons via `pipeline_data.json`

Do not propose a "future-bonus multiplier" — that was the v0.2–v0.4 double-count the framework explicitly fixed.

### G3: Cost is Value, not Provision

"Affordability", "resale potential", "lease decay", "en-bloc upside" are all Value-side. They are handled by `value_model.py` (price residual) and `lease_risk_model.py`. Reject them as Provision components; mention them in §5 (Liveability/Value-side candidates) of the audit report so the user sees that we considered and routed them, not that we missed them.

### G4: Unit-level attributes are out of scope

The framework scores **estates** (planning-area / HDB-town granularity). Unit-level attributes — orientation, floor height, view, facing, exact bedroom mix — are out of scope. Mention them in §5 if buyers cited them, but they do not become Provision components.

---

## How to use this file during the audit

1. Read this file *before* synthesising sweep output.
2. For each candidate factor surfaced by the three sweeps, walk it through Axioms 1–3 + Guardrails G1–G4 in order. The first violation determines the report section:
   - Violates A1 → §5 (Liveability candidate)
   - Violates A2 → §4 (Principled rejection — class-laundering)
   - Violates A3 → §1/§2 with honest provenance tag, OR §4 if no honest version exists
   - Violates G1 → §3 (Nice-to-have) at best, often §4
   - Violates G2 → reroute to `mom` / pipeline_data.json proposal
   - Violates G3 → §5 (Value-side, not Provision)
   - Violates G4 → §5 (out-of-scope) or drop entirely
3. Section §4 of the report MUST list every rejected candidate with the violated axiom and the source that proposed it. This is the audit's *negative space* and is just as important as the positive proposals.
