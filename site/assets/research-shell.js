(() => {
  "use strict";

  const MOBILE_NAVIGATION_QUERY = "(max-width: 900px)";
  const SHELL_SCRIPT_URL = document.currentScript?.src || "";
  const SITE_ROOT_URL = (() => {
    try {
      return new URL("../", SHELL_SCRIPT_URL || document.baseURI);
    } catch {
      return new URL("./", document.baseURI);
    }
  })();
  const DATA_FAMILY_LABELS = Object.freeze({
    estate_model: "Estate model",
    private_transactions: "Private transactions",
    rail_network: "Rail network",
    finance_assumptions: "Finance assumptions",
    market_research: "Market research",
  });

  const ready = callback => {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
    } else {
      callback();
    }
  };

  ready(() => {
    const body = document.body;
    if (!body || body.dataset.researchShell === "off") return;

    const mainTarget = document.querySelector("main, [role='main'], .tbl-wrap, table, h1");
    if (mainTarget && !mainTarget.id) mainTarget.id = "research-content";

    if (mainTarget && !document.querySelector(".research-shell-skip")) {
      const skip = document.createElement("a");
      skip.className = "research-shell-skip";
      skip.href = `#${mainTarget.id}`;
      skip.textContent = "Skip to research content";
      body.prepend(skip);
    }

    let nav = document.querySelector(".research-shell-nav");
    if (!nav) {
      const createdNav = document.createElement("nav");
      createdNav.className = "research-shell-nav";
      createdNav.setAttribute("aria-label", "Research navigation");
      createdNav.innerHTML = `
        <span class="research-shell-identity">
          <a class="research-shell-brand" href="${siteURL("index.html")}">
            <span class="research-shell-brand-mark" aria-hidden="true">SG</span>
            <span>Estate research hub</span>
          </a>
          <span class="research-shell-current">
            <span class="research-shell-current-label">Viewing</span>
            <span class="research-shell-current-title"></span>
          </span>
        </span>
        <button class="research-shell-menu-toggle" type="button"
          aria-expanded="false" aria-controls="research-shell-menu">Menu</button>
        <span class="research-shell-links" id="research-shell-menu">
          <a href="${siteURL("index.html#reports")}">All reports</a>
          <a class="research-shell-primary" href="${siteURL("private_project_comparison_table.html")}">Find a condo</a>
          <a href="${siteURL("comparison_table.html")}">Research an estate</a>
          <a href="${siteURL("home_loan_planner.html")}">Plan a home loan</a>
          <button class="research-shell-copy" type="button">Copy report link</button>
        </span>`;
      const firstContent = Array.from(body.children).find(element =>
        !element.classList.contains("research-shell-skip")
      );
      body.insertBefore(createdNav, firstContent || null);
      nav = createdNav;
    }

    if (nav) {
      enhanceNavigation(nav);
      enhanceFreshness(nav);
    }

    enhanceTableScrollContainers();

    document.querySelectorAll("a[target='_blank']").forEach(link => {
      if (!link.rel) link.rel = "noopener noreferrer";
    });
  });

  function enhanceNavigation(nav) {
    if (nav.dataset.researchShellEnhanced === "true") return;
    nav.dataset.researchShellEnhanced = "true";

    const title = (
      document.title.trim()
      || document.querySelector("main h1, [role='main'] h1, h1")?.textContent?.trim()
      || "Research report"
    );
    const currentTitle = nav.querySelector(".research-shell-current-title");
    if (currentTitle) {
      currentTitle.textContent = title;
      currentTitle.parentElement.title = title;
    }

    const currentContext = nav.querySelector(".research-shell-current");
    if (currentContext) {
      if (markCurrentPage(nav)) {
        currentContext.removeAttribute("aria-current");
      } else {
        currentContext.setAttribute("aria-current", "page");
      }
    } else {
      markCurrentPage(nav);
    }
    bindCopyLink(nav);
    bindMobileNavigation(nav);
  }

  function enhanceTableScrollContainers() {
    const selectors = ".tbl-wrap, .table-wrap, .table-scroll, .matrix-wrap";
    const containers = new Set(document.querySelectorAll(selectors));
    document.querySelectorAll("table").forEach(table => {
      let node = table;
      while (node && node !== document.body) {
        const overflow = getComputedStyle(node).overflowX;
        if (["auto", "scroll", "overlay"].includes(overflow)) {
          containers.add(node);
          break;
        }
        node = node.parentElement;
      }
    });
    [...containers].forEach((container, index) => {
      if (!container.querySelector("table") && container.tagName !== "TABLE") return;
      if (!container.hasAttribute("role")) container.setAttribute("role", "region");
      if (!container.hasAttribute("aria-label") && !container.hasAttribute("aria-labelledby")) {
        container.setAttribute(
          "aria-label",
          `Scrollable research table ${index + 1}`
        );
      }
      if (!container.hasAttribute("tabindex")) container.tabIndex = 0;
    });
  }

  function siteURL(path) {
    return new URL(path, SITE_ROOT_URL).href;
  }

  function markCurrentPage(nav) {
    let currentURL;
    try {
      currentURL = new URL(window.location.href);
    } catch {
      return false;
    }
    let matched = false;
    nav.querySelectorAll("a[href]").forEach(link => {
      link.removeAttribute("aria-current");
      try {
        const targetURL = new URL(link.getAttribute("href"), document.baseURI);
        if (
          targetURL.origin === currentURL.origin
          && targetURL.pathname === currentURL.pathname
        ) {
          link.setAttribute("aria-current", "page");
          matched = true;
        }
      } catch {
        // Keep navigation usable even if a host page supplies a malformed link.
      }
    });
    return matched;
  }

  function bindCopyLink(nav) {
    const copyButton = nav.querySelector(".research-shell-copy");
    if (!copyButton) return;
    copyButton.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(window.location.href);
        announce("Report link copied.");
        copyButton.textContent = "Copied";
        window.setTimeout(() => { copyButton.textContent = "Copy report link"; }, 1800);
      } catch {
        announce("Copy unavailable. Select the address from your browser.");
      }
    });
  }

  function bindMobileNavigation(nav) {
    const toggle = nav.querySelector(".research-shell-menu-toggle");
    const links = nav.querySelector(".research-shell-links");
    if (!toggle || !links) return;

    const mobile = window.matchMedia(MOBILE_NAVIGATION_QUERY);
    let open = false;

    const setOpen = (nextOpen, { returnFocus = false } = {}) => {
      open = Boolean(nextOpen && mobile.matches);
      links.classList.toggle("is-open", open);
      toggle.setAttribute("aria-expanded", String(open));
      toggle.textContent = open ? "Close menu" : "Menu";
      if (returnFocus) toggle.focus();
    };

    toggle.addEventListener("click", () => setOpen(!open));
    links.addEventListener("click", event => {
      if (event.target instanceof Element && event.target.closest("a")) setOpen(false);
    });
    document.addEventListener("click", event => {
      if (open && !nav.contains(event.target)) setOpen(false);
    });
    document.addEventListener("keydown", event => {
      if (open && event.key === "Escape") {
        event.preventDefault();
        setOpen(false, { returnFocus: true });
      }
    });

    const handleViewportChange = () => {
      if (!mobile.matches) setOpen(false);
    };
    if (typeof mobile.addEventListener === "function") {
      mobile.addEventListener("change", handleViewportChange);
    } else {
      mobile.addListener(handleViewportChange);
    }
    setOpen(false);
  }

  function enhanceFreshness(nav) {
    let panel = document.querySelector(".research-shell-freshness");
    if (!panel) {
      panel = document.createElement("section");
      panel.className = "research-shell-freshness";
      panel.setAttribute("aria-label", "Report data currency");
      nav.insertAdjacentElement("afterend", panel);
    }
    if (panel.dataset.researchFreshnessEnhanced === "true") return;
    panel.dataset.researchFreshnessEnhanced = "true";
    void refreshFreshness(panel);
  }

  async function refreshFreshness(panel, { invalidate = false } = {}) {
    panel.setAttribute("aria-busy", "true");
    renderFreshness(panel, {
      familyIds: [],
      families: {},
      message: "Loading report data status…",
    });

    const bootstrap = readFreshnessBootstrap();
    if (bootstrap.value) {
      panel.setAttribute("aria-busy", "false");
      renderFreshness(panel, {
        familyIds: bootstrap.value.data_families,
        families: bootstrap.value.families,
        reportGeneratedAt: bootstrap.value.generated_at,
      });
      return;
    }

    if (window.location.protocol === "file:") {
      panel.setAttribute("aria-busy", "false");
      renderFreshness(panel, {
        familyIds: [],
        families: {},
        message: bootstrap.error
          || "This local file has no embedded report status. Unknown values stay unknown.",
      });
      return;
    }

    const loader = globalThis.SGEstateData;
    if (!loader || typeof loader.loadMany !== "function") {
      panel.setAttribute("aria-busy", "false");
      renderFreshness(panel, {
        familyIds: [],
        families: {},
        message: bootstrap.error
          || "Report data status is unavailable in this publication.",
      });
      return;
    }

    if (invalidate) {
      for (const path of [siteURL("reports.json"), siteURL("data-status.json")]) {
        try {
          loader.invalidate(path);
        } catch {
          // A retry remains useful even if a host supplied a malformed base URL.
        }
      }
    }

    const results = await loader.loadMany([
      { path: siteURL("reports.json"), validate: validateReportCatalog },
      { path: siteURL("data-status.json"), validate: validateDataStatus },
    ]);
    const catalog = results[0]?.status === "fulfilled" ? results[0].value : null;
    const status = results[1]?.status === "fulfilled" ? results[1].value : null;
    const report = catalog ? currentReport(catalog.reports) : null;
    const familyIds = report?.data_families || [];
    const failed = results.some(result => result.status === "rejected");
    let message = "";
    if (!report && catalog) {
      message = "This report has no data-family mapping; currency remains unknown.";
    } else if (failed) {
      message = "Some report status metadata could not be loaded. Unknown values stay unknown.";
    }

    panel.setAttribute("aria-busy", "false");
    renderFreshness(panel, {
      familyIds,
      families: status?.families || {},
      message: bootstrap.error || message,
      retry: failed ? () => refreshFreshness(panel, { invalidate: true }) : null,
    });
  }

  function readFreshnessBootstrap() {
    const node = document.getElementById("research-report-status");
    if (!node) return { value: null, error: "" };
    let value;
    try {
      value = JSON.parse(node.textContent || "");
    } catch {
      return {
        value: null,
        error: "Embedded report status is unreadable. Unknown values stay unknown.",
      };
    }
    if (
      !value
      || value.schema_version !== 1
      || typeof value.report_path !== "string"
      || validateFamilyIds(value.data_families) !== true
      || !value.families
      || typeof value.families !== "object"
      || !Object.hasOwn(value, "generated_at")
      || !isNullableEvidenceDate(value.generated_at)
    ) {
      return {
        value: null,
        error: "Embedded report status has an unexpected schema. Unknown values stay unknown.",
      };
    }
    for (const id of value.data_families) {
      if (validateFamilyStatus(id, value.families[id]) !== true) {
        return {
          value: null,
          error: "Embedded report status is incomplete. Unknown values stay unknown.",
        };
      }
    }
    return { value, error: "" };
  }

  function validateFamilyIds(value) {
    if (
      !Array.isArray(value)
      || value.length === 0
      || new Set(value).size !== value.length
      || value.some(id => !Object.hasOwn(DATA_FAMILY_LABELS, id))
    ) {
      return "The report contains an invalid data-family mapping.";
    }
    return true;
  }

  function validateReportCatalog(value) {
    if (!value || value.schema_version !== 2 || !Array.isArray(value.reports)) {
      return "The report catalog has an unexpected schema.";
    }
    for (const report of value.reports) {
      if (
        !report
        || typeof report.path !== "string"
        || validateFamilyIds(report.data_families) !== true
      ) {
        return "The report catalog contains an invalid data-family mapping.";
      }
    }
    return true;
  }

  function validateDataStatus(value) {
    if (!value || value.schema_version !== 2 || !value.families) {
      return "The report data status has an unexpected schema.";
    }
    for (const id of Object.keys(DATA_FAMILY_LABELS)) {
      if (validateFamilyStatus(id, value.families[id]) !== true) {
        return `The ${id} data-family status is incomplete.`;
      }
    }
    return true;
  }

  function validateFamilyStatus(id, family) {
    if (
      !family
      || typeof family !== "object"
      || typeof family.label !== "string"
      || !family.label.trim()
      || !Object.hasOwn(DATA_FAMILY_LABELS, id)
      || !Object.hasOwn(family, "data_through")
      || !Object.hasOwn(family, "last_checked")
      || !Object.hasOwn(family, "generated_at")
      || !isNullableEvidenceDate(family.data_through)
      || !isNullableEvidenceDate(family.last_checked)
      || !isNullableEvidenceDate(family.generated_at)
      || (family.note != null && typeof family.note !== "string")
    ) {
      return `The ${id} data-family status is incomplete.`;
    }
    return true;
  }

  function isNullableEvidenceDate(value) {
    if (value == null) return true;
    if (typeof value !== "string") return false;
    const text = value.trim();
    if (/^\d{4}$/.test(text)) return true;
    if (/^\d{4}-\d{2}$/.test(text)) {
      const month = Number(text.slice(5, 7));
      return month >= 1 && month <= 12;
    }
    if (!/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(text)) return false;
    return !Number.isNaN(Date.parse(text));
  }

  function currentReport(reports) {
    try {
      const currentURL = new URL(window.location.href);
      const rootURL = new URL(SITE_ROOT_URL.href);
      if (!currentURL.pathname.startsWith(rootURL.pathname)) return null;
      const relative = decodeURIComponent(
        currentURL.pathname.slice(rootURL.pathname.length)
      ).replace(/^\/+/, "");
      return reports.find(report => report.path === relative) || null;
    } catch {
      return null;
    }
  }

  function renderFreshness(panel, {
    familyIds,
    families,
    message = "",
    reportGeneratedAt = null,
    retry = null,
  }) {
    const heading = document.createElement("div");
    heading.className = "research-shell-freshness-heading";
    const title = document.createElement("strong");
    title.textContent = "Data currency";
    const detailLink = document.createElement("a");
    detailLink.href = siteURL("data-status.json");
    detailLink.textContent = "Source details";
    heading.append(title, detailLink);

    const rows = document.createElement("div");
    rows.className = "research-shell-freshness-grid";
    const ids = familyIds.length ? familyIds : [null];
    for (const id of ids) {
      const family = id ? families[id] || {} : {};
      const card = document.createElement("article");
      card.className = "research-shell-freshness-family";
      const familyTitle = document.createElement("a");
      familyTitle.className = "research-shell-freshness-family-title";
      familyTitle.href = siteURL("data-status.json") + (id ? `#${id}` : "");
      familyTitle.textContent = id
        ? family.label || DATA_FAMILY_LABELS[id]
        : "Report data";
      card.setAttribute("aria-label", `${familyTitle.textContent} data currency`);
      const values = document.createElement("dl");
      appendFreshnessValue(values, "Data through", family.data_through);
      appendFreshnessValue(values, "Last checked", family.last_checked);
      appendFreshnessValue(
        values,
        "Generated",
        reportGeneratedAt || family.generated_at
      );
      card.append(familyTitle, values);
      if (typeof family.note === "string" && family.note) {
        const note = document.createElement("p");
        note.textContent = family.note;
        card.append(note);
      }
      rows.append(card);
    }

    const footer = document.createElement("div");
    footer.className = "research-shell-freshness-footer";
    if (message) {
      const status = document.createElement("span");
      status.setAttribute("role", "status");
      status.textContent = message;
      footer.append(status);
    }
    if (retry) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Retry status";
      button.addEventListener("click", retry, { once: true });
      footer.append(button);
    }

    panel.replaceChildren(heading, rows, footer);
  }

  function appendFreshnessValue(list, label, value) {
    const group = document.createElement("div");
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    if (typeof value === "string" && value.trim()) {
      const time = document.createElement("time");
      time.dateTime = value.trim();
      time.textContent = formatEvidenceDate(value);
      description.append(time);
    } else {
      description.textContent = "Unknown";
      description.className = "is-unknown";
    }
    group.append(term, description);
    list.append(group);
  }

  function formatEvidenceDate(value) {
    if (typeof value !== "string" || !value.trim()) return "Unknown";
    const text = value.trim();
    if (/^\d{4}$/.test(text)) return text;
    if (/^\d{4}-\d{2}$/.test(text)) {
      const [year, month] = text.split("-").map(Number);
      if (month >= 1 && month <= 12) {
        return new Intl.DateTimeFormat("en-SG", {
          month: "short",
          year: "numeric",
          timeZone: "UTC",
        }).format(new Date(Date.UTC(year, month - 1, 1)));
      }
    }
    const dateMatch = /^(\d{4})-(\d{2})-(\d{2})/.exec(text);
    if (dateMatch) {
      const [, year, month, day] = dateMatch;
      const parsed = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
      if (!Number.isNaN(parsed.valueOf())) {
        return new Intl.DateTimeFormat("en-SG", {
          day: "numeric",
          month: "short",
          year: "numeric",
          timeZone: "UTC",
        }).format(parsed);
      }
    }
    return text;
  }

  function announce(message) {
    let status = document.querySelector(".research-shell-status");
    if (!status) {
      status = document.createElement("div");
      status.className = "research-shell-status";
      status.setAttribute("role", "status");
      status.setAttribute("aria-live", "polite");
      document.body.append(status);
    }
    status.textContent = message;
    window.setTimeout(() => status.remove(), 2600);
  }
})();
