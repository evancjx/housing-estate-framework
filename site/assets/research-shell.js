(() => {
  "use strict";

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

    if (!document.querySelector(".research-shell-nav")) {
      const nav = document.createElement("nav");
      nav.className = "research-shell-nav";
      nav.setAttribute("aria-label", "Research navigation");
      nav.innerHTML = `
        <a class="research-shell-brand" href="index.html">
          <span class="research-shell-brand-mark" aria-hidden="true">SG</span>
          <span>Estate research hub</span>
        </a>
        <span class="research-shell-links">
          <a class="research-shell-primary" href="private_project_comparison_table.html">Find a condo</a>
          <a href="comparison_table.html">Research an estate</a>
          <button class="research-shell-copy" type="button">Copy report link</button>
        </span>`;
      const firstContent = Array.from(body.children).find(element =>
        !element.classList.contains("research-shell-skip")
      );
      body.insertBefore(nav, firstContent || null);

      const copyButton = nav.querySelector(".research-shell-copy");
      copyButton?.addEventListener("click", async () => {
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

    document.querySelectorAll(".tbl-wrap").forEach((wrapper, index) => {
      if (!wrapper.hasAttribute("role")) wrapper.setAttribute("role", "region");
      if (!wrapper.hasAttribute("aria-label")) {
        wrapper.setAttribute("aria-label", `Scrollable research table ${index + 1}`);
      }
      if (!wrapper.hasAttribute("tabindex")) wrapper.tabIndex = 0;
    });

    document.querySelectorAll("a[target='_blank']").forEach(link => {
      if (!link.rel) link.rel = "noopener noreferrer";
    });
  });

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
