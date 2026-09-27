# Planner Ledger Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make edits in the co-owner "Acquisition funding ledger" drive the planner's timeline, checkpoints and headline projection. When the ledger cannot be applied, fall back to the standard schedule and show a banner saying why.

**Architecture:**
- `buildHoldingProjection` gains an optional `fundingLedger: { rows }`. With it, draws, called consideration and events come from the ledger rows.
- The planner UI asks a registered "ledger source" for rows on every calculation.
- `CondoFundingLedgerV3` registers that source and dispatches `funding-ledger-change` after every ledger render, so ledger edits recalculate the planner.

**Tech Stack:** Vanilla JS (UMD factories), static HTML/CSS, pytest driving Node for engine tests, Playwright (Chromium) for e2e.

**Spec:** `docs/superpowers/specs/2026-09-27-planner-ledger-sync-design.md`

## Global Constraints

- Work only in the worktree `.worktrees/planner-ledger-sync`, on branch `feature/planner-ledger-sync`.
- Tolerance for ledger totals: S$0.01. Loan total over **all** rows = `loanAmount`, and consideration payments = `purchasePrice`.
- Banner texts, exact:
  - applied: `Following your acquisition funding ledger.`
  - not applied: `Ledger edits not applied: <reason>. Showing the standard payment schedule.`
  - stale reason: `the main plan changed after you edited the ledger — update the rows or rebuild the ledger`
  - unbalanced reason: `the ledger does not reconcile — fix the flagged rows`
- Status elements: `#timeline-ledger-status` and `#checkpoint-ledger-status`, both `role="status"` and initially `hidden`. The warning class is `ledger-sync-warning`.
- Event name: `funding-ledger-change`, dispatched on `#timeline-form`.
- New planner API: `setFundingLedgerSource(fn | null)`. `fn(standardProjection)` returns `null | { rows } | { reason }`.
- Script cache-busters become `?v=20260927-1` for both planner scripts.
- **Ruling (plan):** today's comparator (`... || (a.type === "sale" ? 1 : -1)`) is inconsistent. It lists the resale "Completion / full loan draw" **before** "Legal acquisition" when both fall on the same day. The stable comparator restores insertion order (purchase, then draw). BUC event order is unchanged. The spec's "identical without a ledger" is amended for this one case.
- Playwright e2e needs Chromium and local port binding, so run e2e commands with the sandbox disabled.
- No `/tmp`. Scratch files go under `.superpowers/`.

## Review Focus

1. **Partner switched off after the ledger applied.** The banner hides and the standard schedule returns. Pinned in Task 3, test 2.
2. **Main plan changed after ledger edits (stale).** The banner gives the stale reason and the standard schedule shows. Pinned in Task 3, test 2.
3. **Reload with an edited ledger draft.** The ledger still applies after reload. Pinned in Task 3, test 1.
4. **A source that throws or returns a reason.** The banner shows the message and the page still renders. Pinned in Task 2, e2e.
5. **A payment or draw moved after the sale.** It is excluded from the loan at sale, counted as uncalled, and its event is marked after sale. Pinned in Task 1, test 4.

---

### Task 1: Engine ledger mode

**Files:**
- Modify: `site/assets/condo-loan-timeline-planner.js`:
  - helpers before `buildHoldingProjection`, around line 450;
  - the route block, around lines 485–522;
  - checkpoints, chart and events, around lines 614–696;
  - the return object, around line 713.
- Create: `tests/test_condo_loan_timeline_ledger_sync.py`

**Interfaces:**
- Consumes: `funding.buildStandardFundingLedger(projection, 0)`, which returns rows with `key, date, action, category, paymentAmount, loan, …`.
- Produces:
  - `buildHoldingProjection({ ...options, fundingLedger: { rows } })`;
  - result `fundingLedgerApplied: boolean`;
  - ledger events `{ type: "ledger", date, title, afterSale, row: { date, action, category, paymentAmount, loan } }`;
  - it throws `RangeError`/`TypeError` with the messages below.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_condo_loan_timeline_ledger_sync.py`:

```python
"""Funding-ledger driven projections for the condo planner engine."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASE_SCRIPT = ROOT / "site" / "assets" / "condo-loan-timeline-planner.js"
FUNDING_SCRIPT = ROOT / "site" / "assets" / "condo-loan-timeline-funding-v3.js"

BUC = (
    "{route:'buc',purchasePrice:1610000,areaSqft:700,acquisitionDate:'2025-10-25',"
    "topDate:'2028-07-06',saleDate:'2031-10-25',loanAmount:1207404,annualRate:3,"
    "termMonths:360,annualGrowthPct:3,sellingCostPct:2.18,absdPaid:0,purchaseLegal:2800,"
    "purchaseOther:0,saleLegal:3000,saleOther:0,holdingCosts:0,netRent:0,cpfRefund:0}"
)
RESALE = (
    "{route:'resale',purchasePrice:1200000,areaSqft:700,acquisitionDate:'2026-01-01',"
    "completionDate:'2026-03-01',saleDate:'2030-01-01',loanAmount:900000,annualRate:3,"
    "termMonths:360,annualGrowthPct:3,sellingCostPct:2,purchaseLegal:3000,saleLegal:3000}"
)
RESALE_SAME_DAY = RESALE.replace("completionDate:'2026-03-01'", "completionDate:'2026-01-01'")


def _run_node(body: str) -> dict | list:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; ledger sync calculation tests are skipped")
    program = (
        f"const planner=require({json.dumps(str(BASE_SCRIPT))});"
        f"const funding=require({json.dumps(str(FUNDING_SCRIPT))});"
        "const project=(options,rows)=>planner.buildHoldingProjection("
        "rows?{...options,fundingLedger:{rows}}:options);"
        "const ledgerFor=options=>funding.buildStandardFundingLedger("
        "planner.buildHoldingProjection(options),0);"
        "const edit=(rows,key,changes)=>rows.map(row=>row.key===key?{...row,...changes}:row);"
        "const rejection=fn=>{try{fn();return null;}catch(error){return error.message;}};"
        f"const value=(() => {{{body}}})();"
        "process.stdout.write(JSON.stringify(value));"
    )
    completed = subprocess.run(
        [node, "-e", program], check=True, capture_output=True, text=True
    )
    return json.loads(completed.stdout)


def test_without_a_ledger_event_order_is_stable() -> None:
    result = _run_node(
        f"const buc=project({BUC});const resale=project({RESALE_SAME_DAY});"
        "return {buc:buc.events.map(e=>[e.date,e.type]),"
        "resale:resale.events.map(e=>[e.date,e.type]),"
        "applied:[buc.fundingLedgerApplied,resale.fundingLedgerApplied]};"
    )

    assert result["buc"] == [
        ["2025-10-25", "stage"], ["2025-12-25", "stage"], ["2026-03-25", "stage"],
        ["2026-08-25", "stage"], ["2027-02-25", "stage"], ["2027-06-25", "stage"],
        ["2027-09-25", "stage"], ["2028-01-25", "stage"], ["2028-07-06", "stage"],
        ["2029-07-06", "stage"], ["2029-10-25", "ssd-zero"], ["2031-10-25", "sale"],
    ]
    assert result["resale"] == [
        ["2026-01-01", "purchase"], ["2026-01-01", "draw"],
        ["2030-01-01", "ssd-zero"], ["2030-01-01", "sale"],
    ]
    assert result["applied"] == [False, False]


def test_unedited_ledger_matches_the_standard_projection() -> None:
    result = _run_node(
        f"const options={BUC};const rows=ledgerFor(options);"
        "const standard=project(options);const synced=project(options,rows);"
        "const table=projection=>projection.checkpointRows.map(r=>[r.label,r.loan.drawn,"
        "r.loan.interestPaid,r.loan.balance,r.uncalledDeveloperBalance,r.grossEquity]);"
        "return {applied:synced.fundingLedgerApplied,standard:table(standard),"
        "synced:table(synced),profit:[standard.base.economicProfit,synced.base.economicProfit],"
        "owner:[standard.ownerPropertyPaid,synced.ownerPropertyPaid],"
        "ledgerEvents:synced.events.filter(e=>e.type==='ledger').length,rowCount:rows.length};"
    )

    assert result["applied"] is True
    assert len(result["synced"]) == len(result["standard"])
    for synced, standard in zip(result["synced"], result["standard"]):
        assert synced[0] == standard[0]
        assert synced[1:] == pytest.approx(standard[1:], abs=0.01)
    assert result["profit"][1] == pytest.approx(result["profit"][0], abs=0.01)
    assert result["owner"][1] == pytest.approx(result["owner"][0], abs=0.01)
    assert result["ledgerEvents"] == result["rowCount"]


def test_moving_a_loan_draw_moves_the_balance_and_the_event() -> None:
    result = _run_node(
        f"const options={BUC};const rows=ledgerFor(options);"
        "const title=rows.find(r=>r.key==='stage-3').action;"
        "const standard=project(options);"
        "const synced=project(options,edit(rows,'stage-3',{date:'2026-11-25'}));"
        "return {drawn:[standard.checkpointRows[1].loan.drawn,synced.checkpointRows[1].loan.drawn],"
        "interest:[standard.checkpointRows[2].loan.interestPaid,"
        "synced.checkpointRows[2].loan.interestPaid],"
        "dates:synced.events.filter(e=>e.type==='ledger'&&e.title===title).map(e=>e.date)};"
    )

    assert result["drawn"] == pytest.approx([241_404, 80_404], abs=0.01)
    assert result["interest"][1] < result["interest"][0]
    assert result["dates"] == ["2026-11-25"]


def test_payments_after_the_sale_stay_uncalled_and_unpaid() -> None:
    result = _run_node(
        f"const options={BUC};const rows=ledgerFor(options);const standard=project(options);"
        "const title=rows.find(r=>r.key==='stage-9').action;"
        "const lateDraw=project(options,edit(rows,'stage-9',{date:'2032-01-06'}));"
        "const lateDeposit=project(options,edit(rows,'stage-0',{date:'2032-01-01'}));"
        "return {uncalled:lateDraw.uncalledDeveloperBalance,"
        "drawnAtSale:lateDraw.loanAtSale.drawn,"
        "afterSale:lateDraw.events.find(e=>e.type==='ledger'&&e.title===title).afterSale,"
        "owner:[standard.ownerPropertyPaid,lateDeposit.ownerPropertyPaid],"
        "depositUncalled:lateDeposit.uncalledDeveloperBalance};"
    )

    assert result["uncalled"] == pytest.approx(241_500, abs=0.01)
    assert result["drawnAtSale"] == pytest.approx(965_904, abs=0.01)
    assert result["afterSale"] is True
    assert result["owner"] == pytest.approx([402_596, 322_096], abs=0.01)
    assert result["depositUncalled"] == pytest.approx(80_500, abs=0.01)


def test_a_note_row_becomes_a_timeline_event() -> None:
    result = _run_node(
        f"const options={BUC};const rows=[...ledgerFor(options),{{key:'custom-1',"
        "date:'2026-05-01',action:'Keys ceremony',category:'note',paymentAmount:0,loan:0}];"
        "return project(options,rows).events.filter(e=>e.title==='Keys ceremony')"
        ".map(e=>[e.date,e.type,e.row.category]);"
    )

    assert result == [["2026-05-01", "ledger", "note"]]


def test_inconsistent_ledgers_are_rejected_with_a_reason() -> None:
    result = _run_node(
        f"const options={BUC};const rows=ledgerFor(options);"
        "const loanRow=rows.find(r=>r.loan>0);"
        "return {"
        "empty:rejection(()=>project(options,[])),"
        "loanShort:rejection(()=>project(options,edit(rows,loanRow.key,{loan:loanRow.loan-100}))),"
        "costLoan:rejection(()=>project(options,edit(edit(rows,loanRow.key,"
        "{loan:loanRow.loan-100}),'cost-bsd',{loan:100}))),"
        "loanOverPayment:rejection(()=>project(options,edit(rows,loanRow.key,"
        "{paymentAmount:loanRow.loan-1}))),"
        "priceShort:rejection(()=>project(options,edit(rows,'stage-0',{paymentAmount:80400}))),"
        "badDate:rejection(()=>project(options,edit(rows,'stage-0',{date:'2026-13-01'}))),"
        "badCategory:rejection(()=>project(options,edit(rows,'stage-0',{category:'refund'})))};"
    )

    assert result["empty"] == "fundingLedger.rows must be a non-empty array"
    assert "not the loan amount" in result["loanShort"]
    assert result["costLoan"] == (
        "the bank loan can only fund purchase-price payments, not costs or notes"
    )
    assert "loan must not exceed its payment" in result["loanOverPayment"]
    assert "not the purchase price" in result["priceShort"]
    assert "].date is not a valid calendar date" in result["badDate"]
    assert "category must be consideration, cost or note" in result["badCategory"]


def test_resale_ledger_moves_the_completion_draw_without_uncalled_balance() -> None:
    result = _run_node(
        f"const options={RESALE};const rows=ledgerFor(options);"
        "const synced=project(options,edit(rows,'resale-completion',{date:'2026-06-01'}));"
        "return {draws:synced.schedule.draws.map(d=>[d.date,d.amount]),"
        "uncalled:synced.checkpointRows.map(r=>r.uncalledDeveloperBalance),"
        "owner:synced.ownerPropertyPaid};"
    )

    assert result["draws"] == [["2026-06-01", 900_000]]
    assert set(result["uncalled"]) == {0}
    assert result["owner"] == pytest.approx(300_000, abs=0.01)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest -q tests/test_condo_loan_timeline_ledger_sync.py`
Expected: 7 failed.
- `test_without_a_ledger_event_order_is_stable` fails on the resale order (draw before purchase) or on `applied`.
- The others fail because `fundingLedgerApplied` is undefined and the ledger is ignored: drawn stays 241,404 and no `ledger` events appear.
- The rejection test fails because every `rejection` returns `None`.

- [ ] **Step 3: Add the ledger helpers**

In `site/assets/condo-loan-timeline-planner.js`, insert directly before `function buildHoldingProjection(options) {`:

```js
  const LEDGER_CATEGORIES = ["consideration", "cost", "note"];

  function checkedLedgerRows(rows, purchasePrice, loanAmount) {
    if (!Array.isArray(rows) || !rows.length) {
      throw new RangeError("fundingLedger.rows must be a non-empty array");
    }
    const checked = rows.map((row, index) => {
      const name = `fundingLedger.rows[${index}]`;
      const date = String(row.date || "");
      parseISODate(date, `${name}.date`);
      if (!LEDGER_CATEGORIES.includes(row.category)) {
        throw new RangeError(`${name}.category must be consideration, cost or note`);
      }
      const paymentAmount = nonNegative(row.paymentAmount || 0, `${name}.paymentAmount`);
      const loan = nonNegative(row.loan || 0, `${name}.loan`);
      if (loan > paymentAmount + EPSILON) {
        throw new RangeError(`${name}.loan must not exceed its payment`);
      }
      return { date, action: String(row.action || ""), category: row.category, paymentAmount, loan };
    });
    if (checked.some(row => row.category !== "consideration" && row.loan > EPSILON)) {
      throw new RangeError("the bank loan can only fund purchase-price payments, not costs or notes");
    }
    const loanTotal = checked.reduce((total, row) => total + row.loan, 0);
    if (Math.abs(loanTotal - loanAmount) > 0.01) {
      throw new RangeError(
        `ledger loan rows total ${loanTotal.toFixed(2)}, not the loan amount ${loanAmount.toFixed(2)}`
      );
    }
    const considerationTotal = ledgerConsiderationThrough(checked, null, row => row.paymentAmount);
    if (Math.abs(considerationTotal - purchasePrice) > 0.01) {
      throw new RangeError(
        `ledger purchase-price payments total ${considerationTotal.toFixed(2)}, not the purchase price ${purchasePrice.toFixed(2)}`
      );
    }
    return checked;
  }

  function ledgerConsiderationThrough(rows, date, amount) {
    return rows
      .filter(row => row.category === "consideration"
        && (date == null || compareDates(row.date, date) <= 0))
      .reduce((total, row) => total + amount(row), 0);
  }

  function ledgerDraws(rows) {
    return rows
      .filter(row => row.loan > EPSILON)
      .map(row => ({ date: row.date, amount: row.loan, label: row.action }));
  }

```

- [ ] **Step 4: Use the ledger in the route block**

Replace the block from `let plan;` through the closing `}` of the resale `else` (the one ending `uncalledDeveloperBalance = 0;\n    }`) with:

```js
    const ledgerRows = options.fundingLedger == null
      ? null
      : checkedLedgerRows(options.fundingLedger.rows, purchasePrice, loanAmount);
    let plan;
    let draws;
    let ownerPropertyPaid;
    let calledAmount;
    let uncalledDeveloperBalance;
    if (route === "buc") {
      plan = buildBucPlan({
        purchasePrice,
        loanAmount,
        acquisitionDate,
        topDate: options.topDate,
      });
      if (ledgerRows) {
        draws = ledgerDraws(ledgerRows);
        calledAmount = ledgerConsiderationThrough(ledgerRows, saleDate, row => row.paymentAmount);
        ownerPropertyPaid = ledgerConsiderationThrough(
          ledgerRows,
          saleDate,
          row => row.paymentAmount - row.loan
        );
      } else {
        draws = plan.draws;
        const calledStages = plan.stages.filter(stage => compareDates(stage.date, saleDate) <= 0);
        calledAmount = calledStages.reduce((total, stage) => total + stage.amount, 0);
        ownerPropertyPaid = calledStages.reduce(
          (total, stage) => total + stage.ownerContribution,
          0
        );
      }
      uncalledDeveloperBalance = Math.max(0, purchasePrice - calledAmount);
    } else {
      const completionDate = String(options.completionDate || "");
      parseISODate(completionDate, "completionDate");
      if (compareDates(completionDate, acquisitionDate) < 0) {
        throw new RangeError("completionDate must not be before acquisitionDate");
      }
      if (compareDates(saleDate, completionDate) < 0) {
        throw new RangeError("saleDate must not be before completionDate for a resale loan");
      }
      plan = { completionDate };
      if (ledgerRows) {
        draws = ledgerDraws(ledgerRows);
        ownerPropertyPaid = ledgerConsiderationThrough(
          ledgerRows,
          saleDate,
          row => row.paymentAmount - row.loan
        );
      } else {
        draws = loanAmount > EPSILON
          ? [{ date: completionDate, amount: loanAmount, label: "Full loan draw" }]
          : [];
        ownerPropertyPaid = purchasePrice - loanAmount;
      }
      calledAmount = purchasePrice;
      uncalledDeveloperBalance = 0;
    }
```

- [ ] **Step 5: Share the uncalled-balance calculation, and add ledger events and a stable sort**

Directly before `const checkpoints = [{ label: "Acquisition", date: acquisitionDate }];` insert:

```js
    const uncalledAt = date => {
      if (route !== "buc") return 0;
      const called = ledgerRows
        ? ledgerConsiderationThrough(ledgerRows, date, row => row.paymentAmount)
        : plan.stages
          .filter(stage => compareDates(stage.date, date) <= 0)
          .reduce((total, stage) => total + stage.amount, 0);
      return Math.max(0, purchasePrice - called);
    };
```

In `checkpointRows`, replace:

```js
      let uncalled = 0;
      if (route === "buc") {
        const called = plan.stages
          .filter(stage => compareDates(stage.date, checkpoint.date) <= 0)
          .reduce((total, stage) => total + stage.amount, 0);
        uncalled = Math.max(0, purchasePrice - called);
      }
```

with `      const uncalled = uncalledAt(checkpoint.date);`. In the chart loop, replace the same block (using `date`) with `      const uncalled = uncalledAt(date);`.

Replace `const events = route === "buc"` and its first branch so the ledger comes first:

```js
    const events = ledgerRows
      ? ledgerRows.map(row => ({
        type: "ledger",
        date: row.date,
        title: row.action,
        afterSale: compareDates(row.date, saleDate) > 0,
        row,
      }))
      : route === "buc"
        ? plan.stages.map(stage => ({
          type: "stage",
          date: stage.date,
          title: stage.name,
          detail: `${stage.percent}% due · owner ${stage.ownerContribution} · bank ${stage.loanDraw}`,
          afterSale: compareDates(stage.date, saleDate) > 0,
          stage,
        }))
        : [
          { type: "purchase", date: acquisitionDate, title: "Legal acquisition", detail: "SSD and growth clock starts" },
          { type: "draw", date: plan.completionDate, title: "Completion / full loan draw", detail: `Bank draw ${loanAmount}` },
        ];
```

Replace the sort line with:

```js
    events.sort((a, b) => compareDates(a.date, b.date)
      || Number(a.type === "sale") - Number(b.type === "sale"));
```

In the returned object, add `fundingLedgerApplied: Boolean(ledgerRows),` on the line after `plan,`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest -q tests/test_condo_loan_timeline_ledger_sync.py tests/test_condo_loan_timeline_planner.py tests/test_condo_loan_timeline_funding_v3.py`
Expected: all pass. That is the 7 new tests plus the existing 10 and 18.

- [ ] **Step 7: Commit**

```bash
git add site/assets/condo-loan-timeline-planner.js tests/test_condo_loan_timeline_ledger_sync.py
git commit -m "feat(planner): project from an exact funding ledger when supplied"
```

---

### Task 2: Planner ledger source, events and status banner

**Files:**
- Modify: `site/assets/condo-loan-timeline-planner.js`:
  - module-level source before `function init(document) {`;
  - `eventDetail`, around line 959;
  - `calculate`, around line 1133;
  - the listeners, around line 1165;
  - the API return.
- Modify: `condo_loan_timeline_planner.html`:
  - CSS after the `.timeline-wrap` rule, around line 424;
  - the timeline card, around line 902;
  - the checkpoints card, around line 939;
  - the planner script tag, line 1038.
- Modify: `tests/test_condo_loan_timeline_planner.py:264` (script version).
- Test: `tests/test_condo_loan_timeline_ledger_sync.py`, `tests/test_condo_loan_timeline_funding_v3_e2e.py`

**Interfaces:**
- Consumes: Task 1's `fundingLedger` option, the `ledger` events with `row`, and `fundingLedgerApplied`.
- Produces:
  - `CondoTimelinePlanner.setFundingLedgerSource(fn | null)`, which throws `TypeError("funding ledger source must be a function or null")` for other values;
  - the planner recalculates on the `funding-ledger-change` form event;
  - `#timeline-ledger-status` and `#checkpoint-ledger-status` show the banner texts from Global Constraints.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_condo_loan_timeline_ledger_sync.py`:

```python
def test_ledger_source_must_be_a_function_or_null() -> None:
    result = _run_node(
        "return {bad:rejection(()=>planner.setFundingLedgerSource('rows')),"
        "fn:rejection(()=>planner.setFundingLedgerSource(()=>null)),"
        "clear:rejection(()=>planner.setFundingLedgerSource(null))};"
    )

    assert result == {
        "bad": "funding ledger source must be a function or null",
        "fn": None,
        "clear": None,
    }
```

Append to `tests/test_condo_loan_timeline_funding_v3_e2e.py`:

```python
def test_planner_applies_or_explains_a_registered_ledger_source(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    _load_clean(page, url)
    timeline_status = page.locator("#timeline-ledger-status")
    checkpoint_status = page.locator("#checkpoint-ledger-status")
    playwright_api.expect(timeline_status).to_be_hidden()
    playwright_api.expect(checkpoint_status).to_be_hidden()

    register = """
    source => {
      window.CondoTimelinePlanner.setFundingLedgerSource(source);
      document.getElementById('timeline-form')
        .dispatchEvent(new CustomEvent('funding-ledger-change'));
    }
    """
    page.evaluate(
        f"({register})(() => ({{ reason: 'test reason' }}))"
    )
    expected = "Ledger edits not applied: test reason. Showing the standard payment schedule."
    playwright_api.expect(timeline_status).to_have_text(expected)
    playwright_api.expect(checkpoint_status).to_have_text(expected)
    playwright_api.expect(timeline_status).to_have_class(re.compile("ledger-sync-warning"))

    page.evaluate(
        f"""({register})(projection => ({{ rows: [
          ...projection.plan.stages.map(stage => ({{
            date: stage.date, action: stage.name, category: 'consideration',
            paymentAmount: stage.amount, loan: stage.loanDraw,
          }})),
          {{ date: projection.acquisitionDate, action: 'Keys ceremony',
             category: 'note', paymentAmount: 0, loan: 0 }},
        ] }}))"""
    )
    playwright_api.expect(timeline_status).to_have_text(
        "Following your acquisition funding ledger."
    )
    playwright_api.expect(timeline_status).not_to_have_class(re.compile("ledger-sync-warning"))
    playwright_api.expect(
        page.locator("#timeline-events b", has_text="Keys ceremony")
    ).to_have_count(1)
    playwright_api.expect(
        page.locator("#timeline-events article", has_text="Keys ceremony")
    ).to_contain_text("Timeline note")

    page.evaluate(f"({register})(() => {{ throw new Error('source broke'); }})")
    playwright_api.expect(timeline_status).to_have_text(
        "Ledger edits not applied: source broke. Showing the standard payment schedule."
    )

    page.evaluate(f"({register})(null)")
    playwright_api.expect(timeline_status).to_be_hidden()
    playwright_api.expect(checkpoint_status).to_be_hidden()
    assert page_errors == []
```

In `tests/test_condo_loan_timeline_planner.py`, change `"assets/condo-loan-timeline-planner.js?v=20260809-4",` to `"assets/condo-loan-timeline-planner.js?v=20260927-1",`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest -q tests/test_condo_loan_timeline_ledger_sync.py::test_ledger_source_must_be_a_function_or_null tests/test_condo_loan_timeline_planner.py`
Expected:
- the ledger-source test fails with a node `TypeError: planner.setFundingLedgerSource is not a function`, which surfaces as `CalledProcessError`;
- the planner static test fails on the script-version set.

Run (sandbox disabled): `python3 -m pytest -q tests/test_condo_loan_timeline_funding_v3_e2e.py -k registered_ledger_source`
Expected: FAIL, because `#timeline-ledger-status` doesn't exist and `to_be_hidden` times out, or `setFundingLedgerSource` is not a function.

- [ ] **Step 3: Add the source API**

In `condo-loan-timeline-planner.js`, insert directly before `  function init(document) {`:

```js
  let fundingLedgerSource = null;

  function setFundingLedgerSource(source) {
    if (source != null && typeof source !== "function") {
      throw new TypeError("funding ledger source must be a function or null");
    }
    fundingLedgerSource = source || null;
  }

```

In the returned API object, add `    setFundingLedgerSource,` between `sellerStampDutyZeroDate,` and `yearFraction,`.

- [ ] **Step 4: Render ledger events and apply the source in `calculate`**

In `eventDetail`, insert as the first statement:

```js
      if (event.type === "ledger") {
        const row = event.row;
        if (row.category === "note") return "Timeline note";
        if (row.category === "cost") return `Cost ${money(row.paymentAmount)}`;
        return `Pay ${money(row.paymentAmount)} · owner ${money(row.paymentAmount - row.loan)} · bank ${money(row.loan)}`;
      }
```

Directly before `    function calculate({ focusResults = false, announce = false } = {}) {` insert:

```js
    function applyFundingLedger(options, standard) {
      if (!fundingLedgerSource) return { result: standard, notice: null };
      let ledger;
      try {
        ledger = fundingLedgerSource(standard);
      } catch (error) {
        return { result: standard, notice: { applied: false, reason: error.message } };
      }
      if (!ledger) return { result: standard, notice: null };
      if (!ledger.rows) {
        return {
          result: standard,
          notice: { applied: false, reason: ledger.reason || "the ledger is unavailable" },
        };
      }
      try {
        return {
          result: buildHoldingProjection({ ...options, fundingLedger: { rows: ledger.rows } }),
          notice: { applied: true },
        };
      } catch (error) {
        return { result: standard, notice: { applied: false, reason: error.message } };
      }
    }

    function renderLedgerSync(notice) {
      const text = !notice
        ? ""
        : notice.applied
          ? "Following your acquisition funding ledger."
          : `Ledger edits not applied: ${notice.reason}. Showing the standard payment schedule.`;
      ["timeline-ledger-status", "checkpoint-ledger-status"].forEach(id => {
        const element = byId(id);
        element.textContent = text;
        element.hidden = !notice;
        element.classList.toggle("ledger-sync-warning", Boolean(notice && !notice.applied));
      });
    }

```

In `calculate`, replace:

```js
        const result = buildHoldingProjection(data.options);
        latest = { data, result };
        render(data.projectName, result, { announce });
```

with:

```js
        const standard = buildHoldingProjection(data.options);
        const { result, notice } = applyFundingLedger(data.options, standard);
        latest = { data, result };
        render(data.projectName, result, { announce });
        renderLedgerSync(notice);
```

After `    form.addEventListener("cpf-effective-change", () => calculate());` add:

```js
    form.addEventListener("funding-ledger-change", () => calculate());
```

- [ ] **Step 5: Add the status elements, their CSS and the version bump**

In `condo_loan_timeline_planner.html`, after the line `  .timeline-wrap { padding:22px 24px 25px; overflow-x:auto; }` add:

```css
  .ledger-sync-status { margin:14px 24px 0; padding:9px 12px; border-radius:8px; background:var(--accent-soft); color:var(--accent-dark); font-size:13px; }
  .ledger-sync-status.ledger-sync-warning { background:var(--warm-soft); color:#704b16; }
```

Directly before `    <div class="timeline-wrap" role="region" aria-label="Scrollable property and loan events" tabindex="0">` insert:

```html
    <p class="ledger-sync-status" id="timeline-ledger-status" role="status" hidden></p>
```

Directly before `    <div class="table-scroll" role="region" aria-label="Scrollable annual condo loan timeline" tabindex="0">` insert:

```html
    <p class="ledger-sync-status" id="checkpoint-ledger-status" role="status" hidden></p>
```

Change `<script src="assets/condo-loan-timeline-planner.js?v=20260809-4"></script>` to `<script src="assets/condo-loan-timeline-planner.js?v=20260927-1"></script>`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest -q tests/test_condo_loan_timeline_ledger_sync.py tests/test_condo_loan_timeline_planner.py tests/test_condo_loan_timeline_funding_v3.py`
Expected: all pass.

Run (sandbox disabled): `python3 -m pytest -q tests/test_condo_loan_timeline_funding_v3_e2e.py`
Expected: all pass (16 existing + 1 new).

- [ ] **Step 7: Commit**

```bash
git add site/assets/condo-loan-timeline-planner.js condo_loan_timeline_planner.html tests/test_condo_loan_timeline_ledger_sync.py tests/test_condo_loan_timeline_funding_v3_e2e.py tests/test_condo_loan_timeline_planner.py
git commit -m "feat(planner): apply a registered funding ledger and explain fallbacks"
```

---

### Task 3: Wire the co-owner ledger to the planner

**Files:**
- Modify: `site/assets/condo-loan-timeline-funding-v3.js`:
  - `collectProjection`, around line 1998;
  - a new `ledgerSyncState` and `ledgerProjection` after `currentLedger`, around line 2076;
  - `render`, around lines 2766–2819;
  - registration before `const restoredDraft = restoreDraft();`, around line 2826.
- Modify: `condo_loan_timeline_planner.html:1039` (funding script version).
- Modify: `tests/test_condo_loan_timeline_planner.py:265` (script version).
- Test: `tests/test_condo_loan_timeline_funding_v3_e2e.py`

**Interfaces:**
- Consumes:
  - `planner.setFundingLedgerSource`;
  - the `funding-ledger-change` listener;
  - `planner.buildHoldingProjection({ ...options, fundingLedger: { rows } })`;
  - the banner texts (Task 2).
- Produces: user-visible sync. Ledger edits recalculate the timeline and checkpoints. Stale or unbalanced ledgers fall back with the reasons in Global Constraints.

- [ ] **Step 1: Write the failing e2e tests**

Append to `tests/test_condo_loan_timeline_funding_v3_e2e.py`:

```python
def _sample_couple_ledger(page, playwright_api) -> None:
    _fill_and_blur(page.locator("#purchase-price"), "1610000")
    _fill_and_blur(page.locator("#loan-amount"), "1207404")
    _open_details(page, "#advanced-cost-details")
    _fill_and_blur(page.locator("#purchase-legal"), "2800")
    page.locator("#acquisition-date").fill("2025-10-25")
    page.locator("#buc-top-date").fill("2028-07-06")
    page.locator("#sale-date").fill("2031-10-25")
    playwright_api.expect(page.locator("#planner-errors")).to_be_hidden()
    page.locator("#partner-enabled").check()
    _apply_couple_setup(
        page,
        borrower="primary",
        amounts={
            "primary_cash": 86_796,
            "primary_cpf": 141_500,
            "partner_cash": 227_700,
            "partner_cpf": 0,
        },
    )


def _year_one_loan_drawn(page):
    return page.locator("#checkpoint-body tr").nth(1).locator("td").nth(1)


def test_ledger_edits_drive_timeline_and_checkpoints(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    _load_clean(page, url)
    _sample_couple_ledger(page, playwright_api)
    applied = "Following your acquisition funding ledger."
    playwright_api.expect(page.locator("#timeline-ledger-status")).to_have_text(applied)
    playwright_api.expect(page.locator("#checkpoint-ledger-status")).to_have_text(applied)
    playwright_api.expect(_year_one_loan_drawn(page)).to_have_text("S$241,404")

    _open_details(page, "#funding-ledger-editor")
    _fill_and_blur(
        page.locator("#funding-ledger-body [data-row-key='stage-3'][data-field='date']"),
        "2026-11-25",
    )

    playwright_api.expect(_year_one_loan_drawn(page)).to_have_text("S$80,404")
    playwright_api.expect(
        page.locator("#timeline-events time[datetime='2026-11-25']")
    ).to_have_count(1)
    playwright_api.expect(
        page.locator("#timeline-events time[datetime='2026-08-25']")
    ).to_have_count(0)

    page.reload(wait_until="load")
    playwright_api.expect(page.locator("#timeline-ledger-status")).to_have_text(applied)
    playwright_api.expect(_year_one_loan_drawn(page)).to_have_text("S$80,404")
    assert page_errors == []


def test_unusable_ledgers_fall_back_with_a_reason(chromium_page) -> None:
    playwright_api = pytest.importorskip("playwright.sync_api")
    page, url = chromium_page
    _load_clean(page, url)
    _sample_couple_ledger(page, playwright_api)
    status = page.locator("#timeline-ledger-status")
    _open_details(page, "#funding-ledger-editor")
    _fill_and_blur(
        page.locator("#funding-ledger-body [data-row-key='stage-3'][data-field='date']"),
        "2026-11-25",
    )
    playwright_api.expect(_year_one_loan_drawn(page)).to_have_text("S$80,404")

    stage_cash = _money_number(
        page.locator("#funding-ledger-body [data-row-key='stage-0'][data-field='primaryCash']")
    )
    _set_ledger_amount(page, "stage-0", "primaryCash", str(stage_cash - 100))
    playwright_api.expect(status).to_have_text(
        "Ledger edits not applied: the ledger does not reconcile — fix the flagged rows."
        " Showing the standard payment schedule."
    )
    playwright_api.expect(_year_one_loan_drawn(page)).to_have_text("S$241,404")

    _set_ledger_amount(page, "stage-0", "primaryCash", str(stage_cash))
    playwright_api.expect(status).to_have_text("Following your acquisition funding ledger.")
    playwright_api.expect(_year_one_loan_drawn(page)).to_have_text("S$80,404")

    _fill_and_blur(page.locator("#purchase-legal"), "3000")
    playwright_api.expect(status).to_have_text(
        "Ledger edits not applied: the main plan changed after you edited the ledger"
        " — update the rows or rebuild the ledger. Showing the standard payment schedule."
    )
    playwright_api.expect(_year_one_loan_drawn(page)).to_have_text("S$241,404")

    page.locator("#partner-enabled").uncheck()
    playwright_api.expect(status).to_be_hidden()
    playwright_api.expect(page.locator("#checkpoint-ledger-status")).to_be_hidden()
    playwright_api.expect(_year_one_loan_drawn(page)).to_have_text("S$241,404")
```

In `tests/test_condo_loan_timeline_planner.py`, change `"assets/condo-loan-timeline-funding-v3.js?v=20260811-1",` to `"assets/condo-loan-timeline-funding-v3.js?v=20260927-1",`.

- [ ] **Step 2: Run the tests to verify they fail**

Run (sandbox disabled): `python3 -m pytest -q tests/test_condo_loan_timeline_funding_v3_e2e.py -k "drive_timeline or fall_back"`
Expected: 2 failed. `#timeline-ledger-status` stays hidden because no source is registered, so `to_have_text("Following your acquisition funding ledger.")` times out.

Run: `python3 -m pytest -q tests/test_condo_loan_timeline_planner.py`
Expected: FAIL on the funding script version.

- [ ] **Step 3: Split the projection options**

In `condo-loan-timeline-funding-v3.js`, change `    function collectProjection() {` to `    function projectionOptions() {`. Inside it, change `      return planner.buildHoldingProjection({` to `      return {`, and change that function's closing `      });` to `      };`. Then add directly after the function:

```js

    function collectProjection() {
      return planner.buildHoldingProjection(projectionOptions());
    }
```

- [ ] **Step 4: Add the sync state and the ledger-applied projection**

Directly after the closing `}` of `function currentLedger(...)`, insert:

```js

    function ledgerSyncState(projection) {
      if (!enabledInput.checked || !coupleSetupComplete || !coupleFundingPlan) return null;
      const state = currentLedger(projection);
      if (state.stale) {
        return {
          reason: "the main plan changed after you edited the ledger — update the rows or rebuild the ledger",
        };
      }
      if (!validateFundingLedger(state.rows, projection).balanced) {
        return { reason: "the ledger does not reconcile — fix the flagged rows" };
      }
      return { rows: state.rows };
    }

    function ledgerProjection(rows, fallback) {
      try {
        return planner.buildHoldingProjection({ ...projectionOptions(), fundingLedger: { rows } });
      } catch {
        // The planner's ledger status line shows this rejection and falls back to the
        // standard projection, so the owner outcome follows the same fallback.
        return fallback;
      }
    }
```

- [ ] **Step 5: Dispatch after every render, and use the applied projection for the CPF and owner outcome**

Change `    function render({ regenerate = false } = {}) {` to `    function renderLedger({ regenerate = false } = {}) {`.

Inside it, replace:

```js
        try {
          renderCpfEstimate(projection, state.rows, {
            cpfWeightsReliable: validation.balanced && !state.stale,
          });
```

with:

```js
        const ledgerApplies = validation.balanced && !state.stale;
        try {
          renderCpfEstimate(
            ledgerApplies ? ledgerProjection(state.rows, projection) : projection,
            state.rows,
            { cpfWeightsReliable: ledgerApplies }
          );
```

Directly after the closing `}` of `renderLedger` (just before `    function scheduleRender() {`), insert:

```js
    function render(options) {
      renderLedger(options);
      form.dispatchEvent(new view.CustomEvent("funding-ledger-change"));
    }

```

Directly before `    const restoredDraft = restoreDraft();` insert:

```js
    planner.setFundingLedgerSource(ledgerSyncState);
```

In `condo_loan_timeline_planner.html`, change `<script src="assets/condo-loan-timeline-funding-v3.js?v=20260811-1"></script>` to `<script src="assets/condo-loan-timeline-funding-v3.js?v=20260927-1"></script>`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest -q tests/test_condo_loan_timeline_ledger_sync.py tests/test_condo_loan_timeline_planner.py tests/test_condo_loan_timeline_funding_v3.py`
Expected: all pass.

Run (sandbox disabled): `python3 -m pytest -q tests/test_condo_loan_timeline_funding_v3_e2e.py`
Expected: all pass (19). If an existing owner-outcome or CPF assertion changes value, stop and check it against the waterfall. With an unedited ledger the applied projection equals the standard one (Task 1, test 2), so no existing value should move.

- [ ] **Step 7: Run the smoke gate and commit**

Run: `make smoke > .superpowers/planner-ledger-sync-smoke.log 2>&1; tail -5 .superpowers/planner-ledger-sync-smoke.log`
Expected: the same result as main. The only known failure is the environmental `test_data_catalog` failure from untracked `data/inputs/bus_*.json`, which is absent in a clean worktree.

```bash
git add site/assets/condo-loan-timeline-funding-v3.js condo_loan_timeline_planner.html tests/test_condo_loan_timeline_funding_v3_e2e.py tests/test_condo_loan_timeline_planner.py
git commit -m "feat(planner): sync the co-owner funding ledger into the projection"
```
