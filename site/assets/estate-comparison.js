(() => {
  "use strict";

  const dataElement = document.getElementById("estate-comparison-data");
  const tableHead = document.getElementById("estate-table-head");
  const tableBody = document.getElementById("estate-table-body");
  if (!dataElement || !tableHead || !tableBody) return;

  let estates;
  try {
    estates = JSON.parse(dataElement.textContent || "[]");
  } catch (error) {
    document.getElementById("view-caveat").textContent =
      `The estate data could not be loaded: ${error.message}`;
    return;
  }

  const BAND_ORDER = { F: 1, D: 2, C: 3, B: 4, "B+": 5, A: 6 };
  const PRICE_SIGNAL_HIGH = 1.10;
  const PRICE_SIGNAL_LOW = 0.90;
  const VALUE_TRUST_THRESHOLD = 100;
  const ARCHETYPES = {
    A: "Regional",
    B: "Mature HDB",
    C: "Coastal",
    D: "Private enclave",
    E: "New central-edge",
    F: "Infill MRT node",
    G: "New town",
    X: "Not rated",
  };

  const GROUPS = [
    {
      key: "identity",
      label: "Identity",
      help: "Estate name and non-ordering archetype metadata.",
    },
    {
      key: "provision",
      label: "Provision",
      help: "Objective supply-side evidence. Scores within ±0.3 are inside the framework noise floor.",
    },
    {
      key: "liveability",
      label: "Liveability profile",
      help: "Persona-relative household fit at T0 plus the lifestyle horizon trajectory.",
    },
    {
      key: "gap",
      label: "Gap · Liveability − Provision",
      help: "The canonical label treats values within ±0.5 as matched.",
    },
    {
      key: "hdb",
      label: "HDB Value",
      help: "HDB resale segment only; never blended with private resale.",
    },
    {
      key: "private",
      label: "Private Value",
      help: "Private resale segment only; never blended with HDB resale.",
    },
    {
      key: "employment",
      label: "Employment access",
      help: "Current and future access context, not a guaranteed price-growth signal.",
    },
    {
      key: "context",
      label: "Risk & life-path context",
      help: "HDB lease, expressway-distance noise proxy and modeled path changes.",
    },
  ];

  const VIEWS = {
    overview: new Set([
      "estate", "arch", "prov", "yf0", "sp0", "ret0", "ls0",
      "hdb_b", "pvt_b", "emp0", "lease", "noise", "flag",
    ]),
    provision: new Set(["estate", "arch", "d", "prov", "score"]),
    liveability: new Set([
      "estate", "arch", "yf0", "sp0", "ret0", "ls0", "trajectory",
      "trajectory_arrow", "gap_yf", "gap_sp", "gap_ret", "gap_ls",
    ]),
    value: new Set([
      "estate", "arch", "hdb_b", "hdb_m", "hdb_n",
      "pvt_b", "pvt_m", "pvt_n",
    ]),
    future: new Set([
      "estate", "arch", "trajectory", "trajectory_arrow", "emp0", "emp5",
      "emp15", "lease", "noise", "best", "worst", "flag",
    ]),
  };

  const VIEW_CAVEATS = {
    overview: "Overview keeps the lenses visibly separate. Choose a focused view for definitions, provenance and model diagnostics.",
    provision: "Provision is a comparable supply-side scaffold, but raw differences inside ±0.3 are not a defensible ranking. State the archetype whenever comparing scores.",
    liveability: "Liveability is a household profile, not a league table. T0 cells answer different persona questions; the trajectory shown here is for the lifestyle persona only.",
    value: "HDB and private Value remain separate universes. Price adjustment describes residual evidence around each segment model; it is not an appreciation forecast.",
    future: "Future bands include modeled, certainty-discounted context. Employment access is not an automatic investment-return signal, and path labels describe change—not absolute fit.",
    all: "All evidence is a diagnostic matrix. Keep Provision, persona-relative Liveability and each tenure-specific Value segment separate while reading across the row.",
  };

  const escapeHTML = value => String(value ?? "").replace(
    /[&<>"']/g,
    character => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#039;",
    })[character]
  );

  function titleCase(value) {
    if (value == null || value === "") return "—";
    return String(value)
      .toLowerCase()
      .replace(/(^|[\s/(-])\S/g, match => match.toUpperCase())
      .replace(/\bMrt\b/g, "MRT")
      .replace(/\bHdb\b/g, "HDB");
  }

  function available(value) {
    return value !== null && value !== undefined && value !== "";
  }

  function bandHTML(value) {
    if (!available(value) || value === "N/R") {
      return '<span class="band band-NR">N/R</span>';
    }
    const className = String(value).replace("+", "p");
    return `<span class="band band-${escapeHTML(className)}">${escapeHTML(value)}</span>`;
  }

  function archHTML(value) {
    const name = ARCHETYPES[value] || "Unclassified";
    return `<span class="arch-badge"><b>${escapeHTML(value)}</b>&nbsp;·&nbsp;${escapeHTML(name)}</span>`;
  }

  function disruptionHTML(value) {
    if (!available(value)) return '<span class="muted-value">—</span>';
    const number = Number(value);
    if (number >= 1) {
      return '<span class="cell-stack"><b class="disruption-full">1.00×</b><small class="cell-sub">no current loss</small></span>';
    }
    return `<span class="cell-stack"><b class="disruption-loss">${number.toFixed(2)}×</b><small class="cell-sub">current disruption loss</small></span>`;
  }

  function signed(value, digits = 2) {
    if (!available(value)) return "—";
    const number = Number(value);
    return `${number > 0 ? "+" : ""}${number.toFixed(digits)}`;
  }

  function gapHTML(value, label) {
    if (!available(value) || !available(label) || label === "N/R") {
      return '<span class="muted-value">N/R</span>';
    }
    const labels = {
      matched: ["matched", "gap-matched"],
      over_equipped: ["over-equipped", "gap-negative"],
      punches_above: ["punches above", "gap-positive"],
    };
    const [copy, className] = labels[label] || [titleCase(label.replaceAll("_", " ")), "gap-matched"];
    return `<span>${signed(value)}<span class="gap-label ${className}">${escapeHTML(copy)}</span></span>`;
  }

  function trajectoryValues(row) {
    return [row.ls0, row.ls5, row.ls15];
  }

  function trajectoryNet(row) {
    const [start, , end] = trajectoryValues(row);
    if (!available(start) || !available(end)) return null;
    return (BAND_ORDER[end] ?? 0) - (BAND_ORDER[start] ?? 0);
  }

  function trajectoryHTML(row) {
    const values = trajectoryValues(row);
    if (values.some(value => !available(value))) {
      return '<span class="muted-value">N/R</span>';
    }
    const arrow = (start, end) => {
      const difference = (BAND_ORDER[end] ?? 0) - (BAND_ORDER[start] ?? 0);
      return difference > 0 ? "↗" : difference < 0 ? "↘" : "→";
    };
    return `<span class="trajectory">${escapeHTML(values[0])} ${arrow(values[0], values[1])} ${escapeHTML(values[1])} ${arrow(values[1], values[2])} ${escapeHTML(values[2])}</span>`;
  }

  function trajectoryArrowHTML(row) {
    const net = trajectoryNet(row);
    if (net == null) return '<span class="muted-value">—</span>';
    if (net > 0) return `<span class="direction-up" aria-label="Improves by ${net} bands">${net > 1 ? "↑↑" : "↑"}</span>`;
    if (net < 0) return `<span class="direction-down" aria-label="Declines by ${Math.abs(net)} bands">↓</span>`;
    return '<span class="direction-flat" aria-label="No net band change">→</span>';
  }

  function statusCopy(status) {
    return {
      no_data: "No data",
      not_covered: "Not covered",
      unavailable: "Unavailable",
    }[status] || titleCase(String(status || "Unavailable").replaceAll("_", " "));
  }

  function basisHTML(basis) {
    if (!available(basis)) return "";
    if (basis === "direct") {
      return '<span class="status-badge">Direct</span>';
    }
    if (String(basis).startsWith("proxy_from:")) {
      const source = String(basis).split(":", 2)[1];
      return `<span class="status-badge status-proxy">Proxy · ${escapeHTML(titleCase(source))}</span>`;
    }
    return `<span class="status-badge">${escapeHTML(titleCase(String(basis).replaceAll("_", " ")))}</span>`;
  }

  function missingEvidenceHTML(status) {
    return `<span class="status-badge status-missing">${escapeHTML(statusCopy(status))}</span>`;
  }

  function valueBandHTML(band, basis, status) {
    if (status !== "available" || !available(band)) {
      return missingEvidenceHTML(status);
    }
    return `<span class="cell-stack">${bandHTML(band)}${basisHTML(basis)}</span>`;
  }

  function multiplierHTML(value, status, sample) {
    if (status !== "available") {
      return missingEvidenceHTML(status);
    }
    if (!available(sample) || Number(sample) < VALUE_TRUST_THRESHOLD) {
      return '<span class="cell-stack"><span class="status-badge status-proxy">Band only</span><small class="cell-sub">n&lt;100 · decimal hidden</small></span>';
    }
    if (!available(value)) return missingEvidenceHTML("unavailable");
    const number = Number(value);
    let className = "price-near-model";
    let copy = "near baseline";
    if (number >= PRICE_SIGNAL_HIGH) {
      className = "price-below-model";
      copy = "price below baseline";
    } else if (number <= PRICE_SIGNAL_LOW) {
      className = "price-above-model";
      copy = "price above baseline";
    }
    return `<span class="cell-stack"><b class="${className}">${number.toFixed(2)}×</b><small class="cell-sub">${copy}</small></span>`;
  }

  function sampleHTML(value, status) {
    if (status !== "available" || !available(value)) {
      return missingEvidenceHTML(status);
    }
    const number = Number(value);
    const className = number < VALUE_TRUST_THRESHOLD ? "sample-small" : "";
    const note = number < VALUE_TRUST_THRESHOLD ? "band only" : "records";
    return `<span class="cell-stack"><b class="${className}">n=${number.toLocaleString("en-SG")}</b><small class="cell-sub">${note}</small></span>`;
  }

  function noiseHTML(value) {
    if (!available(value)) return '<span class="muted-value">—</span>';
    return `<span class="cell-stack"><b class="noise-score">${escapeHTML(value)} / 5</b><small class="cell-sub">distance proxy</small></span>`;
  }

  function pathHTML(path, delta) {
    if (!available(path)) return '<span class="muted-value">—</span>';
    const directionClass = Number(delta) > 0 ? "direction-up" : Number(delta) < 0 ? "direction-down" : "direction-flat";
    return `<span class="cell-stack path-cell"><b>${escapeHTML(titleCase(String(path).replaceAll("_", " ")))}</b><small class="cell-sub ${directionClass}">modeled Δ ${signed(delta)}</small></span>`;
  }

  function flagHTML(value) {
    if (!value) return '<span class="muted-value">None</span>';
    const flags = {
      nr: ["Not a residential construct", "note-negative"],
      disruption: ["Current disruption loss", "note-caution"],
      hdb_price_below_model: ["HDB price below model baseline", "note-positive"],
      hdb_price_above_model: ["HDB price above model baseline", "note-negative"],
      private_price_below_model: ["Private price below model baseline", "note-positive"],
      private_price_above_model: ["Private price above model baseline", "note-negative"],
    };
    return String(value).split(",").map(flag => {
      const [copy, className] = flags[flag] || [titleCase(flag.replaceAll("_", " ")), ""];
      return `<span class="note-badge ${className}">${escapeHTML(copy)}</span>`;
    }).join("");
  }

  const COLUMNS = [
    { key: "estate", group: "identity", label: "Estate", help: "Estate or sub-estate name.", type: "text", value: row => row.estate, cell: row => `<span>${escapeHTML(titleCase(row.estate))}</span>` },
    { key: "arch", group: "identity", label: "Archetype", help: "Interpretive node family; not an ordering or grade.", type: "text", value: row => row.arch, cell: row => archHTML(row.arch) },
    { key: "d", group: "provision", label: "D loss", help: "Current disruption-loss multiplier used in Liveability; 1.00 means no current loss.", type: "number", value: row => row.d, cell: row => disruptionHTML(row.d) },
    { key: "prov", group: "provision", label: "Band", help: "Objective Provision band before persona-specific fit.", type: "band", value: row => row.prov, cell: row => bandHTML(row.prov) },
    { key: "score", group: "provision", label: "Approx. score", help: "Provision score on the 1–5 scale. Differences inside ±0.3 are within the noise floor.", type: "number", value: row => row.score, cell: row => available(row.score) ? `<span class="muted-value">≈${Number(row.score).toFixed(2)}</span>` : "—" },
    { key: "yf0", group: "liveability", label: "Young family", help: "Young-family Liveability profile at T0.", type: "band", value: row => row.yf0, cell: row => bandHTML(row.yf0) },
    { key: "sp0", group: "liveability", label: "Professional", help: "Single-professional Liveability profile at T0.", type: "band", value: row => row.sp0, cell: row => bandHTML(row.sp0) },
    { key: "ret0", group: "liveability", label: "Retiree", help: "Retiree Liveability profile at T0.", type: "band", value: row => row.ret0, cell: row => bandHTML(row.ret0) },
    { key: "ls0", group: "liveability", label: "Lifestyle", help: "Lifestyle-seeker Liveability profile at T0.", type: "band", value: row => row.ls0, cell: row => bandHTML(row.ls0) },
    { key: "trajectory", group: "liveability", label: "LS · T0 → T5 → T15", help: "Lifestyle-seeker band sequence now, around 2031 and around 2041.", type: "number", value: row => trajectoryNet(row), cell: trajectoryHTML },
    { key: "trajectory_arrow", group: "liveability", label: "LS direction", help: "Net lifestyle-seeker band direction from T0 to T15; not a return forecast.", type: "number", value: row => trajectoryNet(row), cell: trajectoryArrowHTML },
    { key: "gap_yf", group: "gap", label: "Young family", help: "Young-family T0 Liveability minus Provision; canonical dead band ±0.5.", type: "number", value: row => row.gap_yf, cell: row => gapHTML(row.gap_yf, row.gap_yf_label) },
    { key: "gap_sp", group: "gap", label: "Professional", help: "Single-professional T0 Liveability minus Provision; canonical dead band ±0.5.", type: "number", value: row => row.gap_sp, cell: row => gapHTML(row.gap_sp, row.gap_sp_label) },
    { key: "gap_ret", group: "gap", label: "Retiree", help: "Retiree T0 Liveability minus Provision; canonical dead band ±0.5.", type: "number", value: row => row.gap_ret, cell: row => gapHTML(row.gap_ret, row.gap_ret_label) },
    { key: "gap_ls", group: "gap", label: "Lifestyle", help: "Lifestyle-seeker T0 Liveability minus Provision; canonical dead band ±0.5.", type: "number", value: row => row.gap_ls, cell: row => gapHTML(row.gap_ls, row.gap_ls_label) },
    { key: "hdb_b", group: "hdb", label: "Band", help: "HDB resale Value band with evidence basis shown.", type: "band", value: row => row.hdb_b, cell: row => valueBandHTML(row.hdb_b, row.hdb_basis, row.hdb_status) },
    { key: "hdb_m", group: "hdb", label: "Price adj.", help: "Capped HDB segment price-residual multiplier; hidden below the n=100 trust threshold and never a forecast.", type: "number", value: row => row.hdb_m, cell: row => multiplierHTML(row.hdb_m, row.hdb_status, row.hdb_n) },
    { key: "hdb_n", group: "hdb", label: "Sample", help: "HDB resale record count. Below 100, report the band rather than decimal precision.", type: "number", value: row => row.hdb_n, cell: row => sampleHTML(row.hdb_n, row.hdb_status) },
    { key: "pvt_b", group: "private", label: "Band", help: "Private resale Value band with direct or proxy basis shown.", type: "band", value: row => row.pvt_b, cell: row => valueBandHTML(row.pvt_b, row.pvt_basis, row.pvt_status) },
    { key: "pvt_m", group: "private", label: "Price adj.", help: "Capped private-segment price-residual multiplier using the private Provision base; hidden below the n=100 trust threshold and never a forecast.", type: "number", value: row => row.pvt_m, cell: row => multiplierHTML(row.pvt_m, row.pvt_status, row.pvt_n) },
    { key: "pvt_n", group: "private", label: "Sample", help: "Private resale record count. Below 100, report the band rather than decimal precision.", type: "number", value: row => row.pvt_n, cell: row => sampleHTML(row.pvt_n, row.pvt_status) },
    { key: "emp0", group: "employment", label: "T0", help: "Current employment-access context.", type: "band", value: row => row.emp0, cell: row => bandHTML(row.emp0) },
    { key: "emp5", group: "employment", label: "T5", help: "Modeled near-term employment-access context around 2031.", type: "band", value: row => row.emp5, cell: row => bandHTML(row.emp5) },
    { key: "emp15", group: "employment", label: "T15", help: "Modeled long-horizon employment-access context around 2041.", type: "band", value: row => row.emp15, cell: row => bandHTML(row.emp15) },
    { key: "lease", group: "context", label: "HDB lease", help: "HDB remaining-lease risk band or reviewed override; not a private-condo tenure score.", type: "band", value: row => row.lease, cell: row => bandHTML(row.lease) },
    { key: "noise", group: "context", label: "Noise proxy", help: "Expressway-distance proxy on a 1–5 scale; higher means farther, not measured quietness.", type: "number", value: row => row.noise, cell: row => noiseHTML(row.noise) },
    { key: "best", group: "context", label: "Largest change", help: "Life path with the largest modeled delta; not necessarily the best absolute fit.", type: "number", value: row => row.best_delta, cell: row => pathHTML(row.best, row.best_delta) },
    { key: "worst", group: "context", label: "Smallest change", help: "Life path with the smallest modeled delta, which may still be positive.", type: "number", value: row => row.worst_delta, cell: row => pathHTML(row.worst, row.worst_delta) },
    { key: "flag", group: "context", label: "Interpretation notes", help: "Segment-labelled price signals, current disruption and non-residential gate.", type: "text", value: row => row.flag, cell: row => flagHTML(row.flag) },
  ];

  const columnByKey = new Map(COLUMNS.map(column => [column.key, column]));
  const tableWrapper = document.querySelector(".tbl-wrap");
  const emptyState = document.getElementById("empty-state");
  const searchInput = document.getElementById("estate-search");
  const visibleCount = document.getElementById("visible-count");
  const visibleCopy = document.getElementById("visible-copy");
  const sortStatus = document.getElementById("sort-status");
  const viewCaveat = document.getElementById("view-caveat");

  const state = {
    query: "",
    arch: "all",
    view: "overview",
    sort: "estate",
    direction: "asc",
  };

  function isNotRated(row) {
    return row.arch === "X";
  }

  function dataValue(row, column) {
    if (isNotRated(row) && !["estate", "arch", "flag"].includes(column.key)) {
      return null;
    }
    return column.value(row);
  }

  function compareRows(first, second) {
    const column = columnByKey.get(state.sort) || columnByKey.get("estate");
    const a = dataValue(first, column);
    const b = dataValue(second, column);
    const missingA = !available(a) || a === "N/R";
    const missingB = !available(b) || b === "N/R";
    if (missingA !== missingB) return missingA ? 1 : -1;
    if (missingA && missingB) return String(first.estate).localeCompare(String(second.estate));

    let comparison;
    if (column.type === "number") {
      comparison = Number(a) - Number(b);
    } else if (column.type === "band") {
      comparison = (BAND_ORDER[a] ?? -1) - (BAND_ORDER[b] ?? -1);
    } else {
      comparison = String(a).localeCompare(String(b));
    }
    if (comparison === 0) comparison = String(first.estate).localeCompare(String(second.estate));
    return state.direction === "asc" ? comparison : -comparison;
  }

  function activeColumns() {
    return state.view === "all"
      ? new Set(COLUMNS.map(column => column.key))
      : VIEWS[state.view] || VIEWS.overview;
  }

  function keepSortVisible() {
    if (activeColumns().has(state.sort)) return;
    state.sort = "estate";
    state.direction = "asc";
  }

  function buildHeader() {
    const groupRow = document.createElement("tr");
    groupRow.className = "group-row";
    GROUPS.forEach(group => {
      const columns = COLUMNS.filter(column => column.group === group.key);
      const heading = document.createElement("th");
      heading.scope = "colgroup";
      heading.colSpan = columns.length;
      heading.dataset.group = group.key;
      heading.dataset.columns = columns.map(column => column.key).join(",");
      heading.className = `group-${group.key}`;
      heading.title = group.help;
      heading.textContent = group.label;
      groupRow.append(heading);
    });

    const columnRow = document.createElement("tr");
    columnRow.className = "column-row";
    COLUMNS.forEach(column => {
      const heading = document.createElement("th");
      heading.scope = "col";
      heading.dataset.columnKey = column.key;
      if (column.key === "estate") heading.classList.add("estate-column");

      const button = document.createElement("button");
      button.type = "button";
      button.className = "sort-button";
      button.dataset.sort = column.key;
      button.title = column.help;
      button.setAttribute("aria-label", `Sort by ${column.label}. ${column.help}`);
      const label = document.createElement("span");
      label.textContent = column.label;
      const mark = document.createElement("span");
      mark.className = "sort-mark";
      mark.setAttribute("aria-hidden", "true");
      button.append(label, mark);
      heading.append(button);
      columnRow.append(heading);
    });
    tableHead.replaceChildren(groupRow, columnRow);
  }

  function rowHTML(row) {
    const cells = COLUMNS.map(column => {
      const notRated = isNotRated(row) && !["estate", "arch", "flag"].includes(column.key);
      const classes = [
        column.key === "estate" ? "estate-cell" : "",
        column.key === "flag" ? "notes-cell" : "",
        ["best", "worst"].includes(column.key) ? "path-cell" : "",
        notRated ? "not-rated-cell" : "",
      ].filter(Boolean).join(" ");
      const content = notRated
        ? '<span title="Not rated: this row is not a residential construct">N/R</span>'
        : column.cell(row);
      const tag = column.key === "estate" ? "th" : "td";
      const scope = column.key === "estate" ? ' scope="row"' : "";
      return `<${tag}${scope} class="${classes}" data-column-key="${column.key}">${content}</${tag}>`;
    }).join("");
    return `<tr class="${isNotRated(row) ? "nr-row" : ""}" data-estate="${escapeHTML(String(row.estate).toLowerCase())}" data-arch="${escapeHTML(row.arch)}">${cells}</tr>`;
  }

  function filteredRows() {
    const query = state.query.trim().toLocaleLowerCase("en-SG");
    return estates
      .filter(row => state.arch === "all" || row.arch === state.arch)
      .filter(row => !query || String(row.estate).toLocaleLowerCase("en-SG").includes(query))
      .sort(compareRows);
  }

  function applyColumnVisibility() {
    const visible = activeColumns();
    document.querySelectorAll("[data-column-key]").forEach(element => {
      element.hidden = !visible.has(element.dataset.columnKey);
    });
    document.querySelectorAll("[data-group]").forEach(heading => {
      const keys = heading.dataset.columns.split(",");
      const count = keys.filter(key => visible.has(key)).length;
      heading.hidden = count === 0;
      if (count > 0) heading.colSpan = count;
    });
  }

  function sortLabel() {
    const column = columnByKey.get(state.sort) || columnByKey.get("estate");
    return `${column.label} · ${state.direction === "asc" ? "ascending" : "descending"}`;
  }

  function renderHeaderState() {
    tableHead.querySelectorAll("th[data-column-key]").forEach(heading => {
      const active = heading.dataset.columnKey === state.sort;
      if (active) {
        heading.setAttribute(
          "aria-sort",
          state.direction === "asc" ? "ascending" : "descending"
        );
      } else {
        heading.removeAttribute("aria-sort");
      }
    });
    sortStatus.textContent = sortLabel();
  }

  function updateControls() {
    searchInput.value = state.query;
    document.querySelectorAll("[data-view]").forEach(button => {
      const active = button.dataset.view === state.view;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    document.querySelectorAll("button[data-arch]").forEach(button => {
      const active = button.dataset.arch === state.arch;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    viewCaveat.textContent = VIEW_CAVEATS[state.view] || VIEW_CAVEATS.overview;
  }

  function updateURL() {
    const parameters = new URLSearchParams();
    if (state.query) parameters.set("q", state.query);
    if (state.arch !== "all") parameters.set("arch", state.arch);
    if (state.view !== "overview") parameters.set("view", state.view);
    if (state.sort !== "estate") parameters.set("sort", state.sort);
    if (state.direction !== "asc") parameters.set("dir", state.direction);
    const query = parameters.toString();
    history.replaceState({}, "", `${location.pathname}${query ? `?${query}` : ""}${location.hash}`);
  }

  function render({ syncURL = true } = {}) {
    const rows = filteredRows();
    tableBody.innerHTML = rows.map(rowHTML).join("");
    visibleCount.textContent = rows.length.toLocaleString("en-SG");
    visibleCopy.textContent = rows.length === 1 ? "estate context shown" : "estate contexts shown";
    tableWrapper.hidden = rows.length === 0;
    emptyState.hidden = rows.length !== 0;
    applyColumnVisibility();
    renderHeaderState();
    updateControls();
    if (syncURL) updateURL();
  }

  function reset() {
    Object.assign(state, {
      query: "",
      arch: "all",
      view: "overview",
      sort: "estate",
      direction: "asc",
    });
    render();
    searchInput.focus();
  }

  function readURL() {
    const parameters = new URLSearchParams(location.search);
    const view = parameters.get("view");
    const arch = parameters.get("arch");
    const sort = parameters.get("sort");
    state.query = (parameters.get("q") || "").slice(0, 120);
    state.view = view === "all" || Object.hasOwn(VIEWS, view) ? view : "overview";
    state.arch = arch === "all" || Object.hasOwn(ARCHETYPES, arch) ? arch : "all";
    state.sort = columnByKey.has(sort) ? sort : "estate";
    state.direction = parameters.get("dir") === "desc" ? "desc" : "asc";
    keepSortVisible();
  }

  buildHeader();
  readURL();
  render();

  searchInput.addEventListener("input", () => {
    state.query = searchInput.value;
    render();
  });

  document.getElementById("view-options").addEventListener("click", event => {
    const button = event.target.closest("[data-view]");
    if (!button) return;
    state.view = button.dataset.view;
    keepSortVisible();
    render();
  });

  document.getElementById("archetype-options").addEventListener("click", event => {
    const button = event.target.closest("[data-arch]");
    if (!button) return;
    state.arch = button.dataset.arch;
    render();
  });

  tableHead.addEventListener("click", event => {
    const button = event.target.closest("[data-sort]");
    if (!button) return;
    const key = button.dataset.sort;
    if (state.sort === key) state.direction = state.direction === "asc" ? "desc" : "asc";
    else {
      state.sort = key;
      state.direction = "asc";
    }
    render();
  });

  document.getElementById("reset-view").addEventListener("click", reset);
  document.getElementById("empty-reset").addEventListener("click", reset);
  window.addEventListener("popstate", () => {
    readURL();
    render();
  });
})();
