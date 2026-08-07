"""Calculation and static-page guards for the home-loan planner."""

from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "site" / "assets" / "home-loan-planner.js"
PAGE = ROOT / "home_loan_planner.html"


def _run_node(expression: str) -> dict:
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


def test_monthly_rest_matches_reference_amortisation_vector() -> None:
    result = _run_node(
        "(() => {"
        "const schedule = planner.buildSchedule({"
        "principal:600000,annualRate:3.5,termMonths:240,startMonth:'2026-01'"
        "});"
        "return {payment:schedule.firstPayment,monthOne:schedule.rows[0],"
        "balance12:schedule.rows[11].endingBalance,"
        "balance60:schedule.rows[59].endingBalance,"
        "interest:schedule.totalInterest,"
        "zeroRate:planner.monthlyPayment(120000,0,120)};"
        "})()"
    )

    assert result["payment"] == pytest.approx(3479.7583079)
    assert result["monthOne"]["date"] == "2026-01"
    assert result["monthOne"]["interest"] == pytest.approx(1750)
    assert result["monthOne"]["scheduledPrincipal"] == pytest.approx(1729.7583079)
    assert result["balance12"] == pytest.approx(578906.663196)
    assert result["balance60"] == pytest.approx(486759.447414)
    assert result["interest"] == pytest.approx(235141.993896)
    assert result["zeroRate"] == pytest.approx(1000)


def test_new_home_loan_summary_reports_reset_stress_and_five_year_balance() -> None:
    result = _run_node(
        "(() => {"
        "const summary=planner.summarizeHomeLoan({loan:{"
        "principal:600000,annualRate:3.5,introMonths:24,rateAfter:3.5,"
        "termMonths:240,startMonth:'2026-01'}});"
        "return {starting:summary.startingPayment,reset:summary.resetPayment,"
        "resetMonth:summary.resetMonth,stressOne:summary.stressOnePayment,"
        "stressTwo:summary.stressTwoPayment,interest:summary.totalInterest,"
        "balance60:summary.balanceAfterFiveYears,payoff:summary.payoffMonth};"
        "})()"
    )

    assert result["starting"] == pytest.approx(3479.7583079)
    assert result["reset"] == pytest.approx(result["starting"])
    assert result["resetMonth"] == "2028-01"
    assert result["stressOne"] > result["reset"]
    assert result["stressTwo"] > result["stressOne"]
    assert result["interest"] == pytest.approx(235141.993896)
    assert result["balance60"] == pytest.approx(486759.447414)
    assert result["payoff"] == "2045-12"


def test_shorter_home_loan_tenure_raises_payment_but_reduces_interest() -> None:
    result = _run_node(
        "(() => {"
        "const make=months=>planner.summarizeHomeLoan({loan:{"
        "principal:600000,annualRate:3.5,rateAfter:3.5,introMonths:months,"
        "termMonths:months,startMonth:'2026-01'}});"
        "const long=make(240),short=make(180);"
        "return {longPayment:long.startingPayment,shortPayment:short.startingPayment,"
        "longInterest:long.totalInterest,shortInterest:short.totalInterest};"
        "})()"
    )

    assert result["shortPayment"] > result["longPayment"]
    assert result["shortInterest"] < result["longInterest"]


def test_multiple_dated_rate_segments_recast_the_monthly_instalment() -> None:
    result = _run_node(
        "(() => {"
        "const schedule=planner.buildSchedule({principal:600000,annualRate:2.5,"
        "termMonths:36,startMonth:'2026-08',rateSegments:["
        "{startMonth:1,annualRate:2.5},{startMonth:13,annualRate:3.5},"
        "{startMonth:25,annualRate:3.0}]});"
        "return {dates:[schedule.rows[0].date,schedule.rows[12].date,schedule.rows[24].date],"
        "rates:[schedule.rows[11].annualRate,schedule.rows[12].annualRate,"
        "schedule.rows[24].annualRate],payments:[schedule.rows[11].scheduledPayment,"
        "schedule.rows[12].scheduledPayment,schedule.rows[24].scheduledPayment],"
        "segments:schedule.rateSegments,principal:schedule.totalPrincipalDrawn};"
        "})()"
    )

    assert result["dates"] == ["2026-08", "2027-08", "2028-08"]
    assert result["rates"] == [2.5, 3.5, 3.0]
    assert result["payments"][1] > result["payments"][0]
    assert result["payments"][2] < result["payments"][1]
    assert result["segments"] == [
        {"startMonth": 1, "annualRate": 2.5},
        {"startMonth": 13, "annualRate": 3.5},
        {"startMonth": 25, "annualRate": 3.0},
    ]
    assert result["principal"] == 600000


def test_progressive_plan_draws_full_loan_across_construction_milestones() -> None:
    result = _run_node(
        "(() => {"
        "const plan=planner.buildProgressivePlan({propertyPrice:1000000,"
        "loanAmount:750000,loan:{annualRate:3.65,termMonths:300,"
        "startMonth:'2026-08'}});"
        "return {downPayment:plan.downPayment,initial:plan.initialPayment,"
        "option:plan.optionFee,sale:plan.saleAndPurchasePayment,"
        "stageDraws:plan.stages.map(stage=>stage.loanDraw),"
        "stageMonths:plan.stages.map(stage=>stage.month),"
        "stageDates:plan.stages.map(stage=>stage.date),"
        "stagePayments:plan.stages.map(stage=>Math.round(stage.monthlyPayment)),"
        "drawn:plan.schedule.totalPrincipalDrawn,"
        "interest:plan.schedule.totalInterest,"
        "rowOneDate:plan.schedule.rows[0].date,"
        "lastPayoff:plan.schedule.payoffMonth};"
        "})()"
    )

    assert result["downPayment"] == 250000
    assert result["initial"] == 200000
    assert result["option"] == 50000
    assert result["sale"] == 150000
    assert result["stageDraws"] == [50000, 100000, 50000, 50000, 50000, 50000, 250000, 150000]
    assert sum(result["stageDraws"]) == result["drawn"] == 750000
    assert result["stageMonths"] == [1, 7, 13, 16, 19, 22, 25, 37]
    assert result["stageDates"] == [
        "2026-08",
        "2027-02",
        "2027-08",
        "2027-11",
        "2028-02",
        "2028-05",
        "2028-08",
        "2029-08",
    ]
    assert result["stagePayments"] == [254, 769, 1030, 1293, 1557, 1823, 3163, 3991]
    assert result["interest"] == pytest.approx(364723, abs=0.01)
    assert result["rowOneDate"] == "2026-08"
    assert result["lastPayoff"] == "2051-07"


def test_existing_loan_comparison_matches_dbs_reference_vector() -> None:
    result = _run_node(
        "(() => {"
        "const current=planner.buildSchedule({principal:500000,annualRate:4.15,"
        "termMonths:120,startMonth:'2026-08'});"
        "const candidate=planner.buildSchedule({principal:500000,annualRate:3.65,"
        "termMonths:120,startMonth:'2026-08'});"
        "const firstYear=schedule=>schedule.rows.slice(0,12)"
        ".reduce((total,row)=>total+row.interest,0);"
        "return {currentMonthly:current.firstPayment,newMonthly:candidate.firstPayment,"
        "monthlyReduction:current.firstPayment-candidate.firstPayment,"
        "firstYearSaving:firstYear(current)-firstYear(candidate),"
        "currentInterest:current.totalInterest,newInterest:candidate.totalInterest,"
        "lifetimeSaving:current.totalInterest-candidate.totalInterest};"
        "})()"
    )

    assert result["currentMonthly"] == pytest.approx(5097.98, abs=0.01)
    assert result["newMonthly"] == pytest.approx(4979.50, abs=0.01)
    assert result["monthlyReduction"] == pytest.approx(118.47, abs=0.01)
    assert result["firstYearSaving"] == pytest.approx(2423.55, abs=0.01)
    assert result["currentInterest"] == pytest.approx(111757.34, abs=0.01)
    assert result["newInterest"] == pytest.approx(97540.42, abs=0.01)
    assert result["lifetimeSaving"] == pytest.approx(14216.92, abs=0.01)


def test_stepped_rate_recasts_and_uses_dated_rebate_for_cost_recovery() -> None:
    result = _run_node(
        "(() => {"
        "const comparison=planner.compareLoans({horizonMonths:60,"
        "current:{principal:500000,annualRate:3.8,termMonths:240,startMonth:'2026-01'},"
        "candidate:{principal:500000,annualRate:2.6,introMonths:24,"
        "rateAfter:3.2,termMonths:240,startMonth:'2026-01'},"
        "costs:{legal:3000,valuation:500,admin:200,mortgageDuty:500,"
        "rebate:2000,rebateMonth:2}});"
        "return {oldPayment:comparison.currentSchedule.firstPayment,"
        "newPayment:comparison.candidateSchedule.firstPayment,"
        "newBalance24:comparison.candidateSchedule.rows[23].endingBalance,"
        "newPayment25:comparison.candidateSchedule.rows[24].scheduledPayment,"
        "oldLifetime:comparison.currentSchedule.totalInterest,"
        "newLifetime:comparison.candidateSchedule.totalInterest,"
        "netLifetime:comparison.netLifetimeBenefit,"
        "netCost:comparison.netSwitchingCost,"
        "recognizedRebate:comparison.recognizedRebate,"
        "firstRecovery:comparison.firstRecoveryMonth,"
        "durableRecovery:comparison.durableRecoveryMonth};"
        "})()"
    )

    assert result["oldPayment"] == pytest.approx(2977.468424)
    assert result["newPayment"] == pytest.approx(2673.940260)
    assert result["newBalance24"] == pytest.approx(460858.964161)
    assert result["newPayment25"] == pytest.approx(2809.517562)
    assert result["oldLifetime"] == pytest.approx(214592.421762)
    assert result["newLifetime"] == pytest.approx(171030.359723)
    assert result["netLifetime"] == pytest.approx(41362.062039)
    assert result["netCost"] == pytest.approx(2200)
    assert result["recognizedRebate"] == pytest.approx(2000)
    assert result["firstRecovery"] == 5
    assert result["durableRecovery"] == 5


def test_partial_prepayment_recasts_payment_and_reduces_interest() -> None:
    result = _run_node(
        "(() => {"
        "const base={principal:400000,annualRate:3.4,termMonths:240,startMonth:'2026-01'};"
        "const stay=planner.buildSchedule(base);"
        "const prepaid=planner.buildSchedule({...base,extraPayment:50000,extraPaymentMonth:12});"
        "return {baseInterest:stay.totalInterest,prepaidInterest:prepaid.totalInterest,"
        "paymentBefore:prepaid.rows[11].scheduledPayment,"
        "paymentAfter:prepaid.rows[12].scheduledPayment,"
        "prepaidEnding:prepaid.rows.at(-1).endingBalance,"
        "prepaidExtra:prepaid.totalExtraPrincipal};"
        "})()"
    )

    assert result["prepaidExtra"] == pytest.approx(50000)
    assert result["prepaidInterest"] < result["baseInterest"]
    assert result["paymentAfter"] < result["paymentBefore"]
    assert result["prepaidEnding"] == pytest.approx(0, abs=0.01)


def test_partial_prepayment_can_target_a_new_remaining_loan_period() -> None:
    result = _run_node(
        "(() => {"
        "const schedule=planner.buildSchedule({principal:400000,annualRate:3.4,"
        "termMonths:240,startMonth:'2026-01',extraPayment:50000,"
        "extraPaymentMonth:12,prepaymentMode:'target-term',"
        "postPrepaymentMonths:120});"
        "return {months:schedule.rows.length,before:schedule.rows[11].scheduledPayment,"
        "after:schedule.rows[12].scheduledPayment,extra:schedule.totalExtraPrincipal,"
        "interest:schedule.totalInterest,payoff:schedule.payoffMonth,"
        "ending:schedule.rows.at(-1).endingBalance};"
        "})()"
    )

    assert result["months"] == 132
    assert result["before"] == pytest.approx(2299.337250)
    assert result["after"] == pytest.approx(3304.760322)
    assert result["extra"] == 50000
    assert result["interest"] == pytest.approx(74163.285655)
    assert result["payoff"] == "2036-12"
    assert result["ending"] == pytest.approx(0, abs=0.01)


def test_partial_prepayment_can_target_a_new_monthly_instalment() -> None:
    result = _run_node(
        "(() => {"
        "const schedule=planner.buildSchedule({principal:400000,annualRate:3.4,"
        "termMonths:240,startMonth:'2026-01',extraPayment:50000,"
        "extraPaymentMonth:12,prepaymentMode:'target-payment',"
        "postPrepaymentPayment:3000});"
        "return {months:schedule.rows.length,before:schedule.rows[11].scheduledPayment,"
        "after:schedule.rows[12].scheduledPayment,"
        "penultimate:schedule.rows.at(-2).scheduledPayment,"
        "final:schedule.rows.at(-1).scheduledPayment,extra:schedule.totalExtraPrincipal,"
        "interest:schedule.totalInterest,payoff:schedule.payoffMonth,"
        "ending:schedule.rows.at(-1).endingBalance};"
        "})()"
    )

    assert result["months"] == 147
    assert result["before"] == pytest.approx(2299.337250)
    assert result["after"] == pytest.approx(3000)
    assert result["penultimate"] == pytest.approx(3000)
    assert result["final"] == pytest.approx(2466.175545)
    assert result["extra"] == 50000
    assert result["interest"] == pytest.approx(82058.222540)
    assert result["payoff"] == "2038-03"
    assert result["ending"] == pytest.approx(0, abs=0.01)


def test_equal_prepayment_is_not_attributed_to_switching() -> None:
    result = _run_node(
        "(() => {"
        "const loan={principal:400000,annualRate:3.4,termMonths:240,"
        "startMonth:'2026-01',extraPayment:50000,extraPaymentMonth:12};"
        "const comparison=planner.compareLoans({horizonMonths:60,"
        "current:loan,candidate:{...loan},costs:{}});"
        "return {interestSaving:comparison.grossInterestSaving,"
        "netBenefit:comparison.horizonNetBenefit,"
        "balanceDifference:comparison.currentEndingBalance-comparison.candidateEndingBalance};"
        "})()"
    )

    assert result["interestSaving"] == pytest.approx(0, abs=1e-8)
    assert result["netBenefit"] == pytest.approx(0, abs=1e-8)
    assert result["balanceDifference"] == pytest.approx(0, abs=1e-8)


def test_rebate_after_horizon_is_not_counted_in_window_result() -> None:
    result = _run_node(
        "(() => {"
        "const loan={principal:300000,annualRate:3,termMonths:240,startMonth:'2026-01'};"
        "const comparison=planner.compareLoans({horizonMonths:24,"
        "current:loan,candidate:{...loan},"
        "costs:{legal:1000,rebate:5000,rebateMonth:25}});"
        "return {recognized:comparison.recognizedRebate,"
        "windowCost:comparison.windowNetSwitchingCost,"
        "eventualCost:comparison.netSwitchingCost,"
        "netBenefit:comparison.horizonNetBenefit};"
        "})()"
    )

    assert result == {
        "recognized": 0,
        "windowCost": 1000,
        "eventualCost": -4000,
        "netBenefit": -1000,
    }


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


def test_planner_page_is_self_contained_labelled_and_original() -> None:
    html = PAGE.read_text(encoding="utf-8")
    parser = _StructureParser()
    parser.feed(html)

    assert len(parser.ids) == len(set(parser.ids)), "HTML ids must be unique"
    assert set(parser.scripts) == {
        "assets/home-loan-planner.js?v=20260808-3",
        "assets/research-shell.js",
    }
    assert all(
        input_id in parser.labels
        for input_id in (
            "new-loan-amount",
            "new-interest-rate",
            "construction-toggle",
            "property-price",
            "down-payment",
            "existing-loan-amount",
            "current-interest-rate",
            "package-interest-rate",
            "schedule-start-month",
        )
    )
    assert 'id="calculator-errors" role="status" aria-live="polite" hidden' in html
    assert 'id="new-years" aria-label="Loan period years"' in html
    assert 'id="new-months" aria-label="Additional loan period months"' in html
    assert 'id="schedule-start-year" aria-label="Repayment start year"' in html
    assert 'id="new-loan-amount" type="text"' in html
    assert html.count("data-currency-input") >= 11
    assert 'data-loan-tab="new" aria-selected="true"' in html
    assert 'data-loan-panel="existing" hidden' in html
    assert 'aria-labelledby="loan-tab-existing"' in html
    assert 'class="table-scroll" role="region"' in html
    assert html.count('<option value="recast">') == 1
    assert html.count('<option value="target-term">') == 1
    assert html.count('<option value="target-payment">') == 1
    assert 'id="partial-term-fields" hidden' in html
    assert 'id="partial-payment-fields" hidden' in html
    assert "dbs" not in html.lower()
    javascript = SCRIPT.read_text(encoding="utf-8")
    assert "rateSegments" in javascript
    assert "futureDisbursements" in javascript
    assert "prepaymentMode" in javascript
    assert "buildProgressivePlan" in javascript
    assert not any(link.startswith("http") and "gov.sg" not in link for link in parser.links)
