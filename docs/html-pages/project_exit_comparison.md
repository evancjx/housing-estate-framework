# Project Exit Comparison

> Compares explicit private-property exit scenarios with achieved, size-matched transaction evidence. It is not a price forecast or valuation.

## Purpose

Use [project_exit_comparison.html](../../project_exit_comparison.html) to test how shared holding-period, growth and sale-cost assumptions behave across selected condominium projects. Each project starts from its own achieved cohort median and exposes an editable entry-price override. The page keeps observed evidence, user inputs and derived scenario outputs separate so a user can inspect why two projects differ without reducing them to one project score.

The evidence hierarchy, exact formulas and staged official-data roadmap are documented in the [Project Exit Comparison design](../superpowers/specs/2026-08-10-project-exit-comparison-design.md).

This is the active rights-light comparison direction. It does not publish floor-plan images. Image-based floor-plan comparison remains deferred until a rights-cleared pilot satisfies the [publication policy](../FLOOR_PLAN_PUBLICATION_POLICY.md) and [backlog gate](../../TODO.md#image-based-floor-plan-library-and-comparison).

## Data & Scope

The generated page embeds a compact project catalog and the committed transaction-manifest metadata derived from `data/inputs/ura_private.csv`. The browser fetches canonical transaction records from the committed shards under `site/assets/condo-transactions/`; it does not embed the transaction snapshot in the page or call a third-party listing service. Project names, contract dates, areas, sale states and achieved prices are historical transaction evidence; they are not asking prices or proof that every market sale was captured.

The evidence cohort is controlled by:

- selected projects;
- a target unit area and explicit tolerance; and
- the selected sale state.

Dates and sample coverage shown by the page belong to the committed manifest-and-shard vintage. A transaction count measures recorded evidence activity, not listing inventory, marketing duration or probability of sale.

## Decision Inputs

The decision form lets the user add or remove project slots and enter shared cohort and scenario controls:

- target area and area tolerance;
- sale state;
- purchase date and planned sale date;
- assumed annual growth;
- percentage selling allowance; and
- fixed sale costs.

After matching the cohort, each project exposes its own entry baseline. It starts at that project's cohort median and can be overridden without changing the recorded evidence.

The URL-copy control preserves the current comparison inputs for review or sharing. Reset returns the form to its published defaults. Inputs are assumptions, even when their values resemble a historical project result.

The “Continue in full loan & CPF planner” handoff fills the selected project identity, entry price, provisional first-day purchase/sale dates, annual growth, selling allowance, other fixed sale costs and target area. It marks those dates as month-only so the planner can warn the user to replace them with exact legal dates before relying on its SSD estimate. The planner initially sets the loan to an editable 75% of entry price; the property route, loan terms, CPF treatment and holding costs still require user review.

## Outputs

For every selected project, the result view presents the matching evidence cohort and the exit scenario derived from the same user inputs. Evidence statistics should be read with their transaction count, date coverage, area band and sale-state scope. Derived sale values and scenario proceeds are arithmetic scenarios rather than model forecasts; they explicitly exclude SSD, financing and CPF obligations.

Comparison cards are deliberately parallel. The tool does not create an all-market score or recommendation, and changing an assumption can change the displayed scenario without changing the underlying achieved transactions.

## Interpretation Limits

- URA transaction records are achieved evidence. Resale and sub-sale rows are based on lodged caveats, and URA notes that caveat lodgement is not compulsory; new-sale rows use developer-issued Options to Purchase. The extract is not a complete listing or time-on-market dataset.
- Area matching reduces one source of unit-mix drift; it does not establish identical bedrooms, floor, facing, condition, layout, tenure or amenity access.
- Annual growth is supplied by the user and compounded as a scenario. It is not inferred as a guaranteed future return.
- The selling allowance and fixed costs are user inputs. Users must separately verify legal fees, tax and Seller's Stamp Duty exposure, financing, CPF refund obligations and individual eligibility where relevant.
- Small or stale cohorts should not be read as precise market estimates. Missing evidence remains missing rather than being silently imputed.
- Private-property evidence stays separate from the HDB Value universe and from estate-level Provision and persona-relative Liveability.

## Rebuild

Regenerate the checked-in page from committed inputs with:

```bash
make project-exit-comparison
python3 -m pytest -q tests/test_project_exit_comparison_html.py tests/test_pages_site.py
make pages-check
```

The direct generator command is `python3 models/gen_project_exit_comparison_html.py`. Update the generator, external assets and this page guide together when the contract changes.
