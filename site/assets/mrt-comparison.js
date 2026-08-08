(() => {
  "use strict";

  const dataElement = document.getElementById("mrt-comparison-data");
  const lineElement = document.getElementById("mrt-line-summary");
  const configElement = document.getElementById("mrt-comparison-config");
  const tableHead = document.getElementById("mrt-comparison-table-head");
  const tableBody = document.getElementById("mrt-comparison-table-body");
  if (!dataElement || !lineElement || !configElement || !tableHead || !tableBody) return;

  let rows;
  let lines;
  let config;
  try {
    rows = JSON.parse(dataElement.textContent || "[]");
    lines = JSON.parse(lineElement.textContent || "[]");
    config = JSON.parse(configElement.textContent || "{}");
  } catch (error) {
    document.getElementById("view-caveat").textContent =
      `The station data could not be loaded: ${error.message}`;
    return;
  }

  const BAND_ORDER = { F: 1, D: 2, C: 3, B: 4, "B+": 5, A: 6 };
  const VALUE_TRUST_THRESHOLD = Number(config.value_trust_threshold);
  if (!Number.isFinite(VALUE_TRUST_THRESHOLD) || VALUE_TRUST_THRESHOLD <= 0) {
    document.getElementById("view-caveat").textContent =
      "The Value publication threshold is missing or invalid.";
    return;
  }
  const ARCHETYPES = {
    A: "Regional",
    B: "Mature HDB",
    C: "Coastal",
    D: "Private enclave",
    E: "New central-edge",
    F: "Infill MRT node",
    G: "New town",
    X: "Not residential",
  };
  const ASSOCIATION_ORDER = {
    unavailable: 0,
    not_residential: 1,
    out_of_range: 2,
    available: 3,
  };
  const STATUS_ORDER = {
    planned: 1,
    deferred: 2,
    under_construction: 3,
    open: 4,
  };

  const GROUPS = {
    station: { label: "Station record", className: "group-rail" },
    rail: { label: "Encoded rail service", className: "group-rail" },
    proximity: { label: "Centroid association", className: "group-proximity" },
    estate: { label: "Estate reference", className: "group-estate" },
    provision: { label: "Estate Provision", className: "group-provision" },
    liveability: { label: "Estate Liveability", className: "group-liveability" },
    hdb: { label: "Estate HDB Value", className: "group-hdb" },
    private: { label: "Estate private Value", className: "group-private" },
    context: { label: "Estate employment / HDB risk", className: "group-context" },
  };

  const VIEWS = {
    overview: ["station", "code", "line", "status", "estate", "distance", "association", "provision", "employment"],
    rail: ["station", "code", "line", "line_name", "mode", "status", "status_source", "opening", "coordinates", "geometry"],
    proximity: ["station", "code", "line", "estate", "distance", "distance_band", "centroids_800", "centroids_1400", "association"],
    household: ["station", "code", "estate", "association", "archetype", "provision", "provision_score", "provision_evidence", "yf0", "sp0", "ret0", "ls0", "trajectory"],
    value: ["station", "code", "estate", "association", "hdb_value", "hdb_sample", "private_value", "private_sample"],
    future: ["station", "code", "line", "status", "opening", "estate", "association", "trajectory", "employment", "lease"],
    all: [],
  };

  const VIEW_CAVEATS = {
    overview: "Overview keeps rail facts, centroid geometry and estate context visibly separate. Choose a focused view for definitions and evidence states.",
    rail: "Each row is one audited code-line membership, so interchanges repeat across their services. Status is reconciled to the dated LTA map and is not live service information.",
    proximity: "All distances are straight-line station-point to estate-centroid diagnostics. Centroid counts are not station catchments, households served or walking times.",
    household: "Every model cell belongs to the associated estate, not the station. Provision differences inside ±0.3 are not a defensible rank; persona Liveability cells answer different questions.",
    value: "HDB and private resale Value remain separate tenure universes. Direct, proxy, thin-sample and unavailable evidence states stay visible; none is a rail premium forecast.",
    future: "Non-open rail rows distinguish under-construction, deferred and planned memberships within the documented overlay. Estate trajectory and employment fields remain separate and are not delivery or return forecasts.",
    all: "All diagnostics remain a layered audit. Station facts, centroid geometry and estate model outputs must not be collapsed into a station ranking.",
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

  function available(value) {
    return value !== null && value !== undefined && value !== "";
  }

  function titleCase(value) {
    if (!available(value)) return "Unavailable";
    return String(value)
      .toLowerCase()
      .replaceAll("_", " ")
      .replace(/\b\w/g, character => character.toUpperCase())
      .replace(/\bHdb\b/g, "HDB")
      .replace(/\bMrt\b/g, "MRT")
      .replace(/\bLrt\b/g, "LRT")
      .replace(/\bLta\b/g, "LTA")
      .replace(/\bUra\b/g, "URA");
  }

  function bandHTML(value) {
    if (!available(value)) return '<span class="band band-NR">N/R</span>';
    const className = String(value).replace("+", "p");
    return `<span class="band band-${escapeHTML(className)}">${escapeHTML(value)}</span>`;
  }

  function statusHTML(row) {
    const labels = {
      open: "Open",
      under_construction: "Under construction",
      deferred: "Deferred",
      planned: "Planned",
    };
    const status = row.network_status || row.status;
    return `<span class="rail-status rail-status-${escapeHTML(status)}">${escapeHTML(labels[status] || titleCase(status))}</span>`;
  }

  function openingHTML(row) {
    if (row.network_status === "open") {
      return '<span class="cell-stack"><b>In service</b><small class="cell-sub">at status snapshot</small></span>';
    }
    return available(row.planned_opening)
      ? `<span class="cell-stack"><b>${escapeHTML(row.planned_opening)}</b><small class="cell-sub">official target / TBA state</small></span>`
      : '<span class="status-badge status-missing">TBA</span>';
  }

  function statusSourceHTML(row) {
    const labels = {
      lta_system_map_jul_2026: "LTA system map · 21 Jul 2026",
      lta_ccl6_opening_jul_2026: "LTA CCL6 opening notice",
      lta_tel_project: "LTA TEL project page",
      lta_dtl_extensions: "LTA DTL extensions",
      lta_jrl_project: "LTA JRL project page",
      lta_crl1_project: "LTA CRL project page",
    };
    const source = labels[row.network_status_source] || titleCase(row.network_status_source);
    return available(row.network_status_source)
      ? `<span class="cell-stack"><b>${escapeHTML(source)}</b><small class="cell-sub">reviewed status source</small></span>`
      : '<span class="status-badge status-missing">Not recorded</span>';
  }

  function geometryHTML(row) {
    if (!available(row.geometry_basis)) {
      return '<span class="status-badge status-missing">Not recorded</span>';
    }
    const source = available(row.geometry_source) ? titleCase(row.geometry_source) : "Source not recorded";
    return `<span class="cell-stack"><b>${escapeHTML(titleCase(row.geometry_basis))}</b><small class="cell-sub">${escapeHTML(source)}</small></span>`;
  }

  function modeHTML(row) {
    return `<span class="mode-badge mode-${escapeHTML(row.mode)}">${escapeHTML(row.mode)}</span>`;
  }

  function lineHTML(row) {
    return `<span class="line-badge line-${escapeHTML(row.line_key)}" title="${escapeHTML(row.line)}">${escapeHTML(row.line_short)}</span>`;
  }

  function distanceHTML(row) {
    return `<span class="cell-stack"><b>${Number(row.distance_m).toLocaleString("en-SG")} m</b><small class="cell-sub">straight-line to centroid</small></span>`;
  }

  function distanceBandHTML(row) {
    const labels = {
      le600: "≤600 m",
      "601-1000": "601 m–1 km",
      "1001-1400": "1–1.4 km",
      gt1400: ">1.4 km",
    };
    return `<span class="distance-badge distance-${escapeHTML(row.distance_band)}">${escapeHTML(labels[row.distance_band] || row.distance_band)}</span>`;
  }

  function associationHTML(row) {
    const labels = {
      available: "Context shown · ≤1.4 km",
      out_of_range: "Context withheld · >1.4 km",
      not_residential: "N/R · non-residential construct",
      unavailable: "Context unavailable",
    };
    return `<span class="association-badge association-${escapeHTML(row.context_status)}">${escapeHTML(labels[row.context_status] || titleCase(row.context_status))}</span>`;
  }

  function withheldHTML(row) {
    const copy = {
      out_of_range: ["Withheld", "nearest centroid is beyond 1.4 km"],
      not_residential: ["N/R", "nearest construct is not residential"],
      unavailable: ["Unavailable", "no matching estate output"],
    }[row.context_status] || ["Unavailable", "estate context is not publishable"];
    return `<span class="model-withheld"><b>${escapeHTML(copy[0])}</b><small>${escapeHTML(copy[1])}</small></span>`;
  }

  function contextCell(row, renderer) {
    return row.context_status === "available" ? renderer() : withheldHTML(row);
  }

  function archetypeHTML(row) {
    return contextCell(row, () => {
      if (!available(row.archetype)) return '<span class="muted-value">—</span>';
      const label = ARCHETYPES[row.archetype] || "Unclassified";
      return `<span class="arch-badge"><b>${escapeHTML(row.archetype)}</b>&nbsp;·&nbsp;${escapeHTML(label)}</span>`;
    });
  }

  function trajectoryNet(row) {
    if (![row.ls0, row.ls5, row.ls15].every(available)) return null;
    return (BAND_ORDER[row.ls15] ?? 0) - (BAND_ORDER[row.ls0] ?? 0);
  }

  function trajectoryHTML(row) {
    return contextCell(row, () => {
      if (![row.ls0, row.ls5, row.ls15].every(available)) {
        return '<span class="status-badge status-missing">Unavailable</span>';
      }
      const arrow = (start, end) => {
        const change = (BAND_ORDER[end] ?? 0) - (BAND_ORDER[start] ?? 0);
        return change > 0 ? "↗" : change < 0 ? "↘" : "→";
      };
      return `<span class="cell-stack"><b class="trajectory">${escapeHTML(row.ls0)} ${arrow(row.ls0, row.ls5)} ${escapeHTML(row.ls5)} ${arrow(row.ls5, row.ls15)} ${escapeHTML(row.ls15)}</b><small class="cell-sub">Lifestyle · T0 → T5 → T15</small></span>`;
    });
  }

  function statusCopy(status) {
    return {
      no_data: "No data",
      not_covered: "Not covered",
      not_applicable: "Not applicable",
      unavailable: "Unavailable",
    }[status] || titleCase(status);
  }

  function basisHTML(basis) {
    if (!available(basis)) return "";
    if (basis === "direct") return '<span class="basis-badge">Direct</span>';
    if (String(basis).startsWith("proxy_from:")) {
      const source = String(basis).split(":", 2)[1];
      return `<span class="basis-badge basis-proxy">Proxy · ${escapeHTML(titleCase(source))}</span>`;
    }
    return `<span class="basis-badge">${escapeHTML(titleCase(basis))}</span>`;
  }

  function valueHTML(row, segment) {
    return contextCell(row, () => {
      const status = row[`${segment}_value_status`];
      const band = row[`${segment}_value_band`];
      const basis = row[`${segment}_value_basis`];
      if (status !== "available" || !available(band)) {
        const basisDetail = available(basis) && basis !== status ? basisHTML(basis) : "";
        return `<span class="cell-stack value-cell"><span class="status-badge status-missing">${escapeHTML(statusCopy(status))}</span>${basisDetail}</span>`;
      }
      return `<span class="cell-stack value-cell">${bandHTML(band)}${basisHTML(basis)}</span>`;
    });
  }

  function sampleHTML(row, segment) {
    return contextCell(row, () => {
      const status = row[`${segment}_value_status`];
      const rawSample = row[`${segment}_value_n`];
      if (status !== "available" || !available(rawSample)) {
        return `<span class="status-badge status-missing">${escapeHTML(statusCopy(status))}</span>`;
      }
      const sample = Number(rawSample);
      if (!Number.isFinite(sample)) {
        return '<span class="status-badge status-missing">Unavailable</span>';
      }
      const thin = sample < VALUE_TRUST_THRESHOLD;
      return `<span class="cell-stack"><b class="${thin ? "sample-thin" : ""}">n=${sample.toLocaleString("en-SG")}</b><small class="cell-sub">${thin ? "band only · n<100" : "records"}</small></span>`;
    });
  }

  function evidenceHTML(row) {
    return contextCell(row, () => row.measured_only
      ? '<span class="status-badge status-proxy">Measured-only fallback</span>'
      : '<span class="status-badge">Configured evidence mix</span>'
    );
  }

  function employmentHTML(row) {
    return contextCell(row, () => row.employment_status === "available" && available(row.employment_band)
      ? `<span class="cell-stack">${bandHTML(row.employment_band)}<small class="cell-sub">current / T0 access</small></span>`
      : `<span class="status-badge status-missing">${escapeHTML(statusCopy(row.employment_status))}</span>`
    );
  }

  function leaseHTML(row) {
    return contextCell(row, () => row.lease_status === "available" && available(row.lease_band)
      ? `<span class="cell-stack">${bandHTML(row.lease_band)}<small class="cell-sub">HDB lease risk · ${escapeHTML(titleCase(row.lease_source || "source unavailable"))}</small></span>`
      : `<span class="status-badge status-missing">${escapeHTML(statusCopy(row.lease_status))}</span>`
    );
  }

  const COLUMNS = [
    { id: "station", group: "station", label: "Station", help: "Official English station name used for the code-line membership.", type: "text", value: row => row.station, cell: row => escapeHTML(row.station) },
    { id: "code", group: "station", label: "Code", help: "One official service code. Interchanges repeat as separate code-line rows.", type: "text", value: row => row.code, cell: row => `<b>${escapeHTML(row.code)}</b>` },
    { id: "line", group: "rail", label: "Line", help: "Abbreviated rail line for this code-line membership.", type: "text", value: row => row.line, cell: lineHTML },
    { id: "line_name", group: "rail", label: "Rail line name", help: "Full line label for this code-line membership.", type: "text", value: row => row.line, cell: row => `<span class="cell-sub">${escapeHTML(row.line)}</span>` },
    { id: "mode", group: "rail", label: "Mode", help: "MRT or LRT derived from the encoded line label.", type: "text", value: row => row.mode, cell: modeHTML },
    { id: "status", group: "rail", label: "Audited status", help: "Open, under-construction, deferred or planned at the dated snapshot; not a live service feed.", type: "status", value: row => row.network_status, cell: statusHTML },
    { id: "status_source", group: "rail", label: "Status source", help: "Reviewed LTA map, opening notice or project page supporting the dated network status.", type: "text", value: row => row.network_status_source, cell: statusSourceHTML },
    { id: "opening", group: "rail", label: "Opening target", help: "Official target year/period or TBA for a non-open membership; not a guarantee.", type: "text", value: row => row.planned_opening, cell: openingHTML },
    { id: "coordinates", group: "rail", label: "Representative point", help: "Latitude and longitude of a derived footprint/exit/outline representative point used for geometric comparison.", type: "number", value: row => row.lat, cell: row => `<span class="coordinate-cell">${Number(row.lat).toFixed(6)}, ${Number(row.lon).toFixed(6)}</span>` },
    { id: "geometry", group: "rail", label: "Geometry basis", help: "Official source geometry plus the disclosed derivation used to produce the representative point; it is not an official station centroid.", type: "text", value: row => row.geometry_basis, cell: geometryHTML },
    { id: "estate", group: "proximity", label: "Nearest estate centroid", help: "Closest of the framework estate centroid points; not an official assignment.", type: "text", value: row => row.estate, cell: row => `<b>${escapeHTML(titleCase(row.estate))}</b>` },
    { id: "distance", group: "proximity", label: "Centroid distance", help: "Straight-line great-circle distance from station point to nearest estate centroid.", type: "number", value: row => row.distance_m, cell: distanceHTML },
    { id: "distance_band", group: "proximity", label: "Distance bucket", help: "Geometric bucket only; not walking time or a formal catchment.", type: "number", value: row => row.distance_m, cell: distanceBandHTML },
    { id: "centroids_800", group: "proximity", label: "Centroids ≤800 m", help: "Count of framework estate centroids, not households or served estates.", type: "number", value: row => row.centroids_800m, cell: row => `<span class="centroid-count"><b>${Number(row.centroids_800m)}</b><small>estate centroids</small></span>` },
    { id: "centroids_1400", group: "proximity", label: "Centroids ≤1.4 km", help: "Count of framework estate centroids, not households or served estates.", type: "number", value: row => row.centroids_1400m, cell: row => `<span class="centroid-count"><b>${Number(row.centroids_1400m)}</b><small>estate centroids</small></span>` },
    { id: "association", group: "estate", label: "Context publication", help: "Estate signals are withheld for non-residential constructs, missing outputs or distances over 1.4 km.", type: "association", value: row => row.context_status, cell: associationHTML },
    { id: "archetype", group: "estate", label: "Nearest archetype", help: "Archetype of the nearest centroid; interpretive metadata, not a grade.", type: "text", value: row => row.archetype, cell: archetypeHTML },
    { id: "provision", group: "provision", label: "Band", help: "Objective estate Provision band, repeated as context and never a station score.", type: "band", value: row => row.provision_band, cell: row => contextCell(row, () => bandHTML(row.provision_band)) },
    { id: "provision_score", group: "provision", label: "Approx. score", help: "Estate Provision score. Differences inside ±0.3 are within the framework noise floor.", type: "number", value: row => row.provision_score, cell: row => contextCell(row, () => available(row.provision_score) ? `<span class="muted-value">≈${Number(row.provision_score).toFixed(2)}</span>` : '<span class="status-badge status-missing">Unavailable</span>') },
    { id: "provision_evidence", group: "provision", label: "Evidence state", help: "Flags a measured-only fallback when partly measured inputs were absent and present components were renormalised.", type: "text", value: row => row.measured_only ? "measured_only" : "configured", cell: evidenceHTML },
    { id: "yf0", group: "liveability", label: "Young family · T0", help: "Nearest estate young-family Liveability band at T0; persona-relative.", type: "band", value: row => row.yf0, cell: row => contextCell(row, () => bandHTML(row.yf0)) },
    { id: "sp0", group: "liveability", label: "Professional · T0", help: "Nearest estate single-professional Liveability band at T0; persona-relative.", type: "band", value: row => row.sp0, cell: row => contextCell(row, () => bandHTML(row.sp0)) },
    { id: "ret0", group: "liveability", label: "Retiree · T0", help: "Nearest estate retiree Liveability band at T0; persona-relative.", type: "band", value: row => row.ret0, cell: row => contextCell(row, () => bandHTML(row.ret0)) },
    { id: "ls0", group: "liveability", label: "Lifestyle · T0", help: "Nearest estate lifestyle-seeker Liveability band at T0; persona-relative.", type: "band", value: row => row.ls0, cell: row => contextCell(row, () => bandHTML(row.ls0)) },
    { id: "trajectory", group: "liveability", label: "Lifestyle · T0→T5→T15", help: "Nearest estate lifestyle-seeker band path, not price appreciation or station growth.", type: "number", value: trajectoryNet, cell: trajectoryHTML },
    { id: "hdb_value", group: "hdb", label: "Band & basis", help: "Nearest estate HDB-resale Value band and direct/proxy evidence basis.", type: "band", value: row => row.hdb_value_status === "available" ? row.hdb_value_band : null, cell: row => valueHTML(row, "hdb") },
    { id: "hdb_sample", group: "hdb", label: "Sample", help: `HDB-resale record count; below ${VALUE_TRUST_THRESHOLD}, decimal precision is withheld framework-wide.`, type: "number", value: row => row.hdb_value_status === "available" ? row.hdb_value_n : null, cell: row => sampleHTML(row, "hdb") },
    { id: "private_value", group: "private", label: "Band & basis", help: "Nearest estate private-resale Value band, separate from HDB and project-level analysis.", type: "band", value: row => row.private_value_status === "available" ? row.private_value_band : null, cell: row => valueHTML(row, "private") },
    { id: "private_sample", group: "private", label: "Sample", help: `Private-resale record count; below ${VALUE_TRUST_THRESHOLD}, decimal precision is withheld framework-wide.`, type: "number", value: row => row.private_value_status === "available" ? row.private_value_n : null, cell: row => sampleHTML(row, "private") },
    { id: "employment", group: "context", label: "Employment · T0", help: "Current/T0 employment-access band of the associated estate, not a return forecast.", type: "band", value: row => row.employment_band, cell: employmentHTML },
    { id: "lease", group: "context", label: "HDB lease risk", help: "HDB-specific lease-risk evidence of the associated estate; not private-condo tenure risk.", type: "band", value: row => row.lease_band, cell: leaseHTML },
  ];

  const columnMap = new Map(COLUMNS.map(column => [column.id, column]));
  VIEWS.all = COLUMNS.map(column => column.id);

  const elements = {
    search: document.getElementById("station-search"),
    count: document.getElementById("visible-count"),
    countCopy: document.getElementById("visible-copy"),
    sortStatus: document.getElementById("sort-status"),
    caveat: document.getElementById("view-caveat"),
    tableWrap: document.querySelector(".tbl-wrap"),
    empty: document.getElementById("empty-state"),
    lineList: document.getElementById("line-choice-list"),
    columnGuide: document.getElementById("column-guide-list"),
  };

  const state = {
    query: "",
    view: "overview",
    status: "all",
    mode: "all",
    line: "all",
    sort: "station",
    direction: "asc",
  };

  function visibleColumns() {
    return (VIEWS[state.view] || VIEWS.overview).map(id => columnMap.get(id));
  }

  function renderLines() {
    const button = (key, label, detail = "") => `<button type="button" class="filter-button line-filter-button${state.line === key ? " active" : ""}" data-line="${escapeHTML(key)}" aria-pressed="${state.line === key}"><span>${escapeHTML(label)}</span>${detail ? `<small>${escapeHTML(detail)}</small>` : ""}</button>`;
    elements.lineList.innerHTML = [
      button("all", "All encoded lines", `${rows.length} records`),
      ...lines.map(line => button(line.line_key, line.line_short, `${line.records} · ${line.line}`)),
    ].join("");
  }

  function dataValue(row, column) {
    const contextGroups = new Set(["provision", "liveability", "hdb", "private", "context"]);
    if (contextGroups.has(column.group) && row.context_status !== "available") return null;
    return column.value(row);
  }

  function compareRows(first, second) {
    const column = columnMap.get(state.sort) || columnMap.get("station");
    const a = dataValue(first, column);
    const b = dataValue(second, column);
    const missingA = !available(a);
    const missingB = !available(b);
    if (missingA !== missingB) return missingA ? 1 : -1;
    if (missingA && missingB) return `${first.station} ${first.code}`.localeCompare(`${second.station} ${second.code}`);

    let comparison;
    if (column.type === "number") comparison = Number(a) - Number(b);
    else if (column.type === "band") comparison = (BAND_ORDER[a] ?? -1) - (BAND_ORDER[b] ?? -1);
    else if (column.type === "association") comparison = (ASSOCIATION_ORDER[a] ?? -1) - (ASSOCIATION_ORDER[b] ?? -1);
    else if (column.type === "status") comparison = (STATUS_ORDER[a] ?? -1) - (STATUS_ORDER[b] ?? -1);
    else comparison = String(a).localeCompare(String(b), "en-SG", { numeric: true });
    if (comparison === 0) comparison = `${first.station} ${first.code}`.localeCompare(`${second.station} ${second.code}`, "en-SG", { numeric: true });
    return state.direction === "asc" ? comparison : -comparison;
  }

  function filteredRows() {
    const query = state.query.trim().toLocaleLowerCase("en-SG");
    return rows
      .filter(row => state.status === "all" || row.status === state.status)
      .filter(row => state.mode === "all" || row.mode === state.mode)
      .filter(row => state.line === "all" || row.line_key === state.line)
      .filter(row => !query || [row.station, row.code, row.line, row.network_status, row.planned_opening, row.estate].join(" ").toLocaleLowerCase("en-SG").includes(query))
      .sort(compareRows);
  }

  function groupedColumns(columns) {
    const groups = [];
    columns.forEach(column => {
      const previous = groups.at(-1);
      if (previous?.id === column.group) previous.columns.push(column);
      else groups.push({ id: column.group, columns: [column] });
    });
    return groups;
  }

  function renderHead(columns) {
    const groups = groupedColumns(columns);
    tableHead.innerHTML = `
      <tr class="group-row">${groups.map(group => {
        const metadata = GROUPS[group.id];
        return `<th scope="colgroup" colspan="${group.columns.length}" class="${escapeHTML(metadata.className)}" data-group="${escapeHTML(group.id)}">${escapeHTML(metadata.label)}</th>`;
      }).join("")}</tr>
      <tr class="column-row">${columns.map(column => {
        const active = column.id === state.sort;
        const sort = active ? ` aria-sort="${state.direction === "asc" ? "ascending" : "descending"}"` : "";
        const stationClass = column.id === "station" ? " class=\"station-column\"" : "";
        return `<th scope="col" data-column-key="${escapeHTML(column.id)}"${stationClass}${sort}><button type="button" class="sort-button" data-sort="${escapeHTML(column.id)}" title="${escapeHTML(column.help)}" aria-label="Sort by ${escapeHTML(column.label)}. ${escapeHTML(column.help)}"><span>${escapeHTML(column.label)}</span><span class="sort-mark" aria-hidden="true"></span></button></th>`;
      }).join("")}</tr>`;
  }

  function renderColumnGuide(columns) {
    elements.columnGuide.innerHTML = columns.map(column => `
      <div>
        <dt>${escapeHTML(column.label)}</dt>
        <dd>${escapeHTML(column.help)}</dd>
      </div>`).join("");
  }

  function renderBody(columns, visibleRows) {
    tableBody.innerHTML = visibleRows.map(row => {
      const cells = columns.map(column => {
        const tag = column.id === "station" ? "th" : "td";
        const scope = column.id === "station" ? ' scope="row"' : "";
        const className = [
          column.id === "station" ? "station-cell" : "",
          ["hdb_value", "private_value"].includes(column.id) ? "value-cell" : "",
        ].filter(Boolean).join(" ");
        return `<${tag}${scope}${className ? ` class="${className}"` : ""} data-column-key="${escapeHTML(column.id)}">${column.cell(row)}</${tag}>`;
      }).join("");
      const warning = row.context_status === "available" ? "" : " context-warning";
      return `<tr class="${warning.trim()}" data-status="${escapeHTML(row.status)}" data-mode="${escapeHTML(row.mode)}" data-line="${escapeHTML(row.line_key)}" data-context="${escapeHTML(row.context_status)}">${cells}</tr>`;
    }).join("");
  }

  function sortLabel() {
    const column = columnMap.get(state.sort) || columnMap.get("station");
    if (column.id === "station") return `Station · ${state.direction === "asc" ? "A to Z" : "Z to A"}`;
    return `${column.label} · ${state.direction === "asc" ? "ascending" : "descending"}`;
  }

  function updateButtonState(selector, attribute, value) {
    document.querySelectorAll(selector).forEach(button => {
      const active = button.dataset[attribute] === value;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function keepSortVisible() {
    if (!visibleColumns().some(column => column.id === state.sort)) {
      state.sort = "station";
      state.direction = "asc";
    }
  }

  function restoreControlFocus(focus) {
    if (!focus) return;
    const target = [...document.querySelectorAll(`[data-${focus.key}]`)]
      .find(element => element.dataset[focus.key] === focus.value);
    target?.focus({ preventScroll: true });
  }

  function syncURL() {
    const parameters = new URLSearchParams();
    if (state.query) parameters.set("q", state.query);
    if (state.view !== "overview") parameters.set("view", state.view);
    if (state.status !== "all") parameters.set("status", state.status);
    if (state.mode !== "all") parameters.set("mode", state.mode);
    if (state.line !== "all") parameters.set("line", state.line);
    if (state.sort !== "station" || state.direction !== "asc") parameters.set("sort", state.sort);
    if (state.direction !== "asc") parameters.set("dir", state.direction);
    const query = parameters.toString();
    history.replaceState(null, "", `${location.pathname}${query ? `?${query}` : ""}${location.hash}`);
  }

  function readURL() {
    const parameters = new URLSearchParams(location.search);
    const view = parameters.get("view");
    const status = parameters.get("status");
    const mode = parameters.get("mode");
    const line = parameters.get("line");
    const sort = parameters.get("sort");
    state.query = (parameters.get("q") || "").slice(0, 120);
    state.view = Object.hasOwn(VIEWS, view) ? view : "overview";
    state.status = ["all", "open", "future"].includes(status) ? status : "all";
    state.mode = ["all", "mrt", "lrt"].includes(mode) ? mode : "all";
    state.line = line === "all" || lines.some(item => item.line_key === line) ? line : "all";
    if (state.line !== "all") {
      const selectedLine = lines.find(item => item.line_key === state.line);
      if (selectedLine) state.mode = selectedLine.mode;
    }
    const validSort = columnMap.has(sort);
    state.sort = validSort ? sort : "station";
    state.direction = validSort && parameters.get("dir") === "desc" ? "desc" : "asc";
    elements.search.value = state.query;
    keepSortVisible();
  }

  function render({ updateURL = true, restoreFocus = null } = {}) {
    keepSortVisible();
    const columns = visibleColumns();
    const visibleRows = filteredRows();
    renderHead(columns);
    renderColumnGuide(columns);
    renderBody(columns, visibleRows);
    elements.count.textContent = visibleRows.length.toLocaleString("en-SG");
    elements.countCopy.textContent = `of ${rows.length.toLocaleString("en-SG")} station-code records shown`;
    elements.sortStatus.textContent = sortLabel();
    elements.caveat.textContent = VIEW_CAVEATS[state.view] || VIEW_CAVEATS.overview;
    elements.tableWrap.hidden = visibleRows.length === 0;
    elements.empty.hidden = visibleRows.length !== 0;
    updateButtonState("[data-view]", "view", state.view);
    updateButtonState("button[data-status]", "status", state.status);
    updateButtonState("button[data-mode]", "mode", state.mode);
    updateButtonState("button[data-line]", "line", state.line);
    if (updateURL) syncURL();
    restoreControlFocus(restoreFocus);
  }

  function reset({ focusSearch = true } = {}) {
    Object.assign(state, {
      query: "",
      view: "overview",
      status: "all",
      mode: "all",
      line: "all",
      sort: "station",
      direction: "asc",
    });
    elements.search.value = "";
    render();
    if (focusSearch) elements.search.focus();
  }

  document.getElementById("view-options").addEventListener("click", event => {
    const button = event.target.closest("[data-view]");
    if (!button) return;
    state.view = button.dataset.view;
    keepSortVisible();
    render({ restoreFocus: { key: "view", value: state.view } });
  });

  document.getElementById("status-options").addEventListener("click", event => {
    const button = event.target.closest("[data-status]");
    if (!button) return;
    state.status = button.dataset.status;
    render({ restoreFocus: { key: "status", value: state.status } });
  });

  document.getElementById("mode-options").addEventListener("click", event => {
    const button = event.target.closest("[data-mode]");
    if (!button) return;
    state.mode = button.dataset.mode;
    state.line = "all";
    render({ restoreFocus: { key: "mode", value: state.mode } });
  });

  elements.lineList.addEventListener("click", event => {
    const button = event.target.closest("[data-line]");
    if (!button) return;
    state.line = button.dataset.line;
    const selectedLine = lines.find(line => line.line_key === state.line);
    if (selectedLine) state.mode = selectedLine.mode;
    render({ restoreFocus: { key: "line", value: state.line } });
  });

  elements.search.addEventListener("input", () => {
    state.query = elements.search.value;
    render();
  });

  tableHead.addEventListener("click", event => {
    const button = event.target.closest("[data-sort]");
    if (!button) return;
    if (state.sort === button.dataset.sort) state.direction = state.direction === "asc" ? "desc" : "asc";
    else {
      state.sort = button.dataset.sort;
      state.direction = "asc";
    }
    render({ restoreFocus: { key: "sort", value: state.sort } });
  });

  document.getElementById("reset-view").addEventListener("click", () => reset());
  document.getElementById("empty-reset").addEventListener("click", () => reset());
  window.addEventListener("popstate", () => {
    readURL();
    render({ updateURL: true });
  });

  renderLines();
  readURL();
  render();
})();
