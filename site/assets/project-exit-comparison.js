(() => {
  "use strict";

  const MIN_PROJECTS = 2;
  const MAX_PROJECTS = 5;
  const CANONICAL_SOURCE_FALLBACK = "ura_private";
  const PROJECT_CATALOG_SCHEMA = "private-project-catalog.v1";
  const DATASET_REVISION_RE = /^[0-9a-f]{64}$/;
  const REVISION_MISMATCH_MESSAGE = "Transaction data generation changed while this page was open. Reload this page before using transaction evidence.";
  const URL_KEYS = [
    "p", "price", "areaSqft", "tolerancePct", "toleranceSqft", "saleState", "purchaseDate",
    "saleDate", "annualGrowth", "sellingRate", "saleCosts",
    // Remove aliases emitted by early drafts when a canonical URL is written.
    "area", "tolerance", "state", "purchase", "sale", "growth", "allowance", "costs",
  ];

  const ready = callback => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
    } else {
      callback();
    }
  };

  const sameTransactionContract = (actual, expected) => {
    if (actual === expected) return true;
    if (Array.isArray(actual) || Array.isArray(expected)) {
      return Array.isArray(actual) && Array.isArray(expected)
        && actual.length === expected.length
        && actual.every((value, index) => sameTransactionContract(value, expected[index]));
    }
    if (!actual || !expected || typeof actual !== "object" || typeof expected !== "object") {
      return false;
    }
    const actualKeys = Object.keys(actual).sort();
    const expectedKeys = Object.keys(expected).sort();
    return actualKeys.length === expectedKeys.length
      && actualKeys.every(
        (key, index) => key === expectedKeys[index]
          && sameTransactionContract(actual[key], expected[key])
      );
  };

  ready(() => {
    const dataElement = document.getElementById("project-exit-data");
    const elements = {
      app: document.getElementById("decision-lab"),
      form: document.getElementById("decision-form"),
      slots: document.getElementById("project-slots"),
      options: document.getElementById("project-options"),
      add: document.getElementById("add-project"),
      targetArea: document.getElementById("target-area"),
      tolerance: document.getElementById("area-tolerance"),
      saleState: document.getElementById("sale-state"),
      purchaseDate: document.getElementById("purchase-date"),
      saleDate: document.getElementById("planned-sale-date"),
      annualGrowth: document.getElementById("annual-growth"),
      sellingRate: document.getElementById("selling-rate"),
      saleCosts: document.getElementById("sale-costs"),
      results: document.getElementById("comparison-results"),
      status: document.getElementById("status-message"),
      formError: document.getElementById("form-error"),
      copy: document.getElementById("copy-view"),
      reset: document.getElementById("reset-view"),
      catalogState: document.getElementById("project-catalog-state"),
      catalogStatus: document.getElementById("project-catalog-status"),
      catalogRetry: document.getElementById("retry-project-catalog"),
    };

    const required = [
      "app", "form", "slots", "add", "targetArea", "tolerance", "saleState",
      "purchaseDate", "saleDate", "annualGrowth", "sellingRate", "saleCosts",
      "results", "status", "formError", "copy", "reset",
      "catalogState", "catalogStatus", "catalogRetry",
    ];
    const missing = required.filter(key => !elements[key]);
    if (!dataElement || missing.length) {
      const status = elements.status || document.getElementById("status-message");
      if (status) {
        status.textContent = dataElement
          ? `The decision lab shell is incomplete (${missing.join(", ")}).`
          : "The project comparison data is unavailable.";
        status.setAttribute("role", "alert");
      }
      return;
    }

    let payload;
    try {
      payload = JSON.parse(dataElement.textContent || "{}");
      if (!payload || typeof payload !== "object" || !Array.isArray(payload.projects)) {
        throw new TypeError("The embedded payload has an unexpected shape.");
      }
    } catch (error) {
      failPage(`The project comparison data could not be read: ${error.message} Reload this page; if the problem remains, rebuild the report from validated source data.`);
      return;
    }

    const datasetRevision = stringValue(payload.dataset_revision);
    if (!DATASET_REVISION_RE.test(datasetRevision)) {
      failPage("The embedded transaction revision is unavailable. Reload the page; if the problem remains, rebuild the report from one complete transaction generation.");
      return;
    }
    const catalogPath = stringValue(payload.catalog?.path);
    const catalogRevision = stringValue(payload.catalog?.revision);
    const catalogSchema = stringValue(payload.catalog?.schema);
    if (
      !catalogPath
      || !DATASET_REVISION_RE.test(catalogRevision)
      || catalogSchema !== PROJECT_CATALOG_SCHEMA
    ) {
      failPage("The project catalog bootstrap is unavailable. Rebuild the report from one validated catalog generation.");
      return;
    }
    const expectedTransactionSchema = payload.transaction_schema;
    const expectedTransactionEnumerations = payload.transaction_enumerations;
    if (
      !expectedTransactionSchema
      || typeof expectedTransactionSchema !== "object"
      || Array.isArray(expectedTransactionSchema)
      || !expectedTransactionEnumerations
      || typeof expectedTransactionEnumerations !== "object"
      || Array.isArray(expectedTransactionEnumerations)
    ) {
      failPage("The embedded transaction contract is unavailable. Reload the page; if the problem remains, rebuild the report from one complete transaction generation.");
      return;
    }

    let projects = payload.projects
      .filter(project => project && typeof project === "object" && stringValue(project.id))
      .map(normaliseProject);
    let projectById = new Map(projects.map(project => [project.id, project]));
    let projectByLabel = new Map(projects.map(project => [normaliseProjectLabel(project.selectionLabel), project]));
    if (projectById.size < MIN_PROJECTS) {
      failPage("At least two projects are required to open the decision lab.");
      return;
    }

    const canonicalMetadata = payload.source_metadata?.canonical || {};
    const completeEnd = validMonth(canonicalMetadata.complete_end)
      ? canonicalMetadata.complete_end
      : validMonth(canonicalMetadata.complete_through)
        ? canonicalMetadata.complete_through
        : null;
    const analysisStart = validMonth(canonicalMetadata.analysis_60_start)
      ? canonicalMetadata.analysis_60_start
      : completeEnd
        ? addMonths(completeEnd, -59)
        : null;
    const partialMonth = validMonth(canonicalMetadata.partial_month)
      ? canonicalMetadata.partial_month
      : null;
    const canonicalSource = stringValue(canonicalMetadata.source) || CANONICAL_SOURCE_FALLBACK;
    if (!completeEnd || !analysisStart) {
      failPage("Canonical transaction coverage is missing its complete 60-month analysis period.");
      return;
    }

    const configuredMinimum = integerValue(payload.limits?.min_projects);
    const configuredMaximum = integerValue(payload.limits?.max_projects);
    const minimumProjects = clamp(configuredMinimum || MIN_PROJECTS, MIN_PROJECTS, MAX_PROJECTS);
    const maximumProjects = clamp(configuredMaximum || MAX_PROJECTS, minimumProjects, MAX_PROJECTS);
    const requestedCatalogProjectIds = new URL(window.location.href).searchParams.getAll("p");
    const needsCatalogForURL = requestedCatalogProjectIds.some(id => !projectById.has(id));
    const defaults = buildDefaults();
    let state = stateFromURL(defaults);
    let lastAnalyses = [];
    let renderSequence = 0;
    let refreshTimer = 0;
    let catalogReady = false;
    let catalogLoadSequence = 0;

    populateProjectOptions();
    applyGlobalControls();
    renderProjectSlots();
    bindEvents();
    void refresh({ syncURL: !needsCatalogForURL });
    void hydrateProjectCatalog();

    function failPage(message) {
      elements.app?.setAttribute("aria-busy", "false");
      if (elements.status) {
        elements.status.textContent = message;
        elements.status.setAttribute("role", "alert");
      }
      if (elements.results) {
        elements.results.innerHTML = `<div class="decision-error" role="alert"><h2>Decision lab unavailable</h2><p>${escapeHTML(message)}</p></div>`;
      }
    }

    function validateProjectCatalog(catalog) {
      const requiredKeys = [
        "catalog_revision", "contexts", "counts", "latest_project_month", "projects",
        "schema", "transaction_dataset_revision",
      ];
      if (!catalog || typeof catalog !== "object" || Array.isArray(catalog)) {
        return "The project catalog is not an object.";
      }
      const actualKeys = Object.keys(catalog).sort();
      if (
        actualKeys.length !== requiredKeys.length
        || !requiredKeys.every((key, index) => actualKeys[index] === key)
      ) {
        return "The project catalog has an unexpected top-level contract.";
      }
      if (catalog.schema !== catalogSchema || catalog.catalog_revision !== catalogRevision) {
        return "The project catalog revision or schema does not match this page.";
      }
      if (catalog.transaction_dataset_revision !== datasetRevision) {
        return REVISION_MISMATCH_MESSAGE;
      }
      if (
        !Array.isArray(catalog.projects)
        || !catalog.contexts
        || typeof catalog.contexts !== "object"
        || Array.isArray(catalog.contexts)
        || !catalog.counts
        || typeof catalog.counts !== "object"
        || Array.isArray(catalog.counts)
      ) {
        return "The project catalog projects, contexts, or counts are malformed.";
      }
      const ids = new Set();
      let exitCount = 0;
      let comparisonCount = 0;
      let transactionCount = 0;
      const usedContexts = new Set();
      for (const project of catalog.projects) {
        const capabilities = project?.capabilities;
        const capabilityKeys = capabilities && typeof capabilities === "object"
          ? Object.keys(capabilities).sort()
          : [];
        if (
          !project
          || typeof project !== "object"
          || !stringValue(project.id)
          || !stringValue(project.selection_label)
          || !capabilities
          || typeof capabilities !== "object"
          || !sameTransactionContract(
            capabilityKeys,
            ["framework_comparison", "private_explorer", "project_exit", "transactions"]
          )
          || typeof capabilities.private_explorer !== "boolean"
          || typeof capabilities.framework_comparison !== "boolean"
          || typeof capabilities.transactions !== "boolean"
          || typeof capabilities.project_exit !== "boolean"
          || ids.has(String(project.id))
        ) {
          return "The project catalog contains an invalid or duplicate project record.";
        }
        if (
          !capabilities.private_explorer
          || capabilities.transactions !== capabilities.project_exit
          || (capabilities.transactions && !capabilities.framework_comparison)
        ) {
          return "The project catalog contains an inconsistent capability assignment.";
        }
        ids.add(String(project.id));
        if (capabilities.framework_comparison) {
          comparisonCount += 1;
          if (!stringValue(project.context_key) || !catalog.contexts[project.context_key]) {
            return "A comparison project is missing its framework context.";
          }
          usedContexts.add(project.context_key);
        } else if (project.context_key !== null) {
          return "An explorer-only project unexpectedly claims framework context.";
        }
        if (capabilities.transactions) {
          transactionCount += 1;
          if (
            !stringValue(project.transaction_shard).startsWith(
              `assets/condo-transactions/${datasetRevision}/shard-`
            )
            || !Number.isInteger(project.transaction_count)
            || project.transaction_count < 0
          ) {
            return "A transaction-capable catalog record has invalid shard metadata.";
          }
        }
        if (capabilities.project_exit) exitCount += 1;
      }
      const countKeys = Object.keys(catalog.counts).sort();
      if (
        !sameTransactionContract(countKeys, ["all", "comparison", "transaction"])
        || Number(catalog.counts.all) !== catalog.projects.length
        || Number(catalog.counts.comparison) !== comparisonCount
        || Number(catalog.counts.transaction) !== transactionCount
      ) {
        return "The project catalog counts do not reconcile to its project records.";
      }
      if (
        usedContexts.size !== Object.keys(catalog.contexts).length
        || Object.keys(catalog.contexts).some(key => !usedContexts.has(key))
      ) {
        return "The project catalog contains an unused or unreferenced framework context.";
      }
      if (exitCount < minimumProjects) {
        return "The project catalog does not contain enough exit-comparison projects.";
      }
      return true;
    }

    async function hydrateProjectCatalog() {
      const sequence = ++catalogLoadSequence;
      catalogReady = false;
      elements.add.disabled = true;
      elements.catalogState.dataset.state = "loading";
      elements.catalogStatus.textContent = "Loading the full project catalog… The example projects remain usable.";
      elements.catalogStatus.setAttribute("role", "status");
      elements.catalogRetry.hidden = true;
      try {
        if (!window.SGEstateData?.loadJSON) {
          throw new Error("The shared project catalog loader is unavailable.");
        }
        const catalog = await window.SGEstateData.loadJSON(catalogPath, {
          revision: catalogRevision,
          timeoutMs: 12_000,
          validate: validateProjectCatalog,
        });
        if (sequence !== catalogLoadSequence) return;
        const hydratedProjects = catalog.projects
          .filter(project => project.capabilities.project_exit)
          .map(normaliseProject);
        projects = hydratedProjects;
        projectById = new Map(projects.map(project => [project.id, project]));
        projectByLabel = new Map(
          projects.map(project => [normaliseProjectLabel(project.selectionLabel), project])
        );
        catalogReady = true;
        populateProjectOptions();
        elements.catalogState.dataset.state = "ready";
        elements.catalogStatus.textContent = `${projects.length.toLocaleString("en-SG")} projects ready.`;
        elements.catalogStatus.setAttribute("role", "status");
        elements.catalogRetry.hidden = true;
        elements.add.disabled = state.selections.length >= maximumProjects;
        elements.add.setAttribute("aria-disabled", String(elements.add.disabled));
        if (needsCatalogForURL) {
          state = stateFromURL(defaults);
          applyGlobalControls();
          renderProjectSlots();
          clearFormError();
          void refresh({ syncURL: true });
        }
      } catch (error) {
        if (sequence !== catalogLoadSequence) return;
        catalogReady = false;
        elements.add.disabled = true;
        elements.add.setAttribute("aria-disabled", "true");
        const fileHelp = window.location.protocol === "file:"
          ? " Open this report through a local web server; browsers block JSON loading from file:// pages."
          : "";
        const reason = error instanceof Error && error.message
          ? ` ${error.message}`
          : "";
        elements.catalogState.dataset.state = "error";
        elements.catalogStatus.textContent = `The full project catalog could not be loaded.${reason}${fileHelp} The example projects remain usable.`;
        elements.catalogStatus.setAttribute("role", "alert");
        elements.catalogRetry.hidden = false;
      }
    }

    function buildDefaults() {
      const configured = payload.defaults || {};
      const configuredProjectIds = arrayValue(
        Array.isArray(configured)
          ? configured
          : configured.projects || configured.project_ids || configured.selected_projects
      ).map(value => String(value));
      const fallbackProjectIds = projects.slice(0, minimumProjects).map(project => project.id);
      const projectIds = uniqueValidProjectIds(configuredProjectIds).slice(0, maximumProjects);
      while (projectIds.length < minimumProjects) {
        const next = fallbackProjectIds.find(id => !projectIds.includes(id))
          || projects.find(project => !projectIds.includes(project.id))?.id;
        if (!next) break;
        projectIds.push(next);
      }

      return {
        selections: projectIds.map(id => ({ id, price: null })),
        targetArea: positiveNumber(
          (Array.isArray(configured) ? null : configured.target_area_sqft ?? configured.target_area)
            ?? elements.targetArea.value,
          527
        ),
        tolerance: nonNegativeNumber(
          (Array.isArray(configured) ? null : configured.area_tolerance_pct ?? configured.area_tolerance)
            ?? elements.tolerance.value,
          10
        ),
        saleState: normaliseSaleState(
          (Array.isArray(configured) ? null : configured.sale_state) ?? elements.saleState.value
        ) || "Resale",
        purchaseDate: validMonth(Array.isArray(configured) ? null : configured.purchase_date)
          ? configured.purchase_date
          : elements.purchaseDate.value,
        saleDate: validMonth(Array.isArray(configured) ? null : configured.planned_sale_date ?? configured.sale_date)
          ? (configured.planned_sale_date ?? configured.sale_date)
          : elements.saleDate.value,
        annualGrowth: finiteNumber(
          (Array.isArray(configured) ? null : configured.annual_growth) ?? elements.annualGrowth.value
        ) ?? 3,
        sellingRate: nonNegativeNumber(
          (Array.isArray(configured) ? null : configured.selling_rate) ?? elements.sellingRate.value,
          2.18
        ),
        saleCosts: nonNegativeNumber(
          (Array.isArray(configured) ? null : configured.sale_costs) ?? elements.saleCosts.value,
          3000
        ),
      };
    }

    function stateFromURL(fallback) {
      const params = new URL(window.location.href).searchParams;
      const ids = params.getAll("p");
      const prices = params.getAll("price");
      const selections = [];
      ids.forEach((id, index) => {
        if (!projectById.has(id) || selections.some(item => item.id === id)) return;
        const price = finiteNumber(prices[index]);
        selections.push({ id, price: price !== null && price > 0 ? price : null });
      });
      const desiredCount = ids.length
        ? Math.max(minimumProjects, Math.min(maximumProjects, selections.length))
        : Math.max(minimumProjects, Math.min(maximumProjects, fallback.selections.length));
      fallback.selections.forEach(selection => {
        if (selections.length >= desiredCount) return;
        if (!selections.some(item => item.id === selection.id)) selections.push({ ...selection });
      });
      projects.forEach(project => {
        if (selections.length >= desiredCount) return;
        if (!selections.some(item => item.id === project.id)) selections.push({ id: project.id, price: null });
      });

      const get = (canonical, aliases = []) => {
        for (const key of [canonical, ...aliases]) {
          const value = params.get(key);
          if (value !== null && value !== "") return value;
        }
        return null;
      };
      const targetArea = finiteNumber(get("areaSqft", ["area"]));
      const tolerance = finiteNumber(get("tolerancePct", ["toleranceSqft", "tolerance"]));
      const growth = finiteNumber(get("annualGrowth", ["growth"]));
      const sellingRate = finiteNumber(get("sellingRate", ["allowance"]));
      const saleCosts = finiteNumber(get("saleCosts", ["costs"]));
      const purchaseDate = get("purchaseDate", ["purchase"]);
      const saleDate = get("saleDate", ["sale"]);

      return {
        selections: selections.slice(0, maximumProjects),
        targetArea: targetArea !== null && targetArea > 0 ? targetArea : fallback.targetArea,
        tolerance: tolerance !== null && tolerance >= 0 ? tolerance : fallback.tolerance,
        saleState: normaliseSaleState(get("saleState", ["state"])) || fallback.saleState,
        purchaseDate: normaliseInputMonth(purchaseDate) || fallback.purchaseDate,
        saleDate: normaliseInputMonth(saleDate) || fallback.saleDate,
        annualGrowth: growth ?? fallback.annualGrowth,
        sellingRate: sellingRate !== null && sellingRate >= 0 ? sellingRate : fallback.sellingRate,
        saleCosts: saleCosts !== null && saleCosts >= 0 ? saleCosts : fallback.saleCosts,
      };
    }

    function populateProjectOptions() {
      if (!elements.options) return;
      const options = projects.map(project =>
        `<option value="${escapeHTML(project.selectionLabel)}" data-project-id="${escapeHTML(project.id)}"></option>`
      ).join("");
      if (["DATALIST", "SELECT"].includes(elements.options.tagName)) {
        elements.options.innerHTML = options;
      }
    }

    function applyGlobalControls() {
      elements.targetArea.value = displayInputNumber(state.targetArea);
      elements.tolerance.value = displayInputNumber(state.tolerance);
      setSelectValue(elements.saleState, state.saleState);
      elements.purchaseDate.value = state.purchaseDate || "";
      elements.saleDate.value = state.saleDate || "";
      elements.annualGrowth.value = displayInputNumber(state.annualGrowth);
      elements.sellingRate.value = displayInputNumber(state.sellingRate);
      elements.saleCosts.value = displayInputNumber(state.saleCosts);
    }

    function renderProjectSlots() {
      elements.slots.innerHTML = state.selections.map((selection, index) => {
        const project = projectById.get(selection.id);
        return `
          <article class="project-slot" data-index="${index}">
            <div class="project-slot-heading">
              <span class="project-sequence" aria-hidden="true">${index + 1}</span>
              <div>
                <h3>Candidate ${index + 1}</h3>
                <p>${escapeHTML(project?.project || "Select a project")}</p>
              </div>
            </div>
            <div class="project-slot-fields">
              <label class="decision-field">
                <span>Project</span>
                <input data-role="project" type="search" list="project-options" autocomplete="off" spellcheck="false" value="${escapeHTML(project?.selectionLabel || "")}" aria-label="Candidate ${index + 1} project" required>
              </label>
              <label class="decision-field">
                <span>Entry price override <small>optional</small></span>
                <span class="money-input"><span aria-hidden="true">S$</span><input data-role="entry-price" type="number" min="1" max="100000000" step="1000" inputmode="decimal" value="${selection.price === null ? "" : escapeHTML(displayInputNumber(selection.price))}" aria-describedby="entry-help-${index}" placeholder="Use cohort median"></span>
              </label>
            </div>
            <div class="project-slot-actions">
              <p id="entry-help-${index}" class="entry-price-help" data-role="entry-help">Cohort median loads from canonical URA private records.</p>
              <button class="text-button" data-action="auto-price" type="button"${selection.price === null ? " disabled" : ""}>Use cohort median</button>
              <button class="text-button text-button-danger" data-action="remove-project" type="button"${state.selections.length <= minimumProjects ? " disabled" : ""}>Remove</button>
            </div>
          </article>`;
      }).join("");
      elements.add.disabled = !catalogReady || state.selections.length >= maximumProjects;
      elements.add.setAttribute("aria-disabled", String(elements.add.disabled));
    }

    function bindEvents() {
      elements.form.addEventListener("submit", event => {
        event.preventDefault();
        void refresh({ syncURL: true });
      });

      elements.slots.addEventListener("change", event => {
        const slot = event.target.closest(".project-slot");
        if (!slot) return;
        const index = Number(slot.dataset.index);
        if (event.target.matches("[data-role='project']")) {
          const id = projectFromPicker(event.target.value)?.id || "";
          if (!projectById.has(id) || state.selections.some((selection, itemIndex) => selection.id === id && itemIndex !== index)) {
            event.target.setAttribute("aria-invalid", "true");
            showFormError(id
              ? "Choose a different project for each candidate."
              : "Choose a recognized project from the search suggestions.");
            void refresh({ syncURL: false });
            return;
          }
          event.target.removeAttribute("aria-invalid");
          state.selections[index] = { id, price: null };
          clearFormError();
          renderProjectSlots();
          void refresh({ syncURL: true });
        }
      });

      elements.slots.addEventListener("input", event => {
        if (!event.target.matches("[data-role='entry-price']")) return;
        const slot = event.target.closest(".project-slot");
        const index = Number(slot?.dataset.index);
        if (!Number.isInteger(index) || !state.selections[index]) return;
        const price = finiteNumber(event.target.value);
        state.selections[index].price = event.target.value === "" ? null : price;
        const resetButton = slot.querySelector("[data-action='auto-price']");
        if (resetButton) resetButton.disabled = state.selections[index].price === null;
        scheduleRefresh();
      });

      elements.slots.addEventListener("click", event => {
        const button = event.target.closest("button[data-action]");
        const slot = event.target.closest(".project-slot");
        if (!button || !slot) return;
        const index = Number(slot.dataset.index);
        if (button.dataset.action === "auto-price") {
          state.selections[index].price = null;
          const input = slot.querySelector("[data-role='entry-price']");
          if (input) input.value = "";
          button.disabled = true;
          void refresh({ syncURL: true });
        } else if (button.dataset.action === "remove-project" && state.selections.length > minimumProjects) {
          state.selections.splice(index, 1);
          renderProjectSlots();
          void refresh({ syncURL: true });
        }
      });

      elements.add.addEventListener("click", () => {
        if (state.selections.length >= maximumProjects) return;
        const next = projects.find(project => !state.selections.some(selection => selection.id === project.id));
        if (!next) return;
        state.selections.push({ id: next.id, price: null });
        renderProjectSlots();
        void refresh({ syncURL: true });
        elements.slots.querySelector(".project-slot:last-child [data-role='project']")?.focus();
      });

      elements.form.addEventListener("change", event => {
        if (event.target.closest("#project-slots")) return;
        if (event.target.matches("input, select")) void refresh({ syncURL: true });
      });
      elements.form.addEventListener("input", event => {
        if (event.target.closest("#project-slots")) return;
        if (event.target.matches("input[type='number']")) scheduleRefresh();
      });

      elements.copy.addEventListener("click", async () => {
        readGlobalControls();
        const validation = validateState();
        if (validation) {
          showFormError(validation);
          return;
        }
        syncStateToURL("replace");
        try {
          await navigator.clipboard.writeText(window.location.href);
          setStatus("Comparison link copied.");
          const original = elements.copy.textContent;
          elements.copy.textContent = "Copied";
          window.setTimeout(() => { elements.copy.textContent = original; }, 1800);
        } catch {
          setStatus("Copy is unavailable. Select the address from the browser bar.", true);
        }
      });

      elements.reset.addEventListener("click", event => {
        event.preventDefault();
        state = cloneState(defaults);
        applyGlobalControls();
        renderProjectSlots();
        clearFormError();
        syncStateToURL("push");
        void refresh({ syncURL: false });
      });

      elements.catalogRetry.addEventListener("click", () => {
        window.SGEstateData?.invalidate?.(catalogPath, { revision: catalogRevision });
        void hydrateProjectCatalog();
      });

      window.addEventListener("popstate", () => {
        state = stateFromURL(defaults);
        applyGlobalControls();
        renderProjectSlots();
        clearFormError();
        void refresh({ syncURL: false });
      });
    }

    function scheduleRefresh() {
      window.clearTimeout(refreshTimer);
      refreshTimer = window.setTimeout(() => {
        refreshTimer = 0;
        void refresh({ syncURL: true });
      }, 260);
    }

    function readGlobalControls() {
      state.targetArea = finiteNumber(elements.targetArea.value);
      state.tolerance = finiteNumber(elements.tolerance.value);
      state.saleState = normaliseSaleState(elements.saleState.value);
      state.purchaseDate = elements.purchaseDate.value;
      state.saleDate = elements.saleDate.value;
      state.annualGrowth = finiteNumber(elements.annualGrowth.value);
      state.sellingRate = finiteNumber(elements.sellingRate.value);
      state.saleCosts = finiteNumber(elements.saleCosts.value);
    }

    function validateState() {
      const pickerInputs = Array.from(elements.slots.querySelectorAll("[data-role='project']"));
      pickerInputs.forEach(input => input.removeAttribute("aria-invalid"));
      if (pickerInputs.length !== state.selections.length) return "Project controls are incomplete.";
      const pickerProjects = pickerInputs.map(input => projectFromPicker(input.value));
      if (pickerProjects.some(project => !project)) {
        pickerInputs.forEach((input, index) => {
          if (!pickerProjects[index]) input.setAttribute("aria-invalid", "true");
        });
        return "Choose a recognized project from the search suggestions.";
      }
      const duplicateProjectIds = pickerProjects
        .map(project => project.id)
        .filter((id, index, ids) => ids.indexOf(id) !== index || ids.lastIndexOf(id) !== index);
      if (duplicateProjectIds.length) {
        pickerInputs.forEach((input, index) => {
          if (duplicateProjectIds.includes(pickerProjects[index].id)) input.setAttribute("aria-invalid", "true");
        });
        return "Choose a different project for each candidate.";
      }
      if (pickerProjects.some((project, index) => project.id !== state.selections[index]?.id)) {
        pickerInputs.forEach((input, index) => {
          if (pickerProjects[index].id !== state.selections[index]?.id) input.setAttribute("aria-invalid", "true");
        });
        return "Apply each changed project by choosing it from the search suggestions.";
      }
      if (state.selections.length < minimumProjects || state.selections.length > maximumProjects) {
        return `Choose between ${minimumProjects} and ${maximumProjects} projects.`;
      }
      if (new Set(state.selections.map(selection => selection.id)).size !== state.selections.length) {
        return "Choose a different project for each candidate.";
      }
      if (!state.selections.every(selection => projectById.has(selection.id))) {
        return "One of the selected projects is unavailable.";
      }
      if (state.selections.some(selection => selection.price !== null && (!Number.isFinite(selection.price) || selection.price <= 0 || selection.price > 100000000))) {
        return "Each entry-price override must be between S$1 and S$100,000,000, or left blank.";
      }
      if (!Number.isFinite(state.targetArea) || state.targetArea < 200 || state.targetArea > 10000) {
        return "Target size must be between 200 and 10,000 sqft.";
      }
      if (!Number.isFinite(state.tolerance) || state.tolerance < 0 || state.tolerance > 50) {
        return "Size tolerance must be between 0% and 50%.";
      }
      if (!state.saleState) return "Choose a valid sale state.";
      if (!validMonth(state.purchaseDate) || !validMonth(state.saleDate)) return "Enter valid purchase and planned-sale months.";
      if (dateValue(state.saleDate) <= dateValue(state.purchaseDate)) return "Planned sale must be after the purchase date.";
      if (!Number.isFinite(state.annualGrowth) || state.annualGrowth < -20 || state.annualGrowth > 20) {
        return "Annual growth must be between −20% and 20%.";
      }
      if (!Number.isFinite(state.sellingRate) || state.sellingRate < 0 || state.sellingRate > 10) {
        return "Selling allowance must be between 0% and 10%.";
      }
      if (!Number.isFinite(state.saleCosts) || state.saleCosts < 0 || state.saleCosts > 1000000) {
        return "Other sale costs must be between S$0 and S$1,000,000.";
      }
      const holdYears = yearDifference(state.purchaseDate, state.saleDate);
      if (!Number.isFinite(holdYears) || !Number.isFinite(Math.pow(1 + state.annualGrowth / 100, holdYears))) {
        return "The selected months create a scenario that is too long to calculate safely.";
      }
      return "";
    }

    async function refresh({ syncURL = false } = {}) {
      window.clearTimeout(refreshTimer);
      refreshTimer = 0;
      const sequence = ++renderSequence;
      readGlobalControls();
      const validation = validateState();
      if (validation) {
        setLoading(false);
        lastAnalyses = [];
        elements.results.innerHTML = invalidResultsHTML();
        showFormError(validation);
        setStatus("Correct the highlighted assumptions before comparing.", true);
        return;
      }
      clearFormError();
      if (syncURL) syncStateToURL("replace");

      setLoading(true);
      elements.results.innerHTML = loadingHTML();
      const holdYears = yearDifference(state.purchaseDate, state.saleDate);
      const analyses = await Promise.all(state.selections.map(async selection => {
        const project = projectById.get(selection.id);
        try {
          const shard = await loadShard(project.transactionShard);
          return analyseProject(project, selection, shard, holdYears);
        } catch (error) {
          return {
            project,
            selection,
            error: error instanceof Error ? error.message : String(error),
            cohort: emptyCohort(),
            entryPrice: selection.price,
            entrySource: selection.price === null ? "unknown" : "override",
          };
        }
      }));
      if (sequence !== renderSequence) return;

      if (analyses.some(analysis => analysis.error === REVISION_MISMATCH_MESSAGE)) {
        lastAnalyses = [];
        elements.results.innerHTML = revisionFailureHTML();
        elements.results.querySelector("[data-reload-transaction-data]")?.addEventListener(
          "click",
          () => window.location.reload()
        );
        setLoading(false);
        setStatus(REVISION_MISMATCH_MESSAGE, true);
        return;
      }

      lastAnalyses = analyses;
      updateEntryHelpers(analyses);
      elements.results.innerHTML = renderResults(analyses, holdYears);
      enhanceResultRegions(analyses);
      setLoading(false);
      const availableCount = analyses.filter(analysis => !analysis.error).length;
      const errorCount = analyses.length - availableCount;
      setStatus(
        errorCount
          ? `Compared ${availableCount} candidates; ${errorCount} transaction source${errorCount === 1 ? "" : "s"} could not be loaded.`
          : `Comparison updated for ${availableCount} candidates.`,
        errorCount > 0
      );
    }

    function loadShard(path) {
      if (!path) return Promise.reject(new Error("No transaction shard is configured for this project."));
      if (!window.SGEstateData?.loadJSON) {
        return Promise.reject(new Error("The shared transaction data loader is unavailable."));
      }
      return window.SGEstateData.loadJSON(path, {
        revision: datasetRevision,
        timeoutMs: 12_000,
        validate: shard => {
          if (
            !shard
            || typeof shard !== "object"
            || !sameTransactionContract(shard.schema, expectedTransactionSchema)
            || !shard.projects
            || typeof shard.projects !== "object"
            || Array.isArray(shard.projects)
            || !sameTransactionContract(shard.enumerations, expectedTransactionEnumerations)
          ) {
            return "The transaction shard has an unexpected shape.";
          }
          if (shard.dataset_revision !== datasetRevision) {
            return REVISION_MISMATCH_MESSAGE;
          }
          return true;
        },
      });
    }

    function analyseProject(project, selection, shard, holdYears) {
      const rawRecords = shard.projects[project.id];
      if (!Array.isArray(rawRecords)) {
        throw new Error("This project is not present in its configured transaction shard.");
      }
      const records = rawRecords.map(record => decodeRecord(record, shard.enumerations)).filter(Boolean);
      const partialExcluded = partialMonth ? records.filter(record => record.saleMonth === partialMonth).length : 0;
      const canonicalRows = records.filter(record =>
        record.dataSource === canonicalSource
        && compareMonth(record.saleMonth, analysisStart) >= 0
        && compareMonth(record.saleMonth, completeEnd) <= 0
        && (!partialMonth || record.saleMonth !== partialMonth)
      );
      const lowerArea = state.targetArea * (1 - state.tolerance / 100);
      const upperArea = state.targetArea * (1 + state.tolerance / 100);
      const sizeRows = canonicalRows.filter(record => record.areaSqft >= lowerArea && record.areaSqft <= upperArea);
      const cohortRows = sizeRows.filter(record => state.saleState === "all" || record.saleType === state.saleState);
      const resaleRows = sizeRows.filter(record => record.saleType === "Resale");
      const cohort = summariseCohort(cohortRows, resaleRows);
      const entryPrice = selection.price ?? cohort.price.median;
      const entrySource = selection.price === null
        ? (cohort.price.median === null ? "unknown" : "cohort_median")
        : "override";
      const outcome = entryPrice === null ? null : calculateOutcome(entryPrice, state.annualGrowth, holdYears);
      const scenarios = entryPrice === null
        ? []
        : [state.annualGrowth - 3, state.annualGrowth, state.annualGrowth + 3]
          .map((growth, index) => ({
            key: ["lower", "base", "upper"][index],
            growth,
            outcome: growth <= -100 ? null : calculateOutcome(entryPrice, growth, holdYears),
          }));
      const breakEvenGrowth = entryPrice === null
        ? null
        : calculateBreakEvenGrowth(entryPrice, holdYears);
      const analysis = {
        project,
        selection,
        rawCount: records.length,
        canonicalCount: canonicalRows.length,
        sizeCount: sizeRows.length,
        partialExcluded,
        cohort,
        entryPrice,
        entrySource,
        outcome,
        scenarios,
        breakEvenGrowth,
      };
      analysis.plannerURL = buildPlannerURL(analysis);
      return analysis;
    }

    function decodeRecord(record, enumerations) {
      if (!Array.isArray(record) || record.length < 10 || !validMonth(record[0])) return null;
      const price = finiteNumber(record[1]);
      const areaSqm = finiteNumber(record[2]);
      const suppliedAreaSqft = finiteNumber(record[3]);
      const areaSqft = suppliedAreaSqft ?? (areaSqm === null ? null : areaSqm * 10.7639104167);
      if (price === null || price <= 0 || areaSqft === null || areaSqft <= 0) return null;
      const psf = finiteNumber(record[4]) ?? price / areaSqft;
      return {
        saleMonth: record[0],
        price,
        areaSqm,
        areaSqft,
        psf,
        saleType: enumValue(enumerations.sale_types, record[5]),
        floorLevel: enumValue(enumerations.floor_levels, record[6]),
        bedrooms: finiteNumber(record[7]),
        bedroomSource: enumValue(enumerations.bedroom_sources, record[8]),
        dataSource: enumValue(enumerations.data_sources, record[9]),
      };
    }

    function summariseCohort(rows, resaleRows) {
      const sortedRows = [...rows].sort((left, right) =>
        compareMonth(right.saleMonth, left.saleMonth) || right.price - left.price
      );
      const months = [...new Set(resaleRows.map(row => row.saleMonth))].sort(compareMonth);
      const gaps = months.slice(1).map((month, index) => monthIndex(month) - monthIndex(months[index]));
      const latestMonth = months.length ? months[months.length - 1] : null;
      const latestRows = latestMonth ? resaleRows.filter(row => row.saleMonth === latestMonth) : [];
      const trailing12Start = addMonths(completeEnd, -11);
      const trailing24Start = addMonths(completeEnd, -23);
      return {
        n: rows.length,
        rows: sortedRows,
        price: distribution(rows.map(row => row.price)),
        psf: distribution(rows.map(row => row.psf)),
        area: distribution(rows.map(row => row.areaSqft)),
        activeMonths: months.length,
        latestMonth,
        latestPrice: distribution(latestRows.map(row => row.price)).median,
        latestPsf: distribution(latestRows.map(row => row.psf)).median,
        medianMonthGap: distribution(gaps).median,
        trailing12: resaleRows.filter(row => compareMonth(row.saleMonth, trailing12Start) >= 0).length,
        trailing24: resaleRows.filter(row => compareMonth(row.saleMonth, trailing24Start) >= 0).length,
      };
    }

    function emptyCohort() {
      return {
        n: 0,
        rows: [],
        price: distribution([]),
        psf: distribution([]),
        area: distribution([]),
        activeMonths: 0,
        latestMonth: null,
        latestPrice: null,
        latestPsf: null,
        medianMonthGap: null,
        trailing12: 0,
        trailing24: 0,
      };
    }

    function calculateOutcome(entryPrice, growth, holdYears) {
      const projectedSalePrice = entryPrice * Math.pow(1 + growth / 100, holdYears);
      if (!Number.isFinite(projectedSalePrice)) return null;
      const sellingAllowance = projectedSalePrice * state.sellingRate / 100;
      const netBeforeFinancingCPF = projectedSalePrice - sellingAllowance - state.saleCosts;
      return {
        projectedSalePrice,
        grossGain: projectedSalePrice - entryPrice,
        sellingAllowance,
        saleCosts: state.saleCosts,
        netBeforeFinancingCPF,
        netChangeBeforeHoldingCosts: netBeforeFinancingCPF - entryPrice,
      };
    }

    function calculateBreakEvenGrowth(entryPrice, holdYears) {
      if (!(entryPrice > 0) || !(holdYears > 0)) return null;
      const retainedRate = 1 - state.sellingRate / 100;
      if (!(retainedRate > 0)) return null;
      const breakEvenSalePrice = (entryPrice + state.saleCosts) / retainedRate;
      return (Math.pow(breakEvenSalePrice / entryPrice, 1 / holdYears) - 1) * 100;
    }

    function updateEntryHelpers(analyses) {
      analyses.forEach((analysis, index) => {
        const slot = elements.slots.querySelector(`.project-slot[data-index="${index}"]`);
        const helper = slot?.querySelector("[data-role='entry-help']");
        if (!helper) return;
        if (analysis.error) {
          helper.textContent = `Cohort unavailable: ${analysis.error}`;
          helper.classList.add("entry-price-help-error");
        } else if (analysis.cohort.price.median === null) {
          helper.textContent = "No matching canonical URA private record; enter an explicit purchase price to model an outcome.";
          helper.classList.add("entry-price-help-error");
        } else if (analysis.selection.price === null) {
          helper.textContent = `Using cohort median ${formatMoney(analysis.cohort.price.median)} (n=${analysis.cohort.n}).`;
          helper.classList.remove("entry-price-help-error");
        } else {
          helper.textContent = `Override active. Matching cohort median is ${formatMoney(analysis.cohort.price.median)} (n=${analysis.cohort.n}).`;
          helper.classList.remove("entry-price-help-error");
        }
      });
    }

    function renderResults(analyses, holdYears) {
      const period = `${formatMonth(analysisStart)}–${formatMonth(completeEnd)}`;
      const areaBounds = cohortAreaBounds();
      return `
        <section class="decision-method" aria-labelledby="decision-method-title">
          <div>
            <p class="decision-kicker">Evidence boundary</p>
            <h2 id="decision-method-title">Same size. Same holding horizon.</h2>
          </div>
          <div class="method-pills" aria-label="Comparison method">
            <span>Canonical URA private transactions</span>
            <span>${escapeHTML(period)}</span>
            <span>${formatNumber(state.targetArea)} sqft ± ${formatNumber(state.tolerance)}% (${formatNumber(Math.round(areaBounds.lower))}–${formatNumber(Math.round(areaBounds.upper))} sqft)</span>
            <span>${escapeHTML(displaySaleState(state.saleState))}</span>
          </div>
          <p>Headline medians and the exact ledger exclude the incomplete historical backfill and the source partial month${partialMonth ? ` (${escapeHTML(formatMonth(partialMonth))})` : ""}. The 12/24-month figures are recorded Resale-caveat flow proxies, regardless of the selected price-cohort sale state. No project verdict, valuation or return forecast is produced.</p>
        </section>
        <section aria-labelledby="evidence-title">
          <div class="result-heading">
            <div><p class="decision-kicker">Observed evidence</p><h2 id="evidence-title">Candidate evidence cards</h2></div>
            <p>${formatYears(holdYears)} modeled hold · ${formatPercent(state.annualGrowth)} annual growth assumption</p>
          </div>
          <div class="evidence-grid">${analyses.map(renderEvidenceCard).join("")}</div>
        </section>
        ${renderOutcomeMatrix(analyses, holdYears)}
        ${renderScenarioMatrix(analyses)}
        ${renderLedgers(analyses, period)}
      `;
    }

    function renderEvidenceCard(analysis, index) {
      const project = analysis.project;
      if (analysis.error) {
        return `<article class="evidence-card evidence-card-error"><p class="candidate-label">Candidate ${index + 1}</p><h3>${escapeHTML(project.selectionLabel)}</h3><p class="error-copy">Transaction evidence could not load: ${escapeHTML(analysis.error)}</p><p>Project identity remains available, but no cohort or modeled outcome is shown.</p><button type="button" data-retry-transaction-data>Retry transaction evidence</button></article>`;
      }
      const cohort = analysis.cohort;
      const sample = sampleAssessment(cohort.n);
      const station = stationSummary(project);
      const schools = schoolSummary(project);
      const entryLabel = analysis.entrySource === "override"
        ? "Your entry-price override"
        : analysis.entrySource === "cohort_median"
          ? "Same-size cohort median"
          : "Entry price unknown";
      const planLink = analysis.plannerURL
        ? `<a class="planner-link" href="${escapeHTML(analysis.plannerURL)}">Continue in full loan &amp; CPF planner <span aria-hidden="true">→</span></a>`
        : `<span class="planner-link planner-link-disabled" aria-disabled="true">Enter a purchase price to continue to the full planner</span>`;
      return `
        <article class="evidence-card">
          <header>
            <p class="candidate-label">Candidate ${index + 1}</p>
            <h3>${escapeHTML(project.selectionLabel)}</h3>
            <p>${escapeHTML(project.street || "Street unavailable")} · ${escapeHTML(project.districtLabel)} · ${escapeHTML(project.tenure || "Tenure unavailable")}</p>
          </header>
          <div class="entry-evidence">
            <span>${escapeHTML(entryLabel)}</span>
            <strong>${formatMoney(analysis.entryPrice)}</strong>
            <small>${analysis.entrySource === "override" && cohort.price.median !== null ? `Observed median ${formatMoney(cohort.price.median)}` : "Descriptive transaction evidence, not a valuation"}</small>
          </div>
          <dl class="evidence-metrics">
            <div><dt>Matching cohort</dt><dd>n=${formatNumber(cohort.n)}</dd><small class="${sample.className}">${escapeHTML(sample.label)}</small></div>
            <div><dt>Observed price IQR</dt><dd>${formatRange(cohort.price.q1, cohort.price.q3, formatMoney)}</dd><small>Median ${formatMoney(cohort.price.median)}</small></div>
            <div><dt>Observed PSF IQR</dt><dd>${formatRange(cohort.psf.q1, cohort.psf.q3, formatPSF)}</dd><small>Median ${formatPSF(cohort.psf.median)}</small></div>
            <div><dt>Recorded resale flow</dt><dd>${formatNumber(cohort.trailing12)} / ${formatNumber(cohort.trailing24)}</dd><small>Last 12 / 24 complete months · proxy</small></div>
            <div><dt>Recorded resale cadence</dt><dd>${formatMonthGap(cohort.medianMonthGap)}</dd><small>Same-size Resale proxy · ${formatNumber(cohort.activeMonths)} active months · latest active resale month ${latestResaleMonthSummary(cohort)}</small></div>
            <div><dt>Access evidence</dt><dd>${escapeHTML(station.primary)}</dd><small>${escapeHTML(station.secondary)}</small></div>
            <div><dt>Primary-school radius</dt><dd>${escapeHTML(schools.primary)}</dd><small>${escapeHTML(schools.secondary)}</small></div>
            <div><dt>Canonical coverage</dt><dd>${formatNumber(analysis.canonicalCount)} records</dd><small>${analysis.partialExcluded ? `${formatNumber(analysis.partialExcluded)} partial-month record${analysis.partialExcluded === 1 ? "" : "s"} excluded` : "Partial month excluded by period boundary"}</small></div>
          </dl>
          ${cohort.n === 0 ? `<p class="evidence-warning">No ${escapeHTML(displaySaleState(state.saleState).toLocaleLowerCase("en-SG"))} transaction matched this size band. A manual entry price can model a scenario, but it does not create market evidence.</p>` : ""}
          ${state.saleState === "all" ? `<p class="evidence-warning">“All sale states” mixes developer, sub-sale and resale observations. Read the median as a transaction-mix description only.</p>` : ""}
          <footer>${planLink}</footer>
        </article>`;
    }

    function renderOutcomeMatrix(analyses, holdYears) {
      const rows = [
        ["Effective entry price", "Override or observed cohort median", analysis => formatMoney(analysis.entryPrice)],
        ["Projected sale price", `${formatPercent(state.annualGrowth)} p.a. assumption`, analysis => formatMoney(analysis.outcome?.projectedSalePrice)],
        ["Gross price change", "Projected sale less entry price", analysis => formatSignedMoney(analysis.outcome?.grossGain)],
        ["Selling allowance", `${formatPercent(state.sellingRate)} of projected sale`, analysis => formatNegativeMoney(analysis.outcome?.sellingAllowance)],
        ["Other sale costs", "User assumption", analysis => formatNegativeMoney(analysis.outcome?.saleCosts)],
        ["Scenario proceeds before financing / CPF / SSD", "Sale price less selling allowance and other sale costs; SSD is not deducted", analysis => formatMoney(analysis.outcome?.netBeforeFinancingCPF)],
        ["Scenario value change before holding / financing / CPF / SSD", "Scenario proceeds less entry price; SSD is not deducted", analysis => formatSignedMoney(analysis.outcome?.netChangeBeforeHoldingCosts)],
        ["Break-even annual growth", "Covers selling allowance and other sale costs only; excludes SSD", analysis => formatPercent(analysis.breakEvenGrowth)],
      ];
      return `
        <section class="matrix-section" aria-labelledby="outcome-title">
          <div class="result-heading"><div><p class="decision-kicker">Modeled outcome</p><h2 id="outcome-title">Side-by-side sale outcome</h2></div><p>${formatYears(holdYears)} from ${formatDate(state.purchaseDate)} to ${formatDate(state.saleDate)}</p></div>
          <div class="comparison-scroll" role="region" aria-label="Side-by-side modeled sale outcome" tabindex="0">
            <table class="comparison-matrix">
              <caption>Modeled outcome under the current global assumptions</caption>
              <thead><tr><th scope="col">Measure</th>${analyses.map(analysis => `<th scope="col">${escapeHTML(analysis.project.selectionLabel)}</th>`).join("")}</tr></thead>
              <tbody>${rows.map(([label, note, formatter]) => `<tr><th scope="row"><span>${escapeHTML(label)}</span><small>${escapeHTML(note)}</small></th>${analyses.map(analysis => `<td>${analysis.error ? unknownHTML("Source error") : formatter(analysis)}</td>`).join("")}</tr>`).join("")}</tbody>
            </table>
          </div>
          <p class="matrix-caveat">This is not cash released or economic profit. It does not deduct acquisition duties, Seller’s Stamp Duty, loan principal or interest, CPF refund, property tax, maintenance, renovation, rent, vacancy or opportunity cost. Use the full loan &amp; CPF planner from each candidate card for the household-specific waterfall and replace the transferred month-only dates with exact legal dates before relying on its SSD estimate.</p>
        </section>`;
    }

    function renderScenarioMatrix(analyses) {
      const scenarios = [
        { key: "lower", label: "Lower case", growth: state.annualGrowth - 3 },
        { key: "base", label: "Base input", growth: state.annualGrowth },
        { key: "upper", label: "Upper case", growth: state.annualGrowth + 3 },
      ];
      return `
        <section class="matrix-section" aria-labelledby="scenario-title">
          <div class="result-heading"><div><p class="decision-kicker">Sensitivity, not forecast</p><h2 id="scenario-title">Growth scenario matrix</h2></div><p>Current input ± 3 percentage points</p></div>
          <div class="comparison-scroll" role="region" aria-label="Annual growth sensitivity matrix" tabindex="0">
            <table class="comparison-matrix scenario-matrix">
              <caption>Projected sale values under three user-defined growth sensitivities</caption>
              <thead><tr><th scope="col">Scenario</th>${analyses.map(analysis => `<th scope="col">${escapeHTML(analysis.project.selectionLabel)}</th>`).join("")}</tr></thead>
              <tbody>${scenarios.map(scenario => `<tr><th scope="row"><span>${escapeHTML(scenario.label)} · ${formatPercent(scenario.growth)}</span><small>Annual growth assumption</small></th>${analyses.map(analysis => {
                const result = analysis.scenarios?.find(item => item.key === scenario.key)?.outcome;
                if (analysis.error) return `<td>${unknownHTML("Source error")}</td>`;
                if (!result) return `<td>${unknownHTML("Entry price unknown")}</td>`;
                return `<td><strong>${formatMoney(result.projectedSalePrice)}</strong><small>${formatSignedMoney(result.netChangeBeforeHoldingCosts)} before holding / financing / CPF / SSD</small></td>`;
              }).join("")}</tr>`).join("")}</tbody>
            </table>
          </div>
          <p class="matrix-caveat">The ±3 percentage-point cases are mechanical sensitivities. They are not confidence intervals, predicted returns or probabilities.</p>
        </section>`;
    }

    function renderLedgers(analyses, period) {
      return `
        <section class="ledger-section" aria-labelledby="ledger-title">
          <div class="result-heading"><div><p class="decision-kicker">Audit the cohort</p><h2 id="ledger-title">Exact filtered transaction ledger</h2></div><p>${escapeHTML(period)} · source partial month excluded</p></div>
          <p class="ledger-intro">Each ledger contains the exact canonical records used for that project’s headline median: target size band and selected sale state included, incomplete backfill excluded.</p>
          <div class="ledger-list">${analyses.map(renderLedger).join("")}</div>
        </section>`;
    }

    function renderLedger(analysis) {
      const rows = analysis.cohort?.rows || [];
      const projectLabel = analysis.project.selectionLabel;
      const body = analysis.error
        ? `<p class="ledger-empty">Transaction source unavailable: ${escapeHTML(analysis.error)}</p>`
        : rows.length === 0
          ? `<p class="ledger-empty">No canonical record matched the current size band and sale state.</p>`
          : `<div class="ledger-scroll" role="region" aria-label="${escapeHTML(projectLabel)} filtered transactions" tabindex="0"><table class="ledger-table"><caption>${escapeHTML(projectLabel)} exact filtered transactions</caption><thead><tr><th scope="col">Sale month</th><th scope="col">Price</th><th scope="col">Area</th><th scope="col">PSF</th><th scope="col">Sale state</th><th scope="col">Floor band</th><th scope="col">Source</th></tr></thead><tbody>${rows.map(row => `<tr><td>${escapeHTML(formatMonth(row.saleMonth))}</td><td>${formatMoney(row.price)}</td><td>${formatNumber(Math.round(row.areaSqft))} sqft</td><td>${formatPSF(row.psf)}</td><td>${escapeHTML(row.saleType || "Unknown")}</td><td>${escapeHTML(row.floorLevel || "Unknown")}</td><td><span class="source-chip">URA private</span></td></tr>`).join("")}</tbody></table></div>`;
      return `<details class="ledger-card"><summary><span><strong>${escapeHTML(projectLabel)}</strong><small>${formatNumber(rows.length)} matching record${rows.length === 1 ? "" : "s"}</small></span><span aria-hidden="true">+</span></summary>${body}</details>`;
    }

    function buildPlannerURL(analysis) {
      if (!(analysis.entryPrice > 0)) return null;
      const url = new URL("condo_loan_timeline_planner.html", document.baseURI);
      const params = {
        from: "project-exit",
        project: analysis.project.selectionLabel,
        purchasePrice: roundForURL(analysis.entryPrice),
        purchaseDate: `${state.purchaseDate}-01`,
        saleDate: `${state.saleDate}-01`,
        datePrecision: "month",
        annualGrowth: roundForURL(state.annualGrowth),
        sellingRate: roundForURL(state.sellingRate),
        saleCosts: roundForURL(state.saleCosts),
        areaSqft: roundForURL(state.targetArea),
      };
      Object.entries(params).forEach(([key, value]) => url.searchParams.set(key, String(value)));
      return url.href;
    }

    function syncStateToURL(mode) {
      const url = new URL(window.location.href);
      URL_KEYS.forEach(key => url.searchParams.delete(key));
      state.selections.forEach(selection => {
        url.searchParams.append("p", selection.id);
        url.searchParams.append("price", selection.price === null ? "" : roundForURL(selection.price));
      });
      url.searchParams.set("areaSqft", roundForURL(state.targetArea));
      url.searchParams.set("tolerancePct", roundForURL(state.tolerance));
      url.searchParams.set("saleState", state.saleState);
      url.searchParams.set("purchaseDate", state.purchaseDate);
      url.searchParams.set("saleDate", state.saleDate);
      url.searchParams.set("annualGrowth", roundForURL(state.annualGrowth));
      url.searchParams.set("sellingRate", roundForURL(state.sellingRate));
      url.searchParams.set("saleCosts", roundForURL(state.saleCosts));
      const next = `${url.pathname}${url.search}${url.hash}`;
      if (mode === "push") window.history.pushState({}, "", next);
      else window.history.replaceState({}, "", next);
    }

    function enhanceResultRegions(analyses = []) {
      elements.results.querySelectorAll("details.ledger-card").forEach(details => {
        details.addEventListener("toggle", () => {
          const marker = details.querySelector("summary > span:last-child");
          if (marker) marker.textContent = details.open ? "−" : "+";
        });
      });
      elements.results.querySelectorAll("[data-retry-transaction-data]").forEach(button => {
        button.addEventListener("click", () => {
          analyses.filter(analysis => analysis.error).forEach(analysis => {
            if (analysis.project?.transactionShard) {
              window.SGEstateData?.invalidate?.(analysis.project.transactionShard, {
                revision: datasetRevision,
              });
            }
          });
          void refresh({ syncURL: false });
        });
      });
    }

    function setLoading(loading) {
      elements.app.setAttribute("aria-busy", String(loading));
      elements.app.classList.toggle("is-loading", loading);
      elements.add.disabled = loading || state.selections.length >= maximumProjects;
    }

    function setStatus(message, isError = false) {
      elements.status.textContent = message;
      elements.status.classList.toggle("status-error", isError);
    }

    function showFormError(message) {
      elements.formError.hidden = false;
      elements.formError.textContent = message;
      elements.formError.setAttribute("role", "alert");
    }

    function clearFormError() {
      elements.formError.hidden = true;
      elements.formError.textContent = "";
    }

    function loadingHTML() {
      return `<div class="decision-loading" role="status"><span aria-hidden="true"></span><div><strong>Loading selected transaction evidence…</strong><p>Only the transaction shards needed by these candidates are requested.</p></div></div>`;
    }

    function invalidResultsHTML() {
      return `<div class="decision-error decision-results-withheld"><p class="decision-kicker">Results withheld</p><h2>Correct the inputs to refresh the comparison.</h2><p>Previously calculated figures are hidden so they cannot be mistaken for results under the invalid assumptions above.</p></div>`;
    }

    function revisionFailureHTML() {
      return `<div class="decision-error decision-results-withheld" role="alert"><p class="decision-kicker">Reload required</p><h2>Transaction results are withheld.</h2><p>${escapeHTML(REVISION_MISMATCH_MESSAGE)} No cohort, zero-row statistic, or modeled outcome is shown.</p><button type="button" data-reload-transaction-data>Reload page</button></div>`;
    }

    function normaliseProject(project) {
      const transactions = project.transactions || {};
      return {
        ...project,
        id: String(project.id),
        project: stringValue(project.name) || stringValue(project.project) || stringValue(project.selection_label) || String(project.id),
        selectionLabel: stringValue(project.selection_label) || stringValue(project.name) || stringValue(project.project) || String(project.id),
        street: stringValue(project.street),
        districtLabel: districtLabel(project.district),
        planningArea: stringValue(project.planning_area),
        tenure: stringValue(project.tenure),
        transactionShard: stringValue(
          transactions.shard || transactions.transaction_shard || transactions.path || project.transaction_shard
        ),
      };
    }

    function stationSummary(project) {
      const station = project.station || {};
      const display = stringValue(project.station_display || station.display || station.station_display);
      const name = stringValue(station.name || station.station || project.station_name);
      const code = stringValue(station.code || station.station_code || project.station_code);
      const distance = finiteNumber(station.distance_m ?? station.station_distance_m ?? project.station_distance_m);
      const line = stringValue(station.line_short || station.line || project.line_short);
      const status = stringValue(project.station_status || station.status);
      const locationSource = stringValue(project.location_source || station.location_source);
      if (!display && !name) return { primary: "Unknown", secondary: "Station evidence unavailable" };
      const primary = display || [name, code].filter(Boolean).join(" · ");
      if (locationSource !== "project_geocode") {
        const provenance = locationSource === "centroid_proxy"
          ? "Estate-centroid proxy—not project distance"
          : "Location provenance unavailable—distance not treated as project access";
        return { primary, secondary: [provenance, line, status].filter(Boolean).join(" · ") };
      }
      const details = [distance === null ? null : `${formatNumber(Math.round(distance))} m straight-line project-point distance`, line, status].filter(Boolean);
      return { primary, secondary: details.join(" · ") || "Distance unavailable" };
    }

    function schoolSummary(project) {
      const schools = project.schools || {};
      const schoolSource = stringValue(project.school_metrics_source || schools.source);
      if (schoolSource && schoolSource !== "project_geocode") {
        return { primary: "Unknown", secondary: "Project-point school-radius evidence unavailable" };
      }
      const directCount = finiteNumber(
        project.primary_1km_count ?? schools.primary_1km_count ?? schools.within_1km_count ?? schools.primary_within_1km_count
      );
      const flatSchools = stringValue(project.primary_1km_schools);
      const schoolList = (flatSchools
        ? flatSchools.split(";")
        : arrayValue(schools.primary_1km_schools || schools.within_1km || schools.primary_schools))
        .map(stringValue)
        .filter(Boolean);
      const count = directCount ?? (schoolList.length ? schoolList.length : null);
      if (count === null) return { primary: "Unknown", secondary: "Project-point school-radius evidence unavailable" };
      const primary = `${formatNumber(count)} school${count === 1 ? "" : "s"} in 1 km straight-line project-point screen`;
      const evidence = schoolList.length
        ? schoolList.slice(0, 2).join(" · ") + (schoolList.length > 2 ? ` · +${schoolList.length - 2} more` : "")
        : "No school names in the project-point screen";
      const secondary = `${evidence} · Not official P1 home–school distance or admissions eligibility; verify with current OneMap SchoolQuery`;
      return { primary, secondary };
    }

    function sampleAssessment(n) {
      if (n === 0) return { label: "No matching evidence", className: "sample-critical" };
      if (n < 5) return { label: "Very thin · median highly unstable", className: "sample-critical" };
      if (n < 20) return { label: "Small descriptive sample", className: "sample-warning" };
      if (n < 100) return { label: "Descriptive only · n<100", className: "sample-warning" };
      return { label: "Broader observed sample", className: "sample-ok" };
    }

    function distribution(values) {
      const sorted = values.map(Number).filter(Number.isFinite).sort((a, b) => a - b);
      return {
        q1: quantile(sorted, 0.25),
        median: quantile(sorted, 0.5),
        q3: quantile(sorted, 0.75),
      };
    }

    function quantile(sorted, probability) {
      if (!sorted.length) return null;
      if (sorted.length === 1) return sorted[0];
      const position = (sorted.length - 1) * probability;
      const lower = Math.floor(position);
      const remainder = position - lower;
      return sorted[lower + 1] === undefined
        ? sorted[lower]
        : sorted[lower] + remainder * (sorted[lower + 1] - sorted[lower]);
    }

    function setSelectValue(select, desired) {
      const option = Array.from(select.options).find(item => normaliseSaleState(item.value) === desired);
      if (option) select.value = option.value;
    }

    function normaliseSaleState(value) {
      const normalised = String(value || "").trim().toLocaleLowerCase("en-SG").replaceAll("_", " ");
      return {
        "resale": "Resale",
        "sub sale": "Sub Sale",
        "subsale": "Sub Sale",
        "new sale": "New Sale",
        "new": "New Sale",
        "all": "all",
        "all sale states": "all",
      }[normalised] || "";
    }

    function displaySaleState(value) {
      return value === "all" ? "All sale states" : value;
    }

    function uniqueValidProjectIds(ids) {
      return [...new Set(ids)].filter(id => projectById.has(id));
    }

    function normaliseProjectLabel(value) {
      return stringValue(value).toLocaleLowerCase("en-SG");
    }

    function projectFromPicker(value) {
      const text = stringValue(value);
      return projectByLabel.get(normaliseProjectLabel(text)) || projectById.get(text) || null;
    }

    function enumValue(values, encoded) {
      if (encoded === null || encoded === undefined || encoded === "") return "";
      if (typeof encoded === "string") return encoded;
      return Array.isArray(values) && Number.isInteger(Number(encoded))
        ? values[Number(encoded)] ?? ""
        : "";
    }

    function cloneState(source) {
      return {
        ...source,
        selections: source.selections.map(selection => ({ ...selection })),
      };
    }

    function arrayValue(value) {
      return Array.isArray(value) ? value : [];
    }

    function stringValue(value) {
      return value === null || value === undefined ? "" : String(value).trim();
    }

    function finiteNumber(value) {
      if (value === null || value === undefined || value === "") return null;
      const number = Number(value);
      return Number.isFinite(number) ? number : null;
    }

    function integerValue(value) {
      const number = finiteNumber(value);
      return number === null ? null : Math.trunc(number);
    }

    function positiveNumber(value, fallback) {
      const number = finiteNumber(value);
      return number !== null && number > 0 ? number : fallback;
    }

    function nonNegativeNumber(value, fallback) {
      const number = finiteNumber(value);
      return number !== null && number >= 0 ? number : fallback;
    }

    function clamp(value, minimum, maximum) {
      return Math.min(maximum, Math.max(minimum, value));
    }

    function validMonth(value) {
      return /^\d{4}-(0[1-9]|1[0-2])$/.test(String(value || ""));
    }

    function normaliseInputMonth(value) {
      const text = stringValue(value);
      if (validMonth(text)) return text;
      return /^\d{4}-(0[1-9]|1[0-2])-([0-2]\d|3[01])$/.test(text) ? text.slice(0, 7) : "";
    }

    function monthIndex(value) {
      const [year, month] = value.split("-").map(Number);
      return year * 12 + month - 1;
    }

    function addMonths(value, offset) {
      const index = monthIndex(value) + offset;
      const year = Math.floor(index / 12);
      const month = index % 12 + 1;
      return `${year}-${String(month).padStart(2, "0")}`;
    }

    function compareMonth(left, right) {
      return monthIndex(left) - monthIndex(right);
    }

    function dateValue(value) {
      return validMonth(value) ? Date.parse(`${value}-01T00:00:00Z`) : NaN;
    }

    function yearDifference(start, end) {
      return (dateValue(end) - dateValue(start)) / (365.2425 * 24 * 60 * 60 * 1000);
    }

    function districtLabel(value) {
      const text = stringValue(value);
      if (!text) return "District unavailable";
      return /^D/i.test(text) ? text.toLocaleUpperCase("en-SG") : `D${text.padStart(2, "0")}`;
    }

    function displayInputNumber(value) {
      return Number.isInteger(Number(value)) ? String(Number(value)) : String(Number(value).toFixed(2)).replace(/\.00$/, "");
    }

    function roundForURL(value) {
      return Math.round(Number(value) * 100) / 100;
    }

    function formatNumber(value) {
      return Number(value).toLocaleString("en-SG", { maximumFractionDigits: 1 });
    }

    function formatMoney(value) {
      const number = finiteNumber(value);
      return number === null
        ? unknownHTML()
        : `S$${Math.round(number).toLocaleString("en-SG")}`;
    }

    function formatSignedMoney(value) {
      const number = finiteNumber(value);
      if (number === null) return unknownHTML();
      return `${number >= 0 ? "+" : "−"}S$${Math.abs(Math.round(number)).toLocaleString("en-SG")}`;
    }

    function formatNegativeMoney(value) {
      const number = finiteNumber(value);
      return number === null ? unknownHTML() : `−S$${Math.abs(Math.round(number)).toLocaleString("en-SG")}`;
    }

    function formatPSF(value) {
      const number = finiteNumber(value);
      return number === null ? unknownHTML() : `S$${Math.round(number).toLocaleString("en-SG")} psf`;
    }

    function formatPercent(value) {
      const number = finiteNumber(value);
      if (number === null) return unknownHTML();
      const digits = Math.abs(number) < 10 && !Number.isInteger(number) ? 2 : 1;
      return `${number > 0 ? "+" : ""}${number.toLocaleString("en-SG", { minimumFractionDigits: 0, maximumFractionDigits: digits })}%`;
    }

    function formatYears(value) {
      return `${value.toLocaleString("en-SG", { minimumFractionDigits: 1, maximumFractionDigits: 2 })} years`;
    }

    function formatMonth(value) {
      if (!validMonth(value)) return "Unknown month";
      const [year, month] = value.split("-").map(Number);
      return new Intl.DateTimeFormat("en-SG", { month: "short", year: "numeric", timeZone: "UTC" })
        .format(new Date(Date.UTC(year, month - 1, 1)));
    }

    function formatDate(value) {
      if (!validMonth(value)) return "unknown month";
      return formatMonth(value);
    }

    function cohortAreaBounds() {
      return {
        lower: state.targetArea * (1 - state.tolerance / 100),
        upper: state.targetArea * (1 + state.tolerance / 100),
      };
    }

    function latestResaleMonthSummary(cohort) {
      if (!cohort.latestMonth) return "unknown";
      return `${escapeHTML(formatMonth(cohort.latestMonth))} · month median ${formatMoney(cohort.latestPrice)} · ${formatPSF(cohort.latestPsf)}`;
    }

    function formatMonthGap(value) {
      const number = finiteNumber(value);
      if (number === null) return "Unknown";
      return `${number.toLocaleString("en-SG", { maximumFractionDigits: 1 })} month${number === 1 ? "" : "s"}`;
    }

    function formatRange(lower, upper, formatter) {
      if (lower === null || upper === null) return unknownHTML();
      return `${formatter(lower)}–${formatter(upper)}`;
    }

    function unknownHTML(label = "Unknown") {
      return `<span class="unknown-value">${escapeHTML(label)}</span>`;
    }

    function escapeHTML(value) {
      return String(value ?? "").replace(/[&<>"']/g, character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[character]);
    }
  });
})();
