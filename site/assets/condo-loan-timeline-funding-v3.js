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
  const STORAGE_KEY = "housing-estate-framework.condo-loan-timeline-planner-v3.draft.v2";
  const LEGACY_STORAGE_KEY = "housing-estate-framework.condo-loan-timeline-planner-v3.draft.v1";
  const STORAGE_VERSION = 2;
  const VERSION_DATABASE = "housing-estate-framework.condo-loan-timeline-planner-v3";
  const VERSION_DATABASE_VERSION = 1;
  const VERSION_STORE = "planVersions";
  const VERSION_RECORD_SCHEMA = 1;
  const EXPORT_FORMAT = "housing-estate-framework.condo-loan-timeline";
  const EXPORT_FORMAT_VERSION = 1;
  const CALCULATOR_VERSION = "3.2.0";
  const MAX_DRAFT_CHARACTERS = 250000;
  const MAX_IMPORT_BYTES = 1000000;
  const CPF_AUTO_CONTEXTS = ["buc:single", "buc:couple", "resale:single", "resale:couple"];
  const FORM_VALUE_IDS = [
    "project-name", "area-sqft", "acquisition-date", "purchase-price", "loan-amount",
    "loan-rate", "loan-years", "buc-top-date", "resale-completion-date",
    "primary-owner-name", "partner-owner-name", "partner-ownership-share",
    "default-partner-payment-share", "annual-growth", "sale-date",
    "selling-cost-percent", "purchase-market-value", "absd-paid", "purchase-legal",
    "purchase-other", "sale-market-value", "sale-legal", "sale-other", "holding-costs",
    "net-rent", "cpf-primary-acquisition", "cpf-primary-monthly",
    "cpf-partner-monthly", "cpf-oa-rate", "cpf-refund-exact",
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

  function validateVersionName(value) {
    const name = String(value == null ? "" : value).trim();
    if (!name || name.length > 80 || /[\u0000-\u001f\u007f]/.test(name)) {
      throw new RangeError("Version name must be 1 to 80 characters without control characters");
    }
    return name;
  }

  function parseDecisionLabHandoff(search) {
    const params = new URLSearchParams(String(search || ""));
    if (params.get("from") !== "project-exit") return null;

    const project = String(params.get("project") || "").trim();
    if (!project || project.length > 160 || /[\u0000-\u001f\u007f]/.test(project)) {
      throw new RangeError("The comparison project name is invalid");
    }
    const numeric = (key, minimum, maximum) => {
      const raw = params.get(key);
      const value = raw == null || raw.trim() === "" ? NaN : Number(raw);
      if (!Number.isFinite(value) || value < minimum || value > maximum) {
        throw new RangeError(`The comparison ${key} value is invalid`);
      }
      return value;
    };
    const isoDate = key => {
      const value = String(params.get(key) || "");
      if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
        throw new RangeError(`The comparison ${key} date is invalid`);
      }
      const parsed = new Date(`${value}T00:00:00Z`);
      if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) {
        throw new RangeError(`The comparison ${key} date is invalid`);
      }
      return value;
    };

    const purchaseDate = isoDate("purchaseDate");
    const saleDate = isoDate("saleDate");
    const datePrecision = String(params.get("datePrecision") || "month");
    if (datePrecision !== "day" && datePrecision !== "month") {
      throw new RangeError("The comparison datePrecision value is invalid");
    }
    if (saleDate <= purchaseDate) {
      throw new RangeError("The comparison sale date must be after the purchase date");
    }
    return {
      project,
      purchasePrice: numeric("purchasePrice", 1, 100_000_000),
      purchaseDate,
      saleDate,
      datePrecision,
      annualGrowth: numeric("annualGrowth", -99, 30),
      sellingRate: numeric("sellingRate", 0, 20),
      saleCosts: numeric("saleCosts", 0, 10_000_000),
      areaSqft: numeric("areaSqft", 1, 100_000),
    };
  }

  function resolveCpfRefundAmount(options) {
    if (!options || typeof options !== "object" || Array.isArray(options)) {
      throw new TypeError("CPF refund resolution options are required");
    }
    const exact = options.exactRefund == null
      ? null
      : fromCents(toCents(options.exactRefund, "exactRefund"));
    const estimate = roundMoney(nonNegative(
      options.estimatedRefund || 0,
      "estimatedRefund"
    ));
    const lastReliable = options.lastReliableAutoRefund == null
      ? null
      : fromCents(toCents(options.lastReliableAutoRefund, "lastReliableAutoRefund"));
    if (exact != null) {
      return {
        mode: "exact",
        activeRefund: exact,
        lastReliableAutoRefund: lastReliable,
        automaticReliable: Boolean(options.automaticReliable),
      };
    }
    if (options.automaticReliable) {
      return {
        mode: "auto",
        activeRefund: estimate,
        lastReliableAutoRefund: estimate,
        automaticReliable: true,
      };
    }
    return {
      mode: "auto",
      activeRefund: lastReliable == null ? 0 : lastReliable,
      lastReliableAutoRefund: lastReliable,
      automaticReliable: false,
    };
  }

  function createDraftExport(draft, name, exportedAt) {
    if (!draft || typeof draft !== "object" || Array.isArray(draft)) {
      throw new TypeError("A valid draft is required for export");
    }
    const timestamp = exportedAt == null ? new Date().toISOString() : String(exportedAt);
    if (!Number.isFinite(Date.parse(timestamp))) {
      throw new RangeError("Export timestamp is invalid");
    }
    return {
      format: EXPORT_FORMAT,
      formatVersion: EXPORT_FORMAT_VERSION,
      exportedAt: timestamp,
      calculatorVersion: CALCULATOR_VERSION,
      kind: "draft",
      name: validateVersionName(name),
      draft,
    };
  }

  function parseDraftExport(raw) {
    if (typeof raw !== "string" || !raw || raw.length > MAX_IMPORT_BYTES) {
      throw new RangeError("Import file is empty or too large");
    }
    const envelope = JSON.parse(raw);
    if (!envelope || typeof envelope !== "object" || Array.isArray(envelope)) {
      throw new TypeError("Import file must contain one planner draft object");
    }
    const allowed = new Set([
      "format", "formatVersion", "exportedAt", "calculatorVersion", "kind", "name", "draft",
    ]);
    if (Object.keys(envelope).some(key => !allowed.has(key))) {
      throw new RangeError("Import file contains unsupported fields");
    }
    if (envelope.format !== EXPORT_FORMAT || envelope.kind !== "draft") {
      throw new RangeError("This file is not a condo timeline planner draft");
    }
    if (envelope.formatVersion !== EXPORT_FORMAT_VERSION) {
      throw new RangeError("This planner cannot import that draft format version");
    }
    if (!Number.isFinite(Date.parse(String(envelope.exportedAt || "")))) {
      throw new RangeError("Import timestamp is invalid");
    }
    if (typeof envelope.calculatorVersion !== "string"
        || envelope.calculatorVersion.length > 40) {
      throw new RangeError("Import calculator version is invalid");
    }
    validateVersionName(envelope.name);
    if (!envelope.draft || typeof envelope.draft !== "object" || Array.isArray(envelope.draft)) {
      throw new TypeError("Import file does not contain a valid draft");
    }
    return envelope;
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
    const preCpfValueTotal = roundMoney(
      roundMoney(projection.base.cashReleased)
      + roundMoney(projection.base.cpfRefundAvailable || 0)
    );
    const preCpfValue = splitSignedByLegalShare(
      preCpfValueTotal,
      partnerShare,
      true,
      "preCpfSaleValue"
    );
    return {
      primaryShare,
      partnerShare,
      primaryCashReleased,
      partnerCashReleased,
      primaryEconomicProfit,
      partnerEconomicProfit,
      primaryPreCpfValue: preCpfValue.primary,
      partnerPreCpfValue: preCpfValue.partner,
    };
  }

  function signedMoneyCents(value, name) {
    const number = finiteNumber(value, name || "amount");
    const cents = Math.round(number * MONEY_SCALE);
    if (!Number.isSafeInteger(cents)) {
      throw new RangeError(`${name || "amount"} is too large`);
    }
    return cents;
  }

  function splitSignedByLegalShare(value, partnerSharePct, partnerEnabled, name) {
    const totalCents = signedMoneyCents(value, name);
    const partnerShare = partnerEnabled
      ? normalizeShare(partnerSharePct, "partnerOwnershipPct")
      : 0;
    const partnerCents = Math.round(totalCents * partnerShare / 100);
    return {
      primary: fromCents(totalCents - partnerCents),
      partner: fromCents(partnerCents),
    };
  }

  function splitNonNegativeByWeights(value, primaryWeight, partnerWeight) {
    const totalCents = toCents(roundMoney(value), "weighted amount");
    const primary = nonNegative(primaryWeight, "primary CPF weight");
    const partner = nonNegative(partnerWeight, "partner CPF weight");
    const totalWeight = primary + partner;
    if (totalCents > 0 && totalWeight <= EPSILON) return null;
    if (totalCents === 0) return { primary: 0, partner: 0 };
    const primaryCents = Math.round(totalCents * primary / totalWeight);
    return {
      primary: fromCents(primaryCents),
      partner: fromCents(totalCents - primaryCents),
    };
  }

  function buildOwnerSaleOutcome(options) {
    if (!options || typeof options !== "object") {
      throw new TypeError("Owner sale outcome options are required");
    }
    const projection = options.projection;
    if (!projection || !projection.base || !projection.loanAtSale) {
      throw new TypeError("A valid projection is required for the owner sale outcome");
    }
    const partnerEnabled = Boolean(options.partnerEnabled);
    const partnerShare = partnerEnabled
      ? normalizeShare(options.partnerOwnershipPct, "partnerOwnershipPct")
      : 0;
    const primaryShare = 100 - partnerShare;
    const cpfEstimate = options.cpfEstimate;
    const cpfWeightsReliable = options.cpfWeightsReliable !== false;
    const activeCpfRequired = roundMoney(nonNegative(projection.cpfRefund, "cpfRefund"));
    const activeCpfAvailable = roundMoney(nonNegative(
      projection.base.cpfRefundAvailable,
      "cpfRefundAvailable"
    ));
    const activeCpfShortfall = roundMoney(activeCpfRequired - activeCpfAvailable);

    let primaryCpfWeight = 1;
    let partnerCpfWeight = 0;
    let cpfAllocationKnown = !Boolean(options.suppressCpfAllocation);
    let cpfAllocationBasis = partnerEnabled ? "none-required" : "single-owner";
    if (!cpfAllocationKnown) {
      cpfAllocationBasis = "unavailable";
    } else if (partnerEnabled && activeCpfRequired > EPSILON) {
      primaryCpfWeight = cpfEstimate && cpfEstimate.primary
        ? nonNegative(cpfEstimate.primary.refundRequired, "primary CPF estimate")
        : 0;
      partnerCpfWeight = cpfEstimate && cpfEstimate.partner
        ? nonNegative(cpfEstimate.partner.refundRequired, "partner CPF estimate")
        : 0;
      cpfAllocationKnown = cpfWeightsReliable
        && primaryCpfWeight + partnerCpfWeight > EPSILON;
      cpfAllocationBasis = cpfAllocationKnown ? "estimated-p-and-i-ratio" : "unavailable";
    }

    const cpfRequired = cpfAllocationKnown
      ? splitNonNegativeByWeights(activeCpfRequired, primaryCpfWeight, partnerCpfWeight)
      : null;
    const cpfAvailable = cpfAllocationKnown
      ? splitNonNegativeByWeights(activeCpfAvailable, primaryCpfWeight, partnerCpfWeight)
      : null;
    const cpfShortfall = cpfRequired && cpfAvailable
      ? {
        primary: roundMoney(cpfRequired.primary - cpfAvailable.primary),
        partner: roundMoney(cpfRequired.partner - cpfAvailable.partner),
      }
      : null;
    // Use the two already-displayed household amounts as the cent-canonical
    // source. This keeps the owner allocation exactly reconcilable to the
    // household cash + CPF figures even when the projection has sub-cent
    // internal values.
    const householdCash = roundMoney(projection.base.cashReleased);
    const combinedValueTotal = roundMoney(householdCash + activeCpfAvailable);
    const preCpfValue = splitSignedByLegalShare(
      combinedValueTotal,
      partnerShare,
      partnerEnabled,
      "preCpfSaleValue"
    );
    const bankInterest = splitSignedByLegalShare(
      projection.loanAtSale.totalInterestToRedemption,
      partnerShare,
      partnerEnabled,
      "bankInterest"
    );
    const genuineCostsTotal = projection.acquisitionCosts
      + projection.base.saleCosts
      + projection.base.ssd
      + projection.loanAtSale.totalInterestToRedemption
      + projection.holdingCosts;
    const genuineCosts = splitSignedByLegalShare(
      genuineCostsTotal,
      partnerShare,
      partnerEnabled,
      "genuineCosts"
    );
    const economicProfit = splitSignedByLegalShare(
      projection.base.economicProfit,
      partnerShare,
      partnerEnabled,
      "economicProfit"
    );

    function ownerOutcome(owner, share) {
      const combinedValue = preCpfValue[owner];
      const cpfValue = cpfAvailable ? cpfAvailable[owner] : null;
      const cashValue = cpfValue == null
        ? null
        : roundMoney(combinedValue - cpfValue);
      return {
        share,
        cashReleased: cashValue == null ? null : Math.max(0, cashValue),
        cashTopUp: cashValue == null ? null : Math.max(0, -cashValue),
        equalisationGap: cashValue == null ? null : Math.max(0, -cashValue),
        signedCash: cashValue,
        cpfRequired: cpfRequired ? cpfRequired[owner] : null,
        cpfAvailable: cpfValue,
        cpfShortfall: cpfShortfall ? cpfShortfall[owner] : null,
        combinedValue,
        bankInterest: bankInterest[owner],
        genuineCosts: genuineCosts[owner],
        economicProfit: economicProfit[owner],
      };
    }

    return {
      partnerEnabled,
      primary: ownerOutcome("primary", primaryShare),
      partner: ownerOutcome("partner", partnerShare),
      household: {
        cashReleased: householdCash,
        cpfRequired: roundMoney(activeCpfRequired),
        cpfAvailable: roundMoney(activeCpfAvailable),
        cpfShortfall: roundMoney(activeCpfShortfall),
        combinedValue: combinedValueTotal,
        bankInterest: roundMoney(projection.loanAtSale.totalInterestToRedemption),
        genuineCosts: roundMoney(genuineCostsTotal),
        economicProfit: roundMoney(projection.base.economicProfit),
        netRent: roundMoney(projection.netRent),
      },
      cpfAllocationKnown,
      cpfAllocationBasis,
    };
  }

  function buildCpfRefundEstimate(options) {
    if (!options || typeof options !== "object") {
      throw new TypeError("CPF estimate options are required");
    }
    const projection = options.projection;
    if (!projection || !projection.schedule || !projection.saleDate) {
      throw new TypeError("A valid projection is required for the CPF estimate");
    }
    const partnerEnabled = Boolean(options.partnerEnabled);
    const annualRatePct = nonNegative(options.annualRatePct, "annualRatePct");
    const primaryAcquisitionCpf = nonNegative(
      options.primaryAcquisitionCpf || 0,
      "primaryAcquisitionCpf"
    );
    const primaryMonthlyCpf = nonNegative(
      options.primaryMonthlyCpf || 0,
      "primaryMonthlyCpf"
    );
    const partnerMonthlyCpf = partnerEnabled
      ? nonNegative(options.partnerMonthlyCpf || 0, "partnerMonthlyCpf")
      : 0;
    const primaryUsages = [];
    const partnerUsages = [];

    if (partnerEnabled) {
      const ledgerRows = options.ledgerRows || [];
      if (!Array.isArray(ledgerRows)) throw new TypeError("ledgerRows must be an array");
      ledgerRows.forEach((row, index) => {
        const primaryAmount = nonNegative(row.primaryCpf || 0, `ledgerRows[${index}].primaryCpf`);
        const partnerAmount = nonNegative(row.partnerCpf || 0, `ledgerRows[${index}].partnerCpf`);
        if (primaryAmount <= EPSILON && partnerAmount <= EPSILON) return;
        const date = String(row.date || "");
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
          throw new RangeError(`ledgerRows[${index}].date must use YYYY-MM-DD`);
        }
        if (date > projection.saleDate) return;
        if (primaryAmount > EPSILON) primaryUsages.push({ date, amount: primaryAmount });
        if (partnerAmount > EPSILON) partnerUsages.push({ date, amount: partnerAmount });
      });
    } else if (primaryAcquisitionCpf > EPSILON) {
      primaryUsages.push({
        date: projection.acquisitionDate,
        amount: primaryAcquisitionCpf,
      });
    }

    const requestedMonthlyCpf = primaryMonthlyCpf + partnerMonthlyCpf;
    let cappedMonths = 0;
    let mortgageMonths = 0;
    if (requestedMonthlyCpf > EPSILON) {
      projection.schedule.rows
        .filter(row => row.date <= projection.saleDate && row.scheduledPayment > EPSILON)
        .forEach(row => {
          mortgageMonths += 1;
          const applied = Math.min(requestedMonthlyCpf, row.scheduledPayment);
          if (applied + 0.01 < requestedMonthlyCpf) cappedMonths += 1;
          const primaryApplied = applied * primaryMonthlyCpf / requestedMonthlyCpf;
          const partnerApplied = applied - primaryApplied;
          if (primaryApplied > EPSILON) {
            primaryUsages.push({ date: row.date, amount: primaryApplied });
          }
          if (partnerApplied > EPSILON) {
            partnerUsages.push({ date: row.date, amount: partnerApplied });
          }
        });
    }

    const primary = planner.calculateCpfRefundEstimate(
      primaryUsages,
      projection.saleDate,
      annualRatePct
    );
    const partner = planner.calculateCpfRefundEstimate(
      partnerUsages,
      projection.saleDate,
      annualRatePct
    );
    const household = {
      usageCount: primary.usageCount + partner.usageCount,
      principal: primary.principal + partner.principal,
      accruedInterest: primary.accruedInterest + partner.accruedInterest,
      refundRequired: primary.refundRequired + partner.refundRequired,
    };
    return {
      annualRatePct,
      partnerEnabled,
      primary,
      partner,
      household,
      mortgageMonths,
      cappedMonths,
      acquisitionSource: partnerEnabled ? "ledger" : "manual",
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
    let decisionLabDatePrecision = null;
    let coupleFundingPlan = null;
    let coupleSetupComplete = false;
    let coupleDialogDraft = null;
    let coupleDialogDraftActive = false;
    let dialogRequiresEnableConfirmation = false;
    const reliableAutoCpfByContext = new Map();
    let versionDatabasePromise = null;
    const precise = new Intl.NumberFormat("en-SG", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 2,
    });
    const oneDecimal = new Intl.NumberFormat("en-SG", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 1,
    });
    const money = value => `S$${precise.format(roundMoney(Number(value) || 0))}`;
    const signedMoney = value => {
      const amount = roundMoney(Number(value) || 0);
      if (Math.abs(amount) <= 0.001) return "S$0";
      return `${amount > 0 ? "+" : "−"}${money(Math.abs(amount))}`;
    };
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

    function renderDecisionLabDateNotice() {
      byId("decision-lab-handoff-notice").hidden = decisionLabDatePrecision !== "month";
    }

    function localStorageAccess() {
      try {
        return view.localStorage;
      } catch {
        return null;
      }
    }

    function versionStatus(message) {
      const output = byId("version-manager-status");
      if (output) output.textContent = message;
    }

    function openVersionDatabase() {
      if (versionDatabasePromise) return versionDatabasePromise;
      versionDatabasePromise = new Promise((resolve, reject) => {
        if (!view.indexedDB) {
          reject(new Error("IndexedDB is unavailable"));
          return;
        }
        const request = view.indexedDB.open(VERSION_DATABASE, VERSION_DATABASE_VERSION);
        request.onupgradeneeded = () => {
          const database = request.result;
          if (!database.objectStoreNames.contains(VERSION_STORE)) {
            const store = database.createObjectStore(VERSION_STORE, { keyPath: "id" });
            store.createIndex("createdAt", "createdAt", { unique: false });
          }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error || new Error("Cannot open plan versions"));
        request.onblocked = () => reject(new Error("Plan version storage is blocked"));
      }).catch(error => {
        versionDatabasePromise = null;
        throw error;
      });
      return versionDatabasePromise;
    }

    async function versionStoreRequest(mode, method, argument) {
      const database = await openVersionDatabase();
      return new Promise((resolve, reject) => {
        const transaction = database.transaction(VERSION_STORE, mode);
        const store = transaction.objectStore(VERSION_STORE);
        const request = argument === undefined
          ? store[method]()
          : store[method](argument);
        let result;
        request.onsuccess = () => { result = request.result; };
        request.onerror = () => reject(request.error || new Error("Plan version operation failed"));
        transaction.oncomplete = () => resolve(result);
        transaction.onabort = () => reject(transaction.error || new Error("Plan version operation was cancelled"));
        transaction.onerror = () => reject(transaction.error || new Error("Plan version operation failed"));
      });
    }

    function versionId() {
      if (view.crypto && typeof view.crypto.randomUUID === "function") {
        return view.crypto.randomUUID();
      }
      return `plan-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
    }

    function validateVersionRecord(source, { validateDraft = false } = {}) {
      if (!source || typeof source !== "object" || Array.isArray(source)) {
        throw new TypeError("Saved plan version is invalid");
      }
      const allowed = new Set([
        "recordSchemaVersion", "id", "name", "createdAt", "updatedAt", "source",
        "calculatorVersion", "sourceCalculatorVersion", "draft",
      ]);
      if (Object.keys(source).some(key => !allowed.has(key))) {
        throw new RangeError("Saved plan version contains unsupported fields");
      }
      if (source.recordSchemaVersion !== VERSION_RECORD_SCHEMA) {
        throw new RangeError("Saved plan version format is unsupported");
      }
      if (typeof source.id !== "string" || !source.id || source.id.length > 120) {
        throw new RangeError("Saved plan version identifier is invalid");
      }
      const name = validateVersionName(source.name);
      const createdAt = String(source.createdAt || "");
      const updatedAt = String(source.updatedAt || "");
      if (!Number.isFinite(Date.parse(createdAt)) || !Number.isFinite(Date.parse(updatedAt))) {
        throw new RangeError("Saved plan version timestamp is invalid");
      }
      if (!["user", "import", "recovery"].includes(source.source)) {
        throw new RangeError("Saved plan version source is invalid");
      }
      if (typeof source.calculatorVersion !== "string"
          || source.calculatorVersion.length > 40) {
        throw new RangeError("Saved plan calculator version is invalid");
      }
      const sourceCalculatorVersion = source.sourceCalculatorVersion == null
        ? source.calculatorVersion
        : source.sourceCalculatorVersion;
      if (typeof sourceCalculatorVersion !== "string"
          || sourceCalculatorVersion.length > 40) {
        throw new RangeError("Saved plan source calculator version is invalid");
      }
      if (!source.draft || typeof source.draft !== "object" || Array.isArray(source.draft)) {
        throw new TypeError("Saved plan version draft is invalid");
      }
      if (validateDraft) prepareSavedDraft(source.draft);
      return { ...source, name, createdAt, updatedAt, sourceCalculatorVersion };
    }

    async function saveVersionSnapshot(
      name,
      draft,
      source = "user",
      sourceCalculatorVersion = CALCULATOR_VERSION
    ) {
      const checkedName = validateVersionName(name);
      const serialized = JSON.stringify(draft);
      if (serialized.length > MAX_DRAFT_CHARACTERS) {
        throw new RangeError("This draft is too large to save as a version");
      }
      prepareSavedDraft(draft);
      const timestamp = new Date().toISOString();
      const record = {
        recordSchemaVersion: VERSION_RECORD_SCHEMA,
        id: versionId(),
        name: checkedName,
        createdAt: timestamp,
        updatedAt: timestamp,
        source,
        calculatorVersion: CALCULATOR_VERSION,
        sourceCalculatorVersion,
        draft,
      };
      validateVersionRecord(record, { validateDraft: true });
      await versionStoreRequest("readwrite", "add", record);
      return record;
    }

    function versionDateLabel(value) {
      return new Intl.DateTimeFormat("en-SG", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value));
    }

    async function refreshVersionManager(selectedId) {
      const select = byId("saved-version-select");
      const previous = selectedId || select.value;
      try {
        const records = [];
        let invalidCount = 0;
        (await versionStoreRequest("readonly", "getAll")).forEach(record => {
          try {
            records.push(validateVersionRecord(record));
          } catch {
            invalidCount += 1;
          }
        });
        records.sort((first, second) => second.createdAt.localeCompare(first.createdAt));
        select.replaceChildren();
        if (!records.length) {
          const option = document.createElement("option");
          option.value = "";
          option.textContent = "No saved versions yet";
          select.append(option);
        } else {
          records.forEach(record => {
            const option = document.createElement("option");
            option.value = record.id;
            const sourceVersion = record.sourceCalculatorVersion !== CALCULATOR_VERSION
              ? ` · source ${record.sourceCalculatorVersion}`
              : "";
            option.textContent = `${record.source === "recovery" ? "Recovery · " : ""}${record.name} · ${versionDateLabel(record.createdAt)}${sourceVersion}`;
            select.append(option);
          });
          select.value = records.some(record => record.id === previous)
            ? previous
            : records[0].id;
        }
        const hasSelection = Boolean(select.value);
        byId("load-plan-version").disabled = !hasSelection;
        byId("delete-plan-version").disabled = !hasSelection;
        const planCount = records.filter(record => record.source !== "recovery").length;
        const recoveryCount = records.length - planCount;
        versionStatus(records.length
          ? `${planCount} saved plan version${planCount === 1 ? "" : "s"}${recoveryCount ? ` · ${recoveryCount} recovery cop${recoveryCount === 1 ? "y" : "ies"}` : ""} in this browser.${invalidCount ? ` ${invalidCount} unreadable record${invalidCount === 1 ? " was" : "s were"} ignored.` : ""}`
          : `No named versions yet. Your working draft still saves automatically.${invalidCount ? ` ${invalidCount} unreadable record${invalidCount === 1 ? " was" : "s were"} ignored.` : ""}`);
        return records;
      } catch {
        select.replaceChildren();
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "Named versions unavailable";
        select.append(option);
        byId("save-plan-version").disabled = true;
        byId("load-plan-version").disabled = true;
        byId("delete-plan-version").disabled = true;
        versionStatus("Named versions are unavailable in this browser. Export and import still work.");
        return [];
      }
    }

    function cpfEstimateSignature(projection, estimate) {
      return JSON.stringify({
        route: projection.route,
        acquisitionDate: projection.acquisitionDate,
        saleDate: projection.saleDate,
        partnerEnabled: estimate.partnerEnabled,
        annualRatePct: estimate.annualRatePct,
        mortgageMonths: estimate.mortgageMonths,
        cappedMonths: estimate.cappedMonths,
        primary: [
          estimate.primary.usageCount,
          roundMoney(estimate.primary.principal),
          roundMoney(estimate.primary.accruedInterest),
          roundMoney(estimate.primary.refundRequired),
        ],
        partner: [
          estimate.partner.usageCount,
          roundMoney(estimate.partner.principal),
          roundMoney(estimate.partner.accruedInterest),
          roundMoney(estimate.partner.refundRequired),
        ],
      });
    }

    function cpfAutoContext(projection, partnerEnabled) {
      const key = `${projection.route}:${partnerEnabled ? "couple" : "single"}`;
      if (!CPF_AUTO_CONTEXTS.includes(key)) {
        throw new RangeError("CPF automatic-estimate context is invalid");
      }
      return key;
    }

    function encodeCpfRefundState() {
      const exactRefund = currency("cpf-refund-exact", true);
      return {
        mode: exactRefund == null ? "auto" : "exact",
        exactCents: exactRefund == null ? null : toCents(exactRefund, "exact CPF refund"),
        reliableAutoByContext: Object.fromEntries(
          [...reliableAutoCpfByContext.entries()].map(([context, entry]) => [context, {
            cents: entry.cents,
            estimateSignature: entry.estimateSignature,
          }])
        ),
      };
    }

    function decodeCpfRefundState(source, exactRawValue) {
      if (!source || typeof source !== "object" || Array.isArray(source)) {
        throw new TypeError("Saved CPF refund state is invalid");
      }
      const allowed = new Set([
        "mode", "exactCents", "reliableAutoByContext",
      ]);
      if (Object.keys(source).some(key => !allowed.has(key))) {
        throw new RangeError("Saved CPF refund state contains an unknown field");
      }
      if (!["auto", "exact"].includes(source.mode)) {
        throw new RangeError("Saved CPF refund mode is invalid");
      }
      const exactCents = source.exactCents == null ? null : Number(source.exactCents);
      if (exactCents != null && (!Number.isSafeInteger(exactCents) || exactCents < 0)) {
        throw new RangeError("Saved CPF refund amount is invalid");
      }
      if (!source.reliableAutoByContext
          || typeof source.reliableAutoByContext !== "object"
          || Array.isArray(source.reliableAutoByContext)
          || Object.keys(source.reliableAutoByContext).some(
            context => !CPF_AUTO_CONTEXTS.includes(context)
          )) {
        throw new RangeError("Saved automatic CPF contexts are invalid");
      }
      const reliableAutoByContext = new Map();
      Object.entries(source.reliableAutoByContext).forEach(([context, entry]) => {
        if (!entry || typeof entry !== "object" || Array.isArray(entry)
            || Object.keys(entry).some(key => !["cents", "estimateSignature"].includes(key))
            || !Number.isSafeInteger(Number(entry.cents))
            || Number(entry.cents) < 0
            || typeof entry.estimateSignature !== "string"
            || !entry.estimateSignature
            || entry.estimateSignature.length > 5000) {
          throw new RangeError("Saved automatic CPF estimate is invalid");
        }
        reliableAutoByContext.set(context, {
          cents: Number(entry.cents),
          estimateSignature: entry.estimateSignature,
        });
      });
      const exactValue = planner.parseCurrency(exactRawValue, { allowBlank: true });
      if (source.mode === "auto") {
        if (exactValue != null || exactCents != null) {
          throw new RangeError("Automatic CPF mode cannot contain an exact override");
        }
      } else if (exactValue == null || exactCents !== toCents(exactValue, "exact CPF refund")) {
        throw new RangeError("Saved exact CPF refund does not match its form value");
      }
      return {
        mode: source.mode,
        exactCents,
        reliableAutoByContext,
      };
    }

    function normalizeSavedDraft(source) {
      if (!source || typeof source !== "object" || Array.isArray(source)) {
        throw new TypeError("Saved draft is invalid");
      }
      if (source.schemaVersion === STORAGE_VERSION) return source;
      if (source.schemaVersion !== 1) {
        throw new RangeError("Saved draft version is unsupported");
      }
      const allowedLegacy = new Set([
        "schemaVersion", "savedAt", "form", "coupleFunding", "coupleDialogDraft",
        "cpfRefundProvenance", "ledgers",
      ]);
      if (Object.keys(source).some(key => !allowedLegacy.has(key))) {
        throw new RangeError("Legacy draft contains an unknown section");
      }
      if (!source.form || typeof source.form !== "object"
          || !source.form.values || typeof source.form.values !== "object") {
        throw new TypeError("Saved form is missing");
      }
      const values = { ...source.form.values };
      const oldRaw = typeof values["cpf-refund"] === "string" ? values["cpf-refund"] : "0";
      const oldRefund = planner.parseCurrency(oldRaw, { allowBlank: false });
      const provenance = source.cpfRefundProvenance;
      if (provenance != null && (
        !provenance
        || typeof provenance !== "object"
        || Array.isArray(provenance)
        || Object.keys(provenance).some(key => !["source", "estimateSignature"].includes(key))
        || !["manual_exact", "applied_estimate"].includes(provenance.source)
      )) {
        throw new RangeError("Legacy CPF refund provenance is invalid");
      }
      const wasAppliedEstimate = provenance && provenance.source === "applied_estimate";
      const exactOverride = !wasAppliedEstimate && oldRefund > 0 ? oldRaw : "";
      const legacyChecks = source.form.checks || {};
      const legacyRoute = legacyChecks["route-resale"] ? "resale" : "buc";
      const legacyContext = `${legacyRoute}:${legacyChecks["partner-enabled"] ? "couple" : "single"}`;
      const reliableAutoByContext = wasAppliedEstimate ? {
        [legacyContext]: {
          cents: toCents(oldRefund, "legacy automatic CPF refund"),
          estimateSignature: typeof provenance.estimateSignature === "string"
            && provenance.estimateSignature
            ? provenance.estimateSignature
            : "legacy-applied-estimate",
        },
      } : {};
      delete values["cpf-refund"];
      values["cpf-refund-exact"] = exactOverride;
      return {
        schemaVersion: STORAGE_VERSION,
        savedAt: source.savedAt,
        form: { values, checks: source.form.checks || {} },
        coupleFunding: source.coupleFunding,
        coupleDialogDraft: source.coupleDialogDraft,
        cpfRefundState: {
          mode: exactOverride ? "exact" : "auto",
          exactCents: exactOverride ? toCents(oldRefund, "legacy exact CPF refund") : null,
          reliableAutoByContext,
        },
        ledgers: source.ledgers || {},
      };
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
      const allowed = new Set([
        "key", "sequence", "date", "action", "category", "paymentAmountCents",
        "allocationCents",
      ]);
      if (Object.keys(source).some(key => !allowed.has(key))) {
        throw new RangeError("Saved row contains an unknown field");
      }
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
      if (Object.keys(source.allocationCents).some(field => !ALLOCATION_FIELDS.includes(field))) {
        throw new RangeError("Saved row allocations contain an unknown field");
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
      if (Object.keys(source).some(key => !["complete", "borrower", "amountCents"].includes(key))) {
        throw new RangeError("Saved couple funding setup contains an unknown field");
      }
      if (!source.complete) return { complete: false, plan: null };
      if (!source.amountCents || typeof source.amountCents !== "object") {
        throw new TypeError("Saved couple funding amounts are invalid");
      }
      if (Object.keys(source.amountCents).some(field => !OWNER_FUNDING_FIELDS.includes(field))) {
        throw new RangeError("Saved couple funding amounts contain an unknown field");
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
      if (Object.keys(source).some(key => !["borrower", "open", "values"].includes(key))) {
        throw new RangeError("Saved couple setup draft contains an unknown field");
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
        ...(decisionLabDatePrecision ? { decisionLabDatePrecision } : {}),
        form: { values, checks },
        coupleFunding: encodeCoupleFunding(),
        coupleDialogDraft: encodeCoupleDialogDraft(),
        cpfRefundState: encodeCpfRefundState(),
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
        const serialized = JSON.stringify(captureDraft());
        if (serialized.length > MAX_DRAFT_CHARACTERS) {
          throw new RangeError("Draft is too large for automatic saving");
        }
        storage.setItem(STORAGE_KEY, serialized);
        pendingDraftSave = false;
        draftStatus("Saved automatically as the working draft. Reset clears only it; named versions stay.");
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
          storage.removeItem(LEGACY_STORAGE_KEY);
        } catch {
          // Reset still clears in-memory state when browser storage is unavailable.
        }
      }
      draftStatus("Working draft cleared. Named versions were kept; new edits will save automatically.");
    }

    function prepareSavedDraft(source) {
      const saved = normalizeSavedDraft(source);
      const allowedTopLevel = new Set([
        "schemaVersion", "savedAt", "form", "coupleFunding", "coupleDialogDraft",
        "cpfRefundState", "ledgers", "decisionLabDatePrecision",
      ]);
      if (Object.keys(saved).some(key => !allowedTopLevel.has(key))) {
        throw new RangeError("Saved draft contains an unknown section");
      }
      if (!saved.savedAt || !Number.isFinite(Date.parse(String(saved.savedAt)))) {
        throw new RangeError("Saved draft timestamp is invalid");
      }
      const restoredDecisionLabDatePrecision = saved.decisionLabDatePrecision == null
        ? null
        : String(saved.decisionLabDatePrecision);
      if (restoredDecisionLabDatePrecision !== null
          && restoredDecisionLabDatePrecision !== "month") {
        throw new RangeError("Saved decision-lab date precision is invalid");
      }
      if (!saved.form || typeof saved.form !== "object" || Array.isArray(saved.form)) {
        throw new TypeError("Saved form is missing");
      }
      if (Object.keys(saved.form).some(key => !["values", "checks"].includes(key))) {
        throw new RangeError("Saved form contains an unknown section");
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
        if (typeof values[id] !== "string" || values[id].length > 1000) {
          throw new RangeError(`Saved ${id} value is invalid`);
        }
      });
      FORM_CHECK_IDS.forEach(id => {
        if (typeof checks[id] !== "boolean") {
          throw new RangeError(`Saved ${id} state is invalid`);
        }
      });

      const restoredCoupleFunding = decodeCoupleFunding(saved.coupleFunding);
      const restoredCoupleDialogDraft = validateCoupleDialogDraft(
        saved.coupleDialogDraft == null ? null : saved.coupleDialogDraft
      );
      const restoredCpfRefundState = decodeCpfRefundState(
        saved.cpfRefundState,
        values["cpf-refund-exact"]
      );
      const restoredLedgers = new Map();
      const savedLedgers = saved.ledgers || {};
      if (!savedLedgers || typeof savedLedgers !== "object" || Array.isArray(savedLedgers)) {
        throw new TypeError("Saved ledgers are invalid");
      }
      if (Object.keys(savedLedgers).some(route => !["buc", "resale"].includes(route))) {
        throw new RangeError("Saved draft contains an unknown property route");
      }
      Object.entries(savedLedgers).forEach(([route, state]) => {
        if (!state || typeof state !== "object" || !Array.isArray(state.rows)) {
          throw new TypeError("Saved ledger is invalid");
        }
        if (Object.keys(state).some(key => !["signature", "dirty", "rows"].includes(key))) {
          throw new RangeError("Saved ledger contains an unknown field");
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
      return {
        saved,
        values,
        checks,
        restoredCoupleFunding,
        restoredCoupleDialogDraft,
        restoredCpfRefundState,
        restoredLedgers,
        restoredDecisionLabDatePrecision,
      };
    }

    function validateDraftBeforeActivation(source) {
      const prepared = prepareSavedDraft(source);
      const snapshots = {};
      [...FORM_VALUE_IDS, ...FORM_CHECK_IDS].forEach(id => {
        const input = byId(id);
        snapshots[id] = input.type === "checkbox" || input.type === "radio"
          ? input.checked
          : input.value;
      });
      try {
        FORM_VALUE_IDS.forEach(id => { byId(id).value = prepared.values[id]; });
        FORM_CHECK_IDS.forEach(id => { byId(id).checked = prepared.checks[id]; });
        if (byId("route-buc").checked === byId("route-resale").checked) {
          throw new RangeError("Saved property route is invalid");
        }
        validateCurrentDraftInputs();
        return prepared;
      } finally {
        [...FORM_VALUE_IDS, ...FORM_CHECK_IDS].forEach(id => {
          const input = byId(id);
          if (input.type === "checkbox" || input.type === "radio") {
            input.checked = snapshots[id];
          } else {
            input.value = snapshots[id];
          }
        });
      }
    }

    function applySavedDraft(source) {
      const prepared = prepareSavedDraft(source);
      const previousDecisionLabDatePrecision = decisionLabDatePrecision;
      const snapshots = {};
      [...FORM_VALUE_IDS, ...FORM_CHECK_IDS].forEach(id => {
        const input = byId(id);
        snapshots[id] = input.type === "checkbox" || input.type === "radio"
          ? input.checked
          : input.value;
      });
      try {
        FORM_VALUE_IDS.forEach(id => {
          byId(id).value = prepared.values[id];
        });
        FORM_CHECK_IDS.forEach(id => {
          byId(id).checked = prepared.checks[id];
        });
        if (byId("route-buc").checked === byId("route-resale").checked) {
          throw new RangeError("Saved property route is invalid");
        }
        validateCurrentDraftInputs();
        ledgers.clear();
        prepared.restoredLedgers.forEach((state, route) => { ledgers.set(route, state); });
        coupleSetupComplete = prepared.restoredCoupleFunding.complete;
        coupleFundingPlan = prepared.restoredCoupleFunding.plan;
        coupleDialogDraft = prepared.restoredCoupleDialogDraft;
        coupleDialogDraftActive = Boolean(prepared.restoredCoupleDialogDraft);
        reliableAutoCpfByContext.clear();
        prepared.restoredCpfRefundState.reliableAutoByContext.forEach((entry, context) => {
          reliableAutoCpfByContext.set(context, entry);
        });
        const restoredContext = cpfAutoContext(
          { route: routeValue() },
          enabledInput.checked
        );
        const restoredAuto = reliableAutoCpfByContext.get(restoredContext);
        const effectiveCents = prepared.restoredCpfRefundState.mode === "exact"
          ? prepared.restoredCpfRefundState.exactCents
          : restoredAuto?.cents;
        byId("cpf-refund").value = moneyInput(fromCents(effectiveCents || 0));
        decisionLabDatePrecision = prepared.restoredDecisionLabDatePrecision;
        renderDecisionLabDateNotice();
        customCounter = 0;
        ledgers.forEach(state => {
          state.rows.forEach(row => {
            const match = /^custom-(\d+)$/.exec(row.key);
            if (match) customCounter = Math.max(customCounter, Number(match[1]));
          });
        });
        return prepared.saved;
      } catch (error) {
        decisionLabDatePrecision = previousDecisionLabDatePrecision;
        renderDecisionLabDateNotice();
        [...FORM_VALUE_IDS, ...FORM_CHECK_IDS].forEach(id => {
          const input = byId(id);
          if (input.type === "checkbox" || input.type === "radio") input.checked = snapshots[id];
          else input.value = snapshots[id];
        });
        throw error;
      }
    }

    function restoreDraft() {
      const storage = localStorageAccess();
      if (!storage) return false;
      let invalidDraftFound = false;
      for (const key of [STORAGE_KEY, LEGACY_STORAGE_KEY]) {
        try {
          const raw = storage.getItem(key);
          if (!raw) continue;
          if (raw.length > MAX_DRAFT_CHARACTERS) {
            throw new RangeError("Saved draft is too large");
          }
          applySavedDraft(JSON.parse(raw));
          if (key === LEGACY_STORAGE_KEY) {
            try {
              const migrated = JSON.stringify(captureDraft());
              if (migrated.length <= MAX_DRAFT_CHARACTERS) {
                storage.setItem(STORAGE_KEY, migrated);
              }
            } catch {
              // Keep the untouched legacy copy; the in-memory plan is still usable.
            }
            draftStatus("Restored and migrated your earlier browser draft.");
          } else {
            draftStatus("Restored your last saved draft from this browser.");
          }
          return true;
        } catch {
          invalidDraftFound = true;
          if (key === STORAGE_KEY) {
            try {
              storage.removeItem(STORAGE_KEY);
            } catch {
              // A corrupt current draft must not prevent a legacy fallback attempt.
            }
          }
        }
      }
      ledgers.clear();
      coupleSetupComplete = false;
      coupleFundingPlan = null;
      coupleDialogDraft = null;
      coupleDialogDraftActive = false;
      reliableAutoCpfByContext.clear();
      decisionLabDatePrecision = null;
      renderDecisionLabDateNotice();
      byId("cpf-refund").value = "0";
      customCounter = 0;
      if (invalidDraftFound) {
        draftStatus("A saved draft could not be read; defaults were restored and any legacy copy was preserved.");
      }
      return false;
    }

    function applyDecisionLabHandoff(restoredDraft) {
      let handoff;
      try {
        handoff = parseDecisionLabHandoff(view.location.search);
      } catch (error) {
        draftStatus(`Comparison scenario not loaded: ${error.message}.`);
        return false;
      }
      if (!handoff) return false;
      if (restoredDraft && !view.confirm(
        `Load the ${handoff.project} comparison scenario? This replaces selected values in your current working draft; named versions remain unchanged.`
      )) {
        draftStatus("Comparison scenario was not loaded; your working draft is unchanged.");
        return false;
      }

      byId("project-name").value = handoff.project;
      byId("area-sqft").value = String(handoff.areaSqft);
      byId("acquisition-date").value = handoff.purchaseDate;
      byId("purchase-price").value = moneyInput(handoff.purchasePrice);
      byId("purchase-market-value").value = moneyInput(handoff.purchasePrice);
      byId("loan-amount").value = moneyInput(roundMoney(handoff.purchasePrice * 0.75));
      byId("annual-growth").value = String(handoff.annualGrowth);
      byId("sale-date").value = handoff.saleDate;
      byId("selling-cost-percent").value = String(handoff.sellingRate);
      byId("sale-market-value").value = "";
      byId("sale-legal").value = "0";
      byId("sale-other").value = moneyInput(handoff.saleCosts);
      decisionLabDatePrecision = handoff.datePrecision === "month" ? "month" : null;
      renderDecisionLabDateNotice();
      ledgers.clear();
      reliableAutoCpfByContext.clear();
      suppressSaveUntilUserEdit = false;
      draftStatus(
        `Loaded ${handoff.project} from the decision lab. The loan starts at an editable 75% of entry price; review the property route, financing, CPF and holding-cost assumptions before saving a named version.${handoff.datePrecision === "month" ? " Month-only dates were provisionally set to the first day; replace them with exact legal dates before relying on SSD." : ""}`
      );
      byId("project-name").dispatchEvent(new view.Event("input", { bubbles: true }));
      scheduleSave();
      return true;
    }

    function activateDraft(source) {
      const saved = applySavedDraft(source);
      const dialog = byId("couple-funding-dialog");
      if (dialog.open && typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
      dialogRequiresEnableConfirmation = false;
      const route = form.querySelector("input[name='property-route']:checked");
      route.dispatchEvent(new view.Event("change", { bubbles: true }));
      render();
      suppressSaveUntilUserEdit = false;
      const persisted = saveDraft();
      if (enabledInput.checked && (
        !coupleSetupComplete || (coupleDialogDraftActive && coupleDialogDraft?.open)
      )) {
        openCoupleFundingDialog({ confirmEnable: !coupleSetupComplete });
      }
      return { saved, persisted };
    }

    async function saveRecoverySnapshot(label) {
      try {
        const suffix = validateVersionName(label).slice(0, 58);
        const record = await saveVersionSnapshot(
          `Before ${suffix}`.slice(0, 80),
          captureDraft(),
          "recovery"
        );
        try {
          const recoveries = (await versionStoreRequest("readonly", "getAll"))
            .filter(candidate => candidate && candidate.source === "recovery")
            .sort((first, second) => second.createdAt.localeCompare(first.createdAt));
          for (const stale of recoveries.slice(5)) {
            await versionStoreRequest("readwrite", "delete", stale.id);
          }
        } catch {
          // Retention cleanup is best-effort; the newly committed recovery remains valid.
        }
        return record;
      } catch {
        return null;
      }
    }

    function exportFileName(name) {
      const stem = String(name || "condo-plan")
        .normalize("NFKD")
        .replace(/[^a-zA-Z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 60)
        .toLowerCase();
      return `${stem || "condo-plan"}.json`;
    }

    function downloadCurrentDraft() {
      const fallbackName = byId("project-name").value.trim() || "Condo plan";
      const name = validateVersionName(byId("version-name").value || fallbackName);
      const envelope = createDraftExport(captureDraft(), name);
      const serialized = JSON.stringify(envelope, null, 2);
      if (serialized.length > MAX_IMPORT_BYTES) {
        throw new RangeError("This draft is too large to export");
      }
      const blob = new view.Blob([serialized], { type: "application/json" });
      const url = view.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = exportFileName(name);
      link.hidden = true;
      document.body.append(link);
      link.click();
      link.remove();
      view.setTimeout(() => view.URL.revokeObjectURL(url), 0);
      versionStatus(`Exported “${name}”. Keep the JSON file private; it is not encrypted.`);
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

    function renderOwnerOutcomeUnavailable(message) {
      [
        "owner-outcome-primary-cash", "owner-outcome-primary-cpf",
        "owner-outcome-primary-combined", "owner-outcome-primary-bank-interest",
        "owner-outcome-primary-costs", "owner-outcome-primary-profit",
        "owner-outcome-partner-cash", "owner-outcome-partner-cpf",
        "owner-outcome-partner-combined", "owner-outcome-partner-bank-interest",
        "owner-outcome-partner-costs", "owner-outcome-partner-profit",
        "owner-outcome-household-cash", "owner-outcome-household-cpf",
        "owner-outcome-household-combined",
      ].forEach(id => { byId(id).textContent = "—"; });
      byId("owner-outcome-status").textContent = message;
    }

    function renderOwnerSaleOutcome(
      projection,
      cpfEstimate,
      cpfWeightsReliable,
      cpfMode,
      automaticRetained,
      suppressCpfAllocation
    ) {
      const partnerEnabled = enabledInput.checked;
      const names = ownerNames();
      const outcome = buildOwnerSaleOutcome({
        projection,
        cpfEstimate,
        cpfWeightsReliable,
        suppressCpfAllocation,
        partnerEnabled,
        partnerOwnershipPct: partnerEnabled
          ? number("partner-ownership-share")
          : 0,
      });
      const cards = byId("owner-outcome-cards");
      cards.classList.toggle("single", !partnerEnabled);
      byId("owner-outcome-partner-card").hidden = !partnerEnabled;

      function renderOwner(prefix, name, owner) {
        byId(`owner-outcome-${prefix}-name`).textContent = name;
        byId(`owner-outcome-${prefix}-share`).textContent = `${oneDecimal.format(owner.share)}% legal share`;
        const combinedLabel = byId(`owner-outcome-${prefix}-combined-label`);
        const combinedOutput = byId(`owner-outcome-${prefix}-combined`);
        combinedLabel.textContent = owner.combinedValue < -0.001
          ? "Net sale deficit · legal-share split"
          : "Combined value retained · legal-share split";
        combinedOutput.textContent = owner.combinedValue >= 0
          ? money(owner.combinedValue)
          : `${money(Math.abs(owner.combinedValue))} deficit`;
        setSignedClass(combinedOutput, owner.combinedValue);

        const cashLabel = byId(`owner-outcome-${prefix}-cash-label`);
        const cashOutput = byId(`owner-outcome-${prefix}-cash`);
        if (owner.signedCash == null) {
          cashLabel.textContent = "Cash after own CPF routing";
          cashOutput.textContent = "Split unavailable";
          cashOutput.classList.remove("positive", "negative");
        } else if (owner.equalisationGap > 0.001) {
          cashLabel.textContent = "Illustrative owner equalisation gap";
          cashOutput.textContent = money(owner.equalisationGap);
          setSignedClass(cashOutput, -owner.equalisationGap);
        } else {
          cashLabel.textContent = "Cash remaining after own CPF";
          cashOutput.textContent = money(owner.cashReleased);
          setSignedClass(cashOutput, owner.cashReleased);
        }

        const cpfOutput = byId(`owner-outcome-${prefix}-cpf`);
        if (owner.cpfAvailable == null) {
          cpfOutput.textContent = "Split unavailable";
          cpfOutput.classList.remove("positive", "negative");
        } else {
          cpfOutput.textContent = money(owner.cpfAvailable);
          setSignedClass(cpfOutput, owner.cpfAvailable);
        }
        byId(`owner-outcome-${prefix}-bank-interest`).textContent = money(owner.bankInterest);
        byId(`owner-outcome-${prefix}-costs`).textContent = money(owner.genuineCosts);
        const profitOutput = byId(`owner-outcome-${prefix}-profit`);
        const profitLabel = byId(`owner-outcome-${prefix}-profit-label`);
        profitLabel.textContent = owner.economicProfit >= 0
          ? "Illustrative economic profit share"
          : "Illustrative economic loss share";
        profitOutput.textContent = signedMoney(owner.economicProfit);
        setSignedClass(profitOutput, owner.economicProfit);
      }

      renderOwner("primary", names.primary, outcome.primary);
      if (partnerEnabled) renderOwner("partner", names.partner, outcome.partner);
      const householdCash = byId("owner-outcome-household-cash");
      householdCash.textContent = outcome.household.cashReleased >= 0
        ? money(outcome.household.cashReleased)
        : `${money(Math.abs(outcome.household.cashReleased))} top-up`;
      setSignedClass(householdCash, outcome.household.cashReleased);
      byId("owner-outcome-household-cpf").textContent = money(
        outcome.household.cpfAvailable
      );
      const householdCombined = byId("owner-outcome-household-combined");
      householdCombined.textContent = outcome.household.combinedValue >= 0
        ? money(outcome.household.combinedValue)
        : `${money(Math.abs(outcome.household.combinedValue))} deficit`;
      setSignedClass(householdCombined, outcome.household.combinedValue);

      if (automaticRetained) {
        byId("owner-outcome-status").textContent = "The household waterfall retains the last reliable automatic CPF estimate while the couple ledger needs reconciliation. Individual CPF and cash routing will refresh once that ledger is current.";
      } else if (!outcome.cpfAllocationKnown) {
        byId("owner-outcome-status").textContent = `The legal-share value is shown, but the ${money(outcome.household.cpfRequired)} household CPF refund and resulting owner cash cannot be split until the couple ledger is current, reconciled and provides an individual CPF basis.`;
      } else if (partnerEnabled && outcome.household.cpfRequired > EPSILON) {
        byId("owner-outcome-status").textContent = `Combined value is split ${oneDecimal.format(outcome.primary.share)}% / ${oneDecimal.format(outcome.partner.share)}% first. The active ${money(outcome.household.cpfRequired)} ${cpfMode === "exact" ? "exact" : "automatic"} household CPF refund is then apportioned using each owner’s current estimated principal plus accrued-interest ratio and routed from that owner’s share.`;
      } else {
        byId("owner-outcome-status").textContent = `The combined value is allocated by legal share first, then the active ${money(outcome.household.cpfRequired)} ${cpfMode === "exact" ? "exact" : "automatic"} CPF refund is routed from the owner’s share. Household and owner totals reconcile to the current sale waterfall.`;
      }
    }

    function renderCpfUnavailable(message) {
      [
        "cpf-primary-principal", "cpf-primary-interest", "cpf-primary-refund",
        "cpf-primary-available", "cpf-partner-principal", "cpf-partner-interest",
        "cpf-partner-refund", "cpf-partner-available", "cpf-household-principal",
        "cpf-household-interest", "cpf-estimated-refund", "cpf-estimated-available",
        "cpf-estimated-shortfall", "cpf-applied-refund", "cpf-applied-available",
      ].forEach(id => { byId(id).textContent = "—"; });
      byId("use-automatic-cpf").hidden = !byId("cpf-refund-exact").value.trim();
      byId("cpf-refund-status").textContent = message;
      renderOwnerOutcomeUnavailable(`Owner outcome unavailable: ${message}`);
    }

    function setEffectiveCpfRefund(value) {
      const input = byId("cpf-refund");
      const nextCents = toCents(roundMoney(value), "effective CPF refund");
      let currentCents = -1;
      try {
        currentCents = toCents(planner.parseCurrency(input.value), "effective CPF refund");
      } catch {
        // Replace an invalid derived value with the newly resolved amount.
      }
      input.value = moneyInput(fromCents(nextCents));
      if (currentCents !== nextCents) {
        form.dispatchEvent(new view.CustomEvent("cpf-effective-change", {
          detail: { cents: nextCents },
        }));
      }
      return currentCents !== nextCents;
    }

    function renderCpfEstimate(
      projection,
      ledgerRows,
      { cpfWeightsReliable = true } = {}
    ) {
      const partnerEnabled = enabledInput.checked;
      const names = ownerNames();
      byId("cpf-single-acquisition-field").hidden = partnerEnabled;
      byId("cpf-partner-monthly-field").hidden = !partnerEnabled;
      byId("cpf-partner-row").hidden = !partnerEnabled;
      byId("cpf-primary-monthly-label").textContent = partnerEnabled
        ? `${names.primary} CPF used per monthly instalment`
        : "CPF used per monthly instalment";
      byId("cpf-partner-monthly-label").textContent = `${names.partner} CPF used per monthly instalment`;
      byId("cpf-acquisition-mode").textContent = partnerEnabled
        ? (coupleSetupComplete
          ? "Purchase CPF is read from each dated acquisition-ledger row; rows after the planned sale are excluded."
          : "Complete the couple funding setup to estimate purchase CPF from the acquisition ledger.")
        : "Single-owner purchase CPF is assumed to be used on the legal acquisition date.";

      const estimate = buildCpfRefundEstimate({
        projection,
        ledgerRows,
        partnerEnabled,
        primaryAcquisitionCpf: currency("cpf-primary-acquisition"),
        primaryMonthlyCpf: currency("cpf-primary-monthly"),
        partnerMonthlyCpf: currency("cpf-partner-monthly"),
        annualRatePct: number("cpf-oa-rate"),
      });
      const currentEstimateSignature = cpfEstimateSignature(projection, estimate);
      const exactRefund = currency("cpf-refund-exact", true);
      const automaticReliable = !partnerEnabled || cpfWeightsReliable;
      const automaticContext = cpfAutoContext(projection, partnerEnabled);
      if (automaticReliable) {
        reliableAutoCpfByContext.set(automaticContext, {
          cents: toCents(
            roundMoney(estimate.household.refundRequired),
            "automatic CPF refund"
          ),
          estimateSignature: currentEstimateSignature,
        });
      }
      const reliableAutomatic = reliableAutoCpfByContext.get(automaticContext);
      const resolved = resolveCpfRefundAmount({
        exactRefund,
        estimatedRefund: estimate.household.refundRequired,
        automaticReliable,
        lastReliableAutoRefund: reliableAutomatic == null
          ? null
          : fromCents(reliableAutomatic.cents),
      });
      const automaticRetained = resolved.mode === "auto"
        && !automaticReliable
        && reliableAutomatic != null;
      const effectiveChanged = setEffectiveCpfRefund(resolved.activeRefund);
      if (effectiveChanged) projection = collectProjection();

      const estimatedRequired = roundMoney(estimate.household.refundRequired);
      const availableTotal = roundMoney(Math.min(
        estimatedRequired,
        projection.base.cpfRefundProceedsBase
      ));
      const shortfall = roundMoney(Math.max(0, estimatedRequired - availableTotal));
      const ownerAvailable = splitNonNegativeByWeights(
        availableTotal,
        estimate.primary.refundRequired,
        estimate.partner.refundRequired
      ) || { primary: 0, partner: 0 };
      const primaryAvailable = ownerAvailable.primary;
      const partnerAvailable = ownerAvailable.partner;

      byId("cpf-primary-name").textContent = names.primary;
      byId("cpf-partner-name").textContent = names.partner;
      byId("cpf-primary-principal").textContent = money(estimate.primary.principal);
      byId("cpf-primary-interest").textContent = money(estimate.primary.accruedInterest);
      byId("cpf-primary-refund").textContent = money(estimate.primary.refundRequired);
      byId("cpf-primary-available").textContent = money(primaryAvailable);
      byId("cpf-partner-principal").textContent = money(estimate.partner.principal);
      byId("cpf-partner-interest").textContent = money(estimate.partner.accruedInterest);
      byId("cpf-partner-refund").textContent = money(estimate.partner.refundRequired);
      byId("cpf-partner-available").textContent = money(partnerAvailable);
      byId("cpf-household-principal").textContent = money(estimate.household.principal);
      byId("cpf-household-interest").textContent = money(estimate.household.accruedInterest);
      byId("cpf-estimated-refund").textContent = money(estimatedRequired);
      byId("cpf-estimated-available").textContent = money(availableTotal);
      byId("cpf-estimated-shortfall").textContent = money(shortfall);
      setSignedClass(byId("cpf-estimated-shortfall"), -shortfall);
      byId("cpf-applied-refund").textContent = money(projection.cpfRefund);
      byId("cpf-applied-available").textContent = money(projection.base.cpfRefundAvailable);
      byId("use-automatic-cpf").hidden = resolved.mode !== "exact";

      const cappedCopy = estimate.cappedMonths
        ? ` In ${estimate.cappedMonths} month${estimate.cappedMonths === 1 ? "" : "s"}, combined CPF inputs exceeded the modelled instalment and were capped at that instalment.`
        : "";
      const belowEnteredMarketValue = projection.saleMarketValue != null
        && projection.base.salePrice + EPSILON < projection.saleMarketValue;
      const shortfallGuidance = belowEnteredMarketValue
        ? " The projected sale is below your entered market value, so do not assume CPF's market-value no-cash-top-up treatment applies."
        : " If the property is sold at market value and proceeds are insufficient, CPF generally does not require a cash top-up for the CPF shortfall; a below-market disposal can be treated differently.";
      const activeCoverageRequired = roundMoney(resolved.mode === "exact"
        ? projection.cpfRefund
        : estimatedRequired);
      const activeCoverageAvailable = roundMoney(resolved.mode === "exact"
        ? projection.base.cpfRefundAvailable
        : availableTotal);
      const activeCoverageShortfall = roundMoney(Math.max(
        0,
        activeCoverageRequired - activeCoverageAvailable
      ));
      const coverageCopy = activeCoverageShortfall > 0.01
        ? ` Projected proceeds after lender redemption can refund about ${money(activeCoverageAvailable)} of the ${resolved.mode === "exact" ? "active exact" : "estimated"} ${money(activeCoverageRequired)} amount; the ${money(activeCoverageShortfall)} difference is a CPF refund shortfall.${shortfallGuidance}`
        : ` Projected proceeds after lender redemption cover the ${resolved.mode === "exact" ? "active exact" : "estimated"} CPF refund.`;
      if (resolved.mode === "exact") {
        byId("cpf-refund-status").textContent = `Exact override active: ${money(projection.cpfRefund)} drives the sale waterfall. Clear the override to resume automatic updates. The CPF Home ownership dashboard remains authoritative.${coverageCopy}${cappedCopy}`;
      } else if (!automaticReliable && automaticRetained) {
        byId("cpf-refund-status").textContent = `Automatic mode is retaining the last reliable ${money(projection.cpfRefund)} household estimate. The current individual estimate is provisional because the couple ledger is incomplete, stale or not reconciled; reconcile it to refresh the household amount and owner split.${cappedCopy}`;
      } else if (!automaticReliable) {
        byId("cpf-refund-status").textContent = `Automatic mode will start once the couple funding ledger is complete and reconciled. The temporary household amount is ${money(projection.cpfRefund)}, and the individual estimate is provisional.${cappedCopy}`;
      } else {
        byId("cpf-refund-status").textContent = `Automatic mode has synchronised ${money(projection.cpfRefund)} to the sale waterfall from ${estimate.mortgageMonths} modelled mortgage month${estimate.mortgageMonths === 1 ? "" : "s"}. Enter the exact CPF Home ownership dashboard figure above when available.${coverageCopy}${cappedCopy}`;
      }
      renderOwnerSaleOutcome(
        projection,
        estimate,
        cpfWeightsReliable,
        resolved.mode,
        automaticRetained,
        resolved.mode === "auto" && !automaticReliable && estimatedRequired > EPSILON
      );
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
      byId("ledger-owner-outcome").textContent = `${names.primary} ${oneDecimal.format(ownership.primaryShare)}% · ${money(Math.abs(ownership.primaryPreCpfValue))}`;
      byId("ledger-partner-outcome").textContent = `${names.partner} ${oneDecimal.format(ownership.partnerShare)}% · ${money(Math.abs(ownership.partnerPreCpfValue))}`;
      setSignedClass(byId("ledger-owner-outcome"), ownership.primaryPreCpfValue);
      setSignedClass(byId("ledger-partner-outcome"), ownership.partnerPreCpfValue);
      byId("ledger-overall-status").textContent = validation.balanced
        ? "All rows and totals reconcile"
        : "Ledger needs reconciliation";
      byId("ledger-overall-status").className = validation.balanced
        ? "ledger-badge ledger-badge-ok"
        : "ledger-badge ledger-badge-warning";
      byId("ledger-stale").hidden = !state.stale;
      byId("funding-ledger-editor-summary").textContent = validation.balanced
        ? `${validation.rows.length} rows · all reconciled`
        : `${validation.rows.length} rows · review differences`;
      const reviewButton = byId("review-funding-ledger");
      reviewButton.hidden = validation.balanced && !state.stale;
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
      let projection;
      try {
        projection = collectProjection();
      } catch (error) {
        renderCpfUnavailable(`CPF estimate unavailable until the main plan is valid: ${error.message}`);
        showError(enabled && coupleSetupComplete
          ? `Funding ledger unavailable until the main plan is valid: ${error.message}`
          : "");
        return;
      }
      if (!enabled) {
        byId("funding-ledger-editor").open = false;
        showError("");
        try {
          renderCpfEstimate(projection, []);
        } catch (error) {
          renderCpfUnavailable(`CPF estimate unavailable: ${error.message}`);
        }
        return;
      }
      if (!coupleSetupComplete || !coupleFundingPlan) {
        showError("");
        try {
          renderCpfEstimate(projection, [], { cpfWeightsReliable: false });
        } catch (error) {
          renderCpfUnavailable(`CPF estimate unavailable: ${error.message}`);
        }
        return;
      }
      try {
        const state = currentLedger(projection, { regenerate });
        const validation = validateFundingLedger(state.rows, projection);
        showError("");
        renderSummary(validation, projection, state);
        renderRows(validation, projection);
        renderFooter(validation);
        try {
          renderCpfEstimate(projection, state.rows, {
            cpfWeightsReliable: validation.balanced && !state.stale,
          });
        } catch (error) {
          renderCpfUnavailable(`CPF estimate unavailable: ${error.message}`);
        }
      } catch (error) {
        showError(`Funding ledger unavailable until the main plan is valid: ${error.message}`);
      }
    }

    function scheduleRender() {
      view.clearTimeout(refreshTimer);
      refreshTimer = view.setTimeout(() => render(), 0);
    }

    const restoredDraft = restoreDraft();
    const handoffApplied = applyDecisionLabHandoff(restoredDraft);
    if (restoredDraft) {
      form.querySelector("input[name='property-route']:checked").dispatchEvent(
        new view.Event("change", { bubbles: true })
      );
    }
    if (handoffApplied) {
      form.querySelector("input[name='property-route']:checked").dispatchEvent(
        new view.Event("change", { bubbles: true })
      );
    }

    byId("saved-version-select").addEventListener("change", event => {
      const hasSelection = Boolean(event.target.value);
      byId("load-plan-version").disabled = !hasSelection;
      byId("delete-plan-version").disabled = !hasSelection;
    });
    byId("save-plan-version").addEventListener("click", async () => {
      const button = byId("save-plan-version");
      button.disabled = true;
      try {
        const record = await saveVersionSnapshot(
          byId("version-name").value,
          captureDraft(),
          "user"
        );
        await refreshVersionManager(record.id);
        versionStatus(`Saved immutable version “${record.name}”. Later edits stay in the working draft until you save another version.`);
      } catch (error) {
        versionStatus(`Version not saved: ${error.message}`);
      } finally {
        button.disabled = false;
      }
    });
    byId("load-plan-version").addEventListener("click", async () => {
      const id = byId("saved-version-select").value;
      if (!id) return;
      try {
        const record = validateVersionRecord(
          await versionStoreRequest("readonly", "get", id),
          { validateDraft: true }
        );
        if (!view.confirm(`Load “${record.name}”? Your current working draft will be saved as a recovery version first.`)) return;
        const recovery = await saveRecoverySnapshot(record.name);
        if (!recovery && !view.confirm("A recovery copy could not be saved. Continue loading without one?")) return;
        const activation = activateDraft(record.draft);
        await refreshVersionManager(record.id);
        const sourceCopy = record.sourceCalculatorVersion === CALCULATOR_VERSION
          ? ""
          : ` Its inputs originated in calculator ${record.sourceCalculatorVersion} and are recalculated using ${CALCULATOR_VERSION}.`;
        versionStatus(activation.persisted
          ? `Loaded “${record.name}”. It is now the working draft; the named snapshot remains unchanged.${sourceCopy}`
          : `Loaded “${record.name}” for this session, but the working draft could not be saved for refresh. The named snapshot remains available.${sourceCopy}`);
      } catch (error) {
        versionStatus(`Version not loaded: ${error.message}`);
      }
    });
    byId("delete-plan-version").addEventListener("click", async () => {
      const id = byId("saved-version-select").value;
      if (!id) return;
      try {
        const record = validateVersionRecord(
          await versionStoreRequest("readonly", "get", id)
        );
        if (!view.confirm(`Delete the saved version “${record.name}”? This cannot be undone.`)) return;
        await versionStoreRequest("readwrite", "delete", id);
        await refreshVersionManager();
        versionStatus(`Deleted saved version “${record.name}”. The current working draft was not changed.`);
      } catch (error) {
        versionStatus(`Version not deleted: ${error.message}`);
      }
    });
    byId("export-plan-draft").addEventListener("click", () => {
      try {
        downloadCurrentDraft();
      } catch (error) {
        versionStatus(`Draft not exported: ${error.message}`);
      }
    });
    byId("import-plan-draft").addEventListener("click", () => {
      byId("import-plan-file").click();
    });
    byId("import-plan-file").addEventListener("change", async event => {
      const input = event.target;
      const file = input.files && input.files[0];
      if (!file) return;
      try {
        if (file.size > MAX_IMPORT_BYTES) {
          throw new RangeError("Import file exceeds the 1 MB limit");
        }
        const envelope = parseDraftExport(await file.text());
        const prepared = validateDraftBeforeActivation(envelope.draft);
        if (!view.confirm(`Import “${envelope.name}” and replace the working draft? A recovery version will be saved first.`)) return;
        let imported = null;
        try {
          imported = await saveVersionSnapshot(
            envelope.name,
            prepared.saved,
            "import",
            envelope.calculatorVersion
          );
        } catch (versionError) {
          if (!view.confirm(`A named imported version could not be saved (${versionError.message}). Continue as an unsaved working draft without a recovery copy?`)) return;
        }
        if (imported) {
          const recovery = await saveRecoverySnapshot(envelope.name);
          if (!recovery && !view.confirm("A recovery copy could not be saved. Continue importing without one?")) {
            await versionStoreRequest("readwrite", "delete", imported.id);
            await refreshVersionManager();
            return;
          }
        }
        const activation = activateDraft(prepared.saved);
        await refreshVersionManager(imported?.id);
        const versionCopy = imported ? " and a named version" : "";
        const recalculationCopy = envelope.calculatorVersion === CALCULATOR_VERSION
          ? ""
          : ` Inputs came from calculator ${envelope.calculatorVersion} and were recalculated with ${CALCULATOR_VERSION}.`;
        versionStatus(activation.persisted
          ? `Imported “${envelope.name}” as the working draft${versionCopy}.${recalculationCopy}`
          : `Imported “${envelope.name}” for this session${versionCopy}, but the working draft could not be saved for refresh.${recalculationCopy}`);
      } catch (error) {
        versionStatus(`Draft not imported: ${error.message}`);
      } finally {
        input.value = "";
      }
    });
    refreshVersionManager();

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
    byId("review-funding-ledger").addEventListener("click", () => {
      const editor = byId("funding-ledger-editor");
      editor.open = true;
      const target = document.querySelector(
        ".ledger-row-warning .ledger-input, #funding-ledger-body .ledger-input"
      );
      if (target) target.focus();
    });
    byId("funding-ledger-editor").addEventListener("toggle", () => {
      byId("review-funding-ledger").setAttribute(
        "aria-expanded",
        String(byId("funding-ledger-editor").open)
      );
    });
    byId("use-automatic-cpf").addEventListener("click", () => {
      const input = byId("cpf-refund-exact");
      input.value = "";
      input.dispatchEvent(new view.Event("input", { bubbles: true }));
      render();
      input.focus();
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
        byId("funding-ledger-editor").open = true;
        render();
        view.requestAnimationFrame(() => {
          byId("funding-ledger-body").querySelector(
            `[data-row-key="custom-${customCounter}"][data-field="action"]`
          )?.focus();
        });
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
    byId("confirm-decision-lab-dates").addEventListener("click", () => {
      decisionLabDatePrecision = null;
      renderDecisionLabDateNotice();
      scheduleSave();
    });
    form.addEventListener("input", event => {
      if (event.target.closest("#plan-versions-details, #funding-ledger-editor")) return;
      scheduleSave();
      if (event.target.closest("#partner-settings")) return;
      scheduleRender();
    });
    form.addEventListener("change", event => {
      if (event.target.closest("#plan-versions-details, #funding-ledger-editor")) return;
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
      reliableAutoCpfByContext.clear();
      decisionLabDatePrecision = null;
      renderDecisionLabDateNotice();
      const dialog = byId("couple-funding-dialog");
      if (dialog.open && typeof dialog.close === "function") dialog.close();
      else dialog.removeAttribute("open");
      [
        "property-loan-details", "partner-settings", "advanced-cost-details",
        "cpf-assumptions-details", "plan-versions-details", "funding-ledger-editor",
      ].forEach(id => {
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
      byId("cpf-refund").value = "0";
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
    CALCULATOR_VERSION,
    EXPORT_FORMAT,
    EXPORT_FORMAT_VERSION,
    FUNDING_PLAN_SOURCE_ORDER,
    LEGACY_STORAGE_KEY,
    STORAGE_KEY,
    STORAGE_VERSION,
    VERSION_DATABASE,
    allocationTotal,
    applyFundingPlan,
    buildCpfRefundEstimate,
    buildOwnerSaleOutcome,
    buildStandardFundingLedger,
    createDraftExport,
    init,
    makeRow,
    normalizeShare,
    ownerFundingAllocation,
    parseDraftExport,
    parseDecisionLabHandoff,
    resolveCpfRefundAmount,
    splitOutcome,
    toCents,
    fromCents,
    validateVersionName,
    validateFundingPlan,
    validateFundingLedger,
  };
});
