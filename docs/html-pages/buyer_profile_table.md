# Buyer Profile Evaluation

> Explores profile-local estate and tenure choices after buyer constraints and preferences are applied to existing framework outputs.

## Purpose

Use [buyer_profile_table.html](../../buyer_profile_table.html) to inspect which estate/tenure combinations remain eligible for each configured household profile and how those choices rank for that profile.

## Data & Scope

The page is rendered from [buyer_profile_output.csv](../../data/outputs/buyer_profile_output.csv) by [gen_buyer_profile_html.py](../../models/gen_buyer_profile_html.py). That CSV is produced by the [buyer-profile model](../../models/buyer_profile_model.py) from `master_output.csv`, optional life paths, and optional condo/landed segment Value. The committed page was generated on 10 July 2026.

## Comparison Framework

The model applies hard filters before scoring. Filters may constrain tenure, archetype, measured-only rows, minimum Liveability/Value/Employment/Lease/Provision bands, Value sample depth or basis, and horizon-specific disruption.

Eligible choices are then scored with profile-supplied soft weights over Liveability, Value, Employment, HDB Lease, Provision, and an optional life path. Defaults are 45%, 25%, 10%, 10%, 5%, and 5%, respectively; unavailable components are handled through disclosed weight coverage. The table shows rank, score, component bands, Value basis, and filter reasons.

## Controls & Outputs

Filter by profile, estate text, tenure segment, eligibility status, or minimum profile score. Reset restores the full view. Summary cards report each profile’s eligible count and top estate/segment; table rows are ordered with eligible, higher-scoring choices first.

## Interpretation Limits

Ranks remain local to one profile and its requested tenure choices. They are not a universal estate ranking and should not be compared across profiles. This wrapper does not change Provision, Liveability, or Value: Provision remains objective, Liveability remains persona/horizon-relative, and Value remains tenure-segmented. A filtered row records a buy/no-buy rule, not a poor universal score.

## Rebuild

Generate the profile output, then the page:

```bash
python3 models/buyer_profile_model.py \
  --profile data/inputs/buyer_profiles.example.json \
  --master data/outputs/master_output.csv \
  --life-paths data/outputs/life_paths.csv \
  --out data/outputs/buyer_profile_output.csv
python3 models/gen_buyer_profile_html.py
```

Use the actual reviewed profile JSON when making buyer-specific decisions.
