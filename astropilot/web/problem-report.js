"use strict";
(() => {
  const errors = [];
  // Never collect error.message, stack, URL, DOM text, or unhandled rejection values.
  const record = code => { errors.push(code); if (errors.length > 20) errors.shift(); };
  window.addEventListener("error", () => record("browser_error"));
  window.addEventListener("unhandledrejection", () => record("unhandled_promise"));
  const dialog = document.querySelector("#problem-report-dialog");
  const preview = document.querySelector("#problem-report-preview");
  const download = document.querySelector("#problem-report-download");
  const status = document.querySelector("#problem-report-status");
  let generation = 0, report = null;
  document.querySelector("#problem-report-close").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => { generation++; report = null; preview.value = ""; download.disabled = true; });
  document.querySelector("#problem-report-open").addEventListener("click", async () => {
    const current = ++generation; report = null; preview.value = ""; download.disabled = true;
    status.textContent = "Préparation de l’aperçu…"; dialog.showModal();
    const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch("/v1/problem-report", {cache:"no-store", signal:controller.signal});
      if (!response.ok) throw new Error("unavailable");
      const data = await response.json();
      if (current !== generation) return;
      // Select fields again in the browser; unexpected server fields are never exported.
      report = {schema:data.schema, version:data.version, build:data.build,
        architecture:data.architecture, system:data.system, weather_mode:data.weather_mode,
        scope:data.scope, browser_errors:[...errors]};
      preview.value = JSON.stringify(report, null, 2);
      status.textContent = "Relisez l’aperçu. Le fichier sera téléchargé uniquement après votre clic.";
      download.disabled = false;
    } catch (_) {
      if (current === generation) status.textContent = "Rapport indisponible. Fermez ce panneau et réessayez ; vos données sont conservées.";
    } finally { clearTimeout(timer); }
  });
  download.addEventListener("click", () => {
    if (!report || download.disabled) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:"application/json"}));
    const link = document.createElement("a"); link.href = url; link.download = "NightMerit-rapport-probleme.json";
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 60000);
    status.textContent = "Téléchargement demandé. Vous pouvez partager ce fichier avec la personne qui vous aide.";
  });
})();
