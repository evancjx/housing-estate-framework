"""Calculation and static-page guards for the condo timeline planner."""

from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "site" / "assets" / "condo-loan-timeline-planner.js"
PAGE = ROOT / "condo_loan_timeline_planner.html"


def _run_node(expression: str) -> dict | list:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; browser calculation tests are skipped")
    program = (
        f"const planner = require({json.dumps(str(SCRIPT))});"
        f"const value = ({expression});"
        "process.stdout.write(JSON.stringify(value));"
    )
    completed = subprocess.run(
        [node, "-e", program],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_currency_inputs_accept_symbols_commas_decimals_and_raw_digits() -> None:
    result = _run_node(
        "[planner.parseCurrency('$1,207,404.00'),"
        "planner.parseCurrency('S$ 1,207,404.50'),"
        "planner.parseCurrency('1207404'),"
        "planner.parseCurrency('',{allowBlank:true})]"
    )

    assert result == [1207404, 1207404.5, 1207404, None]


def test_bsd_and_ssd_use_current_tiers_and_exact_anniversaries() -> None:
    result = _run_node(
        "({bsd:planner.calculateBSD(1600000,'2026-08-08'),"
        "old:[planner.sellerStampDutyRate('2023-08-05','2026-08-04'),"
        "planner.sellerStampDutyRate('2023-08-05','2026-08-05')],"
        "revised:['2026-08-01','2026-08-02','2027-08-02','2028-08-02',"
        "'2029-08-02'].map(date=>planner.sellerStampDutyRate('2025-08-02',date)),"
        "zero:planner.sellerStampDutyZeroDate('2025-08-02')})"
    )

    assert result == {
        "bsd": 49600,
        "old": [0.04, 0],
        "revised": [0.16, 0.12, 0.08, 0.04, 0],
        "zero": "2029-08-02",
    }


def test_resale_projection_reconciles_loan_equity_profit_and_cash_proceeds() -> None:
    result = _run_node(
        "(() => {const r=planner.buildHoldingProjection({"
        "route:'resale',purchasePrice:1200000,areaSqft:700,"
        "acquisitionDate:'2026-01-01',completionDate:'2026-01-01',"
        "saleDate:'2031-01-01',loanAmount:900000,annualRate:3,termMonths:300,"
        "annualGrowthPct:3,sellingCostPct:2.18,absdPaid:0,purchaseLegal:3000,"
        "purchaseOther:0,saleLegal:3000,saleOther:0,holdingCosts:0,netRent:0,"
        "cpfRefund:0}); return {sale:r.base.salePrice,cagr:r.base.grossCagr,"
        "payments:r.loanAtSale.paymentCount,first:r.schedule.rows[0].scheduledPayment,"
        "drawn:r.loanAtSale.drawn,balance:r.loanAtSale.balance,"
        "principal:r.loanAtSale.principalPaid,interest:r.loanAtSale.interestPaid,"
        "grossEquity:r.base.grossEquity,grossGain:r.base.grossGain,"
        "ownerPaid:r.ownerPropertyPaid,economic:r.base.economicProfit,"
        "cashBefore:r.base.cashBeforeCpf,outflow:r.base.ownerOutflow};})()"
    )

    assert result["sale"] == pytest.approx(1_391_104.965473938)
    assert result["cagr"] == pytest.approx(0.03, abs=1e-12)
    assert result["payments"] == 60
    assert result["first"] == pytest.approx(4267.90182472)
    assert result["drawn"] == 900000
    assert result["balance"] + result["principal"] == pytest.approx(900000)
    assert result["grossEquity"] == pytest.approx(
        result["ownerPaid"] + result["principal"] + result["grossGain"]
    )
    assert result["economic"] == pytest.approx(
        result["cashBefore"] - result["outflow"]
    )


def test_buc_exit_excludes_future_draws_and_deducts_uncalled_developer_balance() -> None:
    result = _run_node(
        "(() => {const r=planner.buildHoldingProjection({"
        "route:'buc',purchasePrice:1000000,areaSqft:527,"
        "acquisitionDate:'2026-01-01',topDate:'2029-01-01',saleDate:'2027-02-01',"
        "loanAmount:750000,annualRate:3.65,termMonths:300,annualGrowthPct:3,"
        "sellingCostPct:2.18,absdPaid:0,purchaseLegal:3000,purchaseOther:0,"
        "saleLegal:3000,saleOther:2000,holdingCosts:0,netRent:0,cpfRefund:0});"
        "return {percents:r.plan.stages.reduce((t,s)=>t+s.percent,0),"
        "allDraws:r.plan.draws.reduce((t,d)=>t+d.amount,0),"
        "allOwner:r.plan.stages.reduce((t,s)=>t+s.ownerContribution,0),"
        "drawnAtSale:r.loanAtSale.drawn,uncalled:r.uncalledDeveloperBalance,"
        "called:r.calledAmount,balance:r.loanAtSale.balance,"
        "principal:r.loanAtSale.principalPaid,grossEquity:r.base.grossEquity,"
        "grossGain:r.base.grossGain,ownerPaid:r.ownerPropertyPaid,"
        "future:r.plan.draws.filter(d=>d.date>r.saleDate).reduce((t,d)=>t+d.amount,0),"
        "warning:r.warnings.join(' ')};})()"
    )

    assert result["percents"] == 100
    assert result["allDraws"] == pytest.approx(750000)
    assert result["allOwner"] == pytest.approx(250000)
    assert result["drawnAtSale"] < result["allDraws"]
    assert result["future"] > 0
    assert result["called"] + result["uncalled"] == pytest.approx(1000000)
    assert result["balance"] + result["principal"] == pytest.approx(
        result["drawnAtSale"]
    )
    assert result["grossEquity"] == pytest.approx(
        result["ownerPaid"] + result["principal"] + result["grossGain"]
    )
    assert "before TOP" in result["warning"]


def test_route_changes_do_not_mutate_shared_financing_inputs_in_the_model() -> None:
    result = _run_node(
        "(() => {const shared={purchasePrice:1700000,areaSqft:700,"
        "acquisitionDate:'2026-08-08',saleDate:'2031-08-08',loanAmount:1207404,"
        "annualRate:3,termMonths:360,annualGrowthPct:3,sellingCostPct:2.18,"
        "absdPaid:0,purchaseLegal:3000,purchaseOther:0,saleLegal:3000,"
        "saleOther:0,holdingCosts:0,netRent:0,cpfRefund:0};"
        "const buc=planner.buildHoldingProjection({...shared,route:'buc',topDate:'2030-08-08'});"
        "const resale=planner.buildHoldingProjection({...shared,route:'resale',"
        "completionDate:'2026-10-08'}); return {buc:buc.loanAmount,resale:resale.loanAmount};})()"
    )

    assert result == {"buc": 1207404, "resale": 1207404}


def test_exact_sale_date_includes_accrued_redemption_interest() -> None:
    result = _run_node(
        "(() => {const schedule=planner.buildLoanSchedule({annualRate:3,termMonths:300,"
        "draws:[{date:'2026-01-01',amount:900000}]});"
        "return ['2026-01-31','2026-02-01','2026-02-15'].map(date=>{"
        "const row=planner.loanSnapshot(schedule,date);return {date,"
        "payments:row.paymentCount,paid:row.interestPaid,accrued:row.accruedInterest,"
        "total:row.totalInterestToRedemption,balance:row.balance,"
        "redemption:row.redemptionAmount};});})()"
    )

    assert [row["payments"] for row in result] == [0, 1, 1]
    assert [row["paid"] for row in result] == pytest.approx([0, 2250, 2250])
    assert result[0]["accrued"] > 0
    assert result[1]["accrued"] == pytest.approx(0)
    assert result[2]["accrued"] > 0
    for row in result:
        assert row["total"] == pytest.approx(row["paid"] + row["accrued"])
        assert row["redemption"] == pytest.approx(row["balance"] + row["accrued"])


def test_redemption_interest_handles_a_progressive_draw_after_last_payment() -> None:
    result = _run_node(
        "(() => {const schedule=planner.buildLoanSchedule({annualRate:3,termMonths:300,"
        "draws:[{date:'2026-01-01',amount:100000},{date:'2026-02-10',amount:50000},"
        "{date:'2026-03-10',amount:25000}]});const row=planner.loanSnapshot(schedule,'2026-02-20');"
        "const afterFirst=schedule.rows[0].endingBalance;"
        "const expected=afterFirst*.03*9/365.2425+(afterFirst+50000)*.03*10/365.2425;"
        "return {drawn:row.drawn,accrued:row.accruedInterest,expected,"
        "balance:row.balance,futureExcluded:row.drawn<175000};})()"
    )

    assert result["drawn"] == 150_000
    assert result["futureExcluded"] is True
    assert result["accrued"] == pytest.approx(result["expected"])


def test_interest_and_cpf_refund_are_each_applied_once_at_sale() -> None:
    result = _run_node(
        "(() => {const common={route:'resale',purchasePrice:1200000,areaSqft:700,"
        "acquisitionDate:'2026-01-01',completionDate:'2026-01-01',"
        "saleDate:'2031-01-15',loanAmount:900000,annualRate:3,termMonths:300,"
        "annualGrowthPct:3,sellingCostPct:2.18,absdPaid:0,purchaseLegal:3000,"
        "purchaseOther:0,saleLegal:3000,saleOther:0,holdingCosts:0,netRent:0};"
        "const none=planner.buildHoldingProjection({...common,cpfRefund:0});"
        "const large=planner.buildHoldingProjection({...common,cpfRefund:9999999});"
        "return {interest:none.loanAtSale.totalInterestToRedemption,"
        "parts:none.loanAtSale.interestPaid+none.loanAtSale.accruedInterest,"
        "identity:none.base.cashBeforeCpf-none.base.ownerOutflow,"
        "economic:none.base.economicProfit,largeEconomic:large.base.economicProfit,"
        "available:large.base.cpfRefundAvailable,"
        "proceedsBase:large.base.cpfRefundProceedsBase,"
        "preCpf:large.base.cashBeforeCpf,"
        "shortfall:large.base.cpfRefundShortfall,cash:large.base.cashReleased};})()"
    )

    assert result["interest"] == pytest.approx(result["parts"])
    assert result["economic"] == pytest.approx(result["identity"])
    assert result["largeEconomic"] == pytest.approx(result["economic"])
    assert result["available"] == pytest.approx(result["proceedsBase"])
    assert result["shortfall"] > 0
    assert result["cash"] == pytest.approx(
        result["preCpf"] - result["proceedsBase"]
    )


def test_cpf_refund_precedes_other_sale_costs_in_the_proceeds_waterfall() -> None:
    result = _run_node(
        "(() => {const r=planner.buildHoldingProjection({"
        "route:'resale',purchasePrice:1000000,areaSqft:700,"
        "acquisitionDate:'2023-01-01',completionDate:'2023-01-01',"
        "saleDate:'2027-01-01',loanAmount:900000,annualRate:0,termMonths:360,"
        "annualGrowthPct:0,sellingCostPct:0,absdPaid:0,purchaseLegal:0,"
        "purchaseOther:0,saleLegal:15000,saleOther:5000,holdingCosts:0,"
        "netRent:0,cpfRefund:9999999});return {sale:r.base.salePrice,"
        "redemption:r.loanAtSale.redemptionAmount,costs:r.base.saleCosts,"
        "available:r.base.cpfRefundAvailable,"
        "proceedsBase:r.base.cpfRefundProceedsBase,"
        "preCpf:r.base.cashBeforeCpf,cash:r.base.cashReleased};})()"
    )

    assert result["proceedsBase"] == pytest.approx(
        result["sale"] - result["redemption"]
    )
    assert result["available"] == pytest.approx(result["proceedsBase"])
    assert result["preCpf"] == pytest.approx(
        result["proceedsBase"] - result["costs"]
    )
    assert result["cash"] == pytest.approx(-result["costs"])


class _StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.labels: set[str] = set()
        self.scripts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "label" and values.get("for"):
            self.labels.add(values["for"])
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"])
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])


def test_page_is_labelled_local_responsive_and_uses_official_sources() -> None:
    html = PAGE.read_text(encoding="utf-8")
    parser = _StructureParser()
    parser.feed(html)

    assert len(parser.ids) == len(set(parser.ids)), "HTML ids must be unique"
    assert set(parser.scripts) == {
        "assets/condo-loan-timeline-planner.js?v=20260808-3",
        "assets/condo-loan-timeline-funding-v3.js?v=20260809-3",
        "assets/research-shell.js",
    }
    for input_id in (
        "route-buc",
        "route-resale",
        "purchase-price",
        "loan-amount",
        "acquisition-date",
        "buc-top-date",
        "resale-completion-date",
        "annual-growth",
        "sale-date",
        "selling-cost-percent",
        "cpf-primary-acquisition",
        "cpf-primary-monthly",
        "cpf-partner-monthly",
        "cpf-oa-rate",
        "cpf-refund",
    ):
        assert input_id in parser.labels
    assert 'id="planner-errors" role="alert" aria-live="polite" hidden' in html
    assert 'class="table-scroll" role="region"' in html
    assert "uncalled developer payments" in html.lower()
    assert "cash released is not investment profit" in html.lower()
    assert "entries stay in this browser" in html
    assert html.count("data-currency-input") >= 10
    assert all(
        not link.startswith("http")
        or any(domain in link for domain in (
            "ura.gov.sg", "iras.gov.sg", "moneysense.gov.sg", "cpf.gov.sg",
        ))
        for link in parser.links
    )
