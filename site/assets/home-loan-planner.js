/* Browser-only home-loan and refinance calculation engine. */
(function (root, factory) {
  "use strict";

  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.RefinancePlanner = api;

  if (root.document) {
    const start = () => api.init(root.document);
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
      start();
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const EPSILON = 1e-8;

  function finiteNumber(value, name) {
    const number = Number(value);
    if (!Number.isFinite(number)) throw new TypeError(`${name} must be a finite number`);
    return number;
  }

  function positiveInteger(value, name) {
    const number = finiteNumber(value, name);
    if (!Number.isInteger(number) || number <= 0) {
      throw new RangeError(`${name} must be a positive integer`);
    }
    return number;
  }

  function monthlyPayment(principal, annualRate, months) {
    const balance = finiteNumber(principal, "principal");
    const rate = finiteNumber(annualRate, "annualRate");
    const count = positiveInteger(months, "months");
    if (balance < 0) throw new RangeError("principal must not be negative");
    if (rate < 0) throw new RangeError("annualRate must not be negative");
    if (balance === 0) return 0;

    const monthlyRate = rate / 1200;
    if (Math.abs(monthlyRate) < EPSILON) return balance / count;
    return balance * monthlyRate / (1 - Math.pow(1 + monthlyRate, -count));
  }

  function parseMonth(value) {
    const match = /^(\d{4})-(\d{2})$/.exec(String(value || ""));
    if (!match) throw new RangeError("startMonth must use YYYY-MM");
    const year = Number(match[1]);
    const month = Number(match[2]);
    if (month < 1 || month > 12) throw new RangeError("startMonth has an invalid month");
    return { year, month };
  }

  function addMonths(value, offset) {
    const start = parseMonth(value);
    const absolute = start.year * 12 + (start.month - 1) + Number(offset || 0);
    const year = Math.floor(absolute / 12);
    const month = absolute - year * 12 + 1;
    return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}`;
  }

  function monthsBetween(startValue, endValue) {
    const start = parseMonth(startValue);
    const end = parseMonth(endValue);
    return (end.year - start.year) * 12 + end.month - start.month;
  }

  function buildSchedule(options) {
    const principal = finiteNumber(options.principal, "principal");
    const termMonths = positiveInteger(options.termMonths, "termMonths");
    const annualRate = finiteNumber(options.annualRate, "annualRate");
    const introMonths = options.introMonths == null
      ? termMonths
      : Math.max(0, Math.min(termMonths, Math.trunc(finiteNumber(options.introMonths, "introMonths"))));
    const rateAfter = options.rateAfter == null
      ? annualRate
      : finiteNumber(options.rateAfter, "rateAfter");
    const extraPayment = options.extraPayment == null
      ? 0
      : finiteNumber(options.extraPayment, "extraPayment");
    const extraPaymentMonth = options.extraPaymentMonth == null || options.extraPaymentMonth === ""
      ? null
      : positiveInteger(options.extraPaymentMonth, "extraPaymentMonth");
    const prepaymentMode = options.prepaymentMode || "recast";
    const postPrepaymentMonths = options.postPrepaymentMonths == null
      ? null
      : positiveInteger(options.postPrepaymentMonths, "postPrepaymentMonths");
    const postPrepaymentPayment = options.postPrepaymentPayment == null
      ? null
      : finiteNumber(options.postPrepaymentPayment, "postPrepaymentPayment");
    const startMonth = options.startMonth || "2026-01";
    parseMonth(startMonth);

    if (principal < 0) throw new RangeError("principal must not be negative");
    if (annualRate < 0 || rateAfter < 0) throw new RangeError("rates must not be negative");
    if (extraPayment < 0) throw new RangeError("extraPayment must not be negative");
    if (extraPaymentMonth && extraPaymentMonth > termMonths) {
      throw new RangeError("extraPaymentMonth must be within the loan term");
    }
    if (!["recast", "shorten", "target-term", "target-payment"].includes(prepaymentMode)) {
      throw new RangeError("prepaymentMode is not supported");
    }
    if (extraPayment > 0 && prepaymentMode === "target-term" && !postPrepaymentMonths) {
      throw new RangeError("postPrepaymentMonths is required for a new loan period");
    }
    if (
      extraPayment > 0
      && prepaymentMode === "target-payment"
      && !(postPrepaymentPayment > 0)
    ) {
      throw new RangeError("postPrepaymentPayment must be positive");
    }

    let rateSegments;
    if (Array.isArray(options.rateSegments) && options.rateSegments.length) {
      rateSegments = options.rateSegments.map((segment, index) => {
        const start = positiveInteger(segment.startMonth, `rateSegments[${index}].startMonth`);
        const rate = finiteNumber(segment.annualRate, `rateSegments[${index}].annualRate`);
        if (start > termMonths) throw new RangeError("rate segment starts after the loan term");
        if (rate < 0) throw new RangeError("rate segment must not be negative");
        return { startMonth: start, annualRate: rate };
      }).sort((a, b) => a.startMonth - b.startMonth);
      if (rateSegments[0].startMonth !== 1) {
        rateSegments.unshift({ startMonth: 1, annualRate });
      }
      rateSegments = rateSegments.filter((segment, index, list) => (
        index === list.length - 1 || segment.startMonth !== list[index + 1].startMonth
      ));
    } else {
      rateSegments = [{
        startMonth: 1,
        annualRate: introMonths === 0 ? rateAfter : annualRate,
      }];
      if (introMonths > 0 && introMonths < termMonths) {
        rateSegments.push({ startMonth: introMonths + 1, annualRate: rateAfter });
      }
    }

    const futureDisbursements = Array.isArray(options.futureDisbursements)
      ? options.futureDisbursements.map((item, index) => {
        const month = positiveInteger(item.month, `futureDisbursements[${index}].month`);
        const amount = finiteNumber(item.amount, `futureDisbursements[${index}].amount`);
        if (month > termMonths) throw new RangeError("disbursement occurs after the loan term");
        if (amount < 0) throw new RangeError("disbursement must not be negative");
        return { month, amount };
      })
      : [];
    const disbursementsByMonth = new Map();
    futureDisbursements.forEach(item => {
      disbursementsByMonth.set(
        item.month,
        (disbursementsByMonth.get(item.month) || 0) + item.amount
      );
    });
    const lastDisbursementMonth = futureDisbursements.reduce(
      (latest, item) => Math.max(latest, item.month),
      0
    );

    const rows = [];
    let balance = principal;
    let activeRate = rateSegments[0].annualRate;
    let segmentIndex = 0;
    let scheduledPayment = monthlyPayment(balance, activeRate, termMonths);
    let maturityMonth = termMonths;
    let fixedPostPrepayment = false;
    const loopMonths = prepaymentMode === "target-term" && extraPaymentMonth
      ? Math.max(termMonths, extraPaymentMonth + postPrepaymentMonths)
      : prepaymentMode === "target-payment" && extraPaymentMonth
        ? Math.max(termMonths, extraPaymentMonth + 600)
        : termMonths;

    for (let month = 1; month <= loopMonths; month += 1) {
      const remainingMonths = Math.max(1, maturityMonth - month + 1);
      let recastRequired = false;
      if (
        segmentIndex + 1 < rateSegments.length
        && month === rateSegments[segmentIndex + 1].startMonth
      ) {
        segmentIndex += 1;
        activeRate = rateSegments[segmentIndex].annualRate;
        recastRequired = true;
      }
      const disbursement = disbursementsByMonth.get(month) || 0;
      const openingBalance = balance;
      if (disbursement > 0) {
        balance += disbursement;
        recastRequired = true;
      }
      if (balance <= EPSILON && month > lastDisbursementMonth) break;
      if (recastRequired && !fixedPostPrepayment) {
        scheduledPayment = monthlyPayment(balance, activeRate, remainingMonths);
      }

      const beginningBalance = balance;
      const interest = beginningBalance * activeRate / 1200;
      if (
        fixedPostPrepayment
        && scheduledPayment <= interest + EPSILON
        && beginningBalance > EPSILON
      ) {
        throw new RangeError("The new monthly instalment is too low to reduce the loan balance");
      }
      const scheduledOutflow = Math.min(scheduledPayment, beginningBalance + interest);
      const scheduledPrincipal = Math.max(0, scheduledOutflow - interest);
      const balanceAfterScheduled = Math.max(0, beginningBalance - scheduledPrincipal);
      const extraPrincipal = month === extraPaymentMonth
        ? Math.min(extraPayment, balanceAfterScheduled)
        : 0;
      balance = Math.max(0, balanceAfterScheduled - extraPrincipal);
      if (balance < 0.005) balance = 0;

      rows.push({
        month,
        date: addMonths(startMonth, month - 1),
        openingBalance,
        disbursement,
        beginningBalance,
        annualRate: activeRate,
        scheduledPayment: scheduledOutflow,
        interest,
        scheduledPrincipal,
        extraPrincipal,
        totalPrincipal: scheduledPrincipal + extraPrincipal,
        totalOutflow: scheduledOutflow + extraPrincipal,
        endingBalance: balance,
      });

      if (extraPrincipal > 0 && balance > EPSILON) {
        if (prepaymentMode === "recast" && month < termMonths) {
          scheduledPayment = monthlyPayment(balance, activeRate, termMonths - month);
        } else if (prepaymentMode === "target-term") {
          maturityMonth = month + postPrepaymentMonths;
          scheduledPayment = monthlyPayment(balance, activeRate, postPrepaymentMonths);
        } else if (prepaymentMode === "target-payment") {
          scheduledPayment = postPrepaymentPayment;
          fixedPostPrepayment = true;
        }
      }
    }

    if (balance > 0.01 && ["target-term", "target-payment"].includes(prepaymentMode)) {
      throw new RangeError("The selected repayment settings do not repay the balance in full");
    }

    const sum = field => rows.reduce((total, row) => total + row[field], 0);
    const totalPrincipalDrawn = principal + futureDisbursements.reduce(
      (total, item) => total + item.amount,
      0
    );
    return {
      rows,
      principal,
      totalPrincipalDrawn,
      termMonths,
      rateSegments,
      totalInterest: sum("interest"),
      totalScheduledPayments: sum("scheduledPayment"),
      totalExtraPrincipal: sum("extraPrincipal"),
      totalOutflow: sum("totalOutflow"),
      firstPayment: rows.length ? rows[0].scheduledPayment : 0,
      payoffMonth: rows.length ? rows[rows.length - 1].date : startMonth,
    };
  }

  function annualiseSchedule(schedule) {
    const groups = [];
    const byYear = new Map();
    schedule.rows.forEach(row => {
      const year = row.date.slice(0, 4);
      if (!byYear.has(year)) {
        const group = {
          year,
          months: 0,
          startBalance: row.beginningBalance,
          scheduledPayments: 0,
          interest: 0,
          scheduledPrincipal: 0,
          extraPrincipal: 0,
          disbursements: 0,
          endingBalance: row.endingBalance,
          rates: [],
          monthlyPayments: [],
        };
        byYear.set(year, group);
        groups.push(group);
      }
      const group = byYear.get(year);
      group.months += 1;
      group.scheduledPayments += row.scheduledPayment;
      group.interest += row.interest;
      group.scheduledPrincipal += row.scheduledPrincipal;
      group.extraPrincipal += row.extraPrincipal;
      group.disbursements += row.disbursement || 0;
      group.endingBalance = row.endingBalance;
      if (!group.rates.some(rate => Math.abs(rate - row.annualRate) < EPSILON)) {
        group.rates.push(row.annualRate);
      }
      if (!group.monthlyPayments.some(payment => (
        Math.abs(payment - row.scheduledPayment) < EPSILON
      ))) {
        group.monthlyPayments.push(row.scheduledPayment);
      }
    });
    return groups;
  }

  const PROGRESSIVE_STAGES = [
    { name: "Foundation", timeframe: "6 mths", propertyPercent: 10, loanWeight: 5, defaultMonth: 1 },
    { name: "Concrete framework", timeframe: "1 yr", propertyPercent: 10, loanWeight: 10, defaultMonth: 7 },
    { name: "Brick walls", timeframe: "1 yr 6 mths", propertyPercent: 5, loanWeight: 5, defaultMonth: 13 },
    { name: "Ceiling, roofing and insulation", timeframe: "1 yr 9 mths", propertyPercent: 5, loanWeight: 5, defaultMonth: 16 },
    { name: "Doors, windows and services", timeframe: "2 yrs", propertyPercent: 5, loanWeight: 5, defaultMonth: 19 },
    { name: "Carparks, roads and drains", timeframe: "2 yrs 3 mths", propertyPercent: 5, loanWeight: 5, defaultMonth: 22 },
    { name: "Temporary Occupation Permit", timeframe: "2 yrs 6 mths", propertyPercent: 25, loanWeight: 25, defaultMonth: 25 },
    { name: "Certificate of Statutory Completion", timeframe: "3 yrs 6 mths", propertyPercent: 15, loanWeight: 15, defaultMonth: 37 },
  ];

  function buildProgressivePlan(options) {
    const propertyPrice = finiteNumber(options.propertyPrice, "propertyPrice");
    const loanAmount = finiteNumber(options.loanAmount, "loanAmount");
    if (propertyPrice <= 0 || loanAmount <= 0) {
      throw new RangeError("propertyPrice and loanAmount must be positive");
    }
    if (loanAmount > propertyPrice) {
      throw new RangeError("loanAmount must not exceed propertyPrice");
    }
    const stageMonths = Array.isArray(options.stageMonths)
      ? options.stageMonths.map((month, index) => (
        positiveInteger(month, `stageMonths[${index}]`)
      ))
      : PROGRESSIVE_STAGES.map(stage => stage.defaultMonth);
    if (stageMonths.length !== PROGRESSIVE_STAGES.length) {
      throw new RangeError("stageMonths must contain one month for every stage");
    }
    stageMonths.forEach((month, index) => {
      if (index > 0 && month <= stageMonths[index - 1]) {
        throw new RangeError("progressive draw months must be strictly increasing");
      }
    });

    const totalLoanWeight = PROGRESSIVE_STAGES.reduce(
      (total, stage) => total + stage.loanWeight,
      0
    );
    const stages = PROGRESSIVE_STAGES.map((stage, index) => {
      const loanDraw = loanAmount * stage.loanWeight / totalLoanWeight;
      const milestoneAmount = propertyPrice * stage.propertyPercent / 100;
      return {
        ...stage,
        month: stageMonths[index],
        loanDraw,
        cashOrCpf: Math.max(0, milestoneAmount - loanDraw),
      };
    });
    const schedule = buildSchedule({
      ...options.loan,
      principal: stages[0].loanDraw,
      futureDisbursements: stages.slice(1).map(stage => ({
        month: stage.month,
        amount: stage.loanDraw,
      })),
    });
    stages.forEach(stage => {
      const row = schedule.rows[stage.month - 1];
      stage.monthlyPayment = row ? row.scheduledPayment : 0;
      stage.date = row ? row.date : addMonths(options.loan.startMonth, stage.month - 1);
    });
    return {
      propertyPrice,
      loanAmount,
      downPayment: propertyPrice - loanAmount,
      initialPayment: propertyPrice * 0.20,
      optionFee: propertyPrice * 0.05,
      saleAndPurchasePayment: propertyPrice * 0.15,
      stages,
      schedule,
    };
  }

  function sumThrough(schedule, field, monthCount) {
    return schedule.rows
      .slice(0, Math.max(0, monthCount))
      .reduce((total, row) => total + row[field], 0);
  }

  function balanceAt(schedule, monthCount) {
    if (monthCount <= 0) return schedule.principal;
    const row = schedule.rows[Math.min(monthCount, schedule.rows.length) - 1];
    return row ? row.endingBalance : 0;
  }

  function normalizeCosts(costs) {
    const source = costs || {};
    const result = {};
    ["legal", "valuation", "admin", "mortgageDuty", "penalty", "clawback", "other", "rebate"].forEach(name => {
      result[name] = source[name] == null ? 0 : finiteNumber(source[name], `costs.${name}`);
      if (result[name] < 0) throw new RangeError(`costs.${name} must not be negative`);
    });
    result.rebateMonth = source.rebateMonth == null
      ? 0
      : Math.trunc(finiteNumber(source.rebateMonth, "costs.rebateMonth"));
    if (result.rebateMonth < 0) {
      throw new RangeError("costs.rebateMonth must not be negative");
    }
    return result;
  }

  function compareLoans(options) {
    const horizonMonths = positiveInteger(options.horizonMonths, "horizonMonths");
    const currentSchedule = buildSchedule(options.current);
    const candidateSchedule = buildSchedule(options.candidate);
    const costs = normalizeCosts(options.costs);
    const grossSwitchingCost = costs.legal + costs.valuation + costs.admin + costs.mortgageDuty
      + costs.penalty + costs.clawback + costs.other;
    const netSwitchingCost = grossSwitchingCost - costs.rebate;
    const recognizedRebate = costs.rebateMonth <= horizonMonths ? costs.rebate : 0;
    const windowNetSwitchingCost = grossSwitchingCost - recognizedRebate;
    const currentInterest = sumThrough(currentSchedule, "interest", horizonMonths);
    const candidateInterest = sumThrough(candidateSchedule, "interest", horizonMonths);
    const grossInterestSaving = currentInterest - candidateInterest;
    const horizonNetBenefit = grossInterestSaving - grossSwitchingCost + recognizedRebate;
    const monthlyNetBenefits = [];
    let cumulativeCurrentInterest = 0;
    let cumulativeCandidateInterest = 0;
    for (let month = 1; month <= horizonMonths; month += 1) {
      cumulativeCurrentInterest += currentSchedule.rows[month - 1]?.interest || 0;
      cumulativeCandidateInterest += candidateSchedule.rows[month - 1]?.interest || 0;
      monthlyNetBenefits.push(
        cumulativeCurrentInterest - cumulativeCandidateInterest - grossSwitchingCost
          + (month >= costs.rebateMonth ? costs.rebate : 0)
      );
    }
    const initialNetBenefit = -grossSwitchingCost + (costs.rebateMonth === 0 ? costs.rebate : 0);
    const benefitPath = [initialNetBenefit, ...monthlyNetBenefits];
    const firstRecoveryMonth = benefitPath.findIndex(value => value >= -EPSILON);
    let durableRecoveryMonth = null;
    for (let month = 0; month < benefitPath.length; month += 1) {
      if (
        benefitPath[month] >= -EPSILON
        && benefitPath.slice(month).every(value => value >= -EPSILON)
      ) {
        durableRecoveryMonth = month;
        break;
      }
    }

    return {
      currentSchedule,
      candidateSchedule,
      costs,
      horizonMonths,
      grossSwitchingCost,
      netSwitchingCost,
      recognizedRebate,
      windowNetSwitchingCost,
      currentInterest,
      candidateInterest,
      grossInterestSaving,
      horizonNetBenefit,
      currentEndingBalance: balanceAt(currentSchedule, horizonMonths),
      candidateEndingBalance: balanceAt(candidateSchedule, horizonMonths),
      initialMonthlyChange: currentSchedule.firstPayment - candidateSchedule.firstPayment,
      firstRecoveryMonth: firstRecoveryMonth < 0 ? null : firstRecoveryMonth,
      durableRecoveryMonth,
      monthlyNetBenefits,
      lifetimeInterestSaving:
        currentSchedule.totalInterest - candidateSchedule.totalInterest,
      netLifetimeBenefit:
        currentSchedule.totalInterest - candidateSchedule.totalInterest - netSwitchingCost,
    };
  }

  function summarizeHomeLoan(options) {
    const schedule = buildSchedule(options.loan);
    const introMonths = options.loan.introMonths == null
      ? schedule.termMonths
      : Math.max(0, Math.trunc(Number(options.loan.introMonths)));
    const resetRow = introMonths < schedule.rows.length
      ? schedule.rows[introMonths]
      : null;
    const stressOneSchedule = buildSchedule({
      ...options.loan,
      rateAfter: finiteNumber(
        options.loan.rateAfter == null ? options.loan.annualRate : options.loan.rateAfter,
        "loan.rateAfter"
      ) + 1,
    });
    const stressTwoSchedule = buildSchedule({
      ...options.loan,
      rateAfter: finiteNumber(
        options.loan.rateAfter == null ? options.loan.annualRate : options.loan.rateAfter,
        "loan.rateAfter"
      ) + 2,
    });
    const stressOneResetRow = introMonths < stressOneSchedule.rows.length
      ? stressOneSchedule.rows[introMonths]
      : null;
    const stressTwoResetRow = introMonths < stressTwoSchedule.rows.length
      ? stressTwoSchedule.rows[introMonths]
      : null;
    const firstYearInterest = sumThrough(schedule, "interest", 12);
    const firstYearPrincipal = sumThrough(schedule, "totalPrincipal", 12);

    return {
      schedule,
      stressOneSchedule,
      stressTwoSchedule,
      loanAmount: schedule.principal,
      startingPayment: schedule.firstPayment,
      resetPayment: resetRow ? resetRow.scheduledPayment : null,
      resetMonth: resetRow ? resetRow.date : null,
      stressOnePayment: stressOneResetRow ? stressOneResetRow.scheduledPayment : null,
      stressTwoPayment: stressTwoResetRow ? stressTwoResetRow.scheduledPayment : null,
      maximumPayment: schedule.rows.reduce(
        (maximum, row) => Math.max(maximum, row.scheduledPayment),
        0
      ),
      totalInterest: schedule.totalInterest,
      totalPaid: schedule.totalOutflow,
      firstYearInterest,
      firstYearPrincipal,
      balanceAfterFiveYears: balanceAt(schedule, 60),
      payoffMonth: schedule.payoffMonth,
    };
  }

  function initModeTabs(document) {
    const tabs = Array.from(document.querySelectorAll("[data-planner-mode]"));
    if (!tabs.length) return;
    const panels = Array.from(document.querySelectorAll("[data-planner-panel]"));

    function activate(mode, updateHash) {
      tabs.forEach(tab => {
        const selected = tab.dataset.plannerMode === mode;
        tab.setAttribute("aria-selected", String(selected));
        tab.tabIndex = selected ? 0 : -1;
      });
      panels.forEach(panel => {
        const selected = panel.dataset.plannerPanel === mode;
        panel.hidden = !selected;
        panel.querySelectorAll("input, select, button").forEach(control => {
          control.disabled = !selected;
        });
      });
      if (updateHash && document.defaultView?.history) {
        const hash = mode === "refinance" ? "#refinance" : "#new-home-loan";
        document.defaultView.history.replaceState(null, "", hash);
      }
    }

    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => activate(tab.dataset.plannerMode, true));
      tab.addEventListener("keydown", event => {
        if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
        event.preventDefault();
        const direction = event.key === "ArrowRight" ? 1 : -1;
        const target = tabs[(index + direction + tabs.length) % tabs.length];
        activate(target.dataset.plannerMode, true);
        target.focus();
      });
    });

    activate(document.defaultView?.location.hash === "#refinance" ? "refinance" : "new-loan", false);
  }

  function initNewHomeLoan(document) {
    const form = document.getElementById("home-loan-form");
    if (!form) return;
    const byId = id => document.getElementById(id);
    const numberFormat = new Intl.NumberFormat("en-SG", { maximumFractionDigits: 0 });
    const money = value => `S$${numberFormat.format(value)}`;
    let latest = null;
    let showFullSchedule = false;

    function nextMonth() {
      const now = new Date();
      const year = now.getFullYear() + (now.getMonth() === 11 ? 1 : 0);
      const month = (now.getMonth() + 1) % 12 + 1;
      return `${year}-${String(month).padStart(2, "0")}`;
    }

    if (!byId("home-start-month").value) byId("home-start-month").value = nextMonth();

    function value(id) {
      const raw = byId(id).value.trim().replace(/,/g, "");
      return raw === "" ? null : Number(raw);
    }

    function requireNumber(id, label, min, max, errors) {
      const number = value(id);
      if (number == null || !Number.isFinite(number)) {
        errors.push({ id, message: `${label} is required.` });
      } else if (number < min || number > max) {
        errors.push({ id, message: `${label} must be between ${min} and ${max}.` });
      }
      return number;
    }

    function optionalNumber(id, label, min, max, errors) {
      const number = value(id);
      if (number == null) return 0;
      if (!Number.isFinite(number) || number < min || number > max) {
        errors.push({ id, message: `${label} must be between ${min} and ${max}.` });
      }
      return number;
    }

    function collect() {
      const errors = [];
      const principal = requireNumber("home-principal", "Loan amount", 1000, 100000000, errors);
      const annualRate = requireNumber("home-rate", "Starting interest rate", 0, 20, errors);
      const introMonths = requireNumber("home-rate-months", "Starting-rate period", 0, 420, errors);
      const rateAfter = requireNumber("home-reset-rate", "Thereafter rate", 0, 20, errors);
      const years = requireNumber("home-years", "Loan tenure", 1, 35, errors);
      const extraPayment = optionalNumber("home-extra-payment", "Partial prepayment", 0, 100000000, errors);
      const extraMonth = optionalNumber("home-extra-month", "Partial prepayment month", 0, 420, errors);
      const startMonth = byId("home-start-month").value;
      const termMonths = Math.round((years || 0) * 12);

      if (!startMonth) errors.push({ id: "home-start-month", message: "Loan completion month is required." });
      if (introMonths > termMonths) {
        errors.push({ id: "home-rate-months", message: "Starting-rate period cannot exceed the loan tenure." });
      }
      if (extraPayment > 0 && (!extraMonth || extraMonth < 1)) {
        errors.push({ id: "home-extra-month", message: "Enter the month when the partial prepayment is made." });
      }
      if (extraPayment > principal) {
        errors.push({ id: "home-extra-payment", message: "Partial prepayment cannot exceed the loan amount." });
      }
      if (extraMonth > termMonths) {
        errors.push({ id: "home-extra-month", message: "Partial prepayment month must be within the loan tenure." });
      }

      return {
        errors,
        summaryOptions: {
          loan: {
            principal,
            annualRate,
            introMonths: Math.round(introMonths || 0),
            rateAfter,
            termMonths,
            startMonth,
            extraPayment,
            extraPaymentMonth: extraPayment > 0 ? Math.round(extraMonth) : null,
          },
        },
      };
    }

    function renderErrors(errors) {
      form.querySelectorAll("[aria-invalid='true']").forEach(input => input.removeAttribute("aria-invalid"));
      const summary = byId("home-error-summary");
      if (!errors.length) {
        summary.hidden = true;
        summary.replaceChildren();
        return;
      }
      const heading = document.createElement("strong");
      heading.textContent = `Check ${errors.length} ${errors.length === 1 ? "field" : "fields"} before calculating:`;
      const list = document.createElement("ul");
      errors.forEach(error => {
        const item = document.createElement("li");
        const link = document.createElement("a");
        link.href = `#${error.id}`;
        link.textContent = error.message;
        item.append(link);
        list.append(item);
        byId(error.id)?.setAttribute("aria-invalid", "true");
      });
      summary.replaceChildren(heading, list);
      summary.hidden = false;
      summary.tabIndex = -1;
      summary.focus();
    }

    function monthLabel(month) {
      const parsed = parseMonth(month);
      return new Intl.DateTimeFormat("en-SG", { month: "short", year: "numeric" })
        .format(new Date(parsed.year, parsed.month - 1, 1));
    }

    function renderSchedule() {
      if (!latest) return;
      const annual = annualiseSchedule(latest.schedule);
      const visible = showFullSchedule ? annual : annual.slice(0, 5);
      byId("home-schedule-body").replaceChildren(...visible.map(group => {
        const row = document.createElement("tr");
        const rates = group.rates.map(rate => `${rate.toFixed(2)}%`).join(" → ");
        const values = [
          group.year,
          rates,
          money(group.startBalance),
          money(group.scheduledPayments + group.extraPrincipal),
          money(group.interest),
          money(group.scheduledPrincipal + group.extraPrincipal),
          money(group.endingBalance),
        ];
        values.forEach((text, index) => {
          const cell = document.createElement(index === 0 ? "th" : "td");
          if (index === 0) cell.scope = "row";
          cell.textContent = text;
          row.append(cell);
        });
        return row;
      }));
      byId("home-schedule-caption").textContent = `${latest.schedule.rows.length} modelled monthly payments · payoff ${monthLabel(latest.payoffMonth)}.`;
      const button = byId("home-show-schedule");
      button.hidden = annual.length <= 5;
      button.textContent = showFullSchedule ? "Show first 5 years" : `Show all ${annual.length} calendar years`;
    }

    function renderWarnings(data, summary) {
      const warnings = [];
      if (summary.resetPayment != null && summary.resetPayment > summary.startingPayment + 1) {
        warnings.push(`The modelled instalment rises by ${money(summary.resetPayment - summary.startingPayment)} after the starting-rate period.`);
      }
      if (data.summaryOptions.loan.extraPayment > 0) {
        warnings.push("The partial prepayment assumes the lender recasts the instalment while preserving the remaining tenure; confirm the actual treatment and any penalty.");
      }
      warnings.push("Purchase taxes, legal fees, insurance, CPF usage, grants and lender eligibility checks are outside this repayment calculation.");
      byId("home-warning-list").replaceChildren(...warnings.map(text => {
        const item = document.createElement("li");
        item.textContent = text;
        return item;
      }));
    }

    function render(data, summary) {
      latest = summary;
      byId("home-start-payment").textContent = money(summary.startingPayment);
      byId("home-result-verdict").textContent = `A ${money(summary.loanAmount)} loan begins at about ${money(summary.startingPayment)} per month under the entered rate path.`;
      byId("home-reset-payment").textContent = summary.resetPayment == null
        ? "No reset entered"
        : money(summary.resetPayment);
      byId("home-reset-date").textContent = summary.resetMonth == null
        ? "Rate held for full tenure"
        : monthLabel(summary.resetMonth);
      byId("home-stress-one-payment").textContent = summary.stressOnePayment == null
        ? "No reset entered"
        : money(summary.stressOnePayment);
      byId("home-stress-two-payment").textContent = summary.stressTwoPayment == null
        ? "No reset entered"
        : money(summary.stressTwoPayment);
      byId("home-interest").textContent = money(summary.totalInterest);
      byId("home-interest-copy").textContent = money(summary.totalInterest);
      byId("home-total-paid").textContent = money(summary.totalPaid);
      byId("home-payoff").textContent = monthLabel(summary.payoffMonth);
      byId("home-first-year-interest").textContent = money(summary.firstYearInterest);
      byId("home-first-year-principal").textContent = money(summary.firstYearPrincipal);
      byId("home-five-year-balance").textContent = money(summary.balanceAfterFiveYears);
      renderWarnings(data, summary);
      renderSchedule();
      byId("home-results-updated").textContent = `Home-loan results updated. Starting monthly repayment is ${money(summary.startingPayment)}.`;
    }

    function calculate(focusResults) {
      const data = collect();
      renderErrors(data.errors);
      if (data.errors.length) return false;
      try {
        const summary = summarizeHomeLoan(data.summaryOptions);
        render(data, summary);
        if (focusResults) {
          byId("home-results-title").tabIndex = -1;
          byId("home-results-title").focus({ preventScroll: true });
          byId("home-results-panel").scrollIntoView({ behavior: "smooth", block: "start" });
        }
        return true;
      } catch (error) {
        renderErrors([{ id: "home-principal", message: `The schedule could not be calculated: ${error.message}` }]);
        return false;
      }
    }

    form.addEventListener("submit", event => {
      event.preventDefault();
      calculate(true);
    });
    form.addEventListener("reset", () => {
      document.defaultView.setTimeout(() => {
        byId("home-start-month").value = nextMonth();
        showFullSchedule = false;
        calculate(false);
        byId("home-principal").focus();
      }, 0);
    });
    byId("home-show-schedule").addEventListener("click", () => {
      showFullSchedule = !showFullSchedule;
      renderSchedule();
    });
    byId("home-print").addEventListener("click", () => document.defaultView.print());
    calculate(false);
  }

  function initLegacy(document) {
    initModeTabs(document);
    initNewHomeLoan(document);
    const form = document.getElementById("refinance-form");
    if (!form) return;

    const byId = id => document.getElementById(id);
    const wholeNumber = new Intl.NumberFormat("en-SG", {
      maximumFractionDigits: 0,
    });
    const compactNumber = new Intl.NumberFormat("en-SG", {
      notation: "compact",
      maximumFractionDigits: 1,
    });
    const money = { format: value => `S$${wholeNumber.format(value)}` };
    const compactMoney = { format: value => `S$${compactNumber.format(value)}` };
    let latest = null;
    let activeSchedule = "candidate";
    let showFullSchedule = false;
    let activeRoute = form.elements.route.value;

    function nextMonth() {
      const now = new Date();
      const year = now.getFullYear() + (now.getMonth() === 11 ? 1 : 0);
      const month = (now.getMonth() + 1) % 12 + 1;
      return `${year}-${String(month).padStart(2, "0")}`;
    }

    if (!byId("switch-month").value) byId("switch-month").value = nextMonth();

    const routeCostFields = [
      "legal-cost",
      "valuation-cost",
      "admin-cost",
      "mortgage-duty",
      "penalty-cost",
      "clawback-cost",
      "other-cost",
      "rebate",
      "rebate-month",
    ];

    function routeDefault(input, route) {
      return route === "reprice"
        ? input.dataset.repriceDefault
        : input.dataset.refinanceDefault;
    }

    function updateRouteCostNote(route) {
      byId("route-cost-note").textContent = route === "reprice"
        ? "Repricing selected: untouched refinance-only legal, valuation, mortgage-duty and rebate illustrations were set to zero. Enter the current lender's actual conversion fee and terms."
        : "Refinancing selected: illustration defaults include legal, valuation and mortgage-duty amounts plus a delayed rebate. Replace them with written quotations.";
    }

    function applyRouteDefaults(nextRoute) {
      routeCostFields.forEach(id => {
        const input = byId(id);
        const previousDefault = routeDefault(input, activeRoute);
        const nextDefault = routeDefault(input, nextRoute);
        if (input.value === previousDefault && nextDefault != null) input.value = nextDefault;
      });
      activeRoute = nextRoute;
      updateRouteCostNote(nextRoute);
    }

    function numberValue(id) {
      const raw = byId(id).value.trim().replace(/,/g, "");
      return raw === "" ? null : Number(raw);
    }

    function requiredNumber(id, label, min, max, errors) {
      const value = numberValue(id);
      if (value == null || !Number.isFinite(value)) {
        errors.push({ id, message: `${label} is required.` });
      } else if (value < min || value > max) {
        errors.push({ id, message: `${label} must be between ${min} and ${max}.` });
      }
      return value;
    }

    function optionalNumber(id, label, min, max, errors) {
      const value = numberValue(id);
      if (value == null) return 0;
      if (!Number.isFinite(value) || value < min || value > max) {
        errors.push({ id, message: `${label} must be between ${min} and ${max}.` });
      }
      return value;
    }

    function collect() {
      const errors = [];
      const balance = requiredNumber("loan-balance", "Outstanding balance", 1000, 100000000, errors);
      const currentRate = requiredNumber("current-rate", "Current interest rate", 0, 20, errors);
      const currentRateMonths = requiredNumber("current-rate-months", "Current-rate period", 0, 420, errors);
      const currentResetRate = requiredNumber("current-reset-rate", "Stay rate after the current period", 0, 20, errors);
      const currentYears = requiredNumber("current-years", "Remaining tenure", 1, 35, errors);
      const candidateRate = requiredNumber("candidate-rate", "Candidate starting rate", 0, 20, errors);
      const introMonths = requiredNumber("intro-months", "Starting-rate period", 0, 420, errors);
      const resetRate = requiredNumber("reset-rate", "Rate after starting period", 0, 20, errors);
      const candidateYears = requiredNumber("candidate-years", "Candidate tenure", 1, 35, errors);
      const horizonMonths = requiredNumber("comparison-horizon", "Comparison horizon", 12, 120, errors);
      const extraPayment = optionalNumber("extra-payment", "Partial prepayment", 0, 100000000, errors);
      const extraMonth = optionalNumber("extra-month", "Partial prepayment month", 0, 420, errors);
      const actualPayment = optionalNumber("actual-payment", "Actual monthly instalment", 0, 1000000, errors);
      const rebate = optionalNumber("rebate", "Cash rebate", 0, 10000000, errors);
      const rebateMonthRaw = numberValue("rebate-month");
      const rebateMonth = rebateMonthRaw == null
        ? 0
        : optionalNumber("rebate-month", "Rebate receipt month", 0, 420, errors);
      const costs = {
        legal: optionalNumber("legal-cost", "Legal cost", 0, 1000000, errors),
        valuation: optionalNumber("valuation-cost", "Valuation cost", 0, 1000000, errors),
        admin: optionalNumber("admin-cost", "Admin or conversion fee", 0, 1000000, errors),
        mortgageDuty: optionalNumber("mortgage-duty", "Mortgage duty", 0, 1000000, errors),
        penalty: optionalNumber("penalty-cost", "Redemption penalty", 0, 10000000, errors),
        clawback: optionalNumber("clawback-cost", "Subsidy clawback", 0, 10000000, errors),
        other: optionalNumber("other-cost", "Other switching cost", 0, 1000000, errors),
        rebate,
        rebateMonth,
      };
      const stressUplift = optionalNumber("stress-uplift", "Stress rate uplift", 0, 10, errors);
      const stressExtraCost = optionalNumber("stress-extra-cost", "Stress extra cost", 0, 1000000, errors);
      const switchMonth = byId("switch-month").value;
      const saleMonth = byId("sale-month").value;
      const lockInEnd = byId("lock-in-end").value;
      const clawbackEnd = byId("clawback-end").value;
      const propertyType = byId("property-type").value;
      const currentSource = byId("current-source").value;
      const route = form.elements.route.value;

      if (!switchMonth) errors.push({ id: "switch-month", message: "Target switch month is required." });
      if (saleMonth && switchMonth && monthsBetween(switchMonth, saleMonth) < 0) {
        errors.push({ id: "sale-month", message: "Expected sale month cannot be before the target switch month." });
      }
      if (propertyType === "private" && currentSource === "hdb") {
        errors.push({ id: "current-source", message: "A private property cannot have an HDB concessionary loan." });
      }
      if (currentSource === "hdb" && route === "reprice") {
        errors.push({ id: "route-refinance", message: "Choose refinance: HDB concessionary loans do not have a bank repricing package." });
      }
      const currentMonths = Math.round((currentYears || 0) * 12);
      const candidateMonths = Math.round((candidateYears || 0) * 12);
      if (currentRateMonths != null && currentRateMonths > currentMonths) {
        errors.push({ id: "current-rate-months", message: "Current-rate period cannot exceed the remaining tenure." });
      }
      if (introMonths != null && introMonths > candidateMonths) {
        errors.push({ id: "intro-months", message: "Starting-rate period cannot exceed the candidate tenure." });
      }
      if (extraPayment > 0 && (!extraMonth || extraMonth < 1)) {
        errors.push({ id: "extra-month", message: "Enter the month when the partial prepayment is made." });
      }
      if (extraPayment > (balance || 0)) {
        errors.push({ id: "extra-payment", message: "Partial prepayment cannot exceed the outstanding balance." });
      }
      if (extraMonth > Math.min(currentMonths, candidateMonths)) {
        errors.push({ id: "extra-month", message: "Partial prepayment month must be within both loan tenures." });
      }
      if (rebate > 0 && rebateMonthRaw == null) {
        errors.push({ id: "rebate-month", message: "Enter when the rebate is received, using month 0 for completion." });
      }

      return {
        errors,
        meta: {
          propertyType,
          currentSource,
          route,
          switchMonth,
          saleMonth,
          lockInEnd,
          clawbackEnd,
          actualPayment,
          stressUplift,
          stressExtraCost,
          ignoreStressRebate: byId("stress-no-rebate").checked,
        },
        comparison: {
          horizonMonths: Math.round(horizonMonths || 0),
          current: {
            principal: balance,
            annualRate: currentRate,
            rateAfter: currentResetRate,
            introMonths: Math.round(currentRateMonths || 0),
            termMonths: currentMonths,
            startMonth: switchMonth,
            extraPayment,
            extraPaymentMonth: extraPayment > 0 ? Math.round(extraMonth) : null,
          },
          candidate: {
            principal: balance,
            annualRate: candidateRate,
            rateAfter: resetRate,
            introMonths: Math.round(introMonths || 0),
            termMonths: candidateMonths,
            startMonth: switchMonth,
            extraPayment,
            extraPaymentMonth: extraPayment > 0 ? Math.round(extraMonth) : null,
          },
          costs,
        },
      };
    }

    function renderErrors(errors) {
      form.querySelectorAll("[aria-invalid='true']").forEach(input => input.removeAttribute("aria-invalid"));
      const summary = byId("error-summary");
      if (!errors.length) {
        summary.hidden = true;
        summary.replaceChildren();
        return;
      }
      const heading = document.createElement("strong");
      heading.textContent = `Check ${errors.length} ${errors.length === 1 ? "field" : "fields"} before calculating:`;
      const list = document.createElement("ul");
      errors.forEach(error => {
        const item = document.createElement("li");
        const link = document.createElement("a");
        link.href = `#${error.id}`;
        link.textContent = error.message;
        item.append(link);
        list.append(item);
        byId(error.id)?.setAttribute("aria-invalid", "true");
      });
      summary.replaceChildren(heading, list);
      summary.hidden = false;
      summary.tabIndex = -1;
      summary.focus();
    }

    function signedCurrency(value) {
      if (Math.abs(value) < 0.5) return money.format(0);
      return `${value > 0 ? "+" : "−"}${money.format(Math.abs(value))}`;
    }

    function monthLabel(value) {
      const parsed = parseMonth(value);
      return new Intl.DateTimeFormat("en-SG", { month: "short", year: "numeric" })
        .format(new Date(parsed.year, parsed.month - 1, 1));
    }

    function recoveryLabel(result, startMonth) {
      if (result.durableRecoveryMonth === 0) return "Immediate*";
      if (result.durableRecoveryMonth == null) return "Not within window";
      return `${result.durableRecoveryMonth} months · ${monthLabel(addMonths(startMonth, result.durableRecoveryMonth))}`;
    }

    function setText(id, value) {
      byId(id).textContent = value;
    }

    function renderWarnings(data, result, stress) {
      const warnings = [];
      const currentMonths = data.comparison.current.termMonths;
      const candidateMonths = data.comparison.candidate.termMonths;
      if (candidateMonths > currentMonths) {
        warnings.push(`The candidate tenure is ${Math.round((candidateMonths - currentMonths) / 12 * 10) / 10} years longer. A lower instalment can come from slower principal repayment.`);
      }
      if (
        data.meta.actualPayment > 0
        && Math.abs(data.meta.actualPayment - result.currentSchedule.firstPayment)
          > Math.max(50, result.currentSchedule.firstPayment * 0.03)
      ) {
        warnings.push(`Your entered instalment differs from the modelled amount by ${money.format(Math.abs(data.meta.actualPayment - result.currentSchedule.firstPayment))}. Check the balance, rate, tenure and whether your payment includes other items.`);
      }
      if (data.meta.lockInEnd && monthsBetween(data.meta.switchMonth, data.meta.lockInEnd) > 0) {
        warnings.push(`The target switch is before the entered lock-in end (${monthLabel(data.meta.lockInEnd)}). Confirm that the redemption penalty field captures the lender's actual charge.`);
      }
      if (data.meta.clawbackEnd && monthsBetween(data.meta.switchMonth, data.meta.clawbackEnd) > 0) {
        warnings.push(`The target switch is before the entered subsidy-clawback end (${monthLabel(data.meta.clawbackEnd)}). Confirm the clawback amount from the Letter of Offer.`);
      }
      if (data.meta.saleMonth) {
        const saleOffset = monthsBetween(data.meta.switchMonth, data.meta.saleMonth);
        if (result.durableRecoveryMonth == null || result.durableRecoveryMonth > saleOffset) {
          warnings.push(`The model does not recover switching costs before the expected sale month (${monthLabel(data.meta.saleMonth)}).`);
        }
      }
      if (result.firstRecoveryMonth != null && result.durableRecoveryMonth == null) {
        warnings.push("Savings briefly cover switching costs, but later modelled rates reverse that recovery within the selected window.");
      }
      if (result.costs.rebate > 0 && result.costs.rebateMonth > result.horizonMonths) {
        warnings.push("The entered rebate arrives after the comparison horizon, so it is excluded from the headline result.");
      }
      if (stress.horizonNetBenefit < 0 && result.horizonNetBenefit >= 0) {
        warnings.push("The base case is positive, but the entered stress case is negative. The decision is sensitive to the post-package rate or costs.");
      }
      if (data.meta.propertyType === "hdb" && data.meta.currentSource === "hdb" && data.meta.route === "refinance") {
        warnings.push("Switching an HDB concessionary loan to a bank loan is generally not reversible. Confirm current HDB and CPF rules before accepting an offer.");
      }
      if (!warnings.length) {
        warnings.push("No structural warning was triggered by these inputs. This does not verify eligibility, package conditions or future rates.");
      }

      const list = byId("warning-list");
      list.replaceChildren(...warnings.map(message => {
        const item = document.createElement("li");
        item.textContent = message;
        return item;
      }));
    }

    function renderComparisonTable(result) {
      const rows = [
        ["Interest over equal window", result.currentInterest, result.candidateInterest, result.grossInterestSaving],
        ["Ending loan balance", result.currentEndingBalance, result.candidateEndingBalance, result.currentEndingBalance - result.candidateEndingBalance],
        ["Initial monthly instalment", result.currentSchedule.firstPayment, result.candidateSchedule.firstPayment, result.initialMonthlyChange],
        ["Lifetime interest*", result.currentSchedule.totalInterest, result.candidateSchedule.totalInterest, result.lifetimeInterestSaving],
      ];
      const body = byId("comparison-body");
      body.replaceChildren(...rows.map(([label, current, candidate, difference]) => {
        const row = document.createElement("tr");
        [label, money.format(current), money.format(candidate), signedCurrency(difference)].forEach((value, index) => {
          const cell = document.createElement(index === 0 ? "th" : "td");
          if (index === 0) cell.scope = "row";
          cell.textContent = value;
          row.append(cell);
        });
        return row;
      }));
    }

    function renderChart(result) {
      const svg = byId("debt-chart");
      const width = 760;
      const height = 270;
      const left = 64;
      const right = 18;
      const top = 20;
      const bottom = 38;
      const maxMonths = Math.max(
        result.currentSchedule.rows.length,
        result.candidateSchedule.rows.length,
        1
      );
      const maxBalance = Math.max(
        result.currentSchedule.principal,
        result.candidateSchedule.principal,
        1
      );
      const x = month => left + (month / maxMonths) * (width - left - right);
      const y = balance => top + (1 - balance / maxBalance) * (height - top - bottom);
      const points = schedule => [
        `${x(0)},${y(schedule.principal)}`,
        ...schedule.rows.map(row => `${x(row.month)},${y(row.endingBalance)}`),
      ].join(" ");

      svg.querySelector(".chart-current").setAttribute("points", points(result.currentSchedule));
      svg.querySelector(".chart-candidate").setAttribute("points", points(result.candidateSchedule));
      svg.querySelector(".chart-y-top").textContent = compactMoney.format(maxBalance);
      svg.querySelector(".chart-y-bottom").textContent = money.format(0);
      svg.querySelector(".chart-x-end").textContent = `${Math.round(maxMonths / 12 * 10) / 10} years`;
      svg.querySelector(".chart-grid-top").setAttribute("y1", String(y(maxBalance)));
      svg.querySelector(".chart-grid-top").setAttribute("y2", String(y(maxBalance)));
      svg.querySelector(".chart-grid-bottom").setAttribute("y1", String(y(0)));
      svg.querySelector(".chart-grid-bottom").setAttribute("y2", String(y(0)));
    }

    function rateLabel(rates) {
      if (rates.length === 1) return `${rates[0].toFixed(2)}%`;
      return rates.map(rate => `${rate.toFixed(2)}%`).join(" → ");
    }

    function renderSchedule() {
      if (!latest) return;
      const schedule = activeSchedule === "current"
        ? latest.result.currentSchedule
        : latest.result.candidateSchedule;
      const annual = annualiseSchedule(schedule);
      const visible = showFullSchedule ? annual : annual.slice(0, 5);
      byId("schedule-body").replaceChildren(...visible.map(group => {
        const row = document.createElement("tr");
        const values = [
          group.year,
          rateLabel(group.rates),
          money.format(group.startBalance),
          money.format(group.scheduledPayments + group.extraPrincipal),
          money.format(group.interest),
          money.format(group.scheduledPrincipal + group.extraPrincipal),
          money.format(group.endingBalance),
        ];
        values.forEach((value, index) => {
          const cell = document.createElement(index === 0 ? "th" : "td");
          if (index === 0) cell.scope = "row";
          cell.textContent = value;
          row.append(cell);
        });
        return row;
      }));
      byId("schedule-caption").textContent = `${activeSchedule === "current" ? "Stay" : "Switch"} scenario · ${schedule.rows.length} modelled monthly payments · payoff ${monthLabel(schedule.payoffMonth)}.`;
      const showButton = byId("show-schedule");
      showButton.hidden = annual.length <= 5;
      showButton.textContent = showFullSchedule ? "Show first 5 years" : `Show all ${annual.length} calendar years`;
      document.querySelectorAll("[data-schedule]").forEach(button => {
        const selected = button.dataset.schedule === activeSchedule;
        button.setAttribute("aria-pressed", String(selected));
        button.classList.toggle("is-active", selected);
      });
    }

    function render(data, result, stress) {
      const routeLabel = data.meta.route === "reprice" ? "Reprice" : "Refinance";
      const routeAction = data.meta.route === "reprice" ? "Repricing" : "Refinancing";
      const horizonYears = result.horizonMonths / 12;
      const positive = result.horizonNetBenefit >= 0;
      setText("result-route", routeLabel);
      setText("result-window", `${horizonYears % 1 === 0 ? horizonYears : horizonYears.toFixed(1)}-year equal window`);
      setText("net-benefit", signedCurrency(result.horizonNetBenefit));
      byId("net-benefit").classList.toggle("is-negative", !positive);
      setText("net-benefit-label", positive ? "Estimated financing-cost benefit" : "Estimated additional financing cost");
      setText("result-verdict", positive
        ? `${routeAction} may lower modelled financing cost by ${money.format(result.horizonNetBenefit)} after entered costs and rebates received within the window.`
        : `${routeAction} costs ${money.format(Math.abs(result.horizonNetBenefit))} more in the selected equal comparison window.`);
      setText("current-payment", money.format(result.currentSchedule.firstPayment));
      setText("candidate-payment", money.format(result.candidateSchedule.firstPayment));
      setText("monthly-change", signedCurrency(result.initialMonthlyChange));
      setText("net-switch-cost", signedCurrency(-result.windowNetSwitchingCost));
      setText("recovery", recoveryLabel(result, data.meta.switchMonth));
      setText("gross-interest-saving", signedCurrency(result.grossInterestSaving));
      setText("breakdown-interest-saving", signedCurrency(result.grossInterestSaving));
      setText("gross-costs", money.format(result.grossSwitchingCost));
      setText("rebates-total", result.recognizedRebate
        ? `${money.format(result.recognizedRebate)} · month ${result.costs.rebateMonth}`
        : money.format(0));
      setText("breakdown-net-benefit", signedCurrency(result.horizonNetBenefit));
      setText("stress-rate", `${(data.comparison.candidate.rateAfter + data.meta.stressUplift).toFixed(2)}%`);
      setText("stress-benefit", signedCurrency(stress.horizonNetBenefit));
      setText("stress-copy", stress.horizonNetBenefit >= 0
        ? "The switch still has a positive modelled cost benefit under this stress input."
        : "The switch has a negative modelled cost benefit under this stress input.");
      byId("stress-card").classList.toggle("is-negative", stress.horizonNetBenefit < 0);
      renderWarnings(data, result, stress);
      renderComparisonTable(result);
      renderChart(result);
      renderSchedule();
      byId("results-updated").textContent = `Results updated. ${routeLabel} scenario ${positive ? "shows" : "does not show"} a financing-cost benefit over ${result.horizonMonths} months.`;
    }

    function calculate({ focusResults = false } = {}) {
      const data = collect();
      renderErrors(data.errors);
      if (data.errors.length) return false;
      try {
        const result = compareLoans(data.comparison);
        const stressComparison = {
          ...data.comparison,
          candidate: {
            ...data.comparison.candidate,
            rateAfter: data.comparison.candidate.rateAfter + data.meta.stressUplift,
          },
          costs: {
            ...data.comparison.costs,
            other: data.comparison.costs.other + data.meta.stressExtraCost,
            rebate: data.meta.ignoreStressRebate ? 0 : data.comparison.costs.rebate,
          },
        };
        const stress = compareLoans(stressComparison);
        latest = { data, result, stress };
        render(data, result, stress);
        if (focusResults) {
          byId("results-title").tabIndex = -1;
          byId("results-title").focus({ preventScroll: true });
          byId("results-panel").scrollIntoView({ behavior: "smooth", block: "start" });
        }
        return true;
      } catch (error) {
        renderErrors([{ id: "loan-balance", message: `The schedule could not be calculated: ${error.message}` }]);
        return false;
      }
    }

    form.addEventListener("submit", event => {
      event.preventDefault();
      calculate({ focusResults: true });
    });

    form.querySelectorAll("input[name='route']").forEach(input => {
      input.addEventListener("change", () => {
        applyRouteDefaults(input.value);
        calculate();
      });
    });

    form.addEventListener("reset", () => {
      window.setTimeout(() => {
        byId("switch-month").value = nextMonth();
        activeSchedule = "candidate";
        showFullSchedule = false;
        activeRoute = "refinance";
        updateRouteCostNote(activeRoute);
        calculate();
        byId("loan-balance").focus();
      }, 0);
    });

    document.querySelectorAll("[data-schedule]").forEach(button => {
      button.addEventListener("click", () => {
        activeSchedule = button.dataset.schedule;
        showFullSchedule = false;
        renderSchedule();
      });
    });

    byId("show-schedule").addEventListener("click", () => {
      showFullSchedule = !showFullSchedule;
      renderSchedule();
    });
    byId("print-plan").addEventListener("click", () => window.print());
    calculate();
  }

  function init(document) {
    const byId = id => document.getElementById(id);
    if (!byId("loan-tab-new")) {
      initLegacy(document);
      return;
    }

    const view = document.defaultView;
    const integer = new Intl.NumberFormat("en-SG", { maximumFractionDigits: 0 });
    const money = value => `S$${integer.format(Math.round(Number(value) || 0))}`;
    const signedMoney = value => {
      const amount = Number(value) || 0;
      if (Math.abs(amount) < 0.5) return money(0);
      return `${amount < 0 ? "−" : ""}${money(Math.abs(amount))}`;
    };
    const monthFormatter = new Intl.DateTimeFormat("en-SG", {
      month: "short",
      year: "numeric",
    });
    const state = {
      activeMode: "new",
      schedule: null,
      progressive: null,
      showAllYears: false,
      expandedYears: new Set(),
      editProgressive: false,
      stageMonths: PROGRESSIVE_STAGES.map(stage => stage.defaultMonth),
      rateRowCounter: 0,
    };

    function numberValue(id) {
      const input = byId(id);
      const raw = String(input?.value ?? "").trim();
      const normalized = raw
        .replace(/\s/g, "")
        .replace(/^(?:S\$|SGD|\$)/i, "")
        .replace(/,/g, "");
      return normalized === "" ? null : Number(normalized);
    }

    function currencyInputText(value, showCents = false) {
      return new Intl.NumberFormat("en-SG", {
        minimumFractionDigits: showCents ? 2 : 0,
        maximumFractionDigits: 2,
      }).format(value);
    }

    function formatCurrencyInput(input) {
      const value = numberValue(input.id);
      if (!Number.isFinite(value)) return;
      input.value = currencyInputText(value, String(input.value).includes("."));
    }

    function setCurrencyValue(id, value, showCents = false) {
      byId(id).value = currencyInputText(value, showCents);
    }

    function monthLabel(value) {
      const parsed = parseMonth(value);
      return monthFormatter.format(new Date(parsed.year, parsed.month - 1, 1));
    }

    function currentStartMonth() {
      return `${byId("schedule-start-year").value}-${byId("schedule-start-month").value}`;
    }

    function populateStartDate() {
      const now = new Date();
      const monthSelect = byId("schedule-start-month");
      const yearSelect = byId("schedule-start-year");
      const monthNames = new Intl.DateTimeFormat("en-SG", { month: "short" });
      for (let month = 1; month <= 12; month += 1) {
        const option = document.createElement("option");
        option.value = String(month).padStart(2, "0");
        option.textContent = monthNames.format(new Date(2026, month - 1, 1));
        monthSelect.append(option);
      }
      for (let year = now.getFullYear(); year <= now.getFullYear() + 35; year += 1) {
        const option = document.createElement("option");
        option.value = String(year);
        option.textContent = String(year);
        yearSelect.append(option);
      }
      monthSelect.value = String(now.getMonth() + 1).padStart(2, "0");
      yearSelect.value = String(now.getFullYear());
      byId("partial-date").value = addMonths(currentStartMonth(), 12);
    }

    function setErrors(errors) {
      document.querySelectorAll("[aria-invalid='true']").forEach(input => {
        input.removeAttribute("aria-invalid");
      });
      const summary = byId("calculator-errors");
      if (!errors.length) {
        summary.hidden = true;
        summary.textContent = "";
        return;
      }
      errors.forEach(error => byId(error.id)?.setAttribute("aria-invalid", "true"));
      summary.textContent = errors.map(error => error.message).join(" ");
      summary.hidden = false;
    }

    function requiredNumber(id, label, minimum, maximum, errors) {
      const value = numberValue(id);
      if (value == null || !Number.isFinite(value)) {
        errors.push({ id, message: `${label} is required.` });
      } else if (value < minimum || value > maximum) {
        errors.push({ id, message: `${label} must be between ${minimum} and ${maximum}.` });
      }
      return value;
    }

    function optionalNumber(id, label, maximum, errors) {
      const value = numberValue(id);
      if (value == null) return 0;
      if (!Number.isFinite(value) || value < 0 || value > maximum) {
        errors.push({ id, message: `${label} must be between 0 and ${maximum}.` });
      }
      return value;
    }

    function termMonths(yearId, monthId, label, errors) {
      const years = requiredNumber(yearId, `${label} years`, 0, 35, errors);
      const months = requiredNumber(monthId, `${label} months`, 0, 11, errors);
      const total = Math.round((years || 0) * 12 + (months || 0));
      if (total < 1) {
        errors.push({ id: yearId, message: `${label} must be at least one month.` });
      }
      return total;
    }

    function createRateRow(containerId, baseRateId, term) {
      if (term < 2) return;
      state.rateRowCounter += 1;
      const row = document.createElement("div");
      row.className = "rate-row";
      row.dataset.rateRow = String(state.rateRowCounter);

      const startLabel = document.createElement("label");
      startLabel.textContent = "From repayment month";
      const start = document.createElement("input");
      start.className = "segment-start";
      start.type = "number";
      start.min = "2";
      start.max = String(term);
      start.step = "1";
      start.value = String(Math.min(term, 25));
      start.setAttribute("aria-label", "Subsequent rate starts from repayment month");
      startLabel.append(start);

      const rateLabel = document.createElement("label");
      rateLabel.textContent = "Interest rate (%)";
      const rate = document.createElement("input");
      rate.className = "segment-rate";
      rate.type = "number";
      rate.min = "0";
      rate.max = "20";
      rate.step = "0.01";
      rate.value = String(numberValue(baseRateId) ?? 3.65);
      rate.setAttribute("aria-label", "Subsequent annual interest rate");
      rateLabel.append(rate);

      const remove = document.createElement("button");
      remove.className = "remove-rate";
      remove.type = "button";
      remove.setAttribute("aria-label", "Remove subsequent interest rate");
      remove.textContent = "×";
      remove.addEventListener("click", () => {
        row.remove();
        calculate();
      });
      row.append(startLabel, rateLabel, remove);
      byId(containerId).append(row);
      calculate();
    }

    function collectRateSegments(baseRateId, containerId, term, errors) {
      const baseRate = requiredNumber(baseRateId, "Interest rate", 0, 20, errors);
      const segments = [{ startMonth: 1, annualRate: baseRate }];
      byId(containerId).querySelectorAll(".rate-row").forEach((row, index) => {
        const startInput = row.querySelector(".segment-start");
        const rateInput = row.querySelector(".segment-rate");
        const start = Number(startInput.value);
        const rate = Number(rateInput.value);
        if (!Number.isInteger(start) || start < 2 || start > term) {
          errors.push({
            id: baseRateId,
            message: `Subsequent rate ${index + 1} must start between month 2 and month ${term}.`,
          });
        }
        if (!Number.isFinite(rate) || rate < 0 || rate > 20) {
          errors.push({ id: baseRateId, message: `Subsequent rate ${index + 1} must be between 0% and 20%.` });
        }
        segments.push({ startMonth: start, annualRate: rate });
      });
      return segments.sort((a, b) => a.startMonth - b.startMonth);
    }

    function partialRepayment(term, startMonth, principal, errors) {
      const amount = optionalNumber("partial-amount", "Partial repayment", 100000000, errors);
      if (!amount) return { extraPayment: 0, extraPaymentMonth: null };
      if (amount > principal) {
        errors.push({ id: "partial-amount", message: "Partial repayment cannot exceed the loan amount." });
      }
      const date = byId("partial-date").value;
      let month = null;
      try {
        month = monthsBetween(startMonth, date) + 1;
      } catch (_error) {
        errors.push({ id: "partial-date", message: "Choose a valid partial repayment month." });
      }
      if (month != null && (month < 1 || month > term)) {
        errors.push({ id: "partial-date", message: "Partial repayment must fall within the loan period." });
      }
      const mode = byId("partial-mode").value;
      const result = {
        extraPayment: amount,
        extraPaymentMonth: month,
        prepaymentMode: mode,
      };
      if (mode === "target-term") {
        result.postPrepaymentMonths = termMonths(
          "partial-new-years", "partial-new-months", "New loan period", errors
        );
      } else if (mode === "target-payment") {
        result.postPrepaymentPayment = requiredNumber(
          "partial-new-payment", "New monthly instalment", 1, 1000000, errors
        );
      }
      return result;
    }

    function collectNewLoan() {
      const errors = [];
      let principal = requiredNumber("new-loan-amount", "Loan amount", 1000, 100000000, errors);
      const term = termMonths("new-years", "new-months", "Loan period", errors);
      const startMonth = currentStartMonth();
      const rateSegments = collectRateSegments(
        "new-interest-rate", "new-rate-segments", term, errors
      );
      const construction = byId("construction-toggle").checked;
      let propertyPrice = null;
      let downPayment = null;
      if (construction) {
        propertyPrice = requiredNumber("property-price", "Property price", 1000, 100000000, errors);
        downPayment = requiredNumber("down-payment", "Downpayment", 0, 100000000, errors);
        if (propertyPrice != null && downPayment != null) {
          principal = propertyPrice - downPayment;
          if (principal <= 0) {
            errors.push({ id: "down-payment", message: "Downpayment must be lower than the property price." });
          } else if (Math.abs((numberValue("new-loan-amount") || 0) - principal) > 0.005) {
            const showCents = byId("property-price").value.includes(".")
              || byId("down-payment").value.includes(".");
            setCurrencyValue("new-loan-amount", principal, showCents);
          }
        }
        if (term < Math.max(...state.stageMonths)) {
          errors.push({ id: "new-years", message: "Loan period must extend beyond the final construction draw." });
        }
      }
      const partial = partialRepayment(term, startMonth, principal || 0, errors);
      return {
        errors,
        construction,
        propertyPrice,
        downPayment,
        loan: {
          principal,
          annualRate: rateSegments[0].annualRate,
          rateSegments,
          termMonths: term,
          startMonth,
          ...partial,
        },
      };
    }

    function collectExistingLoan() {
      const errors = [];
      const principal = requiredNumber(
        "existing-loan-amount", "Outstanding loan amount", 1000, 100000000, errors
      );
      const currentTerm = termMonths("current-years", "current-months", "Current loan period", errors);
      const packageTerm = termMonths("package-years", "package-months", "New package period", errors);
      const startMonth = currentStartMonth();
      const currentRates = collectRateSegments(
        "current-interest-rate", "current-rate-segments", currentTerm, errors
      );
      const packageRates = collectRateSegments(
        "package-interest-rate", "package-rate-segments", packageTerm, errors
      );
      const partialCurrent = partialRepayment(currentTerm, startMonth, principal || 0, errors);
      const partialPackage = partialRepayment(packageTerm, startMonth, principal || 0, errors);
      const costs = ["switch-legal", "switch-valuation", "switch-admin", "switch-penalty", "switch-other"]
        .reduce((sum, id) => sum + optionalNumber(id, "Switching cost", 10000000, errors), 0);
      const rebate = optionalNumber("switch-rebate", "Cash rebate", 10000000, errors);
      return {
        errors,
        costs,
        rebate,
        current: {
          principal,
          annualRate: currentRates[0].annualRate,
          rateSegments: currentRates,
          termMonths: currentTerm,
          startMonth,
          ...partialCurrent,
        },
        candidate: {
          principal,
          annualRate: packageRates[0].annualRate,
          rateSegments: packageRates,
          termMonths: packageTerm,
          startMonth,
          ...partialPackage,
        },
      };
    }

    function rateLabel(rates) {
      return rates.map(rate => `${rate.toFixed(2)}%`).join(" → ");
    }

    function paymentLabel(payments) {
      if (!payments.length) return money(0);
      const low = Math.min(...payments);
      const high = Math.max(...payments);
      return Math.abs(high - low) < 1 ? money(high) : `${money(low)}–${money(high)}`;
    }

    function createCell(value, heading) {
      const cell = document.createElement(heading ? "th" : "td");
      if (heading) cell.scope = "row";
      cell.textContent = value;
      return cell;
    }

    function createMonthDetails(group, schedule) {
      const detailRow = document.createElement("tr");
      detailRow.className = "month-details";
      const cell = document.createElement("td");
      cell.colSpan = 8;
      const table = document.createElement("table");
      table.setAttribute("aria-label", `Monthly repayments for ${group.year}`);
      const head = document.createElement("thead");
      const headRow = document.createElement("tr");
      ["Month", "Rate", "Beginning", "Instalment", "Interest", "Principal", "Ending"]
        .forEach(label => headRow.append(createCell(label, true)));
      head.append(headRow);
      const body = document.createElement("tbody");
      schedule.rows.filter(row => row.date.startsWith(group.year)).forEach(row => {
        const monthRow = document.createElement("tr");
        [
          monthLabel(row.date),
          `${row.annualRate.toFixed(2)}%`,
          money(row.beginningBalance),
          money(row.totalOutflow),
          money(row.interest),
          money(row.totalPrincipal),
          money(row.endingBalance),
        ].forEach((value, index) => monthRow.append(createCell(value, index === 0)));
        body.append(monthRow);
      });
      table.append(head, body);
      cell.append(table);
      detailRow.append(cell);
      return detailRow;
    }

    function renderSchedule() {
      const schedule = state.schedule;
      if (!schedule) return;
      byId("schedule-payoff").textContent = monthLabel(schedule.payoffMonth);
      byId("schedule-interest").textContent = money(schedule.totalInterest);
      byId("schedule-principal").textContent = money(schedule.totalPrincipalDrawn);
      byId("schedule-payable").textContent = money(
        schedule.totalPrincipalDrawn + schedule.totalInterest
      );

      const groups = annualiseSchedule(schedule);
      const visible = state.showAllYears ? groups : groups.slice(0, 5);
      const body = byId("schedule-body");
      body.replaceChildren();
      visible.forEach(group => {
        const row = document.createElement("tr");
        row.append(
          createCell(group.year, true),
          createCell(rateLabel(group.rates)),
          createCell(money(group.startBalance)),
          createCell(paymentLabel(group.monthlyPayments)),
          createCell(money(group.interest)),
          createCell(money(group.scheduledPrincipal + group.extraPrincipal)),
          createCell(money(group.endingBalance))
        );
        const actionCell = document.createElement("td");
        const toggle = document.createElement("button");
        const expanded = state.expandedYears.has(group.year);
        toggle.className = "year-toggle";
        toggle.type = "button";
        toggle.setAttribute("aria-expanded", String(expanded));
        toggle.setAttribute("aria-label", `${expanded ? "Hide" : "Show"} monthly repayments for ${group.year}`);
        toggle.textContent = expanded ? "⌃" : "⌄";
        toggle.addEventListener("click", () => {
          if (expanded) state.expandedYears.delete(group.year);
          else state.expandedYears.add(group.year);
          renderSchedule();
        });
        actionCell.append(toggle);
        row.append(actionCell);
        body.append(row);
        if (expanded) body.append(createMonthDetails(group, schedule));
      });
      const more = byId("schedule-show-more");
      more.hidden = groups.length <= 5;
      more.textContent = state.showAllYears ? "Show less" : "Show more";
    }

    function renderProgressive(plan) {
      const card = byId("progressive-card");
      card.hidden = !plan;
      if (!plan) return;
      byId("progress-initial").textContent = money(plan.initialPayment);
      byId("progress-option").textContent = money(plan.optionFee);
      byId("progress-sale").textContent = money(plan.saleAndPurchasePayment);
      const timeline = byId("progressive-timeline");
      timeline.replaceChildren(...plan.stages.map((stage, index) => {
        const row = document.createElement("div");
        row.className = "timeline-row";
        let date;
        if (state.editProgressive) {
          date = document.createElement("input");
          date.className = "timeline-month";
          date.type = "number";
          date.min = index === 0 ? "1" : String(state.stageMonths[index - 1] + 1);
          date.max = index === state.stageMonths.length - 1
            ? String(plan.schedule.termMonths)
            : String(state.stageMonths[index + 1] - 1);
          date.value = String(state.stageMonths[index]);
          date.setAttribute("aria-label", `${stage.name} draw month`);
          date.addEventListener("change", () => {
            state.stageMonths[index] = Number(date.value);
            calculate();
          });
        } else {
          date = document.createElement("b");
          date.textContent = stage.timeframe;
        }
        const copy = document.createElement("div");
        const title = document.createElement("b");
        title.textContent = stage.name;
        const detail = document.createElement("small");
        detail.textContent = `${stage.propertyPercent}% milestone · ${money(stage.cashOrCpf)} cash/CPF · ${money(stage.loanDraw)} loan`;
        copy.append(title, detail);
        const payment = document.createElement("output");
        payment.textContent = `${money(stage.monthlyPayment)}/mo`;
        row.append(date, copy, payment);
        return row;
      }));
    }

    function renderNew(data, schedule, progressive) {
      const principal = schedule.totalPrincipalDrawn;
      const payoffYear = parseMonth(schedule.payoffMonth).year;
      byId("new-summary-copy").innerHTML = "";
      const prefix = document.createTextNode("At the entered rates, your loan will be fully repaid by ");
      const year = document.createElement("strong");
      year.textContent = String(payoffYear);
      const middle = document.createTextNode(". Total interest is ");
      const interest = document.createElement("strong");
      interest.textContent = money(schedule.totalInterest);
      const suffix = document.createTextNode(` on top of ${money(principal)} principal.`);
      byId("new-summary-copy").append(prefix, year, middle, interest, suffix);
      state.progressive = progressive;
      renderProgressive(progressive);
    }

    function renderExisting(data, current, candidate) {
      const monthlyReduction = current.firstPayment - candidate.firstPayment;
      const firstYear = sumThrough(current, "interest", 12)
        - sumThrough(candidate, "interest", 12);
      const lifetime = current.totalInterest - candidate.totalInterest;
      const net = lifetime - data.costs + data.rebate;
      byId("current-monthly").textContent = money(current.firstPayment);
      byId("package-monthly").textContent = money(candidate.firstPayment);
      byId("monthly-reduction").textContent = signedMoney(monthlyReduction);
      byId("first-year-saving").textContent = signedMoney(firstYear);
      byId("lifetime-saving").textContent = signedMoney(lifetime);
      byId("net-saving-note").textContent = data.costs || data.rebate
        ? `After ${money(data.costs)} of entered fees and ${money(data.rebate)} of rebates, the modelled lifetime interest benefit is ${signedMoney(net)}.`
        : "Add fees and rebates to see their effect on the lifetime comparison.";
      state.progressive = null;
      renderProgressive(null);
    }

    function calculate() {
      try {
        if (state.activeMode === "new") {
          const data = collectNewLoan();
          setErrors(data.errors);
          if (data.errors.length) return false;
          let schedule;
          let progressive = null;
          if (data.construction) {
            progressive = buildProgressivePlan({
              propertyPrice: data.propertyPrice,
              loanAmount: data.loan.principal,
              stageMonths: state.stageMonths,
              loan: data.loan,
            });
            schedule = progressive.schedule;
          } else {
            schedule = buildSchedule(data.loan);
          }
          state.schedule = schedule;
          renderNew(data, schedule, progressive);
        } else {
          const data = collectExistingLoan();
          setErrors(data.errors);
          if (data.errors.length) return false;
          const current = buildSchedule(data.current);
          const candidate = buildSchedule(data.candidate);
          state.schedule = current;
          renderExisting(data, current, candidate);
        }
        renderSchedule();
        return true;
      } catch (error) {
        setErrors([{ id: state.activeMode === "new" ? "new-loan-amount" : "existing-loan-amount", message: `The schedule could not be calculated: ${error.message}` }]);
        return false;
      }
    }

    function activateMode(mode, focusTab) {
      state.activeMode = mode;
      state.showAllYears = false;
      state.expandedYears.clear();
      document.querySelectorAll("[data-loan-tab]").forEach(tab => {
        const active = tab.dataset.loanTab === mode;
        tab.setAttribute("aria-selected", String(active));
        tab.tabIndex = active ? 0 : -1;
      });
      document.querySelectorAll("[data-loan-panel]").forEach(panel => {
        const active = panel.dataset.loanPanel === mode;
        panel.hidden = !active;
        panel.querySelectorAll("input, select, button").forEach(control => {
          control.disabled = !active;
        });
      });
      if (focusTab) byId(`loan-tab-${mode}`).focus();
      calculate();
    }

    function updatePartialFields() {
      const mode = byId("partial-mode").value;
      byId("partial-term-fields").hidden = mode !== "target-term";
      byId("partial-payment-fields").hidden = mode !== "target-payment";
    }

    function alignConstructionValuesToLoan({ preserveDownpaymentRatio = false } = {}) {
      const principal = numberValue("new-loan-amount");
      const currentPrice = numberValue("property-price");
      const currentDownpayment = numberValue("down-payment");
      if (!(principal > 0) || !(currentPrice > 0) || !(currentDownpayment >= 0)) return;

      let propertyPrice;
      let downPayment;
      if (preserveDownpaymentRatio) {
        const enteredRatio = currentDownpayment < currentPrice
          ? currentDownpayment / currentPrice
          : 0.25;
        const ratio = Math.max(0, Math.min(0.95, enteredRatio));
        propertyPrice = principal / (1 - ratio);
        downPayment = propertyPrice - principal;
      } else {
        downPayment = currentDownpayment;
        propertyPrice = principal + downPayment;
      }
      const showCents = byId("new-loan-amount").value.includes(".")
        || Math.abs(propertyPrice - Math.round(propertyPrice)) > 0.005;
      setCurrencyValue("property-price", propertyPrice, showCents);
      setCurrencyValue("down-payment", downPayment, showCents);
    }

    populateStartDate();
    document.querySelectorAll("[data-currency-input]").forEach(input => {
      input.addEventListener("blur", () => formatCurrencyInput(input));
    });
    document.querySelectorAll("[data-loan-tab]").forEach((tab, index, tabs) => {
      tab.addEventListener("click", () => activateMode(tab.dataset.loanTab, false));
      tab.addEventListener("keydown", event => {
        if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
        event.preventDefault();
        const offset = event.key === "ArrowRight" ? 1 : -1;
        const target = tabs[(index + offset + tabs.length) % tabs.length];
        activateMode(target.dataset.loanTab, true);
      });
    });

    byId("new-add-rate").addEventListener("click", () => createRateRow(
      "new-rate-segments", "new-interest-rate",
      Math.round((numberValue("new-years") || 0) * 12 + (numberValue("new-months") || 0))
    ));
    byId("current-add-rate").addEventListener("click", () => createRateRow(
      "current-rate-segments", "current-interest-rate",
      Math.round((numberValue("current-years") || 0) * 12 + (numberValue("current-months") || 0))
    ));
    byId("package-add-rate").addEventListener("click", () => createRateRow(
      "package-rate-segments", "package-interest-rate",
      Math.round((numberValue("package-years") || 0) * 12 + (numberValue("package-months") || 0))
    ));

    [byId("new-loan-form"), byId("existing-loan-form")].forEach(form => {
      form.addEventListener("submit", event => event.preventDefault());
      form.addEventListener("input", event => {
        if (event.target.id === "construction-toggle") return;
        if (form.id === "new-loan-form" && byId("construction-toggle").checked) {
          const price = numberValue("property-price");
          if (event.target.id === "new-loan-amount") {
            alignConstructionValuesToLoan();
          } else if (["property-price", "down-payment"].includes(event.target.id)) {
            const down = numberValue("down-payment");
            if (price != null && down != null && price > down) {
              const showCents = byId("property-price").value.includes(".")
                || byId("down-payment").value.includes(".");
              setCurrencyValue("new-loan-amount", price - down, showCents);
            }
          }
        }
        calculate();
      });
      form.addEventListener("change", calculate);
    });
    byId("construction-toggle").addEventListener("change", () => {
      const checked = byId("construction-toggle").checked;
      byId("construction-fields").hidden = !checked;
      if (checked) alignConstructionValuesToLoan({ preserveDownpaymentRatio: true });
      calculate();
    });
    [
      "schedule-start-month", "schedule-start-year", "partial-amount", "partial-date",
      "partial-mode", "partial-new-years", "partial-new-months", "partial-new-payment",
    ]
      .forEach(id => byId(id).addEventListener("change", calculate));
    ["partial-amount", "partial-new-years", "partial-new-months", "partial-new-payment"]
      .forEach(id => byId(id).addEventListener("input", calculate));
    byId("partial-mode").addEventListener("change", updatePartialFields);
    byId("schedule-show-more").addEventListener("click", () => {
      state.showAllYears = !state.showAllYears;
      renderSchedule();
    });
    byId("edit-progressive").addEventListener("click", () => {
      state.editProgressive = !state.editProgressive;
      byId("edit-progressive").setAttribute("aria-pressed", String(state.editProgressive));
      byId("edit-progressive").textContent = state.editProgressive ? "Done editing" : "Edit timeframe";
      renderProgressive(state.progressive);
    });

    updatePartialFields();
    activateMode("new", false);
  }

  return {
    addMonths,
    annualiseSchedule,
    buildProgressivePlan,
    buildSchedule,
    compareLoans,
    init,
    monthlyPayment,
    monthsBetween,
    summarizeHomeLoan,
  };
});
