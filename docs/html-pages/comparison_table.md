# Estate Comparison Table

> Compares Singapore estates across the repository’s separate Provision, persona-relative Liveability, tenure-segmented Value, employment, risk, and life-path views.

## Purpose

Use [comparison_table.html](../../comparison_table.html) as the headline cross-model estate explorer. It is designed to expose the framework’s component views side by side, not to produce one universal liveability ranking.

## Data & Scope

The [generator](../../models/gen_comparison_html.py) joins [master_output.csv](../../data/outputs/master_output.csv), Provision noise scores, employment outputs for T0/T5/T15, and [life_paths.csv](../../data/outputs/life_paths.csv). The committed page reports 35 estates and was generated on 25 July 2026. Its model meanings come from the active [Provision specification](../../frameworks/1-provision-framework.md) and [Liveability specification](../../frameworks/2-liveability-matrix.md).

## Comparison Framework

- **Identity:** estate and archetype.
- **Provision:** T0 disruption multiplier `D`, objective band, and score.
- **Liveability:** Young Family, Single Professional, Retiree, and Lifestyle bands at T0; Lifestyle T0→T5→T15 sequence and direction.
- **Gap:** each persona’s T0 Liveability score minus Provision.
- **Value:** HDB band/multiplier and separate private band/multiplier/sample count.
- **Employment and risk:** T0/T5/T15 employment, HDB lease band, and 1–5 noise-distance score.
- **Life path and flags:** largest/smallest modeled path changes and interpretation warnings.

## Controls & Outputs

Filter by archetype A–G, search by estate name, or click any column heading to sort. Hover or focus dotted labels for field definitions. Bands, gaps, multipliers, trajectories, and flags remain visible in one horizontally scrollable table.

## Interpretation Limits

Provision is an objective supply-side comparison. Liveability is person-relative and non-comparable across personas or horizons. Do not combine them into a single rank. HDB and private Value are different tenure universes and must not be blended. Multipliers are model-relative pricing signals, not forecasts; gaps describe persona fit, not investment returns.

## Rebuild

From the repository root:

```bash
python3 models/gen_comparison_html.py
```

Run `make pipeline` first when underlying model inputs or outputs have changed, then review the generated HTML and CSV diffs.
