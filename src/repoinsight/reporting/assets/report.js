(() => {
  "use strict";
  const severity = document.getElementById("severity-filter");
  const category = document.getElementById("category-filter");
  const search = document.getElementById("finding-search");
  const reset = document.getElementById("reset-filters");
  const expand = document.getElementById("expand-findings");
  const collapse = document.getElementById("collapse-findings");
  const status = document.getElementById("filter-status");
  const filteredEmpty = document.getElementById("filtered-empty");
  const findings = Array.from(document.querySelectorAll("details.finding"));

  const visibleFindings = () => findings.filter((finding) => !finding.hidden);

  const applyFilters = () => {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    findings.forEach((finding) => {
      const matchesSeverity = severity.value === "all" || finding.dataset.severity === severity.value;
      const matchesCategory = category.value === "all" || finding.dataset.category === category.value;
      const matchesSearch = !query || (finding.dataset.search || "").toLocaleLowerCase().includes(query);
      const matches = matchesSeverity && matchesCategory && matchesSearch;
      finding.hidden = !matches;
      if (matches) visible += 1;
    });
    filteredEmpty.hidden = visible !== 0 || findings.length === 0;
    status.textContent = `${visible} ${visible === 1 ? "finding" : "findings"} shown, highest impact first`;
  };

  [severity, category, search].forEach((control) => control.addEventListener("input", applyFilters));
  reset.addEventListener("click", () => {
    severity.value = "all";
    category.value = "all";
    search.value = "";
    applyFilters();
    severity.focus();
  });
  expand.addEventListener("click", () => {
    visibleFindings().forEach((finding) => { finding.open = true; });
  });
  collapse.addEventListener("click", () => {
    visibleFindings().forEach((finding) => { finding.open = false; });
  });

  let printState = [];
  window.addEventListener("beforeprint", () => {
    printState = findings.map((finding) => finding.open);
    findings.forEach((finding) => { finding.open = true; });
  });
  window.addEventListener("afterprint", () => {
    findings.forEach((finding, index) => { finding.open = printState[index]; });
  });
})();
