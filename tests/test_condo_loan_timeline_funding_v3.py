"""Exact funding-ledger calculations and static guards for the condo planner."""

from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASE_SCRIPT = ROOT / "site" / "assets" / "condo-loan-timeline-planner.js"
FUNDING_SCRIPT = ROOT / "site" / "assets" / "condo-loan-timeline-funding-v3.js"
V3_PAGE = ROOT / "condo_loan_timeline_planner.html"
STORAGE_KEY = "housing-estate-framework.condo-loan-timeline-planner-v3.draft.v1"


def _run_node(expression: str) -> dict | list:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; V3 ledger calculation tests are skipped")
    program = (
        f"const planner=require({json.dumps(str(BASE_SCRIPT))});"
        f"const funding=require({json.dumps(str(FUNDING_SCRIPT))});"
        f"const value=({expression});"
        "process.stdout.write(JSON.stringify(value));"
    )
    completed = subprocess.run(
        [node, "-e", program],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


SAMPLE_PROJECTION = (
    "planner.buildHoldingProjection({route:'buc',purchasePrice:1610000,"
    "areaSqft:700,acquisitionDate:'2025-10-25',topDate:'2028-07-06',"
    "saleDate:'2031-10-25',loanAmount:1207404,annualRate:3,termMonths:360,"
    "annualGrowthPct:3,sellingCostPct:2.18,absdPaid:0,purchaseLegal:2800,"
    "purchaseOther:0,saleLegal:3000,saleOther:0,holdingCosts:0,netRent:0,"
    "cpfRefund:0})"
)


def test_standard_sample_reconciles_property_loan_equity_and_costs() -> None:
    result = _run_node(
        f"(() => {{const projection={SAMPLE_PROJECTION};"
        "const rows=funding.buildStandardFundingLedger(projection,0);"
        "const validation=funding.validateFundingLedger(rows,projection);"
        "const foundation=validation.rows.find(row=>row.key==='stage-2');"
        "return {balanced:validation.balanced,targets:validation.targets,"
        "totals:validation.totals,differences:validation.differences,"
        "foundation:{payment:foundation.paymentAmount,"
        "owner:funding.ownerFundingAllocation(foundation),loan:foundation.loan},"
        "costs:Object.fromEntries(validation.rows.filter(row=>row.category==='cost')"
        ".map(row=>[row.key,row.paymentAmount]))};})()"
    )

    assert result["balanced"] is True
    assert result["targets"] == {
        "purchasePrice": 1_610_000,
        "loanAmount": 1_207_404,
        "ownerFunding": 402_596,
        "acquisitionCosts": 53_400,
    }
    assert result["foundation"] == {
        "payment": 161_000,
        "owner": 80_596,
        "loan": 80_404,
    }
    assert result["totals"]["considerationPayments"] == pytest.approx(1_610_000)
    assert result["totals"]["considerationLoan"] == pytest.approx(1_207_404)
    assert result["totals"]["considerationOwnerFunding"] == pytest.approx(402_596)
    assert result["totals"]["costPayments"] == pytest.approx(53_400)
    assert all(value == pytest.approx(0) for value in result["differences"].values())
    assert result["costs"] == {
        "cost-purchase-legal": 2_800,
        "cost-bsd": 50_100,
        "cost-mortgage-duty": 500,
    }


def test_exact_sample_allocations_expose_the_missing_mortgage_duty_gap() -> None:
    result = _run_node(
        f"(() => {{const projection={SAMPLE_PROJECTION};"
        "const completeRows=funding.buildStandardFundingLedger(projection,0);"
        "const mortgage=completeRows.find(row=>row.key==='cost-mortgage-duty');"
        "const rows=completeRows.filter(row=>row.key!=='cost-mortgage-duty');"
        "Object.assign(rows.find(row=>row.key==='stage-0'),{"
        "primaryCash:0,partnerCash:80500});"
        "Object.assign(rows.find(row=>row.key==='cost-purchase-legal'),{"
        "primaryCash:0,partnerCash:2800});"
        "Object.assign(rows.find(row=>row.key==='cost-bsd'),{"
        "primaryCash:0,partnerCash:50100});"
        "Object.assign(rows.find(row=>row.key==='stage-1'),{"
        "primaryCash:86296,primaryCpf:60904,partnerCash:94300,partnerCpf:0});"
        "Object.assign(rows.find(row=>row.key==='stage-2'),{"
        "primaryCash:0,primaryCpf:80596,partnerCash:0,partnerCpf:0});"
        "const validation=funding.validateFundingLedger(rows,projection);"
        "const ownerSources=validation.totals.primaryCash+validation.totals.primaryCpf+"
        "validation.totals.partnerCash+validation.totals.partnerCpf;"
        "const complete=funding.validateFundingLedger([...rows,mortgage],projection);"
        "return {balanced:validation.balanced,"
        "rowsBalanced:validation.rows.every(row=>row.balanced),"
        "agreement:validation.rows.find(row=>row.key==='stage-1'),"
        "foundation:validation.rows.find(row=>row.key==='stage-2'),"
        "totals:validation.totals,differences:validation.differences,"
        "mortgage:mortgage.paymentAmount,sampleUpfront:ownerSources,"
        "completeBalanced:complete.balanced,"
        "completeUpfront:ownerSources+mortgage.paymentAmount};})()"
    )

    assert result["balanced"] is False
    assert result["rowsBalanced"] is True
    assert result["agreement"]["paymentAmount"] == 241_500
    assert result["agreement"]["primaryCash"] == 86_296
    assert result["agreement"]["primaryCpf"] == 60_904
    assert result["agreement"]["partnerCash"] == 94_300
    assert result["agreement"]["difference"] == pytest.approx(0)
    assert result["foundation"]["primaryCpf"] == 80_596
    assert result["foundation"]["loan"] == 80_404
    assert result["foundation"]["difference"] == pytest.approx(0)
    assert result["totals"]["primaryCash"] == 86_296
    assert result["totals"]["primaryCpf"] == 141_500
    assert result["totals"]["partnerCash"] == 227_700
    assert result["totals"]["partnerCpf"] == 0
    assert result["totals"]["loan"] == 1_207_404
    assert result["differences"]["acquisitionCosts"] == -500
    assert result["differences"]["costAllocated"] == -500
    assert result["mortgage"] == 500
    assert result["sampleUpfront"] == pytest.approx(455_496)
    assert result["completeBalanced"] is True
    assert result["completeUpfront"] == pytest.approx(455_996)


def test_row_variance_and_global_variance_are_both_detected() -> None:
    result = _run_node(
        f"(() => {{const projection={SAMPLE_PROJECTION};"
        "const shortRows=funding.buildStandardFundingLedger(projection,0);"
        "shortRows.find(row=>row.key==='stage-0').primaryCash-=100;"
        "const short=funding.validateFundingLedger(shortRows,projection);"
        "const missingCostRows=funding.buildStandardFundingLedger(projection,0)"
        ".filter(row=>row.key!=='cost-mortgage-duty');"
        "const global=funding.validateFundingLedger(missingCostRows,projection);"
        "const stage=short.rows.find(row=>row.key==='stage-0');"
        "return {short:{balanced:short.balanced,difference:stage.difference,"
        "issue:stage.issue,purchaseAllocated:short.differences.purchaseAllocated,"
        "ownerFunding:short.differences.ownerFunding},"
        "global:{balanced:global.balanced,rowsBalanced:global.rows.every(row=>row.balanced),"
        "costs:global.differences.acquisitionCosts,"
        "allocated:global.differences.costAllocated}};})()"
    )

    assert result["short"] == {
        "balanced": False,
        "difference": 100,
        "issue": "Funding not fully allocated",
        "purchaseAllocated": -100,
        "ownerFunding": -100,
    }
    assert result["global"] == {
        "balanced": False,
        "rowsBalanced": True,
        "costs": -500,
        "allocated": -500,
    }


def test_cent_level_stage_apportionment_has_no_rounding_drift() -> None:
    result = _run_node(
        "(() => {const projection=planner.buildHoldingProjection({route:'buc',"
        "purchasePrice:1610000.01,areaSqft:700,acquisitionDate:'2025-10-25',"
        "topDate:'2028-07-06',saleDate:'2031-10-25',loanAmount:1207404.01,"
        "annualRate:3,termMonths:360,annualGrowthPct:3,sellingCostPct:2.18,"
        "absdPaid:0,purchaseLegal:2800,purchaseOther:0,saleLegal:3000,"
        "saleOther:0,holdingCosts:0,netRent:0,cpfRefund:0});"
        "const validation=funding.validateFundingLedger("
        "funding.buildStandardFundingLedger(projection,33.3),projection);"
        "let precisionError='';try{funding.makeRow({key:'bad',date:'2026-01-01',"
        "action:'Bad precision',paymentAmount:1.001});}catch(error){"
        "precisionError=error.message;}return {balanced:validation.balanced,"
        "payments:validation.totals.considerationPayments,"
        "loan:validation.totals.considerationLoan,"
        "owner:validation.totals.considerationOwnerFunding,"
        "differences:validation.differences,precisionError};})()"
    )

    assert result["balanced"] is True
    assert result["payments"] == 1_610_000.01
    assert result["loan"] == 1_207_404.01
    assert result["owner"] == 402_596
    assert all(value == 0 for value in result["differences"].values())
    assert "more than two decimal places" in result["precisionError"]


def test_legal_ownership_changes_outcomes_without_mutating_funding() -> None:
    result = _run_node(
        f"(() => {{const projection={SAMPLE_PROJECTION};"
        "const rows=funding.buildStandardFundingLedger(projection,40);"
        "const before=JSON.stringify(rows);"
        "const twenty=funding.splitOutcome(projection,20);"
        "const seventy=funding.splitOutcome(projection,70);"
        "const validation=funding.validateFundingLedger(rows,projection);"
        "return {unchanged:before===JSON.stringify(rows),balanced:validation.balanced,"
        "funding:[validation.totals.primaryCash,validation.totals.partnerCash],"
        "shares:[[twenty.primaryShare,twenty.partnerShare],"
        "[seventy.primaryShare,seventy.partnerShare]],"
        "cashSums:[twenty.primaryCashReleased+twenty.partnerCashReleased,"
        "seventy.primaryCashReleased+seventy.partnerCashReleased],"
        "cashReleased:projection.base.cashReleased};})()"
    )

    assert result["unchanged"] is True
    assert result["balanced"] is True
    assert result["funding"] == pytest.approx([294_957.6, 161_038.4])
    assert result["shares"] == [[80, 20], [30, 70]]
    assert result["cashSums"] == pytest.approx(
        [result["cashReleased"], result["cashReleased"]]
    )


def test_exact_couple_plan_allocates_all_four_owner_sources_and_preserves_loan() -> None:
    result = _run_node(
        f"(() => {{const projection={SAMPLE_PROJECTION};"
        "const rows=funding.buildStandardFundingLedger(projection,0);"
        "const applied=funding.applyFundingPlan(rows,{borrower:'primary',"
        "primaryCash:86796,primaryCpf:141500,partnerCash:227700,partnerCpf:0});"
        "const validation=funding.validateFundingLedger(applied.rows,projection);"
        "return {summary:applied.summary,balanced:validation.balanced,"
        "totals:validation.totals,loanDifference:validation.differences.loan};})()"
    )

    assert result["summary"]["borrower"] == "primary"
    assert result["summary"]["ownerFundingRequired"] == 455_996
    assert result["summary"]["ownerFundingPlanned"] == 455_996
    assert result["summary"]["ownerFundingUsed"] == 455_996
    assert result["summary"]["shortage"] == 0
    assert result["summary"]["excess"] == 0
    assert result["summary"]["balanced"] is True
    assert result["summary"]["sources"] == {
        "primaryCash": {"planned": 86_796, "used": 86_796, "excess": 0},
        "primaryCpf": {"planned": 141_500, "used": 141_500, "excess": 0},
        "partnerCash": {"planned": 227_700, "used": 227_700, "excess": 0},
        "partnerCpf": {"planned": 0, "used": 0, "excess": 0},
    }
    assert result["balanced"] is True
    assert result["totals"]["primaryCash"] == 86_796
    assert result["totals"]["primaryCpf"] == 141_500
    assert result["totals"]["partnerCash"] == 227_700
    assert result["totals"]["partnerCpf"] == 0
    assert result["totals"]["loan"] == 1_207_404
    assert result["loanDifference"] == 0


def test_couple_plan_reports_shortage_and_excess_for_every_borrower_choice() -> None:
    result = _run_node(
        f"(() => {{const projection={SAMPLE_PROJECTION};"
        "const rows=funding.buildStandardFundingLedger(projection,0);"
        "const apply=plan=>funding.applyFundingPlan(rows,plan);"
        "const short=apply({borrower:'joint',primaryCash:455896,primaryCpf:0,"
        "partnerCash:0,partnerCpf:0});"
        "const excess=apply({borrower:'partner',primaryCash:456096,primaryCpf:0,"
        "partnerCash:0,partnerCpf:0});"
        "const shortLedger=funding.validateFundingLedger(short.rows,projection);"
        "const excessLedger=funding.validateFundingLedger(excess.rows,projection);"
        "const borrowers=['joint','primary','partner'].map(borrower=>"
        "funding.validateFundingPlan({borrower,primaryCash:1,primaryCpf:2,"
        "partnerCash:3,partnerCpf:4}).borrower);"
        "let invalid='';try{funding.validateFundingPlan({borrower:'guarantor',"
        "primaryCash:1,primaryCpf:2,partnerCash:3,partnerCpf:4});}"
        "catch(error){invalid=error.message;}"
        "return {short:short.summary,excess:excess.summary,"
        "shortLedger:shortLedger.balanced,excessLedger:excessLedger.balanced,"
        "borrowers,invalid};})()"
    )

    assert result["short"]["borrower"] == "joint"
    assert result["short"]["shortage"] == 100
    assert result["short"]["excess"] == 0
    assert result["short"]["balanced"] is False
    assert result["shortLedger"] is False
    assert result["excess"]["borrower"] == "partner"
    assert result["excess"]["shortage"] == 0
    assert result["excess"]["excess"] == 100
    assert result["excess"]["balanced"] is False
    assert result["excessLedger"] is True
    assert result["borrowers"] == ["joint", "primary", "partner"]
    assert "joint, primary or partner" in result["invalid"]


def test_v3_exports_a_versioned_browser_draft_key() -> None:
    result = _run_node("({storageKey:funding.STORAGE_KEY})")

    assert result == {"storageKey": STORAGE_KEY}


class _StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.labels: set[str] = set()
        self.scripts: list[str] = []
        self.details: dict[str, bool] = {}

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "label" and values.get("for"):
            self.labels.add(values["for"])
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        if tag == "details" and values.get("id"):
            self.details[values["id"]] = "open" in values


def test_planner_structure_and_script_dependencies_are_explicit() -> None:
    v3_html = V3_PAGE.read_text(encoding="utf-8")
    parser = _StructureParser()
    parser.feed(v3_html)

    assert "condo-loan-timeline-partner-v2.js" not in v3_html
    assert len(parser.ids) == len(set(parser.ids)), "V3 HTML ids must be unique"
    assert parser.details == {
        "property-loan-details": False,
        "partner-settings": False,
        "advanced-cost-details": False,
    }
    assert {source.split("?", 1)[0] for source in parser.scripts} == {
        "assets/condo-loan-timeline-planner.js",
        "assets/condo-loan-timeline-funding-v3.js",
        "assets/research-shell.js",
    }
    for input_id in (
        "partner-enabled",
        "partner-ownership-share",
        "loan-borrower-joint",
        "loan-borrower-primary",
        "loan-borrower-partner",
        "couple-primary-name",
        "couple-partner-name",
        "couple-primary-cash",
        "couple-primary-cpf",
        "couple-partner-cash",
        "couple-partner-cpf",
    ):
        assert input_id in parser.labels
    for required_id in (
        "funding-ledger-card",
        "funding-ledger-body",
        "funding-ledger-errors",
        "ledger-overall-status",
        "ledger-cost-reconciliation",
        "ledger-difference-footer",
        "regenerate-funding-ledger",
        "add-funding-row",
        "draft-save-status",
        "couple-funding-dialog",
        "couple-funding-form",
        "couple-dialog-close",
        "couple-dialog-cancel",
        "couple-dialog-apply",
        "couple-required-funding",
        "couple-entered-funding",
        "couple-funding-difference",
        "couple-funding-errors",
        "edit-couple-funding",
        "ledger-loan-heading",
        "ledger-loan-column-heading",
    ):
        assert required_id in parser.ids
