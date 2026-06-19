---
name: factor-audit
description: Run a structured deep-research audit to find candidate NEW components for the Singapore housing-estate Provision framework, or candidate upgrades to currently-JUDGED components. Use this whenever the user asks about "other factors", "what's missing from provision", "factor audit", "new components", "audit the framework", "what else should we measure", "research more factors", or any prompt about extending the 15-component Provision model. Even if the user just says "what are we not capturing", this is the skill. It launches three parallel research sweeps (academic frameworks, Singapore open data, real buyer priorities), enforces the framework's principled rejections, and produces a categorised proposal markdown — it does NOT auto-edit framework code.
---

# Factor Audit

A research workflow for proposing new components — or upgrades to currently-JUDGED components — for the Singapore housing-estate **Provision** framework (Document 1). The output is always a proposal the user reviews; this skill never edits the framework code or weights directly.

## When this skill applies

Run this skill on prompts like:

- "What other factors could we measure?"
- "Deep research on missing factors"
- "Audit the framework"
- "What's missing from provision?"
- "Should we add X as a component?" (use it to evaluate a single candidate against the framework's principles, even when only one factor is named)
- "Are there datasets we haven't ingested?"

If the user asks about **Liveability** (persona-relative, demand-side) factors instead, this skill still applies, but flag the distinction clearly in the output — Liveability candidates are NOT scored on the same principles as Provision candidates.

## Pre-flight: load the framework's current state

Before any research, read these so the proposal is grounded in what already exists:

1. `CLAUDE.md` (repo root) — invariants, the Provision/Liveability split, the 15 current components.
2. `frameworks/1-provision-framework.md` — Provision math, weights, archetype tags, the D multiplier, the C veto rules, and the explicit rejection appendix.
3. `frameworks/2-liveability-matrix.md` — the demand-side split. Anything that belongs HERE must not be proposed as a Provision component.
4. `models/provision_model.py` (top of file) — the `W` weight dict and the `PROVENANCE` tag dict. This is the actual code-level source of truth for which 15 components exist and their provenance.

Skim, don't deep-read — pull the component list, the principled rejections, and the noise-floor language.

## The three principled axioms (non-negotiable)

These are baked into the framework. A proposed factor that violates any of them is auto-rejected — flag it in the rejection section of the report, don't silently include it.

1. **Supply-side only.** Provision measures *what is here*, not *what it's like for me*. Anything that is fundamentally a person-place relationship (commute fit, "distance to my parents", lifestyle match) belongs in the Liveability matrix, not Provision.
2. **No class/income laundering.** A "social mix" score launders demographic sorting under a neutral label. Affluent-address proxies, prestige scores, "atas" perception, and similar status signals are permanently excluded. Stewardship metrics (visible upkeep, lighting, neglect, vandalism) are acceptable in principle but only if observably measured, not inferred from who lives there.
3. **Honest provenance.** Every component must declare MEASURED / PARTLY_MEASURED / JUDGED. A factor that *sounds* objective but in practice requires analyst opinion is JUDGED — say so. Don't propose factors whose "measurement" is reading a website or a survey vibe.

Two further framework guardrails to respect:

- **±0.3 cross-grader noise floor.** A factor that won't shift estate scores by more than ~0.3 across reasonable analyst variation is not worth adding — most mature SG estates already saturate the existing 15.
- **D-multiplier is losses-only.** Positive additions / pipeline items go in `mom` (S7) or Liveability T5, never as a "future bonus" multiplier. If a proposed factor is forward-looking, route it through momentum, not as a new Provision component.

Detail and worked rationale for each axiom: see `references/principled-rejections.md`.

## The three research sweeps

Launch these as **parallel Agent calls in one message** (general-purpose subagent). Don't run them in series — the value of this skill is wall-clock speed and independent perspectives.

### Sweep A — international neighborhood-quality frameworks

Prompt the agent to survey academic and policy frameworks and extract dimensions NOT already in the 15 components. Pre-curated source list lives in `references/source-catalog.md` (section A) — paste it into the agent prompt so the agent doesn't have to rediscover them.

Expected return: factor name, source framework(s), why it might matter for SG specifically, provenance estimate, honest discriminating-power assessment.

### Sweep B — Singapore-specific open data not yet ingested

Prompt the agent to scan data.gov.sg, OneMap themes, LTA DataMall, NEA, NParks, URA, MSF, SingStat for layers that could either (i) feed a brand-new component or (ii) upgrade a currently-JUDGED component (`mom`, `hawker`) or PARTLY_MEASURED (`dens`, `env`) to MEASURED. Source list in `references/source-catalog.md` (section B).

Expected return: dataset name + ID/URL, what component it enables, API access method, update cadence, coverage caveats.

### Sweep C — real buyer priorities

Prompt the agent to survey PropertyGuru / 99.co / Stacked Homes / EdgeProp / IPS surveys for what real SG home-buyers prioritise that ISN'T in the 15 components. Source list in `references/source-catalog.md` (section C).

For each cited factor, the agent must explicitly tag: **place-property (Provision-side)** OR **person-relationship (Liveability-side)** — buyers conflate the two and the skill must un-conflate them.

The detailed agent prompts (copy-paste templates) for all three sweeps are in `references/agent-prompts.md`.

## Synthesis: the proposal report

After all three sweeps return, synthesise into ONE markdown report. Save it to:

```
factor_audit_reports/<YYYY-MM-DD>.md
```

(create the directory if it doesn't exist; under the repo root).

Use this exact section structure — downstream tooling and future audits depend on it:

```markdown
# Factor Audit — <YYYY-MM-DD>

## 1. Critical gaps (propose adding)
Factors where all three sweeps converge, that pass the three axioms, and where a Singapore open-data feed exists. These are the ones worth the user's attention first.

For each, give:
- **Name**: short identifier (e.g., `air_quality`)
- **One-line description**
- **Provenance estimate**: MEASURED / PARTLY_MEASURED / JUDGED
- **Proposed weight bucket**: rough fraction (0.01–0.10) with rationale relative to existing weights
- **SG dataset(s)**: dataset ID/URL + update cadence
- **Discriminating power**: will it move estate scores beyond ±0.3? Evidence.
- **Cross-references**: which sweep(s) found it, which existing component it borders

## 2. JUDGED → MEASURED upgrades
Currently-JUDGED or PARTLY_MEASURED components that a newly-identified SG dataset could promote. Same fields as §1, plus the current component name being upgraded.

## 3. Nice-to-have (lower priority)
Factors that pass the axioms but either lack a clean dataset, won't discriminate well, or duplicate existing coverage. List with one-line rationale each — don't expand unless the user asks.

## 4. Principled rejections
Factors that came up in research but violate one of the three axioms. ALWAYS include this section even if empty — it documents what was considered and why it was excluded, which prevents the next audit from re-litigating the same factors.

For each: factor, which axiom it violates, source that proposed it.

## 5. Liveability-side candidates (NOT Provision)
Person-relative factors that surfaced but belong in the persona matrix, not Provision. Brief list with which persona they'd most affect.

## 6. Research provenance
- Sweep A sources cited: [list]
- Sweep B sources cited: [list]
- Sweep C sources cited: [list]
- Date of research, anything that should be re-verified after N months
```

## What this skill does NOT do

- It does NOT modify `provision_model.py`, weights, or any framework markdown. The user reviews the proposal first.
- It does NOT invent dataset URLs. If a sweep agent can't verify a dataset exists, the proposal must say "unverified" rather than fabricate an ID.
- It does NOT rank candidates against each other with false precision. Critical gaps go in §1 unordered (or grouped by sweep-convergence), not as a 1-2-3 stack ranking.
- It does NOT re-run if the user just wants a quick sanity check on a single named factor. For that, evaluate the named factor against the three axioms inline and skip the parallel sweeps.

## Why this skill exists

Re-deriving the framework's invariants in every research session burns context and risks proposing factors the framework already rejects (the "social mix" trap, the demand/supply confusion, etc.). This skill is a memory of the framework's principles plus a pre-curated source catalogue so each audit starts from where the last one ended, not from scratch.
