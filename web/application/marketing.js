"use strict";

(async function hydrateRecordedPreview() {
  const label = id => document.getElementById(id);
  const results = label("previewCases");
  try {
    const response = await fetch("/api/application/demo", {credentials: "omit", cache: "no-store"});
    if (!response.ok) throw new Error("Published sample unavailable");
    const {public_sample, recorded, run, events} = await response.json();
    if (public_sample !== true || recorded !== true || run?.id !== "demo-python-2026-11-07") {
      throw new Error("Published sample provenance missing");
    }

    const partitions = [["train", "Training"], ["validation", "Validation"], ["holdout", "Holdout"]];
    const cases = events.filter(event => event.type === "case_completed");
    function result(phase, model) {
      const checks = cases.filter(event => event.details?.phase === phase && event.details?.model === model);
      if (!checks.length) return "—";
      const passed = checks.filter(event => event.details.passed === true).length;
      return passed + "/" + checks.length + " passed";
    }

    const rows = partitions.map(([phase, title]) => {
      const row = document.createElement("tr");
      const heading = document.createElement("th");
      heading.scope = "row";
      heading.textContent = title;
      row.append(heading);
      for (const model of [run.source, run.target]) {
        const cell = document.createElement("td");
        cell.textContent = result(phase, model);
        row.append(cell);
      }
      return row;
    });

    label("previewSource").textContent = run.source;
    label("previewTarget").textContent = run.target;
    label("previewState").textContent = run.status === "compatible_on_sample"
      ? "Compatible on sample"
      : run.status === "verified_adaptation" ? "Verified repair" : "Recorded evaluation";
    const verified = run.verification?.length && run.verification.every(check => check.passed === true);
    label("previewProvenance").textContent = verified && run.export_available
      ? "Export passed fresh original-runtime verification"
      : "Published evaluation evidence";
    results.replaceChildren(...rows);
  } catch {
    label("previewState").textContent = "Preview unavailable";
    results.rows[0].cells[0].textContent = "Open the recorded run to see its evidence.";
  }
})();
