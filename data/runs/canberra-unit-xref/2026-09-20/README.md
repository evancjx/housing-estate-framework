# Canberra Crescent Residences unit-price collection

Research captured: **20 September 2026, Singapore time**. This is an isolated
research snapshot, not a canonical model input or an official unit register.

The public sources make the proposed cross-reference feasible. Of the **349
units marked SOLD in the Huttons chart**, this snapshot assigns one price value
to **340 units**: 318 have a publicly printed full unit/price pair with matching
transaction attributes elsewhere, and 22 require an inferred unit link. Six
units need review and three have no collected price. Exact unit identities are
not independently established by the public URA records.

Start with **unit_price_inventory.csv**. It contains all 376 physical units,
including the 27 units Huttons marks available. `price_sgd` is intentionally
blank for unresolved rows. Historical price bounds and individual dated
observations remain available; a blank does not mean a zero price.

| Result for Huttons SOLD units | Count |
| --- | ---: |
| Published full unit/price, transaction attributes corroborated | 318 |
| Unit inferred from masked transaction and dated chart | 22 |
| Multiple different historical prices; review required | 5 |
| Published historical price not reconciled to transaction snapshots | 1 |
| No price found | 3 |
| Total | 349 |

## Sources and coverage

| Source | Collected evidence | Limitation |
| --- | --- | --- |
| [PropertyNoob sales](https://propertynoob.com/condo/canberra-crescent-residences/sales) | 330 New Sale records, 324 distinct full unit numbers; 2 Aug 2025–3 Apr 2026 | Historical records include repeated units; block comes from the unit chart |
| [Isaac Yee unit chart](https://canberracrescent.isaacyee.com/units) | 376 units with block, full unit, size and bedrooms; 348 SOLD with reported dates | Agent date semantics unspecified; some dates disagree with transactions and other agents |
| [Huttons public price list](https://portal.huttonsgroup.com/public/pricelist/R070030E?pid=697564dce09a4511a8d56e739ecdaabd) | 376 units; 349 SOLD, 27 available on 20 Sep | No achieved price or sold date for SOLD units; prices for available units are asking prices |
| [PropertyStory](https://propertystory.sg/canberra-crescent-residences/) | 50 recent masked transactions, through 8 Aug 2026 | Page headline transaction count exceeds exposed table; sale type absent from table |
| [EdgeProp](https://www.edgeprop.sg/condo-apartment/canberra-crescent-residences) | Public masked transactions through 26 Aug 2026; 23 post-3-Apr rows added to matching input | Same-date pagination duplicates/omissions prevent claiming a complete fresh ledger |
| Frozen URA PMI project extract | 340 New Sale records through July 2026 | Historical repository snapshot, not a fresh official download; no full unit numbers |

The user's [balance-units page](https://www.canberra-crescentresidences.com.sg/balance-units-chart/)
publishes recent full unit numbers and dates, but explicitly limits its list to
recent sales. The full charts above extend coverage to the whole development.

The source HTML captures were used locally, with hashes recorded in
`provenance.json`. Only extracted factual tables are stored here. Related agent
sites can share the same underlying feed, so matching mirrors do not necessarily
provide independent confirmation.

## Matching rules

1. Copy directly printed full unit numbers from PropertyNoob. Obtain block
   numbers from the complete chart; the direct transaction table does not print
   them. Preserve the originating transaction record and source URL.
2. For masked recent transactions, require a unique candidate among all
   sold-chart units on **block + exact floor + rounded square feet + reported
   sold date within seven days**. Mark the result `inferred_unique_within_7_days`.
   This window is a research assumption, not proof of the unit's identity.
3. Compare transaction month, price, rounded area and containing floor band with
   the local URA snapshot. Separately compare exact date, block, floor, area and
   price with current EdgeProp. Attribute agreement corroborates a transaction's
   price, not its masked stack number. URA public signatures can have multiple
   matching records.
4. Preserve chart dates and transaction dates separately. Do not substitute
   asking prices for achieved prices, or choose one historical price silently
   when a unit has multiple amounts.
5. Multiple sources for the same unit/date/price/area are retained as source
   observations. The inventory counts distinct date/price/area combinations
   separately from observations. Neither count proves distinct completed sales.

## Examples

| Block/unit | Transaction date | Price SGD | Evidence |
| --- | --- | ---: | --- |
| 51 #05-07 | 2026-04-03 | 1,981,100 | Full unit and price printed together by PropertyNoob |
| 51 #04-07 | 2026-06-15 | 1,995,861 | Inferred from masked transaction; chart reports 14 Jun |
| 57 #06-30 | 2026-08-26 | 2,469,854 | Inferred from masked EdgeProp transaction and dated unit chart |

## Unresolved rows

- **51 #12-06, 51 #08-05, 53 #07-13, 55 #10-22, 57 #08-27** have different
  historical prices. Keep every observation. Cancellation, rebooking or record
  correction cannot be determined from these tables alone.
- **51 #10-04** has a directly published price of S$1,346,100 on 2 Aug 2025,
  but no matching transaction signature in the local URA or current EdgeProp
  snapshot. Its chart date is 30 Aug. A masked Block 51 floor-10, 667 sqft
  transaction on 1 Oct is S$1,359,400; the full unit identity of that later
  transaction is not established. The single-price field remains blank.
- **55 #04-23, 57 #10-30, 57 #05-30** have no collected transaction price.
  Huttons marks #04-23 SOLD while Isaac Yee still shows it available. The
  PropertyStory 17 Sep update masks the stack, so this snapshot does not assign
  that date to #04-23 as a confirmed fact.

## Fresh EdgeProp pagination caveat

The site advertises 346 transactions. A normal 35-page pass captured 346 row
occurrences, but only 340 distinct masked signatures. Six pairs repeat across
adjacent page boundaries on dates where the older repository snapshot contains
other rows absent from the fresh pass. This suggests unstable ordering within
same-date pagination; it is not evidence that those old transactions were
withdrawn. Both current occurrence and deduplicated captures are retained. The
23 recent rows used here do not fall in those overlap groups. Canonical source
ledgers have not been replaced.

## Files and reproduction

- `unit_price_inventory.csv`: one row per physical unit; start here.
- `price_observations.csv`: all 403 source observations with match status,
  candidate counts, source dates, URLs and corroboration counts.
- `published_unit_transactions.csv`: 330 directly published transaction rows.
- `masked_transactions.csv`: 50 PropertyStory rows plus 23 recent EdgeProp rows.
- `agent_unit_chart.csv`, `huttons_unit_status.csv`: complete source inventories.
  The Huttons file retains explicitly labelled asking prices for available units.
- `ura_project_snapshot.csv`: the frozen 340-row Canberra extract used for
  historical price corroboration. Its parent input and extract hashes are in
  provenance; changes to the main transaction dataset do not change this run.
- `edgeprop_current_occurrences.csv`, `edgeprop_current_transactions.csv`:
  current public capture before and after duplicate suppression.
- `counts.json`, `provenance.json`: coverage, source hashes and limitations.

Rebuild the derived inventory, observations and counts from the extracted CSVs:

```bash
python3 data/runs/canberra-unit-xref/2026-09-20/build_snapshot.py
```

The build checks the 376-unit inventory and the 340-record historical URA input.
Additional validation checked unique block/unit pairs, all inferred date windows,
the 349-unit Huttons total, the one chart-status conflict and unresolved prices.
This script rebuilds the saved research snapshot; it does not refresh websites.
