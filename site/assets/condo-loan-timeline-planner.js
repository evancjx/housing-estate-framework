/* Browser-only condo holding, loan-timeline and exit-scenario engine. */
(function (root, factory) {
  "use strict";

  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CondoTimelinePlanner = api;

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
  const DAY_MS = 24 * 60 * 60 * 1000;

  function finiteNumber(value, name) {
    const number = Number(value);
    if (!Number.isFinite(number)) throw new TypeError(`${name} must be a finite number`);
    return number;
  }

  function nonNegative(value, name) {
    const number = finiteNumber(value, name);
    if (number < 0) throw new RangeError(`${name} must not be negative`);
    return number;
  }

  function positiveInteger(value, name) {
    const number = finiteNumber(value, name);
    if (!Number.isInteger(number) || number <= 0) {
      throw new RangeError(`${name} must be a positive integer`);
    }
    return number;
  }

  function parseCurrency(value, options) {
    const allowBlank = Boolean(options && options.allowBlank);
    if (typeof value === "number") {
      if (!Number.isFinite(value)) throw new TypeError("currency value must be finite");
      return value;
    }
    const source = String(value == null ? "" : value).trim();
    if (!source && allowBlank) return null;
    const normalized = source
      .replace(/(?:SGD|S\$|\$)/gi, "")
      .replace(/[\s,]/g, "");
    if (!normalized && allowBlank) return null;
    if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(normalized)) {
      throw new RangeError("currency value is not a valid number");
    }
    const number = Number(normalized);
    if (!Number.isFinite(number)) throw new RangeError("currency value is not finite");
    return number;
  }

  function parseISODate(value, name) {
    const label = name || "date";
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
    if (!match) throw new RangeError(`${label} must use YYYY-MM-DD`);
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const date = new Date(Date.UTC(year, month - 1, day));
    if (
      date.getUTCFullYear() !== year
      || date.getUTCMonth() !== month - 1
      || date.getUTCDate() !== day
    ) {
      throw new RangeError(`${label} is not a valid calendar date`);
    }
    return date;
  }

  function toISODate(date) {
    return [
      String(date.getUTCFullYear()).padStart(4, "0"),
      String(date.getUTCMonth() + 1).padStart(2, "0"),
      String(date.getUTCDate()).padStart(2, "0"),
    ].join("-");
  }

  function compareDates(first, second) {
    return parseISODate(first).getTime() - parseISODate(second).getTime();
  }

  function addMonthsISO(value, offset) {
    const date = parseISODate(value);
    const months = Math.trunc(finiteNumber(offset, "offset"));
    const targetMonth = date.getUTCFullYear() * 12 + date.getUTCMonth() + months;
    const year = Math.floor(targetMonth / 12);
    const month = targetMonth - year * 12;
    const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
    return toISODate(new Date(Date.UTC(year, month, Math.min(date.getUTCDate(), lastDay))));
  }

  function addYearsISO(value, years) {
    return addMonthsISO(value, Math.trunc(finiteNumber(years, "years")) * 12);
  }

  function daysBetween(startValue, endValue) {
    const start = parseISODate(startValue, "start date");
    const end = parseISODate(endValue, "end date");
    return Math.round((end.getTime() - start.getTime()) / DAY_MS);
  }

  function yearFraction(startValue, endValue) {
    return daysBetween(startValue, endValue) / 365.2425;
  }

  function completedMonthsBetween(startValue, endValue) {
    const start = parseISODate(startValue, "start date");
    const end = parseISODate(endValue, "end date");
    let months = (end.getUTCFullYear() - start.getUTCFullYear()) * 12
      + end.getUTCMonth() - start.getUTCMonth();
    if (months > 0 && compareDates(addMonthsISO(startValue, months), endValue) > 0) months -= 1;
    return Math.max(0, months);
  }

  function monthlyPayment(principal, annualRate, months) {
    const balance = nonNegative(principal, "principal");
    const rate = nonNegative(annualRate, "annualRate");
    const count = positiveInteger(months, "months");
    if (balance === 0) return 0;
    const monthlyRate = rate / 1200;
    if (Math.abs(monthlyRate) < EPSILON) return balance / count;
    return balance * monthlyRate / (1 - Math.pow(1 + monthlyRate, -count));
  }

  function calculateTieredDuty(amount, tiers) {
    let remaining = nonNegative(amount, "dutiable amount");
    let duty = 0;
    for (const [width, rate] of tiers) {
      if (remaining <= EPSILON) break;
      const band = Math.min(remaining, width);
      duty += band * rate;
      remaining -= band;
    }
    return Math.floor(duty + EPSILON);
  }

  function calculateBSD(amount, acquisitionDate) {
    const price = nonNegative(amount, "dutiable purchase value");
    parseISODate(acquisitionDate, "acquisitionDate");
    if (acquisitionDate >= "2023-02-15") {
      return calculateTieredDuty(price, [
        [180000, 0.01], [180000, 0.02], [640000, 0.03],
        [500000, 0.04], [1500000, 0.05], [Infinity, 0.06],
      ]);
    }
    if (acquisitionDate >= "2018-02-20") {
      return calculateTieredDuty(price, [
        [180000, 0.01], [180000, 0.02], [640000, 0.03], [Infinity, 0.04],
      ]);
    }
    return calculateTieredDuty(price, [
      [180000, 0.01], [180000, 0.02], [Infinity, 0.03],
    ]);
  }

  function sellerStampDutyRate(acquisitionDate, saleDate) {
    parseISODate(acquisitionDate, "acquisitionDate");
    parseISODate(saleDate, "saleDate");
    if (compareDates(saleDate, acquisitionDate) < 0) {
      throw new RangeError("saleDate must not be before acquisitionDate");
    }
    let rates;
    if (acquisitionDate >= "2025-07-04") rates = [0.16, 0.12, 0.08, 0.04];
    else if (acquisitionDate >= "2017-03-11") rates = [0.12, 0.08, 0.04];
    else if (acquisitionDate >= "2011-01-14") rates = [0.16, 0.12, 0.08, 0.04];
    else return 0;
    for (let year = 1; year <= rates.length; year += 1) {
      if (compareDates(saleDate, addYearsISO(acquisitionDate, year)) < 0) {
        return rates[year - 1];
      }
    }
    return 0;
  }

  function sellerStampDutyZeroDate(acquisitionDate) {
    parseISODate(acquisitionDate, "acquisitionDate");
    if (acquisitionDate >= "2025-07-04") return addYearsISO(acquisitionDate, 4);
    if (acquisitionDate >= "2017-03-11") return addYearsISO(acquisitionDate, 3);
    if (acquisitionDate >= "2011-01-14") return addYearsISO(acquisitionDate, 4);
    return acquisitionDate;
  }

  const BUC_STAGE_TEMPLATE = [
    { name: "Booking / option", percent: 5, offset: 0 },
    { name: "Sale & purchase agreement", percent: 15, offset: 2 },
    { name: "Foundation complete", percent: 10, fraction: 0.15 },
    { name: "Concrete framework complete", percent: 10, fraction: 0.32 },
    { name: "Brick walls complete", percent: 5, fraction: 0.50 },
    { name: "Ceiling and roofing complete", percent: 5, fraction: 0.62 },
    { name: "Doors, windows and services", percent: 5, fraction: 0.73 },
    { name: "Carparks, roads and drains", percent: 5, fraction: 0.84 },
    { name: "Temporary Occupation Permit", percent: 25, top: true },
    { name: "Certificate of Statutory Completion", percent: 15, csc: true },
  ];

  function buildBucPlan(options) {
    const purchasePrice = finiteNumber(options.purchasePrice, "purchasePrice");
    const loanAmount = finiteNumber(options.loanAmount, "loanAmount");
    const acquisitionDate = String(options.acquisitionDate || "");
    const topDate = String(options.topDate || "");
    if (purchasePrice <= 0) throw new RangeError("purchasePrice must be positive");
    if (loanAmount < 0 || loanAmount > purchasePrice) {
      throw new RangeError("loanAmount must be between zero and purchasePrice");
    }
    if (purchasePrice - loanAmount + EPSILON < purchasePrice * 0.20) {
      throw new RangeError("The standard BUC schedule needs at least 20% owner funding");
    }
    parseISODate(acquisitionDate, "acquisitionDate");
    parseISODate(topDate, "topDate");
    const topMonths = completedMonthsBetween(acquisitionDate, topDate);
    if (compareDates(topDate, acquisitionDate) <= 0 || topMonths < 12) {
      throw new RangeError("topDate must be at least 12 months after acquisitionDate");
    }

    let previousOffset = 2;
    let fractionalPosition = 0;
    const offsets = BUC_STAGE_TEMPLATE.map(stage => {
      if (stage.offset != null) return stage.offset;
      if (stage.top) return topMonths;
      if (stage.csc) return topMonths + 12;
      const stagesStillBeforeTop = 5 - fractionalPosition;
      const candidate = Math.round(topMonths * stage.fraction);
      const maximum = topMonths - stagesStillBeforeTop;
      const offset = Math.max(previousOffset + 1, Math.min(candidate, maximum));
      previousOffset = offset;
      fractionalPosition += 1;
      return offset;
    });

    let remainingOwnerFunding = purchasePrice - loanAmount;
    const stages = BUC_STAGE_TEMPLATE.map((stage, index) => {
      const amount = purchasePrice * stage.percent / 100;
      const ownerContribution = Math.min(amount, Math.max(0, remainingOwnerFunding));
      const loanDraw = Math.max(0, amount - ownerContribution);
      remainingOwnerFunding = Math.max(0, remainingOwnerFunding - ownerContribution);
      return {
        name: stage.name,
        percent: stage.percent,
        date: stage.top
          ? topDate
          : stage.csc
            ? addMonthsISO(topDate, 12)
            : addMonthsISO(acquisitionDate, offsets[index]),
        amount,
        ownerContribution,
        loanDraw,
      };
    });
    const totalDrawn = stages.reduce((total, stage) => total + stage.loanDraw, 0);
    if (Math.abs(totalDrawn - loanAmount) > 0.01) {
      throw new RangeError("The BUC stages do not allocate the full loan amount");
    }
    return {
      purchasePrice,
      loanAmount,
      acquisitionDate,
      topDate,
      cscDate: addMonthsISO(topDate, 12),
      stages,
      draws: stages
        .filter(stage => stage.loanDraw > EPSILON)
        .map(stage => ({ date: stage.date, amount: stage.loanDraw, label: stage.name })),
      ownerFunding: purchasePrice - loanAmount,
    };
  }

  function buildLoanSchedule(options) {
    const annualRate = nonNegative(options.annualRate, "annualRate");
    const termMonths = positiveInteger(options.termMonths, "termMonths");
    const draws = (options.draws || []).map((draw, index) => {
      const amount = nonNegative(draw.amount, `draws[${index}].amount`);
      const date = String(draw.date || "");
      parseISODate(date, `draws[${index}].date`);
      return { ...draw, amount, date };
    }).filter(draw => draw.amount > EPSILON).sort((a, b) => compareDates(a.date, b.date));
    const totalPrincipalDrawn = draws.reduce((total, draw) => total + draw.amount, 0);
    if (!draws.length) {
      return {
        annualRate, termMonths, draws, rows: [], startDate: null, payoffDate: null,
        totalPrincipalDrawn: 0, totalInterest: 0, totalPayments: 0,
      };
    }

    const startDate = draws[0].date;
    const monthlyRate = annualRate / 1200;
    const rows = [];
    let balance = 0;
    let drawIndex = 0;
    let scheduledPayment = 0;
    let previousPaymentDate = startDate;
    for (let month = 1; month <= termMonths; month += 1) {
      const paymentDate = addMonthsISO(startDate, month);
      let disbursement = 0;
      while (
        drawIndex < draws.length
        && compareDates(draws[drawIndex].date, paymentDate) <= 0
      ) {
        if (compareDates(draws[drawIndex].date, previousPaymentDate) >= 0 || month === 1) {
          disbursement += draws[drawIndex].amount;
        }
        drawIndex += 1;
      }
      const openingBalance = balance;
      balance += disbursement;
      if (disbursement > EPSILON || month === 1) {
        scheduledPayment = monthlyPayment(balance, annualRate, termMonths - month + 1);
      }
      const interest = balance * monthlyRate;
      const payment = Math.min(scheduledPayment, balance + interest);
      const principal = Math.max(0, payment - interest);
      balance = Math.max(0, balance - principal);
      if (balance < 0.005) balance = 0;
      rows.push({
        month, date: paymentDate, openingBalance, disbursement,
        beginningBalance: openingBalance + disbursement,
        scheduledPayment: payment, interest, principal, endingBalance: balance,
      });
      previousPaymentDate = paymentDate;
      if (balance <= EPSILON && drawIndex >= draws.length) break;
    }
    if (balance > 0.01) throw new RangeError("The loan is not repaid within the entered tenure");
    return {
      annualRate,
      termMonths,
      draws,
      rows,
      startDate,
      payoffDate: rows.length ? rows[rows.length - 1].date : null,
      totalPrincipalDrawn,
      totalInterest: rows.reduce((total, row) => total + row.interest, 0),
      totalPayments: rows.reduce((total, row) => total + row.scheduledPayment, 0),
    };
  }

  function loanSnapshot(schedule, date) {
    parseISODate(date, "snapshot date");
    const drawn = schedule.draws
      .filter(draw => compareDates(draw.date, date) <= 0)
      .reduce((total, draw) => total + draw.amount, 0);
    const paidRows = schedule.rows.filter(row => compareDates(row.date, date) <= 0);
    const principalPaid = paidRows.reduce((total, row) => total + row.principal, 0);
    const interestPaid = paidRows.reduce((total, row) => total + row.interest, 0);
    const payments = paidRows.reduce((total, row) => total + row.scheduledPayment, 0);
    const balance = Math.max(0, drawn - principalPaid);
    let currentPayment = paidRows.length ? paidRows[paidRows.length - 1].scheduledPayment : 0;
    if (balance > EPSILON && schedule.startDate) {
      const elapsed = Math.min(
        schedule.termMonths - 1,
        completedMonthsBetween(schedule.startDate, date)
      );
      const drawnSinceLastPayment = paidRows.length
        ? schedule.draws.some(draw => (
          compareDates(draw.date, paidRows[paidRows.length - 1].date) > 0
          && compareDates(draw.date, date) <= 0
        ))
        : drawn > 0;
      if (drawnSinceLastPayment || currentPayment <= EPSILON) {
        currentPayment = monthlyPayment(
          balance,
          schedule.annualRate,
          Math.max(1, schedule.termMonths - elapsed)
        );
      }
    }
    return {
      date,
      drawn,
      principalPaid: Math.min(drawn, principalPaid),
      interestPaid,
      payments,
      balance,
      currentPayment,
      paymentCount: paidRows.length,
    };
  }

  function projectedValue(purchasePrice, annualGrowthPct, acquisitionDate, saleDate) {
    const price = nonNegative(purchasePrice, "purchasePrice");
    const growth = finiteNumber(annualGrowthPct, "annualGrowthPct");
    if (growth <= -100) throw new RangeError("annualGrowthPct must be greater than -100");
    const years = yearFraction(acquisitionDate, saleDate);
    if (years < 0) throw new RangeError("saleDate must not be before acquisitionDate");
    return price * Math.pow(1 + growth / 100, years);
  }

  function buildHoldingProjection(options) {
    const route = options.route;
    if (!['buc', 'resale'].includes(route)) throw new RangeError("route must be buc or resale");
    const purchasePrice = finiteNumber(options.purchasePrice, "purchasePrice");
    const purchaseMarketValue = options.purchaseMarketValue == null
      ? null : nonNegative(options.purchaseMarketValue, "purchaseMarketValue");
    const loanAmount = nonNegative(options.loanAmount, "loanAmount");
    const annualRate = nonNegative(options.annualRate, "annualRate");
    const termMonths = positiveInteger(options.termMonths, "termMonths");
    const acquisitionDate = String(options.acquisitionDate || "");
    const saleDate = String(options.saleDate || "");
    const annualGrowthPct = finiteNumber(options.annualGrowthPct, "annualGrowthPct");
    const areaSqft = nonNegative(options.areaSqft || 0, "areaSqft");
    if (purchasePrice <= 0) throw new RangeError("purchasePrice must be positive");
    if (loanAmount > purchasePrice) throw new RangeError("loanAmount must not exceed purchasePrice");
    if (annualGrowthPct <= -100) throw new RangeError("annualGrowthPct must be greater than -100");
    parseISODate(acquisitionDate, "acquisitionDate");
    parseISODate(saleDate, "saleDate");
    if (compareDates(saleDate, acquisitionDate) <= 0) {
      throw new RangeError("saleDate must be after acquisitionDate");
    }

    const absdPaid = nonNegative(options.absdPaid || 0, "absdPaid");
    const purchaseLegal = nonNegative(options.purchaseLegal || 0, "purchaseLegal");
    const purchaseOther = nonNegative(options.purchaseOther || 0, "purchaseOther");
    const sellingCostPct = nonNegative(options.sellingCostPct || 0, "sellingCostPct");
    const saleLegal = nonNegative(options.saleLegal || 0, "saleLegal");
    const saleOther = nonNegative(options.saleOther || 0, "saleOther");
    const holdingCosts = nonNegative(options.holdingCosts || 0, "holdingCosts");
    const netRent = nonNegative(options.netRent || 0, "netRent");
    const cpfRefund = nonNegative(options.cpfRefund || 0, "cpfRefund");
    const saleMarketValue = options.saleMarketValue == null
      ? null : nonNegative(options.saleMarketValue, "saleMarketValue");
    if (sellingCostPct > 100) throw new RangeError("sellingCostPct must not exceed 100");

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
      draws = plan.draws;
      const calledStages = plan.stages.filter(stage => compareDates(stage.date, saleDate) <= 0);
      calledAmount = calledStages.reduce((total, stage) => total + stage.amount, 0);
      ownerPropertyPaid = calledStages.reduce(
        (total, stage) => total + stage.ownerContribution,
        0
      );
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
      draws = loanAmount > EPSILON
        ? [{ date: completionDate, amount: loanAmount, label: "Full loan draw" }]
        : [];
      calledAmount = purchasePrice;
      ownerPropertyPaid = purchasePrice - loanAmount;
      uncalledDeveloperBalance = 0;
    }

    const schedule = buildLoanSchedule({ annualRate, termMonths, draws });
    const loanAtSale = loanSnapshot(schedule, saleDate);
    const dutiablePurchaseValue = Math.max(purchasePrice, purchaseMarketValue || 0);
    const bsd = calculateBSD(dutiablePurchaseValue, acquisitionDate);
    const mortgageDuty = Math.floor(Math.min(loanAmount * 0.004, 500) + EPSILON);
    const acquisitionCosts = bsd + absdPaid + purchaseLegal + purchaseOther + mortgageDuty;
    const ssdRate = sellerStampDutyRate(acquisitionDate, saleDate);
    const ssdZeroDate = sellerStampDutyZeroDate(acquisitionDate);
    const holdingYears = yearFraction(acquisitionDate, saleDate);

    function evaluateSale(salePrice) {
      const value = nonNegative(salePrice, "salePrice");
      const sellingAllowance = value * sellingCostPct / 100;
      const fixedSaleCosts = saleLegal + saleOther;
      const saleCosts = sellingAllowance + fixedSaleCosts;
      const ssdBase = Math.max(value, saleMarketValue || 0);
      const ssd = Math.floor(ssdBase * ssdRate + EPSILON);
      const grossGain = value - purchasePrice;
      const grossCagr = Math.pow(value / purchasePrice, 1 / holdingYears) - 1;
      const capitalProfit = value - saleCosts - ssd - purchasePrice - acquisitionCosts;
      const economicProfit = capitalProfit - loanAtSale.interestPaid - holdingCosts + netRent;
      const grossEquity = value - uncalledDeveloperBalance - loanAtSale.balance;
      const cashBeforeCpf = grossEquity - saleCosts - ssd;
      const cashReleased = cashBeforeCpf - cpfRefund;
      const ownerOutflow = ownerPropertyPaid + acquisitionCosts + loanAtSale.payments
        + holdingCosts - netRent;
      const netReturnBase = purchasePrice + economicProfit;
      const economicCagr = netReturnBase > 0
        ? Math.pow(netReturnBase / purchasePrice, 1 / holdingYears) - 1
        : null;
      return {
        salePrice: value,
        salePsf: areaSqft > 0 ? value / areaSqft : null,
        sellingAllowance,
        fixedSaleCosts,
        saleCosts,
        ssdBase,
        ssd,
        ssdRate,
        grossGain,
        grossCagr,
        capitalProfit,
        economicProfit,
        economicCagr,
        grossEquity,
        cashBeforeCpf,
        cashReleased,
        cashTopUp: Math.max(0, -cashReleased),
        ownerOutflow,
      };
    }

    function evaluateGrowth(growth) {
      return {
        growth,
        ...evaluateSale(projectedValue(purchasePrice, growth, acquisitionDate, saleDate)),
      };
    }

    const base = evaluateGrowth(annualGrowthPct);
    const scenarios = [
      evaluateGrowth(Math.max(-99.9, annualGrowthPct - 1)),
      base,
      evaluateGrowth(annualGrowthPct + 1),
    ];

    let lower = 0;
    let upper = Math.max(purchasePrice * 2, base.salePrice * 2, 1);
    while (evaluateSale(upper).economicProfit < 0 && upper < purchasePrice * 100) upper *= 2;
    let breakEvenPrice = null;
    let breakEvenGrowth = null;
    if (evaluateSale(upper).economicProfit >= 0) {
      for (let iteration = 0; iteration < 90; iteration += 1) {
        const middle = (lower + upper) / 2;
        if (evaluateSale(middle).economicProfit >= 0) upper = middle;
        else lower = middle;
      }
      breakEvenPrice = upper;
      breakEvenGrowth = (Math.pow(breakEvenPrice / purchasePrice, 1 / holdingYears) - 1) * 100;
    }

    const checkpoints = [{ label: "Acquisition", date: acquisitionDate }];
    for (let year = 1; ; year += 1) {
      const date = addYearsISO(acquisitionDate, year);
      if (compareDates(date, saleDate) >= 0) break;
      checkpoints.push({ label: `Year ${year}`, date });
    }
    checkpoints.push({ label: "Planned sale", date: saleDate });
    const checkpointRows = checkpoints.map(checkpoint => {
      const snapshot = loanSnapshot(schedule, checkpoint.date);
      let uncalled = 0;
      if (route === "buc") {
        const called = plan.stages
          .filter(stage => compareDates(stage.date, checkpoint.date) <= 0)
          .reduce((total, stage) => total + stage.amount, 0);
        uncalled = Math.max(0, purchasePrice - called);
      }
      const value = projectedValue(
        purchasePrice,
        annualGrowthPct,
        acquisitionDate,
        checkpoint.date
      );
      return {
        ...checkpoint,
        value,
        loan: snapshot,
        uncalledDeveloperBalance: uncalled,
        grossEquity: value - uncalled - snapshot.balance,
      };
    });

    const totalMonths = Math.max(1, completedMonthsBetween(acquisitionDate, saleDate));
    const chartStep = Math.max(1, Math.ceil(totalMonths / 72));
    const chartRows = [];
    for (let month = 0; month < totalMonths; month += chartStep) {
      const date = addMonthsISO(acquisitionDate, month);
      const snapshot = loanSnapshot(schedule, date);
      let uncalled = 0;
      if (route === "buc") {
        const called = plan.stages
          .filter(stage => compareDates(stage.date, date) <= 0)
          .reduce((total, stage) => total + stage.amount, 0);
        uncalled = Math.max(0, purchasePrice - called);
      }
      chartRows.push({
        date,
        value: projectedValue(purchasePrice, annualGrowthPct, acquisitionDate, date),
        obligations: snapshot.balance + uncalled,
      });
    }
    chartRows.push({
      date: saleDate,
      value: base.salePrice,
      obligations: loanAtSale.balance + uncalledDeveloperBalance,
    });

    const events = route === "buc"
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
    events.push({
      type: "ssd-zero",
      date: ssdZeroDate,
      title: "First modelled zero-SSD date",
      detail: "Confirm the legal dates with IRAS guidance",
      afterSale: compareDates(ssdZeroDate, saleDate) > 0,
    });
    events.push({
      type: "sale",
      date: saleDate,
      title: "Planned sale",
      detail: `Projected price ${base.salePrice}`,
      afterSale: false,
    });
    events.sort((a, b) => compareDates(a.date, b.date) || (a.type === "sale" ? 1 : -1));

    const warnings = [];
    if (loanAmount / purchasePrice > 0.75 + EPSILON) {
      warnings.push("The entered LTV exceeds 75%; this tool does not assess loan eligibility.");
    }
    if (route === "buc" && compareDates(saleDate, plan.topDate) < 0) {
      warnings.push(
        "The planned sale is before TOP. This is a simplified assignment/subsale projection; confirm restrictions, remaining developer payments and settlement mechanics."
      );
    }
    if (acquisitionDate < "2011-01-14") {
      warnings.push("Automatic SSD history before 14 January 2011 is not modelled.");
    }

    return {
      route,
      purchasePrice,
      purchaseMarketValue,
      dutiablePurchaseValue,
      areaSqft,
      acquisitionDate,
      saleDate,
      holdingYears,
      annualGrowthPct,
      loanAmount,
      annualRate,
      termMonths,
      plan,
      schedule,
      loanAtSale,
      calledAmount,
      ownerPropertyPaid,
      uncalledDeveloperBalance,
      bsd,
      absdPaid,
      mortgageDuty,
      acquisitionCosts,
      purchaseLegal,
      purchaseOther,
      sellingCostPct,
      saleLegal,
      saleOther,
      holdingCosts,
      netRent,
      cpfRefund,
      saleMarketValue,
      ssdRate,
      ssdZeroDate,
      base,
      scenarios,
      breakEvenPrice,
      breakEvenGrowth,
      checkpointRows,
      chartRows,
      events,
      warnings,
    };
  }

  function init(document) {
    const form = document.getElementById("timeline-form");
    if (!form) return;
    const byId = id => document.getElementById(id);
    const view = document.defaultView;
    const integer = new Intl.NumberFormat("en-SG", { maximumFractionDigits: 0 });
    const decimal = new Intl.NumberFormat("en-SG", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
    const dateFormatter = new Intl.DateTimeFormat("en-SG", {
      day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
    });
    const money = value => `S$${integer.format(Math.round(Number(value) || 0))}`;
    const signedMoney = value => {
      const number = Number(value) || 0;
      if (Math.abs(number) < 0.5) return "S$0";
      return `${number > 0 ? "+" : "−"}${money(Math.abs(number))}`;
    };
    const percentage = value => {
      const number = Number(value) || 0;
      return `${number > 0 ? "+" : number < 0 ? "−" : ""}${decimal.format(Math.abs(number))}%`;
    };
    const dateLabel = value => dateFormatter.format(parseISODate(value));
    let latest = null;
    let inputTimer = null;

    function routeValue() {
      return form.querySelector("input[name='property-route']:checked").value;
    }

    function updateRoutePanels() {
      const route = routeValue();
      document.querySelectorAll("[data-route-panel]").forEach(panel => {
        panel.hidden = panel.dataset.routePanel !== route;
      });
      byId("timeline-copy").textContent = route === "buc"
        ? "BUC progress calls, owner contributions, bank draws and the selected sale date."
        : "Legal acquisition, completed-property loan draw, SSD window and the selected sale date.";
    }

    function markValid() {
      form.querySelectorAll("[aria-invalid='true']").forEach(input => {
        input.removeAttribute("aria-invalid");
      });
    }

    function collect() {
      markValid();
      const errors = [];
      const addError = (id, message) => {
        errors.push({ id, message });
        byId(id)?.setAttribute("aria-invalid", "true");
      };
      const numberValue = (id, { minimum = null, maximum = null } = {}) => {
        const value = Number(byId(id).value);
        if (!Number.isFinite(value)) {
          addError(id, "Enter a valid number.");
          return 0;
        }
        if (minimum != null && value < minimum) addError(id, `Enter ${minimum} or more.`);
        if (maximum != null && value > maximum) addError(id, `Enter ${maximum} or less.`);
        return value;
      };
      const currencyValue = (id, { optional = false } = {}) => {
        try {
          const value = parseCurrency(byId(id).value, { allowBlank: optional });
          if (value != null && value < 0) addError(id, "Enter zero or a positive amount.");
          return value;
        } catch {
          addError(id, optional ? "Enter a valid amount or leave this blank." : "Enter a valid amount.");
          return optional ? null : 0;
        }
      };
      const dateValue = id => {
        const value = byId(id).value;
        try { parseISODate(value, id); } catch { addError(id, "Choose a valid date."); }
        return value;
      };

      const route = routeValue();
      const purchasePrice = currencyValue("purchase-price");
      const loanAmount = currencyValue("loan-amount");
      const acquisitionDate = dateValue("acquisition-date");
      const saleDate = dateValue("sale-date");
      const topDate = dateValue("buc-top-date");
      const completionDate = dateValue("resale-completion-date");
      const annualGrowthPct = numberValue("annual-growth", { minimum: -99, maximum: 30 });
      const annualRate = numberValue("loan-rate", { minimum: 0, maximum: 20 });
      const years = numberValue("loan-years", { minimum: 1, maximum: 35 });
      const areaSqft = numberValue("area-sqft", { minimum: 1 });
      const sellingCostPct = numberValue("selling-cost-percent", { minimum: 0, maximum: 20 });

      if (purchasePrice <= 0) addError("purchase-price", "Purchase price must be above zero.");
      if (loanAmount > purchasePrice) addError("loan-amount", "Loan amount cannot exceed the purchase price.");
      if (route === "buc" && loanAmount > purchasePrice * 0.80 + EPSILON) {
        addError("loan-amount", "The standard BUC schedule requires at least 20% owner funding.");
      }
      if (acquisitionDate && saleDate && compareDates(saleDate, acquisitionDate) <= 0) {
        addError("sale-date", "Sale date must be after the legal acquisition date.");
      }
      if (route === "buc" && acquisitionDate && topDate) {
        if (completedMonthsBetween(acquisitionDate, topDate) < 12) {
          addError("buc-top-date", "Expected TOP must be at least 12 months after acquisition.");
        }
      }
      if (route === "resale" && acquisitionDate && completionDate && saleDate) {
        if (compareDates(completionDate, acquisitionDate) < 0) {
          addError("resale-completion-date", "Completion cannot be before acquisition.");
        } else if (compareDates(saleDate, completionDate) < 0) {
          addError("sale-date", "Sale cannot be before the completed-property loan draw.");
        }
      }

      return {
        errors,
        projectName: byId("project-name").value.trim() || "The property",
        options: {
          route,
          propertyPrice: purchasePrice,
          purchasePrice,
          purchaseMarketValue: currencyValue("purchase-market-value", { optional: true }),
          acquisitionDate,
          saleDate,
          areaSqft,
          loanAmount,
          annualRate,
          termMonths: Math.round(years * 12),
          annualGrowthPct,
          topDate,
          completionDate,
          sellingCostPct,
          absdPaid: currencyValue("absd-paid"),
          purchaseLegal: currencyValue("purchase-legal"),
          purchaseOther: currencyValue("purchase-other"),
          saleMarketValue: currencyValue("sale-market-value", { optional: true }),
          saleLegal: currencyValue("sale-legal"),
          saleOther: currencyValue("sale-other"),
          holdingCosts: currencyValue("holding-costs"),
          netRent: currencyValue("net-rent"),
          cpfRefund: currencyValue("cpf-refund"),
        },
      };
    }

    function renderErrors(errors) {
      const box = byId("planner-errors");
      box.replaceChildren();
      box.hidden = errors.length === 0;
      if (!errors.length) return;
      const heading = document.createElement("strong");
      heading.textContent = `Check ${errors.length === 1 ? "this entry" : "these entries"}:`;
      const list = document.createElement("ul");
      errors.forEach(error => {
        const item = document.createElement("li");
        const link = document.createElement("a");
        link.href = `#${error.id}`;
        link.textContent = error.message;
        item.append(link);
        list.append(item);
      });
      box.append(heading, list);
    }

    function setSignedClass(element, value) {
      element.classList.toggle("positive", value > 0.5);
      element.classList.toggle("negative", value < -0.5);
    }

    function renderScenarios(result) {
      const metrics = [
        ["Annual growth input", scenario => percentage(scenario.growth)],
        ["Projected sale price", scenario => money(scenario.salePrice)],
        ["Projected sale PSF", scenario => scenario.salePsf == null ? "Not entered" : money(scenario.salePsf)],
        ["Gross price gain", scenario => signedMoney(scenario.grossGain)],
        ["Seller's Stamp Duty", scenario => `−${money(scenario.ssd)}`],
        ["Capital profit after transaction costs", scenario => signedMoney(scenario.capitalProfit)],
        ["Economic profit after entered costs", scenario => signedMoney(scenario.economicProfit)],
        ["Cash released / top-up", scenario => scenario.cashReleased >= 0
          ? money(scenario.cashReleased)
          : `${money(Math.abs(scenario.cashReleased))} top-up`],
      ];
      const rows = metrics.map(([label, formatter]) => {
        const row = document.createElement("tr");
        const heading = document.createElement("th");
        heading.scope = "row";
        heading.textContent = label;
        row.append(heading);
        result.scenarios.forEach((scenario, index) => {
          const cell = document.createElement("td");
          if (index === 1) cell.className = "scenario-base";
          cell.textContent = formatter(scenario);
          row.append(cell);
        });
        return row;
      });
      byId("scenario-body").replaceChildren(...rows);
    }

    function eventDetail(result, event) {
      if (event.type === "stage") {
        const stage = event.stage;
        return `${stage.percent}% due · owner ${money(stage.ownerContribution)} · bank ${money(stage.loanDraw)}`;
      }
      if (event.type === "draw") return `Bank draws ${money(result.loanAmount)}`;
      if (event.type === "sale") return `Projected ${money(result.base.salePrice)}`;
      return event.detail;
    }

    function renderTimeline(result) {
      const nodes = result.events.map(event => {
        const article = document.createElement("article");
        article.className = `event${event.type === "sale" ? " sale" : ""}${event.afterSale ? " after-sale" : ""}`;
        const time = document.createElement("time");
        time.dateTime = event.date;
        time.textContent = dateLabel(event.date);
        const title = document.createElement("b");
        title.textContent = event.title;
        const detail = document.createElement("small");
        detail.textContent = eventDetail(result, event);
        article.append(time, title, detail);
        if (event.afterSale) {
          const after = document.createElement("small");
          after.textContent = "After planned sale";
          article.append(after);
        }
        return article;
      });
      byId("timeline-events").replaceChildren(...nodes);
    }

    function renderChart(result) {
      const rows = result.chartRows;
      const width = 820;
      const height = 300;
      const left = 65;
      const right = 20;
      const top = 20;
      const bottom = 45;
      const maximum = Math.max(1, ...rows.flatMap(row => [row.value, row.obligations]));
      const x = index => left + (rows.length === 1 ? 0 : index / (rows.length - 1)) * (width - left - right);
      const y = value => top + (1 - value / maximum) * (height - top - bottom);
      const valuePoints = rows.map((row, index) => `${x(index)},${y(row.value)}`);
      const obligationPoints = rows.map((row, index) => `${x(index)},${y(row.obligations)}`);
      byId("chart-value-line").setAttribute("points", valuePoints.join(" "));
      byId("chart-obligation-line").setAttribute("points", obligationPoints.join(" "));
      byId("chart-fill").setAttribute(
        "d",
        `M ${valuePoints.join(" L ")} L ${obligationPoints.slice().reverse().join(" L ")} Z`
      );
      byId("chart-y-top").textContent = money(maximum);
      byId("chart-x-start").textContent = dateLabel(rows[0].date);
      byId("chart-x-end").textContent = dateLabel(rows[rows.length - 1].date);
      byId("loan-value-chart").setAttribute(
        "aria-label",
        `Projected property value rises from ${money(rows[0].value)} to ${money(rows.at(-1).value)}; remaining loan and developer obligations end at ${money(rows.at(-1).obligations)}.`
      );
    }

    function renderCheckpoints(result) {
      const rows = result.checkpointRows.map(checkpoint => {
        const row = document.createElement("tr");
        const values = [
          `${checkpoint.label} · ${dateLabel(checkpoint.date)}`,
          money(checkpoint.value),
          money(checkpoint.loan.drawn),
          checkpoint.loan.currentPayment > 0 ? money(checkpoint.loan.currentPayment) : "Not drawn",
          money(checkpoint.loan.interestPaid),
          money(checkpoint.loan.balance),
          money(checkpoint.uncalledDeveloperBalance),
          money(checkpoint.grossEquity),
        ];
        values.forEach((value, index) => {
          const cell = document.createElement(index === 0 ? "th" : "td");
          if (index === 0) cell.scope = "row";
          cell.textContent = value;
          row.append(cell);
        });
        return row;
      });
      byId("checkpoint-body").replaceChildren(...rows);
      byId("schedule-caption").textContent = `${result.loanAtSale.paymentCount} whole monthly payments are included through ${dateLabel(result.saleDate)}. Monthly-rest illustration; exact lender dates, daily accrual and rounding will differ.`;
    }

    function renderWaterfall(result) {
      const base = result.base;
      byId("waterfall-sale").textContent = money(base.salePrice);
      byId("waterfall-uncalled").textContent = `−${money(result.uncalledDeveloperBalance)}`;
      byId("waterfall-loan").textContent = `−${money(result.loanAtSale.balance)}`;
      byId("waterfall-selling").textContent = `−${money(base.sellingAllowance)}`;
      byId("waterfall-ssd").textContent = `−${money(base.ssd)}`;
      byId("waterfall-fixed").textContent = `−${money(base.fixedSaleCosts)}`;
      byId("waterfall-cpf").textContent = `−${money(result.cpfRefund)}`;
      const total = byId("waterfall-total");
      const label = byId("waterfall-total-label");
      if (base.cashReleased >= 0) {
        label.textContent = "Estimated cash released";
        total.textContent = money(base.cashReleased);
      } else {
        label.textContent = "Estimated cash top-up";
        total.textContent = money(Math.abs(base.cashReleased));
      }
      setSignedClass(total, base.cashReleased);
    }

    function render(projectName, result, { announce = false } = {}) {
      const base = result.base;
      const gainWord = base.grossGain >= 0 ? "gain" : "loss";
      const profitWord = base.economicProfit >= 0 ? "profit" : "loss";
      const cashPhrase = base.cashReleased >= 0
        ? `${money(base.cashReleased)} estimated cash released`
        : `${money(Math.abs(base.cashReleased))} estimated cash top-up`;
      byId("result-route").textContent = result.route === "buc"
        ? "BUC holding scenario"
        : "Completed / resale holding scenario";
      byId("result-verdict").textContent = `At a projected ${money(base.salePrice)} sale on ${dateLabel(result.saleDate)}, ${projectName} records a gross price ${gainWord} of ${money(Math.abs(base.grossGain))}, or ${percentage(base.grossCagr * 100)} a year. After entered transaction costs, duties, mortgage interest and holding items, the modelled economic ${profitWord} is ${money(Math.abs(base.economicProfit))}; this is separate from ${cashPhrase}.`;
      byId("kpi-sale-price").textContent = money(base.salePrice);
      byId("kpi-sale-psf").textContent = base.salePsf == null ? "Area not entered" : `${money(base.salePsf)} psf`;
      byId("kpi-gross-cagr").textContent = percentage(base.grossCagr * 100);
      setSignedClass(byId("kpi-gross-cagr"), base.grossCagr);
      byId("kpi-loan-balance").textContent = money(result.loanAtSale.balance);
      byId("kpi-loan-drawn").textContent = `${money(result.loanAtSale.drawn)} drawn · ${money(result.loanAtSale.interestPaid)} interest paid`;
      byId("kpi-economic-profit").textContent = signedMoney(base.economicProfit);
      setSignedClass(byId("kpi-economic-profit"), base.economicProfit);
      byId("kpi-net-return").textContent = base.economicCagr == null
        ? "Annualised net return is below −100%"
        : `${percentage(base.economicCagr * 100)} p.a. on purchase-price basis`;
      byId("kpi-cash-released").textContent = base.cashReleased >= 0
        ? money(base.cashReleased)
        : `${money(Math.abs(base.cashReleased))} top-up`;
      setSignedClass(byId("kpi-cash-released"), base.cashReleased);
      byId("kpi-break-even-growth").textContent = result.breakEvenGrowth == null
        ? "Not solved"
        : percentage(result.breakEvenGrowth);
      byId("kpi-break-even-price").textContent = result.breakEvenPrice == null
        ? "Check the entered costs"
        : `${money(result.breakEvenPrice)} sale price`;

      const ssdCopy = result.ssdRate > 0
        ? `<b>${integer.format(result.ssdRate * 100)}% SSD is modelled (${money(base.ssd)}).</b> The first modelled zero-SSD disposal date is ${dateLabel(result.ssdZeroDate)}. SSD uses the higher of projected price and the market value you entered.`
        : `<b>No SSD is modelled on the entered dates.</b> The first zero-SSD date for this acquisition schedule is ${dateLabel(result.ssdZeroDate)}.`;
      byId("ssd-banner").innerHTML = ssdCopy;
      if (result.warnings.length) {
        const warning = document.createElement("p");
        warning.style.marginBottom = "0";
        warning.textContent = result.warnings.join(" ");
        byId("ssd-banner").append(warning);
      }

      renderScenarios(result);
      renderTimeline(result);
      renderChart(result);
      renderCheckpoints(result);
      renderWaterfall(result);
      if (announce) {
        byId("result-live").textContent = `Projection updated. Economic ${profitWord} ${money(Math.abs(base.economicProfit))}.`;
      }
    }

    function calculate({ focusResults = false, announce = false } = {}) {
      const data = collect();
      renderErrors(data.errors);
      if (data.errors.length) return false;
      try {
        const result = buildHoldingProjection(data.options);
        latest = { data, result };
        render(data.projectName, result, { announce });
        if (focusResults) {
          byId("result-heading").focus({ preventScroll: true });
          byId("results-panel").scrollIntoView({ behavior: "smooth", block: "start" });
        }
        return true;
      } catch (error) {
        renderErrors([{ id: "purchase-price", message: `The projection could not be calculated: ${error.message}` }]);
        return false;
      }
    }

    form.addEventListener("submit", event => {
      event.preventDefault();
      calculate({ focusResults: true, announce: true });
    });
    form.addEventListener("input", event => {
      if (event.target.matches("input[name='property-route']")) return;
      view.clearTimeout(inputTimer);
      inputTimer = view.setTimeout(() => calculate(), 80);
    });
    form.addEventListener("change", event => {
      if (event.target.matches("input[name='property-route']")) updateRoutePanels();
      calculate();
    });
    form.querySelectorAll("[data-currency-input]").forEach(input => {
      input.addEventListener("blur", () => {
        try {
          const value = parseCurrency(input.value, { allowBlank: Boolean(input.placeholder) });
          if (value != null) {
            const decimals = Math.abs(value - Math.round(value)) > EPSILON ? 2 : 0;
            input.value = new Intl.NumberFormat("en-SG", {
              minimumFractionDigits: decimals,
              maximumFractionDigits: decimals,
            }).format(value);
          }
        } catch {
          // The linked error summary explains invalid currency without rewriting the entry.
        }
      });
    });
    form.addEventListener("reset", () => {
      view.setTimeout(() => {
        updateRoutePanels();
        calculate({ announce: true });
        byId("route-buc").focus();
      }, 0);
    });
    byId("print-plan").addEventListener("click", () => view.print());

    updateRoutePanels();
    calculate();
  }

  return {
    addMonthsISO,
    addYearsISO,
    buildBucPlan,
    buildHoldingProjection,
    buildLoanSchedule,
    calculateBSD,
    completedMonthsBetween,
    init,
    loanSnapshot,
    monthlyPayment,
    parseCurrency,
    projectedValue,
    sellerStampDutyRate,
    sellerStampDutyZeroDate,
    yearFraction,
  };
});
