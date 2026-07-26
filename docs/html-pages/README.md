# HTML Report Documentation

> One guide per published HTML report, covering its evidence contract, comparison method, controls, limits, and rebuild path.

The root HTML files are generated research artifacts. Their guides describe how to use them and
which comparisons they support; [`site/reports.json`](../../site/reports.json) remains the
machine-readable publication catalog. The active model specifications remain
[`frameworks/1-provision-framework.md`](../../frameworks/1-provision-framework.md) and
[`frameworks/2-liveability-matrix.md`](../../frameworks/2-liveability-matrix.md).

## Framework Safeguards

- Provision is objective supply; Liveability is persona-relative. Never combine them into one rank.
- HDB and private Value are separate tenure segments and are not compared across universes.
- Project transactions, access, schools, and tenure are evidence about a project. Estate framework
  values are disclosed context, not project, block, stack, or unit scores.
- Achieved-sale medians are sensitive to period and unit mix. They are not repeat-unit appreciation
  unless a report has separately verified exact physical-unit evidence.

## Report Guides

### Research hub

| Page | Guide |
|---|---|
| [Estate research hub](../../index.html) | [Navigation framework](index.md) |

### Estate, household, and method

| Report | Guide |
|---|---|
| [Estate comparison table](../../comparison_table.html) | [Method and controls](comparison_table.md) |
| [Buyer profile evaluation](../../buyer_profile_table.html) | [Method and controls](buyer_profile_table.md) |
| [MRT station comparison](../../mrt_comparison_table.html) | [Method and controls](mrt_comparison_table.md) |
| [Framework architecture](../../framework_diagram.html) | [Diagram guide](framework_diagram.md) |

### Private projects and districts

| Report | Guide |
|---|---|
| [Private condominium explorer](../../private_project_comparison_table.html) | [Method and controls](private_project_comparison_table.md) |
| [Two-condominium comparison](../../condo_framework_comparison.html) | [Comparison framework](condo_framework_comparison.md) |
| [Multi-condominium comparison](../../multi_condo_framework_comparison.html) | [Comparison framework](multi_condo_framework_comparison.md) |
| [Katong condominium comparison](../../katong_condo_comparison.html) | [Comparison framework](katong_condo_comparison.md) |
| [Poiz versus East-side resale](../../poiz_east_resale_comparison.html) | [Comparison framework](poiz_east_resale_comparison.md) |
| [Poiz unit growth and transactions](../../poiz_east_unit_growth_transactions.html) | [Comparison framework](poiz_east_unit_growth_transactions.md) |
| [District 17 projects](../../private_project_comparison_D17.html) | [Comparison framework](private_project_comparison_D17.md) |
| [District 18 projects](../../private_project_comparison_D18.html) | [Comparison framework](private_project_comparison_D18.md) |
| [District 27 projects](../../private_project_comparison_D27.html) | [Comparison framework](private_project_comparison_D27.md) |
| [District 18 versus 26](../../district_pair_comparison_D18_D26.html) | [Comparison framework](district_pair_comparison_D18_D26.md) |
| [Landed growth dashboard](../../landed_growth_dashboard.html) | [Comparison framework](landed_growth_dashboard.md) |

### Canberra Crescent research

| Report | Guide |
|---|---|
| [District 27 deep analysis](../../canberra_crescent_d27_deep_analysis.html) | [Comparison framework](canberra_crescent_d27_deep_analysis.md) |
| [Strategy 1: micro-location](../../canberra_strategy_1_micro_location.html) | [Comparison framework](canberra_strategy_1_micro_location.md) |
| [Strategy 2: newness](../../canberra_strategy_2_newness.html) | [Comparison framework](canberra_strategy_2_newness.md) |
| [Strategy 3: integration](../../canberra_strategy_3_integration.html) | [Comparison framework](canberra_strategy_3_integration.md) |
| [Strategy 4: unit matching](../../canberra_strategy_4_unit_matching.html) | [Comparison framework](canberra_strategy_4_unit_matching.md) |
| [Strategy 5: sale state](../../canberra_strategy_5_sale_state.html) | [Comparison framework](canberra_strategy_5_sale_state.md) |
| [Strategy 6: planning context](../../canberra_strategy_6_planning_context.html) | [Comparison framework](canberra_strategy_6_planning_context.md) |

## Maintenance

When an HTML page, its generator, data contract, or comparison factors change, update the matching
guide in the same commit. Add or remove catalog entries and guides together. Run
`python3 -m pytest tests/test_page_documentation.py` to verify complete coverage and links.
