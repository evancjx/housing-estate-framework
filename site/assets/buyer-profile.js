(() => {
  "use strict";

  const rows = JSON.parse(document.getElementById("buyer-profile-data").textContent);
  const profiles = JSON.parse(document.getElementById("buyer-profile-summary").textContent);
  const profileMap = new Map(profiles.map((profile) => [profile.profile_id, profile]));
  const defaultProfile = profiles[0]?.profile_id || "";

  const elements = {
    profileList: document.getElementById("profile-choice-list"),
    scenarioDetail: document.getElementById("scenario-detail"),
    search: document.getElementById("estate-search"),
    visibleCount: document.getElementById("visible-count"),
    visibleCopy: document.getElementById("visible-copy"),
    segmentList: document.getElementById("segment-choice-list"),
    tableHead: document.getElementById("buyer-profile-table-head"),
    tableBody: document.getElementById("buyer-profile-table-body"),
    tableGuidance: document.getElementById("table-guidance"),
    sortStatus: document.getElementById("sort-status"),
    caveat: document.getElementById("view-caveat"),
    empty: document.getElementById("empty-state"),
    tableWrap: document.querySelector(".tbl-wrap"),
  };

  const state = {
    profile: defaultProfile,
    query: "",
    status: "eligible",
    segment: "all",
    view: "overview",
    sort: "rank",
    direction: "asc",
  };
  let profilesInitialised = false;
  let renderedScenarioProfile = null;
  let renderedSegmentProfile = null;

  const VIEW_COLUMNS = {
    overview: ["estate", "segment", "status", "rank", "score", "liveability", "value", "coverage"],
    screening: ["estate", "segment", "status", "rank", "reasons", "coverage"],
    household: ["estate", "segment", "status", "rank", "liveability", "employment", "lease", "provision", "life_path"],
    value: ["estate", "segment", "status", "rank", "value", "value_sample", "value_basis", "coverage"],
    evidence: ["estate", "segment", "status", "rank", "coverage", "provision", "value_sample", "value_basis", "reasons"],
    all: ["estate", "segment", "status", "rank", "score", "liveability", "employment", "lease", "provision", "life_path", "value", "value_sample", "value_basis", "coverage", "reasons"],
  };

  const VIEW_CAVEATS = {
    overview: "Overview shows the shortlist outcome while keeping household fit and tenure-specific Value visibly separate.",
    screening: "Eligibility is a hard-filter result for this brief. A filtered estate may suit a different household scenario.",
    household: "Liveability uses the selected persona and horizon. Employment remains current/T0; Lease applies only to HDB.",
    value: "Value evidence stays inside the selected tenure. Samples below 100 are bands only, and proxy rows are not independent estate evidence.",
    evidence: "Coverage shows how much declared model weight had data before renormalisation. Private Provision is privately weighted; measured-only rows remain flagged.",
    all: "All evidence is intentionally wide. Scores and ranks remain conditional on this one scenario and tenure segment.",
  };

  const GROUPS = {
    screening: { label: "Screening", className: "group-screening" },
    profile: { label: "Scenario-local result", className: "group-profile" },
    household: { label: "Household fit", className: "group-liveability" },
    value: { label: "Tenure Value", className: "group-value" },
    evidence: { label: "Evidence diagnostics", className: "group-evidence" },
  };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[character]));
  }

  function titleCase(value) {
    return String(value || "")
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase());
  }

  function formatNumber(value, digits = 2) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits) : "—";
  }

  function formatInteger(value) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.round(number).toLocaleString("en-SG") : "—";
  }

  function signed(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return `${number > 0 ? "+" : ""}${number.toFixed(2)}`;
  }

  function segmentLabel(value) {
    return ({ hdb: "HDB", condo: "Condo", landed: "Landed", private: "Private" })[value] || titleCase(value);
  }

  function horizonLabel(value) {
    return ({ T0: "T0 · current", T5: "T5 · five-year", T15: "T15 · fifteen-year" })[value] || value;
  }

  function bandClass(value) {
    const normalized = String(value || "").trim();
    if (normalized === "B+") return "band-Bp";
    if (["A", "B", "C", "D", "F"].includes(normalized)) return `band-${normalized}`;
    return "band-NR";
  }

  function bandHTML(value) {
    const normalized = String(value || "").trim();
    const labels = {
      "": "Not available",
      "N/A": "Not applicable",
      "N/R": "N/R",
      no_data: "No data",
      not_covered: "Not covered",
    };
    const label = Object.prototype.hasOwnProperty.call(labels, normalized) ? labels[normalized] : normalized;
    return `<span class="band ${bandClass(normalized)}">${esc(label)}</span>`;
  }

  function notResidential(row) {
    return row.archetype === "X";
  }

  function notRatedHTML() {
    return '<span class="muted-value">N/R</span>';
  }

  function cellStack(primary, secondary = "") {
    return `<span class="cell-stack"><span>${primary}</span>${secondary ? `<span class="cell-sub">${secondary}</span>` : ""}</span>`;
  }

  function basisCopy(value, tenure) {
    const basis = String(value || "");
    if (basis === "direct") return '<span class="basis-direct">Direct estate evidence</span>';
    if (basis.startsWith("proxy_from:")) {
      return `<span class="basis-proxy">Proxy from ${esc(titleCase(basis.slice(11)))}</span>`;
    }
    if (basis === "no_hdb_segment") {
      return `<span class="basis-missing">${tenure === "hdb" ? "No matching HDB segment" : "No matching tenure-segment evidence"}</span>`;
    }
    if (basis === "not_covered") return '<span class="basis-missing">Segment not covered</span>';
    if (basis === "N/R") return notRatedHTML();
    return '<span class="basis-missing">No segment evidence</span>';
  }

  function humanReason(token) {
    const [name, value = ""] = String(token).split(":", 2);
    const labels = {
      excluded_archetype: `Archetype ${value || "excluded"} is outside the residential model`,
      archetype_not_allowed: `Archetype ${value || "unknown"} is outside this brief`,
      measured_only: "Measured-only Provision excluded",
      liveability_below: `Household-fit band below ${value}`,
      value_below: `Value band below ${value}`,
      employment_below: `Employment band below ${value}`,
      lease_below: `HDB lease band below ${value}`,
      provision_below: `Provision below ${value}`,
      value_n_below: `Value sample below ${value}`,
      value_not_direct: "Direct Value evidence required",
      value_basis_not_allowed: "Value evidence basis not allowed",
      D_T0_below: `Current disruption multiplier below ${value}`,
      D_T5_below: `T5 disruption multiplier below ${value}`,
      D_T15_below: `T15 disruption multiplier below ${value}`,
    };
    return labels[name] || titleCase(token);
  }

  function reasonsHTML(row) {
    if (notResidential(row)) {
      return '<span class="reason-list"><span class="reason-badge">Not a residential construct</span></span>';
    }
    const reasons = String(row.filter_reasons || "").split(";").filter(Boolean);
    if (!reasons.length) {
      return '<span class="reason-list"><span class="reason-badge reason-pass">All hard filters passed</span></span>';
    }
    return `<span class="reason-list">${reasons.map((reason) => `<span class="reason-badge">${esc(humanReason(reason))}</span>`).join("")}</span>`;
  }

  function coverageHTML(row) {
    if (notResidential(row)) return notRatedHTML();
    const coverage = Number(row.soft_weight_covered);
    if (!Number.isFinite(coverage)) return '<span class="muted-value">Unavailable</span>';
    const percent = Math.round(coverage * 100);
    const badge = `<span class="coverage-badge ${percent < 100 ? "coverage-partial" : ""}">${percent}% weight covered</span>`;
    const notes = [];
    if (percent < 100) notes.push("remaining weights renormalised");
    if (row.measured_only) notes.push("Provision uses measured inputs only");
    return cellStack(badge, esc(notes.join(" · ")));
  }

  function valueHTML(row) {
    if (notResidential(row)) return notRatedHTML();
    const band = bandHTML(row.value_band);
    if (row.value_reporting === "decimal" && row.value_score !== null) {
      return cellStack(band, `score ${formatNumber(row.value_score)}`);
    }
    if (row.value_reporting === "band_only") {
      return cellStack(band, '<span class="band-only">band only</span>');
    }
    return cellStack(band, "no reportable decimal");
  }

  function valueSampleHTML(row) {
    if (notResidential(row)) return notRatedHTML();
    if (row.value_n === null || row.value_n === undefined) return '<span class="muted-value">No sample</span>';
    const count = `n=${formatInteger(row.value_n)}`;
    return row.value_reporting === "band_only"
      ? cellStack(`<span class="sample-small">${count}</span>`, "below 100 · band only")
      : cellStack(count, row.value_reporting === "decimal" ? "decimal reporting allowed" : "evidence unavailable");
  }

  function metricBandHTML(row, bandKey, note) {
    if (notResidential(row)) return notRatedHTML();
    return cellStack(bandHTML(row[bandKey]), esc(note));
  }

  function provisionHTML(row) {
    if (notResidential(row)) return notRatedHTML();
    if (row.tenure === "hdb") {
      return cellStack(bandHTML(row.provision_band), "public Provision · ±0.3 noise floor");
    }
    if (row.provision_score === null || row.provision_score === undefined) {
      return '<span class="muted-value">No private Provision</span>';
    }
    return cellStack(`<strong>${formatNumber(row.provision_score)}</strong>`, "private-weighted · no public band");
  }

  function lifePathHTML(row) {
    if (notResidential(row)) return notRatedHTML();
    if (!row.life_path || row.life_path_end_score === null) return '<span class="muted-value">Not configured</span>';
    return cellStack(
      esc(titleCase(row.life_path)),
      `T0→T5 end ${formatNumber(row.life_path_end_score)} · Δ ${signed(row.life_path_delta)}`,
    );
  }

  const COLUMNS = [
    {
      id: "estate", label: "Estate", group: "screening", sortable: true, direction: "asc",
      headerClass: "estate-column", cellClass: "estate-cell",
      value: (row) => row.estate,
      render: (row) => `<strong>${esc(row.estate)}</strong><span class="cell-sub">Archetype ${esc(row.archetype || "?")}</span>`,
    },
    {
      id: "segment", label: "Tenure", group: "screening", sortable: true, direction: "asc",
      value: (row) => row.tenure,
      render: (row) => `<span class="segment-badge">${esc(segmentLabel(row.tenure))}</span>`,
    },
    {
      id: "status", label: "Result", group: "screening", sortable: true, direction: "asc",
      value: (row) => row.eligible ? 0 : 1,
      render: (row) => `<span class="eligibility-badge ${row.eligible ? "eligibility-yes" : "eligibility-no"}">${row.eligible ? "Shortlisted" : "Filtered"}</span>`,
    },
    {
      id: "rank", label: "Local rank", group: "profile", sortable: true, direction: "asc",
      value: (row) => row.rank,
      render: (row) => notResidential(row) ? notRatedHTML() : row.rank ? `<span class="rank-badge">#${row.rank}</span>` : row.score_reporting === "withheld_value_sample" ? '<span class="filtered-copy">Withheld · Value n&lt;100</span>' : '<span class="filtered-copy">Not ranked</span>',
    },
    {
      id: "score", label: "Profile score", group: "profile", sortable: true, direction: "desc",
      value: (row) => row.profile_score,
      render: (row) => notResidential(row) ? notRatedHTML() : row.profile_score !== null ? cellStack(`<span class="profile-score">${formatNumber(row.profile_score)}</span>`, "experimental scenario diagnostic") : row.score_reporting === "withheld_value_sample" ? '<span class="filtered-copy">Withheld · thin Value sample</span>' : '<span class="filtered-copy">Hidden after hard-filter failure</span>',
    },
    {
      id: "liveability", label: "Liveability", group: "household", sortable: true, direction: "desc",
      value: (row) => bandOrder(row.liveability_band),
      render: (row) => metricBandHTML(row, "liveability_band", `${row.persona} · ${horizonLabel(row.horizon)}`),
    },
    {
      id: "employment", label: "Employment", group: "household", sortable: true, direction: "desc",
      value: (row) => bandOrder(row.employment_band),
      render: (row) => metricBandHTML(row, "employment_band", "current / T0 access"),
    },
    {
      id: "lease", label: "Lease", group: "household", sortable: true, direction: "desc",
      value: (row) => row.tenure === "hdb" ? bandOrder(row.lease_band) : null,
      render: (row) => notResidential(row) ? notRatedHTML() : row.tenure === "hdb" ? metricBandHTML(row, "lease_band", "HDB lease-risk only") : '<span class="muted-value">HDB only</span>',
    },
    {
      id: "provision", label: "Provision", group: "household", sortable: true, direction: "desc",
      value: (row) => row.provision_score,
      render: provisionHTML,
    },
    {
      id: "life_path", label: "Life path", group: "household", sortable: true, direction: "desc",
      value: (row) => row.life_path_end_score,
      render: lifePathHTML,
    },
    {
      id: "value", label: "Value", group: "value", sortable: true, direction: "desc",
      value: (row) => bandOrder(row.value_band),
      render: valueHTML,
    },
    {
      id: "value_sample", label: "Sample", group: "value", sortable: true, direction: "desc",
      value: (row) => row.value_n,
      render: valueSampleHTML,
    },
    {
      id: "value_basis", label: "Basis", group: "value", sortable: true, direction: "asc",
      value: (row) => row.value_basis,
      render: (row) => notResidential(row) ? notRatedHTML() : basisCopy(row.value_basis, row.tenure),
    },
    {
      id: "coverage", label: "Weight coverage", group: "evidence", sortable: true, direction: "desc",
      value: (row) => row.soft_weight_covered,
      render: coverageHTML,
    },
    {
      id: "reasons", label: "Screening reasons", group: "evidence", sortable: false,
      cellClass: "notes-cell", value: () => null, render: reasonsHTML,
    },
  ];
  const columnMap = new Map(COLUMNS.map((column) => [column.id, column]));

  function bandOrder(value) {
    return ({ A: 6, "B+": 5, B: 4, C: 3, D: 2, F: 1 })[value] ?? null;
  }

  function currentColumns() {
    return visibleColumnIds().map((id) => columnMap.get(id));
  }

  function visibleColumnIds() {
    const ids = [...VIEW_COLUMNS[state.view]];
    if (availableSegments().length > 1 && state.segment === "all") {
      return ids.filter((id) => id !== "rank" && id !== "score");
    }
    return ids;
  }

  function profileRows() {
    return rows.filter((row) => row.profile_id === state.profile);
  }

  function availableSegments() {
    return [...new Set(profileRows().map((row) => row.tenure))];
  }

  function matches(row) {
    if (row.profile_id !== state.profile) return false;
    if (state.segment !== "all" && row.tenure !== state.segment) return false;
    if (state.status === "eligible" && !row.eligible) return false;
    if (state.status === "filtered" && row.eligible) return false;
    if (state.query && !row.estate.toLowerCase().includes(state.query.toLowerCase())) return false;
    return true;
  }

  function sortedRows() {
    const column = columnMap.get(state.sort) || columnMap.get("rank");
    const factor = state.direction === "asc" ? 1 : -1;
    return rows.filter(matches).sort((left, right) => {
      const a = column.value(left);
      const b = column.value(right);
      const aMissing = a === null || a === undefined || a === "";
      const bMissing = b === null || b === undefined || b === "";
      if (aMissing !== bMissing) return aMissing ? 1 : -1;
      if (!aMissing && !bMissing) {
        if (typeof a === "number" && typeof b === "number" && a !== b) return (a - b) * factor;
        const comparison = String(a).localeCompare(String(b), "en", { numeric: true, sensitivity: "base" });
        if (comparison) return comparison * factor;
      }
      const estateComparison = left.estate.localeCompare(right.estate);
      return estateComparison || left.tenure.localeCompare(right.tenure);
    });
  }

  function renderProfiles() {
    if (!profilesInitialised) {
      elements.profileList.innerHTML = profiles.map((profile) => `
      <button type="button" class="profile-choice-button" data-profile="${esc(profile.profile_id)}" aria-pressed="false">
        <strong>${esc(profile.label)}</strong>
        <span>${esc(profile.persona)} · ${esc(horizonLabel(profile.horizon))}</span>
        <span>${profile.eligible} of ${profile.rows} shortlisted</span>
      </button>
      `).join("");
      profilesInitialised = true;
    }
    updateButtonState("[data-profile]", "profile", state.profile);
  }

  function gateLabel(key, value) {
    const label = ({
      exclude_archetypes: "Exclude archetype",
      allowed_archetypes: "Allowed archetype",
      exclude_measured_only: "Exclude measured-only",
      min_liveability_band: "Liveability ≥",
      min_value_band: "Value ≥",
      min_employment_band: "Employment ≥",
      min_lease_band: "Lease ≥",
      min_provision_band: "Provision ≥",
      min_value_n: "Value sample ≥",
      require_direct_value: "Direct Value required",
      require_value_basis: "Required basis",
      min_D_T0: "Current D ≥",
      min_D_T5: "T5 D ≥",
      min_D_T15: "T15 D ≥",
    })[key] || titleCase(key);
    const formatted = Array.isArray(value) ? value.join(", ") : typeof value === "boolean" ? (value ? "yes" : "no") : value;
    return `${label} ${formatted}`;
  }

  function renderScenario() {
    if (renderedScenarioProfile === state.profile) return;
    renderedScenarioProfile = state.profile;
    const profile = profileMap.get(state.profile);
    if (!profile) {
      elements.scenarioDetail.innerHTML = "";
      return;
    }
    const gates = Object.entries(profile.hard_filters || {}).filter(([, value]) => value !== false && value !== "" && value !== null);
    const weights = Object.entries(profile.soft_weights || {}).filter(([, value]) => Number(value) > 0);
    const caveats = [];
    if (profile.partial_coverage) caveats.push(`${profile.partial_coverage} shortlisted rows use partial weight coverage`);
    if (profile.band_only_value) caveats.push(`${profile.band_only_value} rows have band-only Value evidence`);
    elements.scenarioDetail.innerHTML = `
      <div class="scenario-copy">
        <p class="eyebrow">Active scenario</p>
        <h3>${esc(profile.label)}</h3>
        <p>${esc(profile.description || "A committed buyer scenario evaluated against current estate outputs.")}</p>
        <div class="scenario-facts">
          <span class="scenario-fact">${esc(profile.persona)}</span>
          <span class="scenario-fact">${esc(horizonLabel(profile.horizon))}</span>
          <span class="scenario-fact">${esc(profile.tenures.map(segmentLabel).join(" + "))}</span>
          <span class="scenario-fact">Life path · ${esc(titleCase(profile.life_path))}</span>
          <span class="scenario-fact">${profile.eligible} / ${profile.rows} shortlisted</span>
          <span class="scenario-fact">${profile.ranked} reportable local ranks</span>
          ${caveats.map((item) => `<span class="scenario-fact">${esc(item)}</span>`).join("")}
        </div>
      </div>
      <div class="scenario-rules">
        <div class="rule-line"><b>Hard gates</b><div class="rule-chips">${gates.map(([key, value]) => `<span class="gate-chip">${esc(gateLabel(key, value))}</span>`).join("") || '<span class="gate-chip">No additional gates</span>'}</div></div>
        <div class="rule-line"><b>Declared weight overrides</b><div class="rule-chips">${weights.map(([key, value]) => `<span class="weight-chip">${esc(titleCase(key))} ${Math.round(Number(value) * 100)}%</span>`).join("") || '<span class="weight-chip">Model defaults</span>'}</div></div>
      </div>
    `;
  }

  function renderSegments() {
    const segments = availableSegments();
    if (state.segment !== "all" && !segments.includes(state.segment)) state.segment = "all";
    if (renderedSegmentProfile !== state.profile) {
      const options = segments.length === 1
        ? [{ id: "all", label: segmentLabel(segments[0]) }]
        : [{ id: "all", label: "All segments" }, ...segments.map((segment) => ({ id: segment, label: segmentLabel(segment) }))];
      elements.segmentList.innerHTML = options.map((option) => `
        <button type="button" class="filter-button" data-segment="${esc(option.id)}" aria-pressed="false">${esc(option.label)}</button>
      `).join("");
      renderedSegmentProfile = state.profile;
    }
    updateButtonState("#segment-choice-list [data-segment]", "segment", state.segment);
  }

  function groupedHeaders(columns) {
    const runs = [];
    for (const column of columns) {
      const previous = runs[runs.length - 1];
      if (previous && previous.group === column.group) previous.count += 1;
      else runs.push({ group: column.group, count: 1 });
    }
    return runs.map((run) => {
      const group = GROUPS[run.group];
      return `<th scope="colgroup" colspan="${run.count}" class="${group.className}" data-group="${esc(run.group)}">${esc(group.label)}</th>`;
    }).join("");
  }

  function renderHead(columns) {
    const labels = columns.map((column) => {
      const active = state.sort === column.id;
      const ariaSort = active ? ` aria-sort="${state.direction === "asc" ? "ascending" : "descending"}"` : "";
      const classes = [column.headerClass || "", active ? "active-sort" : ""].filter(Boolean).join(" ");
      const content = column.sortable
        ? `<button type="button" class="sort-button" data-sort="${column.id}">${esc(column.label)}<span class="sort-mark" aria-hidden="true"></span></button>`
        : `<span class="column-label">${esc(column.label)}</span>`;
      return `<th scope="col" class="${classes}" data-column-key="${column.id}"${ariaSort}>${content}</th>`;
    }).join("");
    elements.tableHead.innerHTML = `<tr class="group-row">${groupedHeaders(columns)}</tr><tr class="column-row">${labels}</tr>`;
  }

  function renderBody(columns, visibleRows) {
    elements.tableBody.innerHTML = visibleRows.map((row) => {
      const classes = [!row.eligible ? "filtered-row" : "", notResidential(row) ? "nr-row" : ""].filter(Boolean).join(" ");
      const cells = columns.map((column) => {
        const className = column.cellClass || "";
        const content = column.render(row);
        if (column.id === "estate") return `<th scope="row" class="${className}" data-column-key="${column.id}">${content}</th>`;
        return `<td class="${className}" data-column-key="${column.id}">${content}</td>`;
      }).join("");
      return `<tr class="${classes}">${cells}</tr>`;
    }).join("");
  }

  function sortCopy() {
    const column = columnMap.get(state.sort);
    const direction = state.direction === "asc" ? "low to high / A to Z" : "high to low / Z to A";
    return `${column?.label || "Scenario rank"} · ${direction}`;
  }

  function updateButtonState(selector, attribute, value) {
    document.querySelectorAll(selector).forEach((button) => {
      const active = button.dataset[attribute] === value;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function keepSortVisible() {
    const visible = new Set(visibleColumnIds());
    const unavailableForFiltered = state.status === "filtered" && ["rank", "score"].includes(state.sort);
    if (!visible.has(state.sort) || !columnMap.get(state.sort)?.sortable || unavailableForFiltered) {
      state.sort = visible.has("rank") ? "rank" : "estate";
      if (unavailableForFiltered) state.sort = "estate";
      state.direction = "asc";
    }
  }

  function restoreControlFocus(focus) {
    if (!focus) return;
    const target = [...document.querySelectorAll(`[data-${focus.key}]`)]
      .find((element) => element.dataset[focus.key] === focus.value);
    target?.focus({ preventScroll: true });
  }

  function syncURL() {
    const parameters = new URLSearchParams();
    if (state.profile && state.profile !== defaultProfile) parameters.set("profile", state.profile);
    if (state.query) parameters.set("q", state.query);
    if (state.status !== "eligible") parameters.set("status", state.status);
    if (state.segment !== "all") parameters.set("segment", state.segment);
    if (state.view !== "overview") parameters.set("view", state.view);
    if (state.sort !== "rank") parameters.set("sort", state.sort);
    if (state.direction !== "asc") parameters.set("dir", state.direction);
    const query = parameters.toString();
    const target = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
    window.history.replaceState(null, "", target);
  }

  function readURL() {
    const parameters = new URLSearchParams(window.location.search);
    const profile = parameters.get("profile");
    const status = parameters.get("status");
    const segment = parameters.get("segment");
    const view = parameters.get("view");
    const sort = parameters.get("sort");
    const direction = parameters.get("dir");
    state.profile = profileMap.has(profile) ? profile : defaultProfile;
    state.query = parameters.get("q") || "";
    state.status = ["eligible", "filtered", "all"].includes(status) ? status : "eligible";
    state.segment = ["all", "hdb", "condo", "landed", "private"].includes(segment) ? segment : "all";
    state.view = Object.prototype.hasOwnProperty.call(VIEW_COLUMNS, view) ? view : "overview";
    state.sort = columnMap.has(sort) ? sort : "rank";
    state.direction = direction === "desc" ? "desc" : "asc";
    elements.search.value = state.query;
    keepSortVisible();
  }

  function render({ updateURL = true, restoreFocus = null } = {}) {
    renderProfiles();
    renderScenario();
    renderSegments();
    keepSortVisible();
    const columns = currentColumns();
    const visibleRows = sortedRows();
    renderHead(columns);
    renderBody(columns, visibleRows);
    elements.visibleCount.textContent = String(visibleRows.length);
    const total = profileRows().filter((row) => state.segment === "all" || row.tenure === state.segment).length;
    elements.visibleCopy.textContent = `of ${total} choices shown`;
    elements.sortStatus.textContent = sortCopy();
    const multiTenure = availableSegments().length > 1 && state.segment === "all";
    elements.caveat.textContent = VIEW_CAVEATS[state.view]
      + (multiTenure ? " Choose one tenure segment to reveal its local score and rank." : "");
    elements.tableGuidance.textContent = multiTenure
      ? "Multiple tenure segments are shown alphabetically. Choose one tenure to reveal its local score and rank."
      : state.status === "filtered"
      ? "Filtered choices have no public rank and are shown alphabetically. Sorting reorganises evidence for inspection only."
      : "The default order follows the selected profile-and-tenure rank. Sorting reorganises evidence for inspection and does not create a cross-profile ranking.";
    elements.empty.hidden = visibleRows.length !== 0;
    elements.tableWrap.hidden = visibleRows.length === 0;
    updateButtonState("[data-view]", "view", state.view);
    updateButtonState("[data-status]", "status", state.status);
    if (updateURL) syncURL();
    restoreControlFocus(restoreFocus);
  }

  elements.profileList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-profile]");
    if (!button) return;
    state.profile = button.dataset.profile;
    state.segment = "all";
    state.sort = "rank";
    state.direction = "asc";
    render({ restoreFocus: { key: "profile", value: state.profile } });
  });

  elements.segmentList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-segment]");
    if (!button) return;
    state.segment = button.dataset.segment;
    state.sort = "rank";
    state.direction = "asc";
    render({ restoreFocus: { key: "segment", value: state.segment } });
  });

  document.getElementById("view-options").addEventListener("click", (event) => {
    const button = event.target.closest("[data-view]");
    if (!button) return;
    state.view = button.dataset.view;
    render();
  });

  document.getElementById("status-options").addEventListener("click", (event) => {
    const button = event.target.closest("[data-status]");
    if (!button) return;
    state.status = button.dataset.status;
    render();
  });

  elements.search.addEventListener("input", () => {
    state.query = elements.search.value.trim();
    render();
  });

  elements.tableHead.addEventListener("click", (event) => {
    const button = event.target.closest("[data-sort]");
    if (!button) return;
    const column = columnMap.get(button.dataset.sort);
    if (!column?.sortable) return;
    if (state.sort === column.id) state.direction = state.direction === "asc" ? "desc" : "asc";
    else {
      state.sort = column.id;
      state.direction = column.direction || "asc";
    }
    render({ restoreFocus: { key: "sort", value: column.id } });
  });

  document.getElementById("reset-view").addEventListener("click", () => {
    Object.assign(state, {
      profile: defaultProfile,
      query: "",
      status: "eligible",
      segment: "all",
      view: "overview",
      sort: "rank",
      direction: "asc",
    });
    elements.search.value = "";
    render();
  });

  document.getElementById("empty-reset").addEventListener("click", () => {
    Object.assign(state, { query: "", status: "eligible", segment: "all", view: "overview", sort: "rank", direction: "asc" });
    elements.search.value = "";
    render();
    elements.search.focus();
  });

  window.addEventListener("popstate", () => {
    readURL();
    render();
  });

  readURL();
  render();
})();
