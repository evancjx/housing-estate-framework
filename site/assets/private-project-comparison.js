(() => {
  "use strict";

  const dataElement = document.getElementById("private-project-comparison-data");
  const configElement = document.getElementById("private-project-comparison-config");
  const tableHead = document.getElementById("private-project-table-head");
  const tableBody = document.getElementById("private-project-table-body");
  if (!dataElement || !configElement || !tableHead || !tableBody) return;

  const elements = {
    search: document.getElementById("project-search"),
    count: document.getElementById("visible-count"),
    countCopy: document.getElementById("visible-copy"),
    views: document.getElementById("view-options"),
    district: document.getElementById("district-filter"),
    station: document.getElementById("station-filter"),
    sale: document.getElementById("sale-filter"),
    source: document.getElementById("source-filter"),
    primary: document.getElementById("primary-filter"),
    reset: document.getElementById("reset-view"),
    tableWrap: document.getElementById("table-wrap"),
    sortStatus: document.getElementById("sort-status"),
    caveat: document.getElementById("view-caveat"),
    columnGuide: document.getElementById("column-guide-list"),
    empty: document.getElementById("empty-state"),
    emptyReset: document.getElementById("empty-reset"),
    renderedCopy: document.getElementById("rendered-copy"),
    showMore: document.getElementById("show-more"),
  };

  let rows;
  let config;
  try {
    rows = JSON.parse(dataElement.textContent || "[]");
    config = JSON.parse(configElement.textContent || "{}");
    if (!Array.isArray(rows) || !config || typeof config !== "object" || Array.isArray(config)) {
      throw new TypeError("The embedded project payload has an unexpected shape.");
    }
  } catch (error) {
    if (elements.caveat) {
      elements.caveat.textContent = `The project evidence could not be loaded: ${error.message}`;
    }
    if (elements.tableWrap) elements.tableWrap.hidden = true;
    if (elements.empty) {
      elements.empty.hidden = false;
      const heading = elements.empty.querySelector("h3");
      const copy = elements.empty.querySelector("p");
      if (heading) heading.textContent = "Project evidence unavailable.";
      if (copy) copy.textContent = "Reload the page or regenerate the project explorer.";
      if (elements.emptyReset) elements.emptyReset.hidden = true;
    }
    return;
  }

  const configuredPageSize = Number(config.page_size);
  const pageSize = Number.isInteger(configuredPageSize) && configuredPageSize > 0 && configuredPageSize <= 500
    ? configuredPageSize
    : 100;
  const trustThreshold = Number.isFinite(Number(config.value_trust_threshold))
    ? Number(config.value_trust_threshold)
    : 100;
  const recentMonths = Number.isFinite(Number(config.recent_window_months))
    ? Number(config.recent_window_months)
    : 12;
  const BAND_ORDER = { F: 1, D: 2, C: 3, B: 4, "B+": 5, A: 6 };

  const GROUPS = {
    identity: {
      label: "Project identity",
      className: "group-project",
    },
    access: {
      label: "Access diagnostics",
      className: "group-access",
    },
    schools: {
      label: "School-radius diagnostics",
      className: "group-schools",
    },
    price: {
      label: "Achieved price evidence",
      className: "group-price",
    },
    transactions: {
      label: "Transaction profile",
      className: "group-transactions",
    },
    context: {
      label: "Surrounding-estate context",
      className: "group-context",
    },
  };

  const VIEWS = {
    overview: [
      "project", "district", "planning_area", "station", "station_distance_m",
      "primary_access", "median_price_mil", "median_area_sqm", "median_psm",
      "n", "recent_delta_pct", "context_area", "provision_band", "private_value_band",
    ],
    access: [
      "project", "street", "district", "planning_area", "station", "line",
      "station_distance_m", "location_source", "geocode",
    ],
    schools: [
      "project", "district", "primary_access", "primary_1km_schools",
      "best_primary_1km_school", "best_primary_1km_rank", "best_primary_1km_distance_m",
      "secondary_2km_count", "best_secondary_2km_school", "best_secondary_2km_rank",
      "best_secondary_2km_distance_m", "jc_5km_count", "best_jc_5km_school",
      "best_jc_5km_rank", "best_jc_5km_distance_m", "school_metrics_source",
    ],
    price: [
      "project", "district", "planning_area", "median_price_mil", "median_area_sqm",
      "median_psm", "district_delta_pct", "area_delta_pct", "recent_median_psm",
      "recent_delta_pct", "n", "recent_n",
    ],
    transactions: [
      "project", "district", "property_type", "n", "recent_n", "first_sale",
      "last_sale", "sale_mix", "tenure", "market_segment",
    ],
    context: [
      "project", "district", "planning_area", "context_area", "context_status",
      "archetype", "context_basis",
      "provision_band", "provision_score", "private_value_band", "private_value_score",
      "private_value_n",
    ],
  };

  const VIEW_CAVEATS = {
    overview: "Overview keeps achieved transactions, project access and surrounding-estate context visibly separate. No overall project rank is calculated.",
    access: "Distances are straight-line diagnostics to an operational MRT/LRT station. A centroid fallback is not a project-level distance or walking time.",
    schools: "School radii use matched project coordinates where available. Selectivity ranks are sourced screening proxies; verify current MOE boundaries and eligibility independently.",
    price: `Project medians mix unit sizes, layouts, floors and sale states. Recent vs all uses the latest ${recentMonths} months, is mix-sensitive and is not an appreciation rate.`,
    transactions: "Samples combine the observed unit and sale mix within each grouped project row. Small or old samples require a like-for-like transaction check.",
    context: "Provision and private Value belong to the surrounding estate, not the condominium. They remain separate evidence lenses and are not project scores or return forecasts.",
  };

  const escapeHTML = value => String(value ?? "").replace(
    /[&<>"']/g,
    character => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[character]
  );

  function available(value) {
    return value !== null && value !== undefined && value !== "" && value !== "-";
  }

  function finiteNumber(value) {
    if (!available(value)) return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function titleCase(value) {
    if (!available(value)) return "Unavailable";
    return String(value)
      .toLocaleLowerCase("en-SG")
      .replace(/(^|[\s/(-])\S/g, match => match.toLocaleUpperCase("en-SG"))
      .replace(/\bMrt\b/g, "MRT")
      .replace(/\bLrt\b/g, "LRT")
      .replace(/\bHdb\b/g, "HDB")
      .replace(/\bJc\b/g, "JC");
  }

  function missingHTML(label = "Unavailable") {
    return `<span class="status-badge status-missing">${escapeHTML(label)}</span>`;
  }

  function plainHTML(value, { title = false } = {}) {
    if (!available(value)) return missingHTML();
    return escapeHTML(title ? titleCase(value) : value);
  }

  function stackHTML(primary, secondary = "", left = false) {
    return `<span class="cell-stack${left ? " cell-stack-left" : ""}">${primary}${secondary ? `<small class="cell-sub">${secondary}</small>` : ""}</span>`;
  }

  function integerHTML(value) {
    const number = finiteNumber(value);
    return number !== null
      ? `<span class="numeric-value">${number.toLocaleString("en-SG")}</span>`
      : missingHTML();
  }

  function distanceHTML(value, note = "straight-line") {
    const number = finiteNumber(value);
    if (number === null) return missingHTML();
    const className = number <= 500 ? "distance-near" : number <= 1000 ? "distance-mid" : "distance-far";
    return stackHTML(
      `<span class="distance-badge ${className}">${Math.round(number).toLocaleString("en-SG")} m</span>`,
      escapeHTML(note)
    );
  }

  function moneyPSMHTML(value) {
    const number = finiteNumber(value);
    return number !== null
      ? `<span class="money-value">S$${Math.round(number).toLocaleString("en-SG")} / m²</span>`
      : missingHTML();
  }

  function moneyMillionHTML(value) {
    const number = finiteNumber(value);
    return number !== null
      ? `<span class="money-value">S$${number.toFixed(2)}m</span>`
      : missingHTML();
  }

  function areaHTML(value) {
    const number = finiteNumber(value);
    return number !== null
      ? `<span class="numeric-value">${Math.round(number).toLocaleString("en-SG")} m²</span>`
      : missingHTML();
  }

  function deltaHTML(value, note = "") {
    const number = finiteNumber(value);
    if (number === null) return missingHTML();
    const className = number > 0 ? "delta-positive" : number < 0 ? "delta-negative" : "delta-flat";
    const primary = `<span class="${className}">${number > 0 ? "+" : ""}${number.toFixed(1)}%</span>`;
    return note ? stackHTML(primary, escapeHTML(note)) : primary;
  }

  function bandHTML(value) {
    if (!available(value)) return missingHTML("Not covered");
    const className = value === "B+" ? "band-Bp" : `band-${String(value).toLocaleUpperCase("en-SG")}`;
    return `<span class="band ${escapeHTML(className)}">${escapeHTML(value)}</span>`;
  }

  function projectHTML(row) {
    return stackHTML(
      `<strong>${escapeHTML(titleCase(row.project))}</strong>`,
      available(row.street) ? escapeHTML(titleCase(row.street)) : "Street unavailable",
      true
    );
  }

  function districtHTML(row) {
    return available(row.district)
      ? `<span class="numeric-value">D${escapeHTML(row.district)}</span>`
      : missingHTML();
  }

  function stationHTML(row) {
    if (!available(row.station)) return missingHTML("Station unavailable");
    const code = available(row.station_code) ? escapeHTML(row.station_code) : "Code unavailable";
    const status = row.station_status === "Open" ? "Operational" : titleCase(row.station_status);
    return stackHTML(`<strong>${escapeHTML(titleCase(row.station))}</strong>`, `${code} · ${escapeHTML(status)}`);
  }

  function lineHTML(row) {
    if (!available(row.line_short)) return missingHTML();
    return stackHTML(`<span class="status-badge">${escapeHTML(row.line_short)}</span>`, available(row.line) ? escapeHTML(titleCase(row.line)) : "");
  }

  function locationSourceHTML(row) {
    if (row.location_source === "project_geocode") {
      return stackHTML('<span class="source-badge source-geocode">Project geocode</span>', "project-level spatial diagnostic");
    }
    if (row.location_source === "centroid_proxy") {
      return stackHTML('<span class="source-badge source-proxy">Estate-centroid fallback</span>', "not a project-level distance");
    }
    return missingHTML("Source unavailable");
  }

  function geocodeHTML(row) {
    if (row.location_source !== "project_geocode") return missingHTML("No project geocode");
    const status = available(row.geocode_status) ? titleCase(row.geocode_status) : "Matched";
    const score = finiteNumber(row.geocode_score);
    return stackHTML(
      `<span class="status-badge status-good">${escapeHTML(status)}</span>`,
      score !== null ? `OneMap match score ${score.toLocaleString("en-SG")}` : "score unavailable"
    );
  }

  function schoolEvidenceAvailable(row) {
    return row.school_metrics_source === "project_geocode";
  }

  function primaryAccessHTML(row) {
    if (!schoolEvidenceAvailable(row) || row.has_primary_1km === null || row.has_primary_1km === undefined) {
      return missingHTML("School evidence unavailable");
    }
    if (row.has_primary_1km === false) {
      return stackHTML('<span class="status-badge status-warning">None found</span>', "within 1 km straight-line radius");
    }
    const count = finiteNumber(row.primary_1km_count);
    const countCopy = count !== null ? `${count.toLocaleString("en-SG")} school${count === 1 ? "" : "s"}` : "school found";
    const ranked = row.has_ranked_primary_1km === true ? " · ranked proxy present" : "";
    return stackHTML('<span class="status-badge status-good">Within 1 km</span>', `${escapeHTML(countCopy)}${ranked}`);
  }

  function schoolListHTML(row) {
    if (!schoolEvidenceAvailable(row)) return missingHTML("School evidence unavailable");
    if (row.has_primary_1km === false) {
      return stackHTML(
        '<span class="status-badge status-warning">None found</span>',
        "measured within 1 km straight-line radius"
      );
    }
    return available(row.primary_1km_schools)
      ? stackHTML(`<span>${escapeHTML(titleCase(row.primary_1km_schools))}</span>`, "within 1 km straight-line radius", true)
      : missingHTML("School list unavailable");
  }

  function schoolHTML(value, count, radius) {
    const number = finiteNumber(count);
    if (!available(value)) {
      if (number === 0) return missingHTML(`None within ${radius}`);
      return missingHTML();
    }
    return stackHTML(`<strong>${escapeHTML(titleCase(value))}</strong>`, `selectivity proxy within ${escapeHTML(radius)}`, true);
  }

  function rankHTML(value) {
    const number = finiteNumber(value);
    return number !== null
      ? stackHTML(`<span class="numeric-value">#${number.toLocaleString("en-SG")}</span>`, "sourced selectivity proxy")
      : missingHTML("No ranked proxy");
  }

  function schoolSourceHTML(row) {
    return schoolEvidenceAvailable(row)
      ? stackHTML('<span class="source-badge source-geocode">Project-coordinate metrics</span>', "radius diagnostic")
      : missingHTML("School evidence unavailable");
  }

  function contextAreaHTML(row) {
    if (!available(row.context_area)) return missingHTML("Context unavailable");
    return stackHTML(`<strong>${escapeHTML(titleCase(row.context_area))}</strong>`, "surrounding-estate context only", true);
  }

  function contextBasisHTML(row) {
    if (row.context_basis === "direct") {
      return stackHTML('<span class="source-badge source-project">Direct area match</span>', "estate-level join");
    }
    if (available(row.context_basis)) {
      return stackHTML('<span class="source-badge source-proxy">Proxy context</span>', escapeHTML(String(row.context_basis).replace(/^proxy:/, "from ")));
    }
    return missingHTML();
  }

  function contextStatusHTML(row) {
    if (row.context_status === "not_residential") {
      return stackHTML('<span class="status-badge status-warning">N/R</span>', "non-residential framework gate");
    }
    if (row.context_status === "available") {
      return stackHTML('<span class="status-badge status-good">Available</span>', "surrounding-estate context");
    }
    return missingHTML("Context unavailable");
  }

  function archetypeHTML(row) {
    if (row.context_status === "not_residential") {
      return stackHTML('<span class="status-badge status-warning">X · Not rated</span>', "model fields withheld");
    }
    return available(row.archetype)
      ? stackHTML(`<span class="status-badge">${escapeHTML(row.archetype)}</span>`, "interpretive metadata · not a grade")
      : missingHTML("Not recorded");
  }

  function contextBandHTML(row, key) {
    if (row.context_status === "not_residential") return missingHTML("N/R");
    return bandHTML(row[key]);
  }

  function provisionScoreHTML(row) {
    if (row.context_status === "not_residential") return missingHTML("N/R");
    const number = finiteNumber(row.provision_score);
    return number !== null
      ? stackHTML(`<span class="numeric-value">≈${number.toFixed(2)}</span>`, "estate score · ±0.3 noise floor")
      : missingHTML("Not covered");
  }

  function privateValueScoreHTML(row) {
    if (row.context_status === "not_residential") return missingHTML("N/R");
    const score = finiteNumber(row.private_value_score);
    const sample = finiteNumber(row.private_value_n);
    if (sample !== null && sample < trustThreshold) {
      return stackHTML('<span class="sample-warning">Band only</span>', `decimal withheld · n<${trustThreshold}`);
    }
    if (score === null) return missingHTML("Not covered");
    return stackHTML(`<span class="numeric-value">${score.toFixed(2)} / 5</span>`, "estate private Value score · not a multiplier");
  }

  function privateSampleHTML(row) {
    if (row.context_status === "not_residential") return missingHTML("N/R");
    const number = finiteNumber(row.private_value_n);
    if (number === null) return missingHTML("Not covered");
    const primary = `<span class="numeric-value">n=${number.toLocaleString("en-SG")}</span>`;
    return number < trustThreshold
      ? stackHTML(primary, `thin sample · band only below ${trustThreshold}`)
      : stackHTML(primary, "estate private-resale records");
  }

  const COLUMNS = [
    { id: "project", group: "identity", label: "Project", help: "URA project name, grouped with street, district and planning area. No overall rank is calculated.", type: "text", value: row => row.project, cell: projectHTML },
    { id: "street", group: "identity", label: "Street", help: "Street reported in the committed URA transaction snapshot.", type: "text", value: row => row.street, cell: row => plainHTML(row.street, { title: true }) },
    { id: "property_type", group: "identity", label: "Dominant type", help: "Most frequently reported private property type in the grouped project record.", type: "text", value: row => row.property_type, cell: row => plainHTML(row.property_type, { title: true }) },
    { id: "district", group: "identity", label: "Postal district", help: "Postal district from the transaction record; it is not a project ranking segment.", type: "text", value: row => row.district, cell: districtHTML },
    { id: "planning_area", group: "identity", label: "Planning area", help: "Planning area used to attach separately labelled estate framework context.", type: "text", value: row => row.planning_area, cell: row => plainHTML(row.planning_area, { title: true }) },

    { id: "station", group: "access", label: "Nearest operational MRT/LRT", help: "Nearest operational station from the project point or disclosed estate-centroid fallback.", type: "text", value: row => row.station, cell: stationHTML },
    { id: "line", group: "access", label: "Rail line", help: "Encoded rail line for the nearest operational station membership.", type: "text", value: row => row.line, cell: lineHTML },
    { id: "station_distance_m", group: "access", label: "Straight-line distance", help: "Great-circle project-to-station distance in metres; fallback rows instead measure from an estate centroid. It is not walking time.", type: "number", value: row => row.station_distance_m, cell: row => distanceHTML(row.station_distance_m, row.location_source === "project_geocode" ? "project point to station" : "centroid proxy · not project distance") },
    { id: "location_source", group: "access", label: "Location source", help: "Distinguishes matched project geocodes from estate-centroid fallbacks.", type: "text", value: row => row.location_source, cell: locationSourceHTML },
    { id: "geocode", group: "access", label: "Geocode evidence", help: "OneMap match status and score when a project geocode is available.", type: "number", value: row => row.location_source === "project_geocode" ? row.geocode_score : null, cell: geocodeHTML },

    { id: "primary_access", group: "schools", label: "Primary schools ≤1 km", help: "Whether the matched project point has at least one primary school within a 1 km straight-line radius; not an admissions guarantee.", type: "boolean", value: row => schoolEvidenceAvailable(row) ? row.has_primary_1km : null, cell: primaryAccessHTML },
    { id: "primary_1km_schools", group: "schools", label: "Primary-school list", help: "Primary schools found within 1 km of the matched project coordinate. A measured zero remains distinct from unavailable evidence.", type: "text", value: row => row.primary_1km_schools, cell: schoolListHTML },
    { id: "best_primary_1km_school", group: "schools", label: "Primary proxy", help: "Best sourced selectivity proxy among primary schools within 1 km; not a project or admissions rank.", type: "text", value: row => row.best_primary_1km_school, cell: row => schoolHTML(row.best_primary_1km_school, row.primary_1km_count, "1 km") },
    { id: "best_primary_1km_rank", group: "schools", label: "Primary proxy rank", help: "Sourced selectivity-proxy rank; lower does not make the condominium universally better.", type: "number", value: row => row.best_primary_1km_rank, cell: row => rankHTML(row.best_primary_1km_rank) },
    { id: "best_primary_1km_distance_m", group: "schools", label: "Primary distance", help: "Straight-line distance to the selected primary-school proxy.", type: "number", value: row => row.best_primary_1km_distance_m, cell: row => distanceHTML(row.best_primary_1km_distance_m, "project point to school") },
    { id: "secondary_2km_count", group: "schools", label: "Secondary count ≤2 km", help: "Secondary schools found within a 2 km straight-line radius.", type: "number", value: row => row.secondary_2km_count, cell: row => integerHTML(row.secondary_2km_count) },
    { id: "best_secondary_2km_school", group: "schools", label: "Secondary proxy", help: "Best sourced selectivity proxy among secondary schools within 2 km.", type: "text", value: row => row.best_secondary_2km_school, cell: row => schoolHTML(row.best_secondary_2km_school, row.secondary_2km_count, "2 km") },
    { id: "best_secondary_2km_rank", group: "schools", label: "Secondary proxy rank", help: "Sourced selectivity-proxy rank, not a project score.", type: "number", value: row => row.best_secondary_2km_rank, cell: row => rankHTML(row.best_secondary_2km_rank) },
    { id: "best_secondary_2km_distance_m", group: "schools", label: "Secondary distance", help: "Straight-line distance to the selected secondary-school proxy.", type: "number", value: row => row.best_secondary_2km_distance_m, cell: row => distanceHTML(row.best_secondary_2km_distance_m, "project point to school") },
    { id: "jc_5km_count", group: "schools", label: "JC count ≤5 km", help: "Junior colleges or Year 5 schools found within a 5 km straight-line radius.", type: "number", value: row => row.jc_5km_count, cell: row => integerHTML(row.jc_5km_count) },
    { id: "best_jc_5km_school", group: "schools", label: "JC proxy", help: "Best sourced selectivity proxy among junior colleges or Year 5 schools within 5 km.", type: "text", value: row => row.best_jc_5km_school, cell: row => schoolHTML(row.best_jc_5km_school, row.jc_5km_count, "5 km") },
    { id: "best_jc_5km_rank", group: "schools", label: "JC proxy rank", help: "Sourced selectivity-proxy rank, not a project score.", type: "number", value: row => row.best_jc_5km_rank, cell: row => rankHTML(row.best_jc_5km_rank) },
    { id: "best_jc_5km_distance_m", group: "schools", label: "JC distance", help: "Straight-line distance to the selected junior-college proxy.", type: "number", value: row => row.best_jc_5km_distance_m, cell: row => distanceHTML(row.best_jc_5km_distance_m, "project point to school") },
    { id: "school_metrics_source", group: "schools", label: "School evidence source", help: "School-radius metrics require a matched project coordinate; missing states are not treated as no schools.", type: "text", value: row => row.school_metrics_source, cell: schoolSourceHTML },

    { id: "median_price_mil", group: "price", label: "Median price", help: "Median achieved transaction quantum across mixed unit sizes, layouts, floors and sale states.", type: "number", value: row => row.median_price_mil, cell: row => moneyMillionHTML(row.median_price_mil) },
    { id: "median_area_sqm", group: "price", label: "Median area", help: "Median transacted unit area; use it to detect mix differences, not as a layout match.", type: "number", value: row => row.median_area_sqm, cell: row => areaHTML(row.median_area_sqm) },
    { id: "median_psm", group: "price", label: "Median S$/m²", help: "Full-window median achieved price per square metre for the grouped project record.", type: "number", value: row => row.median_psm, cell: row => moneyPSMHTML(row.median_psm) },
    { id: "district_delta_pct", group: "price", label: "Vs district", help: "Project median S$/m² versus the mixed postal-district median; a screening comparison, not a controlled valuation.", type: "number", value: row => row.district_delta_pct, cell: row => deltaHTML(row.district_delta_pct, "vs mixed district median") },
    { id: "area_delta_pct", group: "price", label: "Vs planning area", help: "Project median S$/m² versus the mixed planning-area median.", type: "number", value: row => row.area_delta_pct, cell: row => deltaHTML(row.area_delta_pct, "vs mixed area median") },
    { id: "recent_median_psm", group: "price", label: "Recent median S$/m²", help: `Median achieved S$/m² in the latest ${recentMonths}-month window; inspect recent n.`, type: "number", value: row => row.recent_median_psm, cell: row => moneyPSMHTML(row.recent_median_psm) },
    { id: "recent_delta_pct", group: "price", label: "Recent vs all", help: `Recent ${recentMonths}-month median versus the full observed project median. It is mix-sensitive and is not an appreciation rate.`, type: "number", value: row => row.recent_delta_pct, cell: row => deltaHTML(row.recent_delta_pct, "mix-sensitive · not appreciation") },

    { id: "n", group: "transactions", label: "Transactions", help: "Total achieved transaction count in the grouped project record.", type: "number", value: row => row.n, cell: row => integerHTML(row.n) },
    { id: "recent_n", group: "transactions", label: "Recent transactions", help: `Achieved transaction count in the latest ${recentMonths}-month comparison window.`, type: "number", value: row => row.recent_n, cell: row => integerHTML(row.recent_n) },
    { id: "first_sale", group: "transactions", label: "First observed", help: "Earliest transaction month in the committed project sample, not the project completion date.", type: "text", value: row => row.first_sale, cell: row => plainHTML(row.first_sale) },
    { id: "last_sale", group: "transactions", label: "Latest observed", help: "Latest transaction month in the committed project sample.", type: "text", value: row => row.last_sale, cell: row => plainHTML(row.last_sale) },
    { id: "sale_mix", group: "transactions", label: "Sale mix", help: "Counts of new-sale, resale and sub-sale records present in the grouped sample.", type: "text", value: row => row.sale_mix, cell: row => stackHTML(`<span>${escapeHTML(row.sale_mix || "Unknown")}</span>`, "observed sale states", true) },
    { id: "tenure", group: "transactions", label: "Dominant tenure", help: "Most frequently reported tenure text in the grouped transactions.", type: "text", value: row => row.tenure, cell: row => plainHTML(row.tenure, { title: true }) },
    { id: "market_segment", group: "transactions", label: "Market segment", help: "Most frequently reported URA market segment in the grouped transactions.", type: "text", value: row => row.market_segment, cell: row => plainHTML(row.market_segment) },

    { id: "context_area", group: "context", label: "Context estate", help: "Estate/planning-area context used for framework joins. It is context for the project, not a project score.", type: "text", value: row => row.context_area, cell: contextAreaHTML },
    { id: "context_status", group: "context", label: "Framework status", help: "Whether surrounding-estate model context is available, unavailable or gated as non-residential.", type: "text", value: row => row.context_status, cell: contextStatusHTML },
    { id: "archetype", group: "context", label: "Estate archetype", help: "Interpretive surrounding-estate metadata, not a condominium grade. X rows are not rated and publish no model fields.", type: "text", value: row => row.archetype, cell: archetypeHTML },
    { id: "context_basis", group: "context", label: "Context basis", help: "Direct planning-area match or explicitly labelled proxy used for the estate-level join.", type: "text", value: row => row.context_basis, cell: contextBasisHTML },
    { id: "provision_band", group: "context", label: "Provision band", help: "Objective surrounding-estate Provision band. It is not a condominium grade and is withheld for X rows.", type: "band", value: row => row.provision_band, cell: row => contextBandHTML(row, "provision_band") },
    { id: "provision_score", group: "context", label: "Provision score", help: "Approximate surrounding-estate Provision score; differences within ±0.3 are inside the framework noise floor.", type: "number", value: row => row.provision_score, cell: provisionScoreHTML },
    { id: "private_value_band", group: "context", label: "Private Value band", help: "Surrounding-estate private-resale Value band, separate from HDB, not a project score and withheld for X rows.", type: "band", value: row => row.private_value_band, cell: row => contextBandHTML(row, "private_value_band") },
    { id: "private_value_score", group: "context", label: "Private Value score", help: `Surrounding-estate private Value score on the framework's 1–5 scale. It is not a price multiplier; decimal precision is withheld below ${trustThreshold} records.`, type: "number", value: row => finiteNumber(row.private_value_n) >= trustThreshold ? row.private_value_score : null, cell: privateValueScoreHTML },
    { id: "private_value_n", group: "context", label: "Private Value sample", help: `Surrounding-estate private-resale sample; below ${trustThreshold}, report the band rather than decimal precision.`, type: "number", value: row => row.private_value_n, cell: privateSampleHTML },
  ];

  const columnMap = new Map(COLUMNS.map(column => [column.id, column]));
  const state = {
    query: "",
    view: "overview",
    district: "all",
    station: "all",
    sale: "all",
    source: "all",
    primary: "all",
    sort: "project",
    direction: "asc",
  };
  let renderLimit = pageSize;

  function visibleColumns() {
    return (VIEWS[state.view] || VIEWS.overview).map(id => columnMap.get(id)).filter(Boolean);
  }

  function isMissing(value) {
    return !available(value) || (typeof value === "number" && !Number.isFinite(value));
  }

  function compareRows(first, second) {
    const column = columnMap.get(state.sort) || columnMap.get("project");
    const firstValue = column.value(first);
    const secondValue = column.value(second);
    const firstMissing = isMissing(firstValue);
    const secondMissing = isMissing(secondValue);
    if (firstMissing !== secondMissing) return firstMissing ? 1 : -1;

    let comparison = 0;
    if (!firstMissing) {
      if (column.type === "number") comparison = Number(firstValue) - Number(secondValue);
      else if (column.type === "band") comparison = (BAND_ORDER[firstValue] ?? -1) - (BAND_ORDER[secondValue] ?? -1);
      else if (column.type === "boolean") comparison = Number(firstValue) - Number(secondValue);
      else comparison = String(firstValue).localeCompare(String(secondValue), "en-SG", { numeric: true, sensitivity: "base" });
    }
    if (comparison !== 0) return state.direction === "asc" ? comparison : -comparison;
    return `${first.project || ""} ${first.street || ""}`.localeCompare(
      `${second.project || ""} ${second.street || ""}`,
      "en-SG",
      { numeric: true, sensitivity: "base" }
    );
  }

  function matchesPrimary(row) {
    if (state.primary === "all") return true;
    if (state.primary === "has") return row.has_primary_1km === true;
    if (state.primary === "ranked") return row.has_ranked_primary_1km === true;
    if (state.primary === "none") {
      return row.school_metrics_source === "project_geocode" && row.has_primary_1km === false;
    }
    if (state.primary === "missing") return row.school_metrics_source !== "project_geocode";
    return true;
  }

  function filteredRows() {
    const query = state.query.trim().toLocaleLowerCase("en-SG");
    return rows
      .filter(row => state.district === "all" || String(row.district) === state.district)
      .filter(row => state.station === "all" || String(row.station_key) === state.station)
      .filter(row => state.sale === "all" || String(row.sale_mix || "").includes(state.sale))
      .filter(row => state.source === "all" || row.location_source === state.source)
      .filter(matchesPrimary)
      .filter(row => !query || [
        row.project, row.street, row.district, row.planning_area, row.station,
        row.station_code, row.line, row.property_type, row.tenure, row.market_segment,
        row.sale_mix, row.context_area, row.primary_1km_schools,
        row.best_primary_1km_school, row.best_secondary_2km_school, row.best_jc_5km_school,
      ].join(" ").toLocaleLowerCase("en-SG").includes(query))
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
        const active = state.sort === column.id;
        const ariaSort = active ? ` aria-sort="${state.direction === "asc" ? "ascending" : "descending"}"` : "";
        const className = column.id === "project" ? ' class="project-column"' : "";
        return `<th scope="col" data-column-key="${escapeHTML(column.id)}" data-group="${escapeHTML(column.group)}"${className}${ariaSort}><button type="button" class="sort-button" data-sort="${escapeHTML(column.id)}" title="${escapeHTML(column.help)}" aria-label="Sort by ${escapeHTML(column.label)}. ${escapeHTML(column.help)}"><span>${escapeHTML(column.label)}</span><span class="sort-mark" aria-hidden="true"></span></button></th>`;
      }).join("")}</tr>`;
  }

  function renderColumnGuide(columns) {
    if (!elements.columnGuide) return;
    elements.columnGuide.innerHTML = columns.map(column => `
      <div>
        <dt>${escapeHTML(column.label)}</dt>
        <dd>${escapeHTML(column.help)}</dd>
      </div>`).join("");
  }

  function renderBody(columns, visibleRows) {
    tableBody.innerHTML = visibleRows.map(row => {
      const cells = columns.map(column => {
        const rowHeader = column.id === "project";
        const tag = rowHeader ? "th" : "td";
        const scope = rowHeader ? ' scope="row"' : "";
        const className = rowHeader ? ' class="project-cell"' : "";
        const columnKey = rowHeader ? "" : ` data-column-key="${escapeHTML(column.id)}"`;
        return `<${tag}${scope}${className}${columnKey} data-group="${escapeHTML(column.group)}">${column.cell(row)}</${tag}>`;
      }).join("");
      return `<tr data-district="${escapeHTML(row.district)}" data-station="${escapeHTML(row.station_key)}" data-source="${escapeHTML(row.location_source)}">${cells}</tr>`;
    }).join("");
  }

  function sortLabel() {
    const column = columnMap.get(state.sort) || columnMap.get("project");
    if (column.id === "project") return `Project · ${state.direction === "asc" ? "A to Z" : "Z to A"}`;
    return `${column.label} · ${state.direction === "asc" ? "ascending" : "descending"}`;
  }

  function selectHasValue(select, value) {
    return Boolean(select && [...select.options].some(option => option.value === value));
  }

  function syncControls() {
    if (elements.search) elements.search.value = state.query;
    for (const key of ["district", "station", "sale", "source", "primary"]) {
      if (elements[key]) elements[key].value = state[key];
    }
    document.querySelectorAll("#view-options [data-view]").forEach(button => {
      const active = button.dataset.view === state.view;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  function keepSortVisible() {
    if (!visibleColumns().some(column => column.id === state.sort)) {
      state.sort = "project";
      state.direction = "asc";
    }
  }

  function syncURL() {
    const parameters = new URLSearchParams();
    if (state.query) parameters.set("q", state.query);
    if (state.view !== "overview") parameters.set("view", state.view);
    if (state.district !== "all") parameters.set("district", state.district);
    if (state.station !== "all") parameters.set("station", state.station);
    if (state.sale !== "all") parameters.set("sale", state.sale);
    if (state.source !== "all") parameters.set("source", state.source);
    if (state.primary !== "all") parameters.set("primary", state.primary);
    if (state.sort !== "project" || state.direction !== "asc") parameters.set("sort", state.sort);
    if (state.direction !== "asc") parameters.set("dir", state.direction);
    const query = parameters.toString();
    history.replaceState(null, "", `${location.pathname}${query ? `?${query}` : ""}${location.hash}`);
  }

  function readURL() {
    const parameters = new URLSearchParams(location.search);
    const view = parameters.get("view");
    const districtRaw = String(parameters.get("district") || "").replace(/^D/i, "");
    const district = /^\d+$/.test(districtRaw) ? districtRaw.padStart(2, "0") : districtRaw;
    const station = parameters.get("station");
    const sale = parameters.get("sale");
    const source = parameters.get("source");
    const primary = parameters.get("primary");
    const sort = parameters.get("sort");

    state.query = (parameters.get("q") || "").slice(0, 160);
    state.view = Object.hasOwn(VIEWS, view) ? view : "overview";
    state.district = selectHasValue(elements.district, district) ? district : "all";
    state.station = selectHasValue(elements.station, station) ? station : "all";
    state.sale = selectHasValue(elements.sale, sale) ? sale : "all";
    state.source = selectHasValue(elements.source, source) ? source : "all";
    state.primary = selectHasValue(elements.primary, primary) ? primary : "all";
    state.sort = columnMap.has(sort) ? sort : "project";
    state.direction = columnMap.has(sort) && parameters.get("dir") === "desc" ? "desc" : "asc";
    keepSortVisible();
    syncControls();
  }

  function restoreHeaderFocus(sort) {
    if (!sort) return;
    tableHead.querySelector(`[data-sort="${CSS.escape(sort)}"]`)?.focus({ preventScroll: true });
  }

  function render({ updateURL = true, resetBatch = false, focusSort = null } = {}) {
    keepSortVisible();
    if (resetBatch) renderLimit = pageSize;
    const columns = visibleColumns();
    const matchingRows = filteredRows();
    const renderedRows = matchingRows.slice(0, renderLimit);
    renderHead(columns);
    renderColumnGuide(columns);
    renderBody(columns, renderedRows);
    syncControls();

    if (elements.count) elements.count.textContent = matchingRows.length.toLocaleString("en-SG");
    if (elements.countCopy) {
      elements.countCopy.textContent = `of ${rows.length.toLocaleString("en-SG")} projects match`;
    }
    if (elements.sortStatus) elements.sortStatus.textContent = sortLabel();
    if (elements.caveat) elements.caveat.textContent = VIEW_CAVEATS[state.view] || VIEW_CAVEATS.overview;
    if (elements.renderedCopy) {
      elements.renderedCopy.textContent = matchingRows.length
        ? `Showing ${renderedRows.length.toLocaleString("en-SG")} of ${matchingRows.length.toLocaleString("en-SG")} matching projects.`
        : "No matching projects to render.";
    }
    if (elements.showMore) elements.showMore.hidden = renderedRows.length >= matchingRows.length;
    if (elements.tableWrap) elements.tableWrap.hidden = matchingRows.length === 0;
    if (elements.empty) elements.empty.hidden = matchingRows.length !== 0;
    if (updateURL) syncURL();
    restoreHeaderFocus(focusSort);
  }

  function reset({ focusSearch = true } = {}) {
    Object.assign(state, {
      query: "",
      view: "overview",
      district: "all",
      station: "all",
      sale: "all",
      source: "all",
      primary: "all",
      sort: "project",
      direction: "asc",
    });
    render({ resetBatch: true });
    if (focusSearch) elements.search?.focus();
  }

  elements.views?.addEventListener("click", event => {
    const button = event.target.closest("[data-view]");
    if (!button || !Object.hasOwn(VIEWS, button.dataset.view)) return;
    state.view = button.dataset.view;
    keepSortVisible();
    render({ resetBatch: true });
    document.querySelector(`#view-options [data-view="${CSS.escape(state.view)}"]`)?.focus({ preventScroll: true });
  });

  elements.search?.addEventListener("input", () => {
    state.query = elements.search.value.slice(0, 160);
    render({ resetBatch: true });
  });

  for (const key of ["district", "station", "sale", "source", "primary"]) {
    elements[key]?.addEventListener("change", () => {
      state[key] = elements[key].value;
      render({ resetBatch: true });
    });
  }

  tableHead.addEventListener("click", event => {
    const button = event.target.closest("[data-sort]");
    if (!button || !columnMap.has(button.dataset.sort)) return;
    if (state.sort === button.dataset.sort) state.direction = state.direction === "asc" ? "desc" : "asc";
    else {
      state.sort = button.dataset.sort;
      state.direction = "asc";
    }
    render({ resetBatch: true, focusSort: state.sort });
  });

  elements.showMore?.addEventListener("click", () => {
    renderLimit += pageSize;
    render({ updateURL: false });
    if (elements.showMore.hidden) elements.tableWrap?.focus({ preventScroll: true });
    else elements.showMore.focus({ preventScroll: true });
  });
  elements.reset?.addEventListener("click", () => reset());
  elements.emptyReset?.addEventListener("click", () => reset());
  window.addEventListener("popstate", () => {
    readURL();
    render({ updateURL: true, resetBatch: true });
  });

  readURL();
  render({ resetBatch: true });
})();
