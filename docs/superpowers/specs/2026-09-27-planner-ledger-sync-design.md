# Planner Ledger Sync — Design

**Date:** 2026-09-27
**Status:** Draft for review
**Scope:** `condo_loan_timeline_planner.html`, `site/assets/condo-loan-timeline-planner.js`,
`site/assets/condo-loan-timeline-funding-v3.js` and their tests.

## Problem

Edits in **Acquisition funding ledger → Edit exact-dollar funding rows** never reach the main
projection:

- `CondoFundingLedgerV3.render()` redraws only the ledger, the CPF estimate and the owner outcome.
- `CondoTimelinePlanner.calculate()` calls `buildHoldingProjection(options)`, which always rebuilds
  draws from the standard progressive-payment schedule (BUC) or a single completion draw (resale).
- The ledger card sits outside `#timeline-form`, so a ledger edit does not even trigger a
  recalculation.

As a result, **Property and loan timeline** and **Annual holding checkpoints** ignore the ledger.

## Goal

When the couple ledger is on, set up, reconciled and current, the main projection follows it:

- the timeline shows one event per ledger row (payments, costs and timeline notes), plus the zero-SSD
  date and the sale;
- the checkpoints use the ledger's dated loan draws and dated consideration payments;
- every ledger edit updates both sections without pressing Calculate.

When the ledger cannot be applied, the projection falls back to today's standard schedule and a
banner explains why (agreed 2026-09-27).

## What a ledger edit can and cannot change

`validateFundingLedger` only reports `balanced` when all of these hold to the cent:

- consideration payments = purchase price;
- consideration loan = loan amount;
- owner funding = purchase price − loan amount;
- cost payments = the engine's acquisition costs.

So a balanced ledger always has the engine's totals. What it can change is **timing and split**:

- when each bank draw happens, and how the loan is split across payments;
- when each consideration payment is made, and therefore the uncalled developer balance;
- the owner-funded amount paid by the sale date, if a payment is moved after the sale.

Through the draw timing, it also changes the loan schedule: interest to date, the instalment, the
balance at sale, and so the sale waterfall and economic profit. The design applies the ledger to the
whole main result, not only to the two sections. Otherwise the headline, the waterfall and the
checkpoints would disagree with one another.

Verified with the sample plan on 2026-09-27: the unedited standard ledger, and a couple plan applied
to it, produce exactly the engine's eight BUC draws. Turning sync on therefore changes nothing until
a row is edited.

## Design

### 1. Engine: `options.fundingLedger`

`buildHoldingProjection(options)` accepts an optional `fundingLedger: { rows }`. Each row needs
`date`, `action`, `category` (`consideration` | `cost` | `note`), `paymentAmount` and `loan`. Other
fields are ignored.

**Validation** (throws `RangeError`, with a message suitable for the banner):

- `rows` is a non-empty array;
- every `date` is a valid ISO date;
- every `category` is one of the three values;
- `paymentAmount` and `loan` are finite and ≥ 0, and `loan ≤ paymentAmount`;
- Σ `loan` over **all** rows = `loanAmount`, within S$0.01. This also catches a loan allocated to a
  cost row, which `validateFundingLedger` does not reject today;
- Σ `paymentAmount` over consideration rows = `purchasePrice`, within S$0.01.

**Derivation**, for both routes:

- `draws`: one per row with `loan > 0` — `{ date, amount: loan, label: action }`;
- `ownerPropertyPaid`: Σ (`paymentAmount − loan`) over consideration rows dated on or before the
  sale.

For BUC:

- `calledAmount`: Σ consideration `paymentAmount` dated on or before the sale;
- `uncalledDeveloperBalance = max(0, purchasePrice − calledAmount)`.

For resale, as today: `calledAmount = purchasePrice` and `uncalledDeveloperBalance = 0`.

**Checkpoints and chart rows**: the uncalled balance at a date comes from one helper. In ledger mode
it is based on consideration rows dated on or before that date; otherwise on stages. It is always 0
for resale.

**Events**: one per ledger row, in ledger order, shaped as
`{ type: "ledger", date, title: action, afterSale, row }`. The zero-SSD and sale events are added as
today. The sort becomes stable and the sale stays last on its date:
`compareDates(a.date, b.date) || (a.type === "sale") - (b.type === "sale")`. Without this, same-day
ledger rows (for example exercising the S&P, BSD and the 15% payment) could be reordered.

**Everything else** — `plan`, BSD, mortgage duty, acquisition costs, scenarios, break-even — is
unchanged. The result gains `fundingLedgerApplied: true | false`.

**Without `fundingLedger`**, output is identical to today, apart from the stable sort (see Testing).

### 2. Wiring

**Planner (`condo-loan-timeline-planner.js`):**

- New API: `setFundingLedgerSource(fn)`. The function receives the standard (ledger-free)
  projection and returns one of:
  - `null` — no ledger in play;
  - `{ rows }` — apply these rows;
  - `{ reason }` — a ledger is in play but cannot be applied.
- `calculate()`:
  1. builds the standard projection;
  2. asks the source (a throw becomes a `reason`);
  3. if it gets `rows`, rebuilds with `fundingLedger`. If that throws, it keeps the standard
     projection and uses the error message as the reason;
  4. renders the result and the banner.
- The planner listens for a `funding-ledger-change` event on `#timeline-form` and calls
  `calculate()`.

**Ledger (`condo-loan-timeline-funding-v3.js`):**

- `ledgerSyncState(projection)` returns:
  - `null` when the partner switch is off or the couple setup is incomplete;
  - `{ reason }` when the ledger is stale;
  - `{ reason }` when it is unbalanced;
  - otherwise `{ rows: state.rows }`.
- `init` registers `planner.setFundingLedgerSource(ledgerSyncState)`.
- At the end of every `render()`, it dispatches `funding-ledger-change` on the form. Ledger edits,
  rebuilds and draft restores therefore recalculate the main projection.
- **Consistency**: when the sync applies rows, `render()` passes the ledger-applied projection to
  `renderCpfEstimate` (the CPF estimate and owner outcome). The owner outcome states that it
  "reconciles to the current sale waterfall"; that stays true only if both come from the same
  projection. The ledger's own reconciliation targets still come from the standard projection,
  which is what `validateFundingLedger` checks against.

### 3. Banner

One `role="status"` line inside each of the two cards: `#timeline-ledger-status` and
`#checkpoint-ledger-status`.

| State | Text | Visible |
| --- | --- | --- |
| No ledger (partner off / setup incomplete) | — | hidden |
| Applied | "Following your acquisition funding ledger." | yes |
| Not applied | "Ledger edits not applied: <reason>. Showing the standard payment schedule." | yes, warning style |

Reasons:

- **Stale**: "the main plan changed after you edited the ledger — update the rows or rebuild the
  ledger".
- **Unbalanced**: "the ledger does not reconcile — fix the flagged rows".
- **Engine rejection**: the `RangeError` message.

Script `?v=` query strings are bumped so cached pages load the new code.

## Non-goals

- Changing how the ledger is generated, validated or stored. The one exception is that the engine
  rejects loan on cost rows.
- Using the ledger's cost rows for acquisition costs. They must already equal the engine's to the
  cent.
- Modelling unpaid resale consideration as an obligation. Resale keeps
  `uncalledDeveloperBalance = 0`.
- Any change to single-owner mode. There is no ledger there.

## Error handling

- A stale, unbalanced or rejected ledger never breaks the page. The standard projection renders
  with the banner.
- An exception inside the source function is caught and shown as the reason. It is never swallowed
  silently.

## Testing

**Node unit tests** (pytest via `_run_node`), with the sample BUC plan:

1. **No ledger**: output equals today's for the BUC and resale samples. The events snapshot proves
   the stable sort does not reorder the existing events.
2. **Unedited ledger**: the unedited standard ledger gives the same checkpoints and headline as no
   ledger, to the cent.
3. **Moved draw**: moving one loan draw later lowers "loan drawn" and interest at the checkpoint in
   between, and moves the timeline event.
4. **Moved payment**: moving a consideration payment after the sale raises
   `uncalledDeveloperBalance` and lowers `ownerPropertyPaid`.
5. **Note row**: a note row appears as a timeline event with its action as the title.
6. **Rejections**: loan total ≠ `loanAmount`, loan on a cost row, consideration total ≠ price, and a
   bad date each throw `RangeError`.
7. **Resale**: a resale ledger with a moved completion draw changes the draw date; uncalled stays 0.

**Playwright e2e** (Chromium; sandbox off):

1. Couple setup complete, then edit a ledger loan row's date. The timeline shows the new date and
   the Year-N checkpoint's "Loan drawn" changes, with no Calculate click. The status reads
   "Following your acquisition funding ledger."
2. Unbalance a row. The banner shows "Ledger edits not applied…" and the timeline reverts to the
   standard stages. Rebalance it and the ledger applies again.
3. Existing e2e and unit suites pass, including the owner-outcome reconciliation to the waterfall.

## Risks

- **The headline figures move when draw dates are edited.** This is intended, because the ledger is
  the user's truth, but it may surprise a user who expected only the two sections to change. The
  status line says the projection follows the ledger.
- **Double calculation per keystroke**: form input recalculates, and so does the ledger render's
  event. The engine runs in milliseconds, so this is acceptable. Deduplicating it would add state
  for no visible gain.
- **A ledger row dated before the acquisition** is accepted, as the ledger allows it today. A draw
  there starts the loan early.
