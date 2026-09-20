(() => {
  "use strict";

  // Arrays preserve duplicate/blank column names, empty fields and repeated rows.
  function parseCSV(text) {
    const input = text.replace(/^\uFEFF/, "");
    if (!input.length) return [];
    const rows = [];
    let row = [], field = "", quoted = false, closed = false, started = false;
    const endField = () => { row.push(field); field = ""; closed = false; started = false; };
    const endRow = () => { endField(); rows.push(row); row = []; };
    for (let i = 0; i < input.length; i += 1) {
      const character = input[i];
      if (quoted) {
        if (character === '"') {
          if (input[i + 1] === '"') { field += '"'; i += 1; }
          else { quoted = false; closed = true; }
        } else field += character;
      } else if (character === ",") {
        endField();
      } else if (character === "\r" || character === "\n") {
        endRow();
        if (character === "\r" && input[i + 1] === "\n") i += 1;
      } else if (character === '"' && !started && !closed) {
        quoted = true;
        started = true;
      } else {
        if (closed || character === '"') throw new Error("CSV contains an invalid quoted field.");
        field += character;
        started = true;
      }
    }
    if (quoted) throw new Error("CSV contains an unfinished quoted field.");
    // A final record separator is not an extra row; an explicit blank row is.
    if (started || closed || row.length || field.length) endRow();
    return rows;
  }

  function serializeCSV(rows) {
    return "\uFEFF" + rows.map(row => row.map(value => {
      const text = String(value);
      return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
    }).join(",")).join("\r\n") + (rows.length ? "\r\n" : "");
  }

  function validatePath(path) {
    if (typeof path !== "string" || !/^research\/(?:[A-Za-z0-9][A-Za-z0-9._-]*\/)*[A-Za-z0-9][A-Za-z0-9._-]*\.csv$/i.test(path)
        || !path.startsWith("research/")) {
      throw new Error("Open a CSV link from a research report. Only published files inside research/ are supported.");
    }
    return path;
  }

  const numericPattern = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
  const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
  function sortRecords(records, column, direction, numeric) {
    return [...records].sort((a, b) => {
      const left = a.row[column] ?? "", right = b.row[column] ?? "";
      if (left === "" && right !== "") return 1;
      if (right === "" && left !== "") return -1;
      const order = numeric && left !== "" && right !== ""
        ? Number(left) - Number(right) : collator.compare(left, right);
      return order * direction || a.index - b.index;
    });
  }

  // Small pure helpers are also available to the offline site validation tests.
  globalThis.ResearchCSV = Object.freeze({ parseCSV, serializeCSV, validatePath, sortRecords });
  if (typeof document === "undefined") return;

  async function start() {
    const element = id => document.getElementById(id);
    const status = element("data-status");
    try {
      const path = validatePath(new URLSearchParams(window.location.search).get("path"));
      const base = new URL("./", window.location.href);
      const url = new URL(path, base);
      if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname + "research/")) {
        throw new Error("The CSV must belong to this research site.");
      }
      const filename = path.split("/").pop();
      element("data-filename").textContent = filename;
      element("data-source").textContent = path;
      document.title = `${filename} · Research data`;
      const original = element("data-original");
      original.href = url.href;
      original.download = filename;
      const response = await fetch(url.href, { credentials: "same-origin", redirect: "error" });
      if (!response.ok) throw new Error(`The published CSV could not be loaded (HTTP ${response.status}).`);
      if ((response.headers.get("content-type") || "").includes("text/html")) {
        throw new Error("The file returned a web page instead of CSV data. Check the report link.");
      }
      const parsed = parseCSV(await response.text());
      if (!parsed.length) throw new Error("This CSV file is empty.");
      const headers = parsed[0];
      const rows = parsed.slice(1);
      const width = rows.reduce((count, row) => Math.max(count, row.length), headers.length);
      const records = rows.map((row, index) => ({ row, index }));
      const searchValues = rows.map(row => row.map(value => value.toLocaleLowerCase()));
      const numericColumns = Array.from({ length: width }, (_, column) => {
        const values = rows.map(row => row[column] ?? "").filter(value => value !== "");
        return values.length > 0 && values.every(value => numericPattern.test(value) && Number.isFinite(Number(value)));
      });
      let filtered = records, page = 0, pageSize = 100, sortColumn = null, sortDirection = 1;
      let filterTimer;
      const headRow = document.createElement("tr");
      const headerCells = [];
      for (let column = 0; column < width; column += 1) {
        const th = document.createElement("th");
        th.scope = "col";
        th.setAttribute("aria-sort", "none");
        const button = document.createElement("button");
        button.type = "button";
        button.className = "data-sort";
        const label = document.createElement("span");
        const title = headers[column] === undefined ? `Column ${column + 1} (no header)`
          : headers[column] || `Column ${column + 1} (empty header)`;
        label.textContent = title;
        button.title = `Sort column ${column + 1}: ${title}`;
        const icon = document.createElement("span");
        icon.className = "data-sort-icon";
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = "↕";
        button.append(label, icon);
        button.addEventListener("click", () => {
          sortDirection = sortColumn === column ? -sortDirection : 1;
          sortColumn = column;
          page = 0;
          updateSelection();
        });
        th.append(button);
        headRow.append(th);
        headerCells.push({ th, icon });
      }
      element("data-head").append(headRow);
      element("data-caption").textContent = `${filename}; ${rows.length.toLocaleString()} source rows`;

      function render() {
        const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
        page = Math.min(page, pages - 1);
        const first = page * pageSize;
        const visible = filtered.slice(first, first + pageSize);
        const fragment = document.createDocumentFragment();
        for (const record of visible) {
          const tr = document.createElement("tr");
          for (let column = 0; column < width; column += 1) {
            const td = document.createElement("td");
            td.textContent = record.row[column] ?? "";
            tr.append(td);
          }
          fragment.append(tr);
        }
        if (!visible.length) {
          const tr = document.createElement("tr"), td = document.createElement("td");
          td.colSpan = width;
          td.textContent = "No rows match your search.";
          tr.append(td);
          fragment.append(tr);
        }
        element("data-body").replaceChildren(fragment);
        status.textContent = `${filtered.length.toLocaleString()} of ${rows.length.toLocaleString()} rows · ${width.toLocaleString()} columns`;
        element("data-page-info").textContent = filtered.length
          ? `Rows ${(first + 1).toLocaleString()}–${(first + visible.length).toLocaleString()} · Page ${page + 1} of ${pages.toLocaleString()}`
          : "0 matching rows";
        element("data-first").disabled = page === 0;
        element("data-previous").disabled = page === 0;
        element("data-next").disabled = page >= pages - 1;
        element("data-last").disabled = page >= pages - 1;
        headerCells.forEach(({ th, icon }, index) => {
          th.setAttribute("aria-sort", index !== sortColumn ? "none" : sortDirection === 1 ? "ascending" : "descending");
          icon.textContent = index !== sortColumn ? "↕" : sortDirection === 1 ? "↑" : "↓";
        });
        element("data-table").parentElement.scrollTop = 0;
      }

      function updateSelection() {
        const query = element("data-search").value.toLocaleLowerCase();
        filtered = query ? records.filter(record => searchValues[record.index].some(value => value.includes(query))) : records;
        if (sortColumn !== null) filtered = sortRecords(filtered, sortColumn, sortDirection, numericColumns[sortColumn]);
        render();
      }

      element("data-search").addEventListener("input", () => {
        clearTimeout(filterTimer);
        filterTimer = setTimeout(() => { page = 0; updateSelection(); }, 150);
      });
      element("data-page-size").addEventListener("change", event => {
        pageSize = Number(event.target.value);
        page = 0;
        render();
      });
      for (const [id, move] of [
        ["data-first", () => 0], ["data-previous", () => page - 1],
        ["data-next", () => page + 1], ["data-last", () => Math.max(0, Math.ceil(filtered.length / pageSize) - 1)]
      ]) element(id).addEventListener("click", () => { page = move(); render(); });

      element("data-filtered").addEventListener("click", () => {
        // Flush a pending search so a quick download matches the visible query.
        clearTimeout(filterTimer);
        updateSelection();
        const blob = new Blob([serializeCSV([headers, ...filtered.map(record => record.row)])], { type: "text/csv;charset=utf-8" });
        const blobURL = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = blobURL;
        link.download = filename.replace(/\.csv$/i, "-filtered.csv");
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(blobURL), 1000);
      });
      element("data-explorer").hidden = false;
      render();
    } catch (error) {
      status.dataset.error = "true";
      status.textContent = error.message || "The research data could not be loaded. Return to the report and try its CSV link again.";
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
})();
