/* Exact-dollar co-owner funding ledger for condo timeline planner V3. */
(function (root, factory) {
  "use strict";

  const api = factory(root.CondoTimelinePlanner);
  if (typeof module === "object" && module.exports) {
    module.exports = factory(require("./condo-loan-timeline-planner.js"));
  }
  root.CondoFundingLedgerV3 = api;

  if (root.document) {
    const start = () => api.init(root.document);
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", start, { once: true });
    } else {
      start();
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function (planner) {
  "use strict";

  const EPSILON = 1e-8;
  const MONEY_SCALE = 100;
  const STORAGE_KEY = "housing-estate-framework.condo-loan-timeline-planner-v3.draft.v1";
  const STORAGE_VERSION = 1;
  const FORM_VALUE_IDS = [
    "project-name", "area-sqft", "acquisition-date", "purchase-price", "loan-amount",
    "loan-rate", "loan-years", "buc-top-date", "resale-completion-date",
    "primary-owner-name", "partner-owner-name", "partner-ownership-share",
    "default-partner-payment-share", "annual-growth", "sale-date",
    "selling-cost-percent", "purchase-market-value", "absd-paid", "purchase-legal",
    "purchase-other", "sale-market-value", "sale-legal", "sale-other", "holding-costs",
    "net-rent", "cpf-refund",
  ];
  const FORM_CHECK_IDS = ["route-buc", "route-resale", "partner-enabled"];
  const ALLOCATION_FIELDS = [
    "primaryCash", "primaryCpf", "loan", "partnerCash", "partnerCpf",
  ];
  const OWNER_FUNDING_FIELDS = [
    "primaryCash", "primaryCpf", "partnerCash", "partnerCpf",
  ];
  const COUPLE_DIALOG_VALUE_IDS = [
    "couple-primary-name", "couple-partner-name", "couple-primary-cash",
    "couple-primary-cpf", "couple-partner-cash", "couple-partner-cpf",
  ];
  const FUNDING_PLAN_BORROWERS = ["joint", "primary", "partner"];
  // Cash is consumed before CPF so early cash calls naturally receive cash.
  // Primary-before-partner is only a deterministic tie-breaker, not a claim
  // about legal liability or CPF eligibility.
  const FUNDING_PLAN_SOURCE_ORDER = [
    "primaryCash", "partnerCash", "primaryCpf", "partnerCpf",
  ];

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

  function toCents(value, name) {
    const number = nonNegative(value, name || "amount");
    const scaled = number * MONEY_SCALE;
    if (!Number.isSafeInteger(Math.round(scaled))) {
      throw new RangeError(`${name || "amount"} is too large`);
    }
    if (Math.abs(scaled - Math.round(scaled)) > 1e-6) {
      throw new RangeError(`${name || "amount"} must not have more than two decimal places`);
    }
    return Math.round(scaled);
  }

  function fromCents(value) {
    const cents = finiteNumber(value, "cents");
    if (!Number.isSafeInteger(cents)) throw new RangeError("cents must be a safe integer");
    return cents / MONEY_SCALE;
  }

  function roundMoney(value) {
    const number = finiteNumber(value, "amount");
    const cents = Math.round(number * MONEY_SCALE);
    if (!Number.isSafeInteger(cents)) throw new RangeError("amount is too large");
    return fromCents(cents);
  }

  function normalizeShare(value, name) {
    const number = finiteNumber(value, name || "share");
    if (number < 0 || number > 100) {
      throw new RangeError(`${name || "share"} must be from 0 to 100`);
    }
    return number;
  }

  function emptyAllocations() {
    return {
      primaryCash: 0,
      primaryCpf: 0,
      loan: 0,
      partnerCash: 0,
      partnerCpf: 0,
    };
  }

  function allocationTotal(row) {
    return fromCents(ALLOCATION_FIELDS.reduce(
      (total, field) => total + toCents(row[field] || 0, field),
      0
    ));
  }

  function ownerFundingAllocation(row) {
    return fromCents(
      toCents(row.primaryCash || 0, "primaryCash")
      + toCents(row.primaryCpf || 0, "primaryCpf")
      + toCents(row.partnerCash || 0, "partnerCash")
      + toCents(row.partnerCpf || 0, "partnerCpf")
    );
  }

  function makeRow(options) {
    const category = options.category || "consideration";
    if (!["consideration", "cost", "note"].includes(category)) {
      throw new RangeError("row category is not supported");
    }
    const row = {
      key: String(options.key),
      sequence: Number(options.sequence || 0),
      date: String(options.date || ""),
      action: String(options.action || ""),
      category,
      paymentAmount: fromCents(toCents(options.paymentAmount || 0, "paymentAmount")),
      ...emptyAllocations(),
    };
    ALLOCATION_FIELDS.forEach(field => {
      row[field] = fromCents(toCents(options[field] || 0, field));
    });
    return row;
  }

  function splitOwnerFunding(amount, partnerSharePct) {
    const ownerFundingCents = toCents(amount, "ownerFunding");
    const partnerShare = normalizeShare(partnerSharePct, "partnerSharePct");
    const partnerCashCents = Math.round(ownerFundingCents * partnerShare / 100);
    return {
      primaryCash: fromCents(ownerFundingCents - partnerCashCents),
      partnerCash: fromCents(partnerCashCents),
    };
  }

  function validateFundingPlan(plan) {
    if (!plan || typeof plan !== "object" || Array.isArray(plan)) {
      throw new TypeError("funding plan must be an object");
    }
    if (!FUNDING_PLAN_BORROWERS.includes(plan.borrower)) {
      throw new RangeError("borrower must be joint, primary or partner");
    }
    const checked = { borrower: plan.borrower };
    OWNER_FUNDING_FIELDS.forEach(field => {
      if (!Object.prototype.hasOwnProperty.call(plan, field)
          || plan[field] == null || plan[field] === "") {
        throw new TypeError(`plan.${field} is required`);
      }
      checked[field] = fromCents(toCents(plan[field], `plan.${field}`));
    });
    return checked;
  }

  function applyFundingPlan(rows, plan) {
    if (!Array.isArray(rows)) throw new TypeError("rows must be an array");
    const checkedPlan = validateFundingPlan(plan);
    const plannedCents = Object.fromEntries(OWNER_FUNDING_FIELDS.map(field => [
      field,
      toCents(checkedPlan[field], `plan.${field}`),
    ]));
    const remainingCents = { ...plannedCents };
    const usedCents = Object.fromEntries(OWNER_FUNDING_FIELDS.map(field => [field, 0]));

    const appliedRows = rows.map((source, index) => {
      if (!source || typeof source !== "object" || Array.isArray(source)) {
        throw new TypeError(`rows[${index}] must be an object`);
      }
      const row = makeRow({ ...source, key: source.key || `row-${index}` });
      if (!Number.isFinite(row.sequence)) {
        throw new TypeError(`rows[${index}].sequence must be finite`);
      }
      OWNER_FUNDING_FIELDS.forEach(field => { row[field] = 0; });
      return row;
    });

    const monetaryIndexes = appliedRows
      .map((row, index) => ({ row, index }))
      .filter(item => item.row.category !== "note")
      .sort((first, second) => {
        const firstDate = first.row.date;
        const secondDate = second.row.date;
        if (firstDate !== secondDate) {
          if (!firstDate) return 1;
          if (!secondDate) return -1;
          return firstDate.localeCompare(secondDate);
        }
        const firstCategory = first.row.category === "cost" ? 0 : 1;
        const secondCategory = second.row.category === "cost" ? 0 : 1;
        return firstCategory - secondCategory
          || first.row.sequence - second.row.sequence
          || first.index - second.index;
      })
      .map(item => item.index);

    let requiredCents = 0;
    monetaryIndexes.forEach(index => {
      const row = appliedRows[index];
      const paymentCents = toCents(row.paymentAmount, `rows[${index}].paymentAmount`);
      const loanCents = toCents(row.loan, `rows[${index}].loan`);
      if (loanCents > paymentCents) {
        throw new RangeError(`rows[${index}].loan cannot exceed its payment amount`);
      }
      let rowRequirementCents = paymentCents - loanCents;
      requiredCents += rowRequirementCents;
      FUNDING_PLAN_SOURCE_ORDER.forEach(field => {
        if (rowRequirementCents === 0 || remainingCents[field] === 0) return;
        const allocationCents = Math.min(rowRequirementCents, remainingCents[field]);
        row[field] = fromCents(allocationCents);
        usedCents[field] += allocationCents;
        remainingCents[field] -= allocationCents;
        rowRequirementCents -= allocationCents;
      });
    });

    const plannedTotalCents = OWNER_FUNDING_FIELDS.reduce(
      (total, field) => total + plannedCents[field],
      0
    );
    const usedTotalCents = OWNER_FUNDING_FIELDS.reduce(
      (total, field) => total + usedCents[field],
      0
    );
    const shortageCents = Math.max(0, requiredCents - usedTotalCents);
    const excessCents = plannedTotalCents - usedTotalCents;
    const sources = Object.fromEntries(OWNER_FUNDING_FIELDS.map(field => [field, {
      planned: fromCents(plannedCents[field]),
      used: fromCents(usedCents[field]),
      excess: fromCents(remainingCents[field]),
    }]));

    return {
      rows: appliedRows,
      summary: {
        borrower: checkedPlan.borrower,
        ownerFundingRequired: fromCents(requiredCents),
        ownerFundingPlanned: fromCents(plannedTotalCents),
        ownerFundingUsed: fromCents(usedTotalCents),
        shortage: fromCents(shortageCents),
        excess: fromCents(excessCents),
        balanced: shortageCents === 0 && excessCents === 0,
        sources,
      },
    };
  }

  function apportionStageAmounts(purchasePrice, stages) {
    const totalCents = toCents(purchasePrice, "purchasePrice");
    const weighted = stages.map((stage, index) => {
      const percent = nonNegative(stage.percent, `stages[${index}].percent`);
      const ideal = totalCents * percent / 100;
      const cents = Math.floor(ideal);
      return { index, cents, remainder: ideal - cents };
    });
    const percentTotal = stages.reduce((total, stage) => total + stage.percent, 0);
    if (Math.abs(percentTotal - 100) > EPSILON) {
      throw new RangeError("BUC stage percentages must total 100%");
    }
    let centsLeft = totalCents - weighted.reduce((total, item) => total + item.cents, 0);
    [...weighted]
      .sort((first, second) => second.remainder - first.remainder || first.index - second.index)
      .forEach(item => {
        if (centsLeft <= 0) return;
        weighted[item.index].cents += 1;
        centsLeft -= 1;
      });
    if (centsLeft !== 0) throw new RangeError("BUC stage amounts could not be apportioned");
    return weighted.map(item => fromCents(item.cents));
  }

  function buildStandardFundingLedger(projection, partnerSharePct) {
    if (!projection || !projection.route) throw new TypeError("projection is required");
    const partnerShare = normalizeShare(partnerSharePct, "partnerSharePct");
    const rows = [];
    let sequence = 0;
    const push = row => {
      sequence += 10;
      rows.push(makeRow({ sequence, ...row }));
    };
    const acquisitionDate = projection.acquisitionDate;
    const agreementDate = planner.addMonthsISO(acquisitionDate, 1);

    if (projection.route === "buc") {
      const stageAmounts = apportionStageAmounts(
        projection.purchasePrice,
        projection.plan.stages
      );
      let ownerFundingCents = toCents(
        projection.purchasePrice - projection.loanAmount,
        "ownerFunding"
      );
      projection.plan.stages.forEach((stage, index) => {
        if (index === 1) {
          push({
            key: "note-sp-received",
            date: agreementDate,
            action: "Receive Sale & Purchase Agreement",
            category: "note",
          });
          if (projection.purchaseLegal > EPSILON) {
            push({
              key: "cost-purchase-legal",
              date: agreementDate,
              action: "Purchase legal fee",
              category: "cost",
              paymentAmount: projection.purchaseLegal,
              primaryCash: projection.purchaseLegal,
            });
          }
          if (projection.purchaseOther > EPSILON) {
            push({
              key: "cost-purchase-other",
              date: agreementDate,
              action: "Other purchase costs",
              category: "cost",
              paymentAmount: projection.purchaseOther,
              primaryCash: projection.purchaseOther,
            });
          }
          push({
            key: "note-sp-exercise",
            date: stage.date,
            action: "Exercise Sale & Purchase Agreement",
            category: "note",
          });
          if (projection.bsd > EPSILON) {
            push({
              key: "cost-bsd",
              date: stage.date,
              action: "Buyer's Stamp Duty",
              category: "cost",
              paymentAmount: projection.bsd,
              primaryCash: projection.bsd,
            });
          }
          if (projection.absdPaid > EPSILON) {
            push({
              key: "cost-absd",
              date: stage.date,
              action: "Additional Buyer's Stamp Duty entered",
              category: "cost",
              paymentAmount: projection.absdPaid,
              primaryCash: projection.absdPaid,
            });
          }
          if (projection.mortgageDuty > EPSILON) {
            push({
              key: "cost-mortgage-duty",
              date: stage.date,
              action: "Mortgage duty",
              category: "cost",
              paymentAmount: projection.mortgageDuty,
              primaryCash: projection.mortgageDuty,
            });
          }
        }
        const paymentAmount = stageAmounts[index];
        const paymentCents = toCents(paymentAmount, "paymentAmount");
        const ownerContributionCents = Math.min(paymentCents, ownerFundingCents);
        const loanDrawCents = paymentCents - ownerContributionCents;
        ownerFundingCents -= ownerContributionCents;
        const ownerSplit = splitOwnerFunding(
          fromCents(ownerContributionCents),
          partnerShare
        );
        push({
          key: `stage-${index}`,
          date: stage.date,
          action: stage.name,
          category: "consideration",
          paymentAmount,
          primaryCash: ownerSplit.primaryCash,
          partnerCash: ownerSplit.partnerCash,
          loan: fromCents(loanDrawCents),
        });
      });
    } else {
      push({
        key: "note-acquisition",
        date: acquisitionDate,
        action: "Legal acquisition / accepted agreement",
        category: "note",
      });
      if (projection.purchaseLegal > EPSILON) {
        push({
          key: "cost-purchase-legal",
          date: acquisitionDate,
          action: "Purchase legal fee",
          category: "cost",
          paymentAmount: projection.purchaseLegal,
          primaryCash: projection.purchaseLegal,
        });
      }
      if (projection.purchaseOther > EPSILON) {
        push({
          key: "cost-purchase-other",
          date: acquisitionDate,
          action: "Other purchase costs",
          category: "cost",
          paymentAmount: projection.purchaseOther,
          primaryCash: projection.purchaseOther,
        });
      }
      if (projection.bsd > EPSILON) {
        push({
          key: "cost-bsd",
          date: acquisitionDate,
          action: "Buyer's Stamp Duty",
          category: "cost",
          paymentAmount: projection.bsd,
          primaryCash: projection.bsd,
        });
      }
      if (projection.absdPaid > EPSILON) {
        push({
          key: "cost-absd",
          date: acquisitionDate,
          action: "Additional Buyer's Stamp Duty entered",
          category: "cost",
          paymentAmount: projection.absdPaid,
          primaryCash: projection.absdPaid,
        });
      }
      if (projection.mortgageDuty > EPSILON) {
        push({
          key: "cost-mortgage-duty",
          date: projection.plan.completionDate,
          action: "Mortgage duty",
          category: "cost",
          paymentAmount: projection.mortgageDuty,
          primaryCash: projection.mortgageDuty,
        });
      }
      const ownerSplit = splitOwnerFunding(
        projection.purchasePrice - projection.loanAmount,
        partnerShare
      );
      push({
        key: "resale-completion",
        date: projection.plan.completionDate,
        action: "Completion / property payment",
        category: "consideration",
        paymentAmount: projection.purchasePrice,
        primaryCash: ownerSplit.primaryCash,
        partnerCash: ownerSplit.partnerCash,
        loan: projection.loanAmount,
      });
    }
    return rows.sort((first, second) => (
      first.date.localeCompare(second.date) || first.sequence - second.sequence
    ));
  }

  function validateFundingLedger(rows, projection) {
    if (!Array.isArray(rows)) throw new TypeError("rows must be an array");
    if (!projection) throw new TypeError("projection is required");
    const totals = {
      considerationPayments: 0,
      considerationAllocated: 0,
      considerationOwnerFunding: 0,
      considerationLoan: 0,
      costPayments: 0,
      costAllocated: 0,
      primaryCash: 0,
      primaryCpf: 0,
      loan: 0,
      partnerCash: 0,
      partnerCpf: 0,
    };
    const checkedRows = rows.map((source, index) => {
      const row = makeRow({ ...source, key: source.key || `row-${index}` });
      const allocated = allocationTotal(row);
      const difference = roundMoney(row.paymentAmount - allocated);
      let issue = "";
      if (!row.date) issue = "Date required";
      else if (!row.action.trim()) issue = "Action required";
      else if (row.category === "note" && (row.paymentAmount > EPSILON || allocated > EPSILON)) {
        issue = "Timeline notes must be S$0";
      } else if (Math.abs(difference) > 0.01) {
        issue = difference > 0 ? "Funding not fully allocated" : "Funding exceeds payment";
      }
      if (row.category === "consideration") {
        totals.considerationPayments += row.paymentAmount;
        totals.considerationAllocated += allocated;
        totals.considerationOwnerFunding += ownerFundingAllocation(row);
        totals.considerationLoan += row.loan;
      } else if (row.category === "cost") {
        totals.costPayments += row.paymentAmount;
        totals.costAllocated += allocated;
      }
      ALLOCATION_FIELDS.forEach(field => { totals[field] += row[field]; });
      return { ...row, allocated, difference, issue, balanced: !issue };
    });

    Object.keys(totals).forEach(key => { totals[key] = roundMoney(totals[key]); });

    const targets = {
      purchasePrice: roundMoney(projection.purchasePrice),
      loanAmount: roundMoney(projection.loanAmount),
      ownerFunding: roundMoney(projection.purchasePrice - projection.loanAmount),
      acquisitionCosts: roundMoney(projection.acquisitionCosts),
    };
    const differences = {
      purchasePayments: roundMoney(totals.considerationPayments - targets.purchasePrice),
      purchaseAllocated: roundMoney(totals.considerationAllocated - targets.purchasePrice),
      loan: roundMoney(totals.considerationLoan - targets.loanAmount),
      ownerFunding: roundMoney(totals.considerationOwnerFunding - targets.ownerFunding),
      acquisitionCosts: roundMoney(totals.costPayments - targets.acquisitionCosts),
      costAllocated: roundMoney(totals.costAllocated - targets.acquisitionCosts),
    };
    const balanced = checkedRows.every(row => row.balanced)
      && Object.values(differences).every(value => Math.abs(value) <= 0.01);
    return { rows: checkedRows, totals, targets, differences, balanced };
  }

  function splitOutcome(projection, partnerOwnershipPct) {
    const partnerShare = normalizeShare(partnerOwnershipPct, "partnerOwnershipPct");
    const primaryShare = 100 - partnerShare;
    const primaryCashReleased = projection.base.cashReleased * primaryShare / 100;
    const partnerCashReleased = projection.base.cashReleased - primaryCashReleased;
    const primaryEconomicProfit = projection.base.economicProfit * primaryShare / 100;
    const partnerEconomicProfit = projection.base.economicProfit - primaryEconomicProfit;
    return {
      primaryShare,
      partnerShare,
      primaryCashReleased,
      partnerCashReleased,
      primaryEconomicProfit,
      partnerEconomicProfit,
    };
  }

  function init(document) {
    const form = document.getElementById("timeline-form");
    const enabledInput = document.getElementById("partner-enabled");
    if (!form || !enabledInput || !planner) return;
    const byId = id => document.getElementById(id);
    const view = document.defaultView;
    const ledgers = new Map();
    let customCounter = 0;
    let refreshTimer = null;
    let saveTimer = null;
    let pendingDraftSave = false;
    let suppressSaveUntilUserEdit = false;
    let coupleFundingPlan = null;
    let coupleSetupComplete = false;
    let coupleDialogDraft = null;
    let coupleDialogDraftActive = false;
    let dialogRequiresEnableConfirmation = false;
    const precise = new Intl.NumberFormat("en-SG", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
    const oneDecimal = new Intl.NumberFormat("en-SG", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 1,
    });
    const money = value => `S$${precise.format(roundMoney(Number(value) || 0))}`;
    const moneyInput = value => precise.format(Number(value) || 0);

    function currency(id, optional) {
      const value = planner.parseCurrency(byId(id).value, { allowBlank: Boolean(optional) });
      return value == null ? null : value;
    }

    function number(id) {
      return finiteNumber(byId(id).value, id);
    }

    function routeValue() {
      const checked = form.querySelector("input[name='property-route']:checked");
      if (!checked) throw new RangeError("Choose a property route");
      return checked.value;
    }

    function draftStatus(message) {
      const output = byId("draft-save-status");
      if (output) output.textContent = message;
    }

    function localStorageAccess() {
      try {
        return view.localStorage;
      } catch {
        return null;
      }
    }

    function validateCurrentDraftInputs() {
      if (!form.checkValidity()) throw new RangeError("Some form fields are invalid");
      normalizeShare(number("partner-ownership-share"), "Partner legal ownership");
      normalizeShare(number("default-partner-payment-share"), "Partner funding share");
      return collectProjection();
    }

    function encodeLedgerRow(row) {
      return {
        key: String(row.key),
        sequence: Number(row.sequence || 0),
        date: String(row.date || ""),
        action: String(row.action || ""),
        category: String(row.category || "note"),
        paymentAmountCents: toCents(row.paymentAmount || 0, "paymentAmount"),
        allocationCents: Object.fromEntries(ALLOCATION_FIELDS.map(field => [
          field,
          toCents(row[field] || 0, field),
        ])),
      };
    }

    function decodeLedgerRow(source, seenKeys) {
      if (!source || typeof source !== "object") throw new TypeError("Saved row is invalid");
      const key = String(source.key || "");
      const sequence = Number(source.sequence);
      const date = String(source.date || "");
      const action = String(source.action || "");
      if (!key || key.length > 120 || seenKeys.has(key)) {
        throw new RangeError("Saved row keys must be unique");
      }
      if (!Number.isSafeInteger(sequence) || Math.abs(sequence) > 10000000) {
        throw new RangeError("Saved row sequence is invalid");
      }
      if (date && !/^\d{4}-\d{2}-\d{2}$/.test(date)) {
        throw new RangeError("Saved row date is invalid");
      }
      if (action.length > 300) throw new RangeError("Saved row action is too long");
      if (!source.allocationCents || typeof source.allocationCents !== "object") {
        throw new TypeError("Saved row allocations are invalid");
      }
      const paymentAmountCents = Number(source.paymentAmountCents);
      if (!Number.isSafeInteger(paymentAmountCents) || paymentAmountCents < 0) {
        throw new RangeError("Saved payment amount is invalid");
      }
      const allocations = Object.fromEntries(ALLOCATION_FIELDS.map(field => {
        const cents = Number(source.allocationCents[field]);
        if (!Number.isSafeInteger(cents) || cents < 0) {
          throw new RangeError(`Saved ${field} allocation is invalid`);
        }
        return [field, fromCents(cents)];
      }));
      seenKeys.add(key);
      return makeRow({
        key,
        sequence,
        date,
        action,
        category: source.category,
        paymentAmount: fromCents(paymentAmountCents),
        ...allocations,
      });
    }

    function encodeCoupleFunding() {
      if (!coupleSetupComplete || !coupleFundingPlan) return { complete: false };
      const checked = validateFundingPlan(coupleFundingPlan);
      return {
        complete: true,
        borrower: checked.borrower,
        amountCents: Object.fromEntries(OWNER_FUNDING_FIELDS.map(field => [
          field,
          toCents(checked[field], `plan.${field}`),
        ])),
      };
    }

    function decodeCoupleFunding(source) {
      if (source == null) return { complete: false, plan: null };
      if (!source || typeof source !== "object" || typeof source.complete !== "boolean") {
        throw new TypeError("Saved couple funding setup is invalid");
      }
      if (!source.complete) return { complete: false, plan: null };
      if (!source.amountCents || typeof source.amountCents !== "object") {
        throw new TypeError("Saved couple funding amounts are invalid");
      }
      const plan = { borrower: source.borrower };
      OWNER_FUNDING_FIELDS.forEach(field => {
        const cents = Number(source.amountCents[field]);
        if (!Number.isSafeInteger(cents) || cents < 0) {
          throw new RangeError(`Saved ${field} funding is invalid`);
        }
        plan[field] = fromCents(cents);
      });
      return { complete: true, plan: validateFundingPlan(plan) };
    }

    function snapshotCoupleDialogDraft() {
      const borrower = document.querySelector("input[name='loan-borrower']:checked");
      return {
        borrower: borrower ? borrower.value : "",
        open: Boolean(byId("couple-funding-dialog").open),
        values: Object.fromEntries(COUPLE_DIALOG_VALUE_IDS.map(id => [id, byId(id).value])),
      };
    }

    function validateCoupleDialogDraft(source) {
      if (source == null) return null;
      if (!source || typeof source !== "object" || Array.isArray(source)) {
        throw new TypeError("Saved couple setup draft is invalid");
      }
      if (!FUNDING_PLAN_BORROWERS.includes(source.borrower)) {
        throw new RangeError("Saved couple setup borrower is invalid");
      }
      if (source.open != null && typeof source.open !== "boolean") {
        throw new TypeError("Saved couple setup open state is invalid");
      }
      if (!source.values || typeof source.values !== "object" || Array.isArray(source.values)) {
        throw new TypeError("Saved couple setup values are invalid");
      }
      if (Object.keys(source.values).some(id => !COUPLE_DIALOG_VALUE_IDS.includes(id))) {
        throw new RangeError("Saved couple setup contains an unknown field");
      }
      const values = {};
      COUPLE_DIALOG_VALUE_IDS.forEach(id => {
        const value = source.values[id];
        if (typeof value !== "string" || value.length > 1000) {
          throw new RangeError(`Saved ${id} value is invalid`);
        }
        values[id] = value;
      });
      return { borrower: source.borrower, open: source.open === true, values };
    }

    function encodeCoupleDialogDraft() {
      if (!coupleDialogDraftActive) return null;
      if (byId("couple-funding-dialog").open || !coupleDialogDraft) {
        coupleDialogDraft = snapshotCoupleDialogDraft();
      }
      return validateCoupleDialogDraft(coupleDialogDraft);
    }

    function captureDraft() {
      validateCurrentDraftInputs();
      const values = Object.fromEntries(FORM_VALUE_IDS.map(id => [id, byId(id).value]));
      const checks = Object.fromEntries(FORM_CHECK_IDS.map(id => [id, byId(id).checked]));
      const savedLedgers = {};
      ledgers.forEach((state, route) => {
        if (!["buc", "resale"].includes(route)) return;
        savedLedgers[route] = {
          signature: String(state.signature || ""),
          dirty: Boolean(state.dirty),
          rows: state.rows.map(encodeLedgerRow),
        };
      });
      return {
        schemaVersion: STORAGE_VERSION,
        savedAt: new Date().toISOString(),
        form: { values, checks },
        coupleFunding: encodeCoupleFunding(),
        coupleDialogDraft: encodeCoupleDialogDraft(),
        ledgers: savedLedgers,
      };
    }

    function saveDraft() {
      view.clearTimeout(saveTimer);
      saveTimer = null;
      if (suppressSaveUntilUserEdit) return false;
      const storage = localStorageAccess();
      if (!storage) {
        draftStatus("Automatic saving is unavailable in this browser.");
        return false;
      }
      try {
        storage.setItem(STORAGE_KEY, JSON.stringify(captureDraft()));
        pendingDraftSave = false;
        draftStatus("Saved automatically in this browser. Reset clears the saved draft.");
        return true;
      } catch (error) {
        if (error instanceof RangeError || error instanceof TypeError) {
          draftStatus("Not saved yet — finish the highlighted or incomplete entries.");
        } else {
          draftStatus("This browser could not save the draft.");
        }
        return false;
      }
    }

    function scheduleSave() {
      suppressSaveUntilUserEdit = false;
      pendingDraftSave = true;
      view.clearTimeout(saveTimer);
      draftStatus("Saving draft…");
      saveTimer = view.setTimeout(saveDraft, 180);
    }

    function clearSavedDraft() {
      view.clearTimeout(saveTimer);
      saveTimer = null;
      pendingDraftSave = false;
      suppressSaveUntilUserEdit = true;
      const storage = localStorageAccess();
      if (storage) {
        try {
          storage.removeItem(STORAGE_KEY);
        } catch {
          // Reset still clears in-memory state when browser storage is unavailable.
        }
      }
      draftStatus("Saved draft cleared. New edits will be saved automatically.");
    }

    function restoreDraft() {
      const storage = localStorageAccess();
      if (!storage) return false;
      const snapshots = {};
      [...FORM_VALUE_IDS, ...FORM_CHECK_IDS].forEach(id => {
        const input = byId(id);
        snapshots[id] = input.type === "checkbox" || input.type === "radio"
          ? input.checked
          : input.value;
      });
      try {
        const raw = storage.getItem(STORAGE_KEY);
        if (!raw) return false;
        if (raw.length > 250000) throw new RangeError("Saved draft is too large");
        const saved = JSON.parse(raw);
        if (!saved || saved.schemaVersion !== STORAGE_VERSION) {
          throw new RangeError("Saved draft version is unsupported");
        }
        if (!saved.form || typeof saved.form !== "object") {
          throw new TypeError("Saved form is missing");
        }
        const values = saved.form.values || {};
        const checks = saved.form.checks || {};
        if (Object.keys(values).some(id => !FORM_VALUE_IDS.includes(id))) {
          throw new RangeError("Saved form contains an unknown field");
        }
        if (Object.keys(checks).some(id => !FORM_CHECK_IDS.includes(id))) {
          throw new RangeError("Saved form contains an unknown control");
        }
        FORM_VALUE_IDS.forEach(id => {
          if (!(id in values)) return;
          if (typeof values[id] !== "string" || values[id].length > 1000) {
            throw new RangeError(`Saved ${id} value is invalid`);
          }
          byId(id).value = values[id];
        });
        FORM_CHECK_IDS.forEach(id => {
          if (!(id in checks)) return;
          if (typeof checks[id] !== "boolean") {
            throw new RangeError(`Saved ${id} state is invalid`);
          }
          byId(id).checked = checks[id];
        });
        if (byId("route-buc").checked === byId("route-resale").checked) {
          throw new RangeError("Saved property route is invalid");
        }
        validateCurrentDraftInputs();

        const restoredCoupleFunding = decodeCoupleFunding(saved.coupleFunding);
        const restoredCoupleDialogDraft = validateCoupleDialogDraft(
          saved.coupleDialogDraft == null ? null : saved.coupleDialogDraft
        );
        const restoredLedgers = new Map();
        const savedLedgers = saved.ledgers || {};
        if (!savedLedgers || typeof savedLedgers !== "object") {
          throw new TypeError("Saved ledgers are invalid");
        }
        if (Object.keys(savedLedgers).some(route => !["buc", "resale"].includes(route))) {
          throw new RangeError("Saved draft contains an unknown property route");
        }
        Object.entries(savedLedgers).forEach(([route, state]) => {
          if (!state || typeof state !== "object" || !Array.isArray(state.rows)) {
            throw new TypeError("Saved ledger is invalid");
          }
          if (state.rows.length > 250 || typeof state.signature !== "string"
            || state.signature.length > 20000 || typeof state.dirty !== "boolean") {
            throw new RangeError("Saved ledger exceeds its limits");
          }
          const seenKeys = new Set();
          const rows = state.rows.map(row => decodeLedgerRow(row, seenKeys));
          restoredLedgers.set(route, {
            rows,
            signature: state.signature,
            dirty: state.dirty,
            stale: false,
          });
        });
        ledgers.clear();
        restoredLedgers.forEach((state, route) => { ledgers.set(route, state); });
        coupleSetupComplete = restoredCoupleFunding.complete;
        coupleFundingPlan = restoredCoupleFunding.plan;
        coupleDialogDraft = restoredCoupleDialogDraft;
        coupleDialogDraftActive = Boolean(restoredCoupleDialogDraft);
        customCounter = 0;
        ledgers.forEach(state => {
          state.rows.forEach(row => {
            const match = /^custom-(\d+)$/.exec(row.key);
            if (match) customCounter = Math.max(customCounter, Number(match[1]));
          });
        });
        draftStatus("Restored your last saved draft from this browser.");
        return true;
      } catch {
        [...FORM_VALUE_IDS, ...FORM_CHECK_IDS].forEach(id => {
          const input = byId(id);
          if (input.type === "checkbox" || input.type === "radio") input.checked = snapshots[id];
          else input.value = snapshots[id];
        });
        ledgers.clear();
        coupleSetupComplete = false;
        coupleFundingPlan = null;
        coupleDialogDraft = null;
        coupleDialogDraftActive = false;
        customCounter = 0;
        try {
          storage.removeItem(STORAGE_KEY);
        } catch {
          // Ignore storage cleanup failures and continue with safe HTML defaults.
        }
        draftStatus("The saved draft was invalid and was cleared; defaults were restored.");
        return false;
      }
    }

    function collectProjection() {
      const route = routeValue();
      return planner.buildHoldingProjection({
        route,
        purchasePrice: currency("purchase-price"),
        purchaseMarketValue: currency("purchase-market-value", true),
        acquisitionDate: byId("acquisition-date").value,
        saleDate: byId("sale-date").value,
        areaSqft: number("area-sqft"),
        loanAmount: currency("loan-amount"),
        annualRate: number("loan-rate"),
        termMonths: Math.round(number("loan-years") * 12),
        annualGrowthPct: number("annual-growth"),
        topDate: byId("buc-top-date").value,
        completionDate: byId("resale-completion-date").value,
        sellingCostPct: number("selling-cost-percent"),
        absdPaid: currency("absd-paid"),
        purchaseLegal: currency("purchase-legal"),
        purchaseOther: currency("purchase-other"),
        saleMarketValue: currency("sale-market-value", true),
        saleLegal: currency("sale-legal"),
        saleOther: currency("sale-other"),
        holdingCosts: currency("holding-costs"),
        netRent: currency("net-rent"),
        cpfRefund: currency("cpf-refund"),
      });
    }

    function projectionSignature(projection) {
      return JSON.stringify({
        route: projection.route,
        purchasePrice: projection.purchasePrice,
        loanAmount: projection.loanAmount,
        acquisitionDate: projection.acquisitionDate,
        bsd: projection.bsd,
        absdPaid: projection.absdPaid,
        purchaseLegal: projection.purchaseLegal,
        purchaseOther: projection.purchaseOther,
        mortgageDuty: projection.mortgageDuty,
        coupleFunding: coupleSetupComplete && coupleFundingPlan
          ? OWNER_FUNDING_FIELDS.map(field => toCents(coupleFundingPlan[field], field))
          : null,
        plan: projection.route === "buc"
          ? projection.plan.stages.map(stage => [stage.date, stage.amount, stage.loanDraw])
          : projection.plan.completionDate,
      });
    }

    function generatedFundingLedger(projection) {
      const rows = buildStandardFundingLedger(projection, 0);
      return coupleSetupComplete && coupleFundingPlan
        ? applyFundingPlan(rows, coupleFundingPlan).rows
        : rows;
    }

    function currentLedger(projection, { regenerate = false } = {}) {
      const route = projection.route;
      const signature = projectionSignature(projection);
      let state = ledgers.get(route);
      if (!state || regenerate) {
        state = {
          rows: generatedFundingLedger(projection),
          signature,
          dirty: false,
          stale: false,
        };
        ledgers.set(route, state);
      } else if (state.signature !== signature) {
        if (state.dirty) state.stale = true;
        else {
          state.rows = generatedFundingLedger(projection);
          state.signature = signature;
          state.stale = false;
        }
      } else {
        state.stale = false;
      }
      return state;
    }

    function ownerNames() {
      return {
        primary: byId("primary-owner-name").value.trim() || "Owner 1",
        partner: byId("partner-owner-name").value.trim() || "Partner",
      };
    }

    function modalMoney(id) {
      const parsed = planner.parseCurrency(byId(id).value);
      return fromCents(toCents(parsed, id));
    }

    function readCoupleFundingPlan() {
      const borrower = document.querySelector("input[name='loan-borrower']:checked");
      return validateFundingPlan({
        borrower: borrower ? borrower.value : "",
        primaryCash: modalMoney("couple-primary-cash"),
        primaryCpf: modalMoney("couple-primary-cpf"),
        partnerCash: modalMoney("couple-partner-cash"),
        partnerCpf: modalMoney("couple-partner-cpf"),
      });
    }

    function fundingPlanResult(projection, plan) {
      return applyFundingPlan(buildStandardFundingLedger(projection, 0), plan);
    }

    function seedCoupleFundingPlan(projection) {
      if (coupleSetupComplete && coupleFundingPlan) return { ...coupleFundingPlan };
      const share = normalizeShare(number("default-partner-payment-share"));
      const validation = validateFundingLedger(
        buildStandardFundingLedger(projection, share),
        projection
      );
      return validateFundingPlan({
        borrower: "joint",
        primaryCash: validation.totals.primaryCash,
        primaryCpf: validation.totals.primaryCpf,
        partnerCash: validation.totals.partnerCash,
        partnerCpf: validation.totals.partnerCpf,
      });
    }

    function showCoupleError(message) {
      const output = byId("couple-funding-errors");
      output.textContent = message || "";
      output.hidden = !message;
    }

    function renderCoupleReconciliation(projection, plan) {
      const summary = fundingPlanResult(projection, plan).summary;
      byId("couple-required-funding").textContent = money(summary.ownerFundingRequired);
      byId("couple-entered-funding").textContent = money(summary.ownerFundingPlanned);
      const difference = byId("couple-funding-difference");
      if (summary.shortage > EPSILON) {
        difference.textContent = `${money(summary.shortage)} short`;
        setSignedClass(difference, -summary.shortage);
      } else if (summary.excess > EPSILON) {
        difference.textContent = `${money(summary.excess)} excess`;
        setSignedClass(difference, summary.excess);
      } else {
        difference.textContent = "S$0 · matched";
        difference.classList.remove("negative");
        difference.classList.add("positive");
      }
      return summary;
    }

    function updateCoupleDialogSummary() {
      try {
        const projection = collectProjection();
        const plan = readCoupleFundingPlan();
        renderCoupleReconciliation(projection, plan);
        showCoupleError("");
      } catch {
        byId("couple-entered-funding").textContent = "—";
        byId("couple-funding-difference").textContent = "Check the amounts";
      }
    }

    function updateLoanLabels() {
      const names = ownerNames();
      const borrower = coupleFundingPlan ? coupleFundingPlan.borrower : "joint";
      const longLabel = borrower === "primary"
        ? `${names.primary} bank loan`
        : borrower === "partner"
          ? `${names.partner} bank loan`
          : "Joint bank loan";
      const shortLabel = borrower === "joint" ? "Joint loan" : longLabel;
      byId("ledger-loan-heading").textContent = longLabel;
      byId("ledger-loan-column-heading").textContent = shortLabel;
    }

    function updateCouplePlanStatus(projection) {
      const output = byId("couple-plan-status");
      if (!coupleSetupComplete || !coupleFundingPlan) {
        output.textContent = "Complete the couple funding setup before generating the ledger.";
        output.className = "couple-plan-status negative";
        updateLoanLabels();
        return;
      }
      try {
        const summary = fundingPlanResult(projection || collectProjection(), coupleFundingPlan).summary;
        if (summary.shortage > EPSILON) {
          output.textContent = `Saved setup: ${money(summary.shortage)} shortfall · edit the couple funding setup`;
          output.className = "couple-plan-status negative";
        } else if (summary.excess > EPSILON) {
          output.textContent = `Saved setup: ${money(summary.excess)} remains unallocated`;
          output.className = "couple-plan-status positive";
        } else {
          output.textContent = `Saved setup: ${money(summary.ownerFundingRequired)} owner funding fully allocated`;
          output.className = "couple-plan-status positive";
        }
      } catch {
        output.textContent = "Update the property inputs to reconcile the couple funding setup.";
        output.className = "couple-plan-status negative";
      }
      updateLoanLabels();
    }

    function openCoupleFundingDialog({ confirmEnable = false } = {}) {
      const dialog = byId("couple-funding-dialog");
      try {
        const projection = collectProjection();
        dialogRequiresEnableConfirmation = confirmEnable;
        if (coupleDialogDraftActive && coupleDialogDraft) {
          const draft = validateCoupleDialogDraft(coupleDialogDraft);
          COUPLE_DIALOG_VALUE_IDS.forEach(id => {
            byId(id).value = draft.values[id];
          });
          const borrower = document.querySelector(
            `input[name='loan-borrower'][value='${draft.borrower}']`
          );
          if (borrower) borrower.checked = true;
        } else {
          const plan = seedCoupleFundingPlan(projection);
          byId("couple-primary-name").value = ownerNames().primary;
          byId("couple-partner-name").value = ownerNames().partner;
          const borrower = document.querySelector(
            `input[name='loan-borrower'][value='${plan.borrower}']`
          );
          if (borrower) borrower.checked = true;
          OWNER_FUNDING_FIELDS.forEach(field => {
            const id = {
              primaryCash: "couple-primary-cash",
              primaryCpf: "couple-primary-cpf",
              partnerCash: "couple-partner-cash",
              partnerCpf: "couple-partner-cpf",
            }[field];
            byId(id).value = moneyInput(plan[field]);
          });
        }
        showCoupleError("");
        updateCoupleDialogSummary();
        if (typeof dialog.showModal === "function") dialog.showModal();
        else dialog.setAttribute("open", "");
        if (coupleDialogDraftActive && coupleDialogDraft) {
          coupleDialogDraft = { ...coupleDialogDraft, open: true };
          scheduleSave();
        }
        view.setTimeout(() => byId("couple-primary-name").focus(), 0);
      } catch (error) {
        if (confirmEnable) enabledInput.checked = false;
        render();
        showError(`Couple setup needs valid property inputs first: ${error.message}`);
      }
    }

    function closeCoupleFundingDialog({ cancelled = false } = {}) {
      const dialog = byId("couple-funding-dialog");
      if (typeof dialog.close === "function" && dialog.open) dialog.close();
      else dialog.removeAttribute("open");
      if (cancelled && coupleDialogDraftActive && coupleDialogDraft) {
        coupleDialogDraft = { ...coupleDialogDraft, open: false };
        scheduleSave();
      }
      if (cancelled && dialogRequiresEnableConfirmation) {
        enabledInput.checked = false;
        render();
        scheduleSave();
      }
      dialogRequiresEnableConfirmation = false;
    }

    function applyCoupleFundingDialog() {
      try {
        const projection = collectProjection();
        const primaryName = byId("couple-primary-name").value.trim();
        const partnerName = byId("couple-partner-name").value.trim();
        if (!primaryName || !partnerName) throw new RangeError("Enter both owner names");
        if (primaryName.length > 100 || partnerName.length > 100) {
          throw new RangeError("Owner names must be 100 characters or fewer");
        }
        const plan = readCoupleFundingPlan();
        renderCoupleReconciliation(projection, plan);
        const shouldRebuild = !coupleSetupComplete || !coupleFundingPlan
          || OWNER_FUNDING_FIELDS.some(field => (
            toCents(coupleFundingPlan[field], field) !== toCents(plan[field], field)
          ));
        coupleFundingPlan = plan;
        coupleSetupComplete = true;
        coupleDialogDraft = null;
        coupleDialogDraftActive = false;
        byId("primary-owner-name").value = primaryName;
        byId("partner-owner-name").value = partnerName;
        const plannedTotal = OWNER_FUNDING_FIELDS.reduce(
          (total, field) => total + plan[field],
          0
        );
        const partnerTotal = plan.partnerCash + plan.partnerCpf;
        byId("default-partner-payment-share").value = plannedTotal > EPSILON
          ? oneDecimal.format(partnerTotal / plannedTotal * 100)
          : "50";
        if (shouldRebuild) {
          // Rebuild only the route being viewed. The other route remains
          // available; its signature will regenerate a clean ledger or flag a
          // manually edited ledger as stale when the user next opens it.
          ledgers.delete(projection.route);
          currentLedger(projection, { regenerate: true });
        } else {
          currentLedger(projection);
        }
        closeCoupleFundingDialog();
        render();
        updateCouplePlanStatus(projection);
        scheduleSave();
      } catch (error) {
        showCoupleError(`Cannot apply this setup: ${error.message}`);
      }
    }

    function showError(message) {
      const box = byId("funding-ledger-errors");
      box.textContent = message || "";
      box.hidden = !message;
    }

    function setSignedClass(element, value) {
      element.classList.toggle("positive", value > 0.01);
      element.classList.toggle("negative", value < -0.01);
    }

    function reconciliationText(target, actual) {
      const difference = actual - target;
      if (Math.abs(difference) <= 0.01) return `${money(target)} · reconciled`;
      return `${money(target)} target · ${money(actual)} ledger · ${difference > 0 ? "+" : "−"}${money(Math.abs(difference))}`;
    }

    function inputCell(row, field, label, type) {
      const cell = document.createElement("td");
      let input;
      if (type === "select") {
        input = document.createElement("select");
        [
          ["consideration", "Property payment"],
          ["cost", "Acquisition cost"],
          ["note", "Timeline note"],
        ].forEach(([value, text]) => {
          const option = document.createElement("option");
          option.value = value;
          option.textContent = text;
          option.selected = row[field] === value;
          input.append(option);
        });
      } else {
        input = document.createElement("input");
        input.type = type || "text";
        input.value = field === "paymentAmount" || ALLOCATION_FIELDS.includes(field)
          ? moneyInput(row[field])
          : row[field];
        if (field === "paymentAmount" || ALLOCATION_FIELDS.includes(field)) {
          input.inputMode = "decimal";
          input.dataset.currency = "true";
        }
      }
      input.className = `ledger-input ledger-${field}`;
      input.dataset.rowKey = row.key;
      input.dataset.field = field;
      input.setAttribute("aria-label", `${label} for ${row.action || "ledger row"}`);
      cell.append(input);
      return cell;
    }

    function renderRows(validation, projection) {
      const rows = validation.rows.map(row => {
        const tr = document.createElement("tr");
        if (!row.balanced) tr.className = "ledger-row-warning";
        tr.append(
          inputCell(row, "date", "Date", "date"),
          inputCell(row, "action", "Action", "text"),
          inputCell(row, "category", "Category", "select"),
          inputCell(row, "paymentAmount", "Payment amount", "text")
        );
        const percent = document.createElement("td");
        percent.textContent = row.category === "consideration" && projection.purchasePrice > 0
          ? `${oneDecimal.format(row.paymentAmount / projection.purchasePrice * 100)}%`
          : "—";
        tr.append(percent);
        [
          ["primaryCash", "Primary owner cash"],
          ["primaryCpf", "Primary owner CPF"],
          ["loan", byId("ledger-loan-heading").textContent],
          ["partnerCash", "Partner cash"],
          ["partnerCpf", "Partner CPF"],
        ].forEach(([field, label]) => tr.append(inputCell(row, field, label, "text")));
        const allocatedCell = document.createElement("td");
        allocatedCell.textContent = money(row.allocated);
        const differenceCell = document.createElement("td");
        differenceCell.textContent = Math.abs(row.difference) <= 0.01
          ? "S$0"
          : `${row.difference > 0 ? "+" : "−"}${money(Math.abs(row.difference))}`;
        setSignedClass(differenceCell, -Math.abs(row.difference));
        const status = document.createElement("td");
        status.className = row.balanced ? "ledger-status-ok" : "ledger-status-bad";
        status.textContent = row.balanced
          ? (row.category === "note" ? "Timeline only" : "Balanced")
          : `${row.issue}${Math.abs(row.difference) > 0.01
            ? ` · ${row.difference > 0 ? "short " : "over "}${money(Math.abs(row.difference))}`
            : ""}`;
        const remove = document.createElement("td");
        const button = document.createElement("button");
        button.className = "ledger-remove";
        button.type = "button";
        button.dataset.removeRow = row.key;
        button.setAttribute("aria-label", `Remove ${row.action || "ledger row"}`);
        button.textContent = "×";
        remove.append(button);
        tr.append(allocatedCell, differenceCell, status, remove);
        return tr;
      });
      byId("funding-ledger-body").replaceChildren(...rows);
    }

    function renderSummary(validation, projection, state) {
      const totals = validation.totals;
      const targets = validation.targets;
      const names = ownerNames();
      const ownership = splitOutcome(
        projection,
        normalizeShare(number("partner-ownership-share"), "Partner legal ownership")
      );
      const summaryItems = [
        ["ledger-purchase-reconciliation", targets.purchasePrice, totals.considerationPayments],
        ["ledger-loan-reconciliation", targets.loanAmount, totals.considerationLoan],
        ["ledger-equity-reconciliation", targets.ownerFunding, totals.considerationOwnerFunding],
        ["ledger-cost-reconciliation", targets.acquisitionCosts, totals.costPayments],
      ];
      summaryItems.forEach(([id, target, actual]) => {
        const output = byId(id);
        output.textContent = reconciliationText(target, actual);
        output.classList.toggle("negative", Math.abs(target - actual) > 0.01);
        output.classList.toggle("positive", Math.abs(target - actual) <= 0.01);
      });
      byId("ledger-primary-cash-total").textContent = money(totals.primaryCash);
      byId("ledger-primary-cpf-total").textContent = money(totals.primaryCpf);
      byId("ledger-partner-cash-total").textContent = money(totals.partnerCash);
      byId("ledger-partner-cpf-total").textContent = money(totals.partnerCpf);
      byId("ledger-loan-total").textContent = money(totals.loan);
      byId("ledger-primary-cash-heading").textContent = `${names.primary} cash`;
      byId("ledger-primary-cpf-heading").textContent = `${names.primary} CPF`;
      byId("ledger-partner-cash-heading").textContent = `${names.partner} cash`;
      byId("ledger-partner-cpf-heading").textContent = `${names.partner} CPF`;
      byId("ledger-owner-outcome").textContent = `${names.primary} ${oneDecimal.format(ownership.primaryShare)}% · ${money(Math.abs(ownership.primaryCashReleased))}`;
      byId("ledger-partner-outcome").textContent = `${names.partner} ${oneDecimal.format(ownership.partnerShare)}% · ${money(Math.abs(ownership.partnerCashReleased))}`;
      setSignedClass(byId("ledger-owner-outcome"), projection.base.cashReleased);
      setSignedClass(byId("ledger-partner-outcome"), projection.base.cashReleased);
      byId("ledger-overall-status").textContent = validation.balanced
        ? "All rows and totals reconcile"
        : "Ledger needs reconciliation";
      byId("ledger-overall-status").className = validation.balanced
        ? "ledger-badge ledger-badge-ok"
        : "ledger-badge ledger-badge-warning";
      byId("ledger-stale").hidden = !state.stale;
      byId("ledger-route-copy").textContent = projection.route === "buc"
        ? "BUC funding ledger · purchase payments, acquisition costs and timeline-only actions"
        : "Completed-property funding ledger · one completion payment plus acquisition costs and timeline actions";
    }

    function renderFooter(validation) {
      const totals = validation.totals;
      byId("ledger-payment-total").textContent = money(
        totals.considerationPayments + totals.costPayments
      );
      byId("ledger-primary-cash-footer").textContent = money(totals.primaryCash);
      byId("ledger-primary-cpf-footer").textContent = money(totals.primaryCpf);
      byId("ledger-loan-footer").textContent = money(totals.loan);
      byId("ledger-partner-cash-footer").textContent = money(totals.partnerCash);
      byId("ledger-partner-cpf-footer").textContent = money(totals.partnerCpf);
      const allocated = totals.primaryCash + totals.primaryCpf + totals.loan
        + totals.partnerCash + totals.partnerCpf;
      const payments = totals.considerationPayments + totals.costPayments;
      byId("ledger-allocated-footer").textContent = money(allocated);
      byId("ledger-difference-footer").textContent = Math.abs(payments - allocated) <= 0.01
        ? "S$0"
        : `${payments - allocated > 0 ? "+" : "−"}${money(Math.abs(payments - allocated))}`;
    }

    function updateOwnershipPreview() {
      try {
        const partnerShare = normalizeShare(number("partner-ownership-share"));
        byId("primary-ownership-preview").textContent = `${oneDecimal.format(100 - partnerShare)}%`;
      } catch {
        byId("primary-ownership-preview").textContent = "—";
      }
      byId("regenerate-funding-ledger").textContent = "Rebuild ledger from couple funding setup";
      byId("regenerate-funding-ledger").disabled = !coupleSetupComplete;
    }

    function render({ regenerate = false } = {}) {
      const enabled = enabledInput.checked;
      byId("partner-settings").hidden = !enabled;
      byId("funding-ledger-card").hidden = !enabled || !coupleSetupComplete;
      enabledInput.setAttribute("aria-expanded", String(enabled));
      updateOwnershipPreview();
      updateCouplePlanStatus();
      if (!enabled) {
        showError("");
        return;
      }
      if (!coupleSetupComplete || !coupleFundingPlan) {
        showError("");
        return;
      }
      try {
        const projection = collectProjection();
        const state = currentLedger(projection, { regenerate });
        const validation = validateFundingLedger(state.rows, projection);
        showError("");
        renderSummary(validation, projection, state);
        renderRows(validation, projection);
        renderFooter(validation);
      } catch (error) {
        showError(`Funding ledger unavailable until the main plan is valid: ${error.message}`);
      }
    }

    function scheduleRender() {
      view.clearTimeout(refreshTimer);
      refreshTimer = view.setTimeout(() => render(), 130);
    }

    const restoredDraft = restoreDraft();
    if (restoredDraft) {
      form.querySelector("input[name='property-route']:checked").dispatchEvent(
        new view.Event("change", { bubbles: true })
      );
    }

    enabledInput.addEventListener("change", () => {
      render();
      if (enabledInput.checked) openCoupleFundingDialog({ confirmEnable: true });
      scheduleSave();
    });
    byId("partner-ownership-share").addEventListener("input", () => {
      updateOwnershipPreview();
      scheduleRender();
      scheduleSave();
    });
    byId("default-partner-payment-share").addEventListener("input", () => {
      updateOwnershipPreview();
      scheduleSave();
    });
    ["primary-owner-name", "partner-owner-name"].forEach(id => {
      byId(id).addEventListener("input", () => {
        scheduleRender();
        scheduleSave();
      });
    });
    byId("regenerate-funding-ledger").addEventListener("click", () => {
      render({ regenerate: true });
      scheduleSave();
    });
    byId("edit-couple-funding").addEventListener("click", () => {
      openCoupleFundingDialog({ confirmEnable: false });
    });
    byId("couple-funding-form").addEventListener("submit", event => {
      event.preventDefault();
      applyCoupleFundingDialog();
    });
    ["couple-dialog-close", "couple-dialog-cancel"].forEach(id => {
      byId(id).addEventListener("click", () => {
        closeCoupleFundingDialog({ cancelled: true });
      });
    });
    byId("couple-funding-dialog").addEventListener("cancel", event => {
      event.preventDefault();
      closeCoupleFundingDialog({ cancelled: true });
    });
    [
      "couple-primary-cash", "couple-primary-cpf",
      "couple-partner-cash", "couple-partner-cpf",
    ].forEach(id => {
      byId(id).addEventListener("input", () => {
        coupleDialogDraftActive = true;
        coupleDialogDraft = snapshotCoupleDialogDraft();
        updateCoupleDialogSummary();
        scheduleSave();
      });
    });
    ["couple-primary-name", "couple-partner-name"].forEach(id => {
      byId(id).addEventListener("input", () => {
        coupleDialogDraftActive = true;
        coupleDialogDraft = snapshotCoupleDialogDraft();
        scheduleSave();
      });
    });
    document.querySelectorAll("input[name='loan-borrower']").forEach(input => {
      input.addEventListener("change", () => {
        coupleDialogDraftActive = true;
        coupleDialogDraft = snapshotCoupleDialogDraft();
        updateCoupleDialogSummary();
        scheduleSave();
      });
    });
    byId("add-funding-row").addEventListener("click", () => {
      try {
        const projection = collectProjection();
        const state = currentLedger(projection);
        customCounter += 1;
        state.rows.push(makeRow({
          key: `custom-${customCounter}`,
          sequence: 10000 + customCounter,
          date: projection.acquisitionDate,
          action: "New payment or timeline action",
          category: "note",
        }));
        state.dirty = true;
        render();
        scheduleSave();
      } catch (error) {
        showError(`Cannot add a row: ${error.message}`);
      }
    });
    byId("funding-ledger-body").addEventListener("change", event => {
      const input = event.target.closest("[data-row-key][data-field]");
      if (!input) return;
      try {
        const projection = collectProjection();
        const state = currentLedger(projection);
        const row = state.rows.find(item => item.key === input.dataset.rowKey);
        if (!row) return;
        const field = input.dataset.field;
        if (field === "paymentAmount" || ALLOCATION_FIELDS.includes(field)) {
          row[field] = fromCents(toCents(planner.parseCurrency(input.value), field));
        } else {
          row[field] = input.value;
        }
        state.dirty = true;
        state.stale = state.signature !== projectionSignature(projection);
        render();
        scheduleSave();
      } catch (error) {
        input.setAttribute("aria-invalid", "true");
        showError(`Cannot update that row: ${error.message}`);
      }
    });
    byId("funding-ledger-body").addEventListener("click", event => {
      const button = event.target.closest("[data-remove-row]");
      if (!button) return;
      try {
        const projection = collectProjection();
        const state = currentLedger(projection);
        state.rows = state.rows.filter(row => row.key !== button.dataset.removeRow);
        state.dirty = true;
        render();
        scheduleSave();
      } catch (error) {
        showError(`Cannot remove that row: ${error.message}`);
      }
    });
    form.addEventListener("input", event => {
      scheduleSave();
      if (event.target.closest("#partner-settings")) return;
      scheduleRender();
    });
    form.addEventListener("change", event => {
      scheduleSave();
      if (event.target === enabledInput) return;
      scheduleRender();
    });
    form.addEventListener("reset", () => {
      view.clearTimeout(refreshTimer);
      refreshTimer = null;
      clearSavedDraft();
      ledgers.clear();
      customCounter = 0;
      coupleSetupComplete = false;
      coupleFundingPlan = null;
      coupleDialogDraft = null;
      coupleDialogDraftActive = false;
      dialogRequiresEnableConfirmation = false;
      const dialog = byId("couple-funding-dialog");
      if (dialog.open && typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
      ["property-loan-details", "partner-settings", "advanced-cost-details"].forEach(id => {
        byId(id).open = false;
      });
      // Hidden inputs use the browser's default-value mode, so assigning to
      // `.value` while applying a couple setup also changes what a native
      // form reset considers their default. Restore these explicitly before
      // the browser completes its native reset action.
      byId("primary-owner-name").value = "Owner 1";
      byId("partner-owner-name").value = "Partner";
      byId("default-partner-payment-share").value = "50";
      byId("couple-primary-name").value = "Owner 1";
      byId("couple-partner-name").value = "Partner";
      byId("loan-borrower-joint").checked = true;
      view.setTimeout(() => render(), 0);
    });
    view.addEventListener("pagehide", () => {
      if (pendingDraftSave) saveDraft();
    });
    render();
    if (enabledInput.checked && (
      !coupleSetupComplete || (coupleDialogDraftActive && coupleDialogDraft?.open)
    )) {
      openCoupleFundingDialog({ confirmEnable: !coupleSetupComplete });
    }
  }

  return {
    ALLOCATION_FIELDS,
    FUNDING_PLAN_SOURCE_ORDER,
    STORAGE_KEY,
    allocationTotal,
    applyFundingPlan,
    buildStandardFundingLedger,
    init,
    makeRow,
    normalizeShare,
    ownerFundingAllocation,
    splitOutcome,
    toCents,
    fromCents,
    validateFundingPlan,
    validateFundingLedger,
  };
});
