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


def test_resale_payment_after_the_sale_is_rejected() -> None:
    result = _run_node(
        f"const options={RESALE};const rows=ledgerFor(options);"
        "return rejection(()=>project(options,edit(rows,'resale-completion',{date:'2030-06-01'})));"
    )

    assert result == "a resale purchase payment cannot fall after the planned sale"


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
