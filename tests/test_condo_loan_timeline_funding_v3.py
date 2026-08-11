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
STORAGE_KEY = "housing-estate-framework.condo-loan-timeline-planner-v3.draft.v2"
LEGACY_STORAGE_KEY = "housing-estate-framework.condo-loan-timeline-planner-v3.draft.v1"


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


def test_owner_sale_outcome_reconciles_legal_and_individual_cpf_allocations() -> None:
    projection = SAMPLE_PROJECTION.replace("cpfRefund:0", "cpfRefund:100000")
    result = _run_node(
        f"(() => {{const projection={projection};"
        "const outcome=funding.buildOwnerSaleOutcome({projection,partnerEnabled:true,"
        "partnerOwnershipPct:40,cpfWeightsReliable:true,cpfEstimate:{"
        "primary:{refundRequired:80000},partner:{refundRequired:20000}}});"
        "return {outcome,cash:projection.base.cashReleased,"
        "available:projection.base.cpfRefundAvailable,"
        "interest:projection.loanAtSale.totalInterestToRedemption,"
        "economic:projection.base.economicProfit};})()"
    )
    outcome = result["outcome"]

    assert outcome["cpfAllocationKnown"] is True
    assert outcome["cpfAllocationBasis"] == "estimated-p-and-i-ratio"
    assert outcome["primary"]["share"] == 60
    assert outcome["partner"]["share"] == 40
    assert outcome["primary"]["signedCash"] + outcome["partner"][
        "signedCash"
    ] == pytest.approx(outcome["household"]["cashReleased"])
    assert outcome["primary"]["combinedValue"] == pytest.approx(
        outcome["household"]["combinedValue"] * 0.6,
        abs=0.01,
    )
    assert outcome["partner"]["combinedValue"] == pytest.approx(
        outcome["household"]["combinedValue"] * 0.4,
        abs=0.01,
    )
    assert outcome["primary"]["cpfAvailable"] == pytest.approx(
        result["available"] * 0.8,
        abs=0.01,
    )
    assert outcome["primary"]["cpfAvailable"] + outcome["partner"][
        "cpfAvailable"
    ] == pytest.approx(result["available"])
    for owner in (outcome["primary"], outcome["partner"]):
        assert owner["signedCash"] + owner["cpfAvailable"] == pytest.approx(
            owner["combinedValue"]
        )
    assert outcome["primary"]["bankInterest"] + outcome["partner"][
        "bankInterest"
    ] == pytest.approx(result["interest"])
    assert outcome["primary"]["economicProfit"] + outcome["partner"][
        "economicProfit"
    ] == pytest.approx(result["economic"])
    assert outcome["primary"]["combinedValue"] + outcome["partner"][
        "combinedValue"
    ] == pytest.approx(outcome["household"]["combinedValue"])


def test_owner_sale_outcome_splits_combined_value_before_each_owners_cpf() -> None:
    result = _run_node(
        "(() => {const projection={cpfRefund:154286,acquisitionCosts:0,"
        "holdingCosts:0,netRent:0,base:{cashReleased:429266,"
        "cpfRefundAvailable:154286,saleCosts:0,ssd:0,economicProfit:0},"
        "loanAtSale:{totalInterestToRedemption:0}};"
        "return funding.buildOwnerSaleOutcome({projection,partnerEnabled:true,"
        "partnerOwnershipPct:50,cpfWeightsReliable:true,cpfEstimate:{"
        "primary:{refundRequired:154286},partner:{refundRequired:0}}});})()"
    )

    assert result["household"]["cashReleased"] == 429_266
    assert result["household"]["cpfAvailable"] == 154_286
    assert result["household"]["combinedValue"] == 583_552
    assert result["primary"]["combinedValue"] == 291_776
    assert result["partner"]["combinedValue"] == 291_776
    assert result["primary"]["cpfAvailable"] == 154_286
    assert result["partner"]["cpfAvailable"] == 0
    assert result["primary"]["signedCash"] == 137_490
    assert result["partner"]["signedCash"] == 291_776
    for owner in (result["primary"], result["partner"]):
        assert owner["signedCash"] + owner["cpfAvailable"] == owner["combinedValue"]


def test_owner_sale_outcome_handles_shortfall_rounding_and_unknown_cpf_split() -> None:
    projection = SAMPLE_PROJECTION.replace("cpfRefund:0", "cpfRefund:9999999")
    result = _run_node(
        f"(() => {{const projection={projection};"
        "const estimate={primary:{refundRequired:3},partner:{refundRequired:1}};"
        "const known=funding.buildOwnerSaleOutcome({projection,partnerEnabled:true,"
        "partnerOwnershipPct:100,cpfWeightsReliable:true,cpfEstimate:estimate});"
        "const unknown=funding.buildOwnerSaleOutcome({projection,partnerEnabled:true,"
        "partnerOwnershipPct:50,cpfWeightsReliable:false,cpfEstimate:estimate});"
        "const suppressed=funding.buildOwnerSaleOutcome({projection,partnerEnabled:false,"
        "partnerOwnershipPct:0,cpfWeightsReliable:true,suppressCpfAllocation:true,"
        "cpfEstimate:estimate});return {known,unknown,suppressed};})()"
    )
    known = result["known"]
    unknown = result["unknown"]

    assert known["primary"]["combinedValue"] == 0
    assert known["primary"]["signedCash"] == -known["primary"]["cpfAvailable"]
    assert known["primary"]["equalisationGap"] == known["primary"]["cpfAvailable"]
    assert known["primary"]["signedCash"] + known["partner"][
        "signedCash"
    ] == pytest.approx(known["household"]["cashReleased"])
    for owner in (known["primary"], known["partner"]):
        assert owner["signedCash"] + owner["cpfAvailable"] == pytest.approx(
            owner["combinedValue"]
        )
    for key in ("cpfRequired", "cpfAvailable", "cpfShortfall"):
        assert known["primary"][key] + known["partner"][key] == pytest.approx(
            known["household"][key]
        )
    assert known["primary"]["cpfRequired"] == pytest.approx(
        known["primary"]["cpfAvailable"] + known["primary"]["cpfShortfall"]
    )
    assert known["partner"]["cpfRequired"] == pytest.approx(
        known["partner"]["cpfAvailable"] + known["partner"]["cpfShortfall"]
    )
    assert unknown["cpfAllocationKnown"] is False
    assert unknown["cpfAllocationBasis"] == "unavailable"
    assert unknown["primary"]["cpfAvailable"] is None
    assert unknown["primary"]["signedCash"] is None
    assert unknown["partner"]["signedCash"] is None
    assert unknown["partner"]["combinedValue"] is not None
    assert unknown["primary"]["combinedValue"] + unknown["partner"][
        "combinedValue"
    ] == pytest.approx(unknown["household"]["combinedValue"])
    assert result["suppressed"]["cpfAllocationKnown"] is False
    assert result["suppressed"]["primary"]["cpfAvailable"] is None
    assert result["suppressed"]["primary"]["signedCash"] is None
    assert result["suppressed"]["primary"]["combinedValue"] == pytest.approx(
        result["suppressed"]["household"]["combinedValue"]
    )


def test_unreliable_automatic_zero_suppresses_provisional_owner_routing() -> None:
    result = _run_node(
        "(() => {const projection={cpfRefund:0,acquisitionCosts:0,holdingCosts:0,"
        "netRent:0,base:{cashReleased:400000,cpfRefundAvailable:0,saleCosts:0,"
        "ssd:0,economicProfit:0},loanAtSale:{totalInterestToRedemption:0}};"
        "return funding.buildOwnerSaleOutcome({projection,partnerEnabled:true,"
        "partnerOwnershipPct:50,cpfWeightsReliable:false,suppressCpfAllocation:true,"
        "cpfEstimate:{primary:{refundRequired:10000},"
        "partner:{refundRequired:5000}}});})()"
    )

    assert result["cpfAllocationKnown"] is False
    assert result["primary"]["cpfAvailable"] is None
    assert result["primary"]["signedCash"] is None
    assert result["partner"]["signedCash"] is None


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
    result = _run_node(
        "({storageKey:funding.STORAGE_KEY,legacyStorageKey:funding.LEGACY_STORAGE_KEY,"
        "storageVersion:funding.STORAGE_VERSION,"
        "versionDatabase:funding.VERSION_DATABASE})"
    )

    assert result == {
        "storageKey": STORAGE_KEY,
        "legacyStorageKey": LEGACY_STORAGE_KEY,
        "storageVersion": 2,
        "versionDatabase": "housing-estate-framework.condo-loan-timeline-planner-v3",
    }


def test_cpf_refund_resolution_distinguishes_blank_auto_from_exact_zero() -> None:
    result = _run_node(
        "(() => ({"
        "automatic:funding.resolveCpfRefundAmount({exactRefund:null,"
        "estimatedRefund:154286.294,automaticReliable:true,"
        "lastReliableAutoRefund:null}),"
        "exactZero:funding.resolveCpfRefundAmount({exactRefund:0,"
        "estimatedRefund:154286.29,automaticReliable:true,"
        "lastReliableAutoRefund:120000}),"
        "retained:funding.resolveCpfRefundAmount({exactRefund:null,"
        "estimatedRefund:170000,automaticReliable:false,"
        "lastReliableAutoRefund:154286.29}),"
        "unavailable:funding.resolveCpfRefundAmount({exactRefund:null,"
        "estimatedRefund:170000,automaticReliable:false,"
        "lastReliableAutoRefund:null})}))()"
    )

    assert result["automatic"] == {
        "mode": "auto",
        "activeRefund": 154_286.29,
        "lastReliableAutoRefund": 154_286.29,
        "automaticReliable": True,
    }
    assert result["exactZero"]["mode"] == "exact"
    assert result["exactZero"]["activeRefund"] == 0
    assert result["retained"]["activeRefund"] == 154_286.29
    assert result["retained"]["automaticReliable"] is False
    assert result["unavailable"]["activeRefund"] == 0
    assert result["unavailable"]["lastReliableAutoRefund"] is None


def test_portable_draft_envelope_is_versioned_and_strict() -> None:
    result = _run_node(
        "(() => {const draft={schemaVersion:2,form:{values:{},checks:{}},"
        "savedAt:'2026-08-09T01:02:03.000Z'};"
        "const envelope=funding.createDraftExport(draft,'Base 3% plan',"
        "'2026-08-09T02:03:04.000Z');"
        "const parsed=funding.parseDraftExport(JSON.stringify(envelope));"
        "let future='';try{funding.parseDraftExport(JSON.stringify({"
        "...envelope,formatVersion:2}));}catch(error){future=error.message;}"
        "let unknown='';try{funding.parseDraftExport(JSON.stringify({"
        "...envelope,unexpected:true}));}catch(error){unknown=error.message;}"
        "let oversized='';try{funding.parseDraftExport('x'.repeat(1000001));}"
        "catch(error){oversized=error.message;}"
        "return {envelope,parsedName:parsed.name,future,unknown,oversized};})()"
    )

    assert result["envelope"]["format"] == (
        "housing-estate-framework.condo-loan-timeline"
    )
    assert result["envelope"]["formatVersion"] == 1
    assert result["envelope"]["calculatorVersion"] == "3.2.0"
    assert result["envelope"]["kind"] == "draft"
    assert result["parsedName"] == "Base 3% plan"
    assert "format version" in result["future"]
    assert "unsupported fields" in result["unknown"]
    assert "too large" in result["oversized"]


def test_decision_lab_handoff_is_explicit_versioned_and_strict() -> None:
    result = _run_node(
        "(() => {const valid=funding.parseDecisionLabHandoff("
        "'?from=project-exit&project=The%20LakeGarden%20Residences'"
        "+'&purchasePrice=1000000&purchaseDate=2023-08-08'"
        "+'&saleDate=2026-09-08&datePrecision=month&annualGrowth=3&sellingRate=2.18'"
        "+'&saleCosts=3000&areaSqft=527');"
        "const legacy=funding.parseDecisionLabHandoff("
        "'?from=project-exit&project=Legacy&purchasePrice=1000000'"
        "+'&purchaseDate=2023-08-01&saleDate=2026-09-01&annualGrowth=3'"
        "+'&sellingRate=2.18&saleCosts=3000&areaSqft=527');"
        "const unrelated=funding.parseDecisionLabHandoff('?from=another-tool');"
        "let badDate='';try{funding.parseDecisionLabHandoff("
        "'?from=project-exit&project=Example&purchasePrice=1000000'"
        "+'&purchaseDate=2026-02-30&saleDate=2030-01-01&annualGrowth=3'"
        "+'&sellingRate=2.18&saleCosts=3000&areaSqft=527');}"
        "catch(error){badDate=error.message;}"
        "let badRate='';try{funding.parseDecisionLabHandoff("
        "'?from=project-exit&project=Example&purchasePrice=1000000'"
        "+'&purchaseDate=2026-01-01&saleDate=2030-01-01&annualGrowth=3'"
        "+'&sellingRate=21&saleCosts=3000&areaSqft=527');}"
        "catch(error){badRate=error.message;}"
        "let badPrecision='';try{funding.parseDecisionLabHandoff("
        "'?from=project-exit&project=Example&purchasePrice=1000000'"
        "+'&purchaseDate=2026-01-01&saleDate=2030-01-01&datePrecision=guess'"
        "+'&annualGrowth=3&sellingRate=2.18&saleCosts=3000&areaSqft=527');}"
        "catch(error){badPrecision=error.message;}"
        "return {valid,legacy,unrelated,badDate,badRate,badPrecision};})()"
    )

    assert result["valid"] == {
        "project": "The LakeGarden Residences",
        "purchasePrice": 1_000_000,
        "purchaseDate": "2023-08-08",
        "saleDate": "2026-09-08",
        "datePrecision": "month",
        "annualGrowth": 3,
        "sellingRate": 2.18,
        "saleCosts": 3_000,
        "areaSqft": 527,
    }
    assert result["legacy"]["datePrecision"] == "month"
    assert result["unrelated"] is None
    assert "purchaseDate date is invalid" in result["badDate"]
    assert "sellingRate value is invalid" in result["badRate"]
    assert "datePrecision value is invalid" in result["badPrecision"]


def test_cpf_refund_estimate_uses_dated_owner_allocations_before_sale_only() -> None:
    result = _run_node(
        f"(() => {{const projection={SAMPLE_PROJECTION};"
        "const ledgerRows=["
        "{date:'2030-10-25',primaryCpf:100000,partnerCpf:0},"
        "{date:'2031-10-25',primaryCpf:0,partnerCpf:50000},"
        "{date:'2032-01-01',primaryCpf:99999,partnerCpf:88888}];"
        "const estimate=funding.buildCpfRefundEstimate({projection,ledgerRows,"
        "partnerEnabled:true,primaryAcquisitionCpf:77777,primaryMonthlyCpf:0,"
        "partnerMonthlyCpf:0,annualRatePct:2.5});"
        "return estimate;})()"
    )

    expected_primary = 100_000 * 1.025 ** (365 / 365.2425)
    assert result["acquisitionSource"] == "ledger"
    assert result["primary"]["principal"] == 100_000
    assert result["primary"]["refundRequired"] == pytest.approx(expected_primary)
    assert result["partner"] == pytest.approx({
        "usageCount": 1,
        "annualRatePct": 2.5,
        "principal": 50_000,
        "accruedInterest": 0,
        "refundRequired": 50_000,
    })
    assert result["household"]["principal"] == 150_000
    assert result["household"]["usageCount"] == 2


def test_monthly_cpf_estimate_does_not_change_bank_interest() -> None:
    result = _run_node(
        f"(() => {{const projection={SAMPLE_PROJECTION};"
        "const before=projection.loanAtSale.totalInterestToRedemption;"
        "const estimate=funding.buildCpfRefundEstimate({projection,ledgerRows:[],"
        "partnerEnabled:true,primaryMonthlyCpf:100,partnerMonthlyCpf:50,"
        "annualRatePct:2.5});return {before,"
        "after:projection.loanAtSale.totalInterestToRedemption,estimate};})()"
    )

    assert result["after"] == pytest.approx(result["before"])
    assert result["estimate"]["mortgageMonths"] > 0
    assert result["estimate"]["cappedMonths"] == 0
    assert result["estimate"]["household"]["principal"] == pytest.approx(
        result["estimate"]["mortgageMonths"] * 150
    )
    assert result["estimate"]["household"]["accruedInterest"] > 0


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
        "cpf-assumptions-details": False,
        "plan-versions-details": False,
        "funding-ledger-editor": False,
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
        "funding-ledger-editor",
        "funding-ledger-editor-summary",
        "funding-ledger-scroll-hint",
        "review-funding-ledger",
        "financing-interest-card",
        "bank-interest-paid",
        "bank-interest-accrued",
        "bank-interest-total",
        "bank-principal-outstanding",
        "bank-redemption-total",
        "cpf-household-principal",
        "cpf-household-interest",
        "cpf-estimated-refund",
        "cpf-estimated-available",
        "cpf-estimated-shortfall",
        "cpf-applied-refund",
        "cpf-refund-exact",
        "use-automatic-cpf",
        "version-name",
        "save-plan-version",
        "saved-version-select",
        "load-plan-version",
        "delete-plan-version",
        "export-plan-draft",
        "import-plan-draft",
        "import-plan-file",
        "version-manager-status",
        "owner-sale-outcome",
        "owner-outcome-primary-card",
        "owner-outcome-partner-card",
        "owner-outcome-primary-cash",
        "owner-outcome-primary-cpf",
        "owner-outcome-primary-combined",
        "owner-outcome-primary-bank-interest",
        "owner-outcome-primary-costs",
        "owner-outcome-primary-profit",
        "owner-outcome-household-cash",
        "owner-outcome-household-cpf",
        "owner-outcome-household-combined",
        "owner-outcome-status",
    ):
        assert required_id in parser.ids
