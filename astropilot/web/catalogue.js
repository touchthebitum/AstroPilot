"use strict";
const cataloguePage = {offset:0, limit:25, total:0, generation:0, controller:null, searchSignature:null};
const catalogueEquipment = new URLSearchParams(location.search).get("equipment");
const node = selector => document.querySelector(selector);
function paragraph(text, className) {
  const p = document.createElement("p"); p.textContent = text;
  if (className) p.className = className;
  return p;
}
function referenceLink(url, label) {
  const a = document.createElement("a"); a.href = url; a.textContent = label;
  a.target = "_blank"; a.rel = "noopener noreferrer"; return a;
}
function offlineCataloguePage(query) {
  const source = window.NIGHTMERIT_OFFLINE_CATALOGUE;
  const normalise = text => text.normalize("NFKD").toLowerCase().replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "").replace(/([a-z])0+(?=[1-9])/g, "$1");
  const needle = normalise(query.get("q") || "");
  let matches = source.results.filter(object => (!needle || object.search_text.includes(needle))
    && (!query.get("kind") || object.kind === query.get("kind"))
    && (!query.get("framing") || object.framing.status === query.get("framing")));
  if (needle) matches.sort((a,b) => Number(!a.aliases.some(x => normalise(x) === needle)) - Number(!b.aliases.some(x => normalise(x) === needle)) || a.catalogue_id.localeCompare(b.catalogue_id));
  const offset = Number(query.get("offset")), limit = Number(query.get("limit"));
  return {...source, total:matches.length, offset, limit, results:matches.slice(offset, offset+limit)};
}
function showCatalogue(payload) {
  cataloguePage.total = payload.total;
  node("#catalogue-count").textContent = `${payload.catalogue.records.toLocaleString("fr-CH")} fiches répertoriées, dont les ${payload.catalogue.messier_designations} références Messier (M102 avec note d’identification).`;
  const g = payload.geometry;
  node("#equipment-summary").textContent = `${payload.equipment_name} · ` + (g.status === "nominal"
    ? `champ nominal : ${g.field_width_deg.toFixed(2)}° × ${g.field_height_deg.toFixed(2)}°, capteur entier à la focale déclarée.` : g.reason);
  node("#catalogue-status").textContent = payload.total
    ? `${payload.offset + 1}–${Math.min(payload.offset + payload.limit, payload.total)} sur ${payload.total.toLocaleString("fr-CH")} résultat(s).`
    : "Aucune fiche ne correspond à cette recherche. Essayez une autre référence ou élargissez les filtres.";
  const results = node("#catalogue-results"); results.replaceChildren();
  for (const object of payload.results) {
    const article = document.createElement("article"); const title = document.createElement("h2"); title.textContent = object.display_name;
    article.append(title, paragraph(object.kind_label + (object.constellation ? ` · ${object.constellation}` : "")));
    const size = object.major_arcmin == null ? "Dimensions non renseignées."
      : `${object.extent_bound === "lower_limit" ? "Extension supérieure à" : "Dimension principale cataloguée approximative :"} ${object.major_arcmin}′${object.minor_arcmin == null ? "" : ` × ${object.minor_arcmin}′`}.`;
    article.append(paragraph(size), paragraph(object.scope), paragraph(object.framing.label));
    if (object.dimension_note) article.append(paragraph(object.dimension_note));
    if (object.dimensions_inconsistent) article.append(paragraph("Les axes fournis par la source sont incohérents ; le cadrage n’est pas certifié."));
    for (const note of object.identity_notes) {
      article.append(paragraph(note.text));
      for (const url of note.sources) article.append(referenceLink(url, "Source de l’identification"));
    }
    const details = document.createElement("details"); const summary = document.createElement("summary"); summary.textContent = "Identifiants, mesures et précisions";
    details.append(summary, paragraph(`Identifiants : ${object.aliases.join(", ")}.`));
    if (object.ra_deg != null && object.dec_deg != null) details.append(paragraph(`Position déclarée par la source : ${object.ra_deg.toFixed(5)}°, ${object.dec_deg.toFixed(5)}°. ${object.coordinate_reference}`));
    const magnitudes = Object.entries(object.magnitudes).filter(([, value]) => value != null);
    if (magnitudes.length) details.append(paragraph(`Magnitudes cataloguées : ${magnitudes.map(([band,value]) => `${band} : ${value}`).join(" ; ")}. Une magnitude totale ne suffit pas à prévoir la facilité photographique d’un objet étendu.`));
    for (const note of object.curated_notes) {
      details.append(paragraph(`${note.name} : ${note.scope} ${note.advice}`));
      if (note.extent_arcmin != null) details.append(paragraph(`Étendue de cette fiche étudiée : ${note.extent_bound === "lower_limit" ? "> " : "environ "}${note.extent_arcmin}′. Les périmètres des sources peuvent différer.`));
      else details.append(paragraph("L’étendue de la nébulosité photographique reste non documentée dans cette fiche étudiée."));
    }
    details.append(paragraph(`Provenance : ${object.source_id}, entrée ${object.source_row}. ${object.license || "Voir la source bibliographique de la fiche étudiée."}`, "source"));
    if (object.source_url) details.append(referenceLink(object.source_url, "Consulter la source de cette fiche"));
    article.append(details); results.append(article);
  }
  node("#catalogue-provenance").textContent = `Version source : ${payload.catalogue.source_revision}. Import du ${payload.catalogue.retrieved_on}. ${payload.catalogue.excluded_duplicates} doublons explicites et ${payload.catalogue.excluded_nonexistent} entrées inexistantes exclus. ${payload.catalogue.counting_note}`;
  node("#catalogue-previous").disabled = payload.offset === 0;
  node("#catalogue-next").disabled = payload.offset + payload.limit >= payload.total;
}
async function loadCatalogue(offset=0) {
  const signature = JSON.stringify([node("#catalogue-query").value.trim(), node("#catalogue-kind").value, node("#catalogue-framing").value]);
  if (signature !== cataloguePage.searchSignature) offset = 0;
  const generation = ++cataloguePage.generation;
  cataloguePage.controller?.abort(); cataloguePage.controller = new AbortController();
  node("#catalogue-status").textContent = "Recherche dans le catalogue local…";
  node("#catalogue-previous").disabled = true; node("#catalogue-next").disabled = true;
  const query = new URLSearchParams({q:node("#catalogue-query").value.trim(), offset, limit:cataloguePage.limit});
  if (catalogueEquipment) query.set("equipment", catalogueEquipment);
  if (node("#catalogue-kind").value) query.set("kind", node("#catalogue-kind").value);
  if (node("#catalogue-framing").value) query.set("framing", node("#catalogue-framing").value);
  try {
    let payload;
    if (window.NIGHTMERIT_OFFLINE_CATALOGUE) payload = offlineCataloguePage(query);
    else {
      const response = await fetch(`/v1/target-catalogue/search?${query}`, {signal:cataloguePage.controller.signal, cache:"no-store"});
      if (!response.ok) throw new Error(response.status === 422 ? "equipment" : "unavailable");
      payload = await response.json();
    }
    if (generation !== cataloguePage.generation) return;
    cataloguePage.offset = offset; cataloguePage.searchSignature = signature; showCatalogue(payload);
  } catch (error) {
    if (generation !== cataloguePage.generation || error.name === "AbortError") return;
    node("#catalogue-results").replaceChildren();
    node("#catalogue-status").textContent = error.message === "equipment"
      ? "Votre matériel doit être configuré pour comparer les cadrages. Revenez à NightMerit et renseignez-le."
      : "Le catalogue local n’a pas pu être lu. Revenez à NightMerit puis réessayez.";
  }
}
node("#catalogue-search").addEventListener("submit", event => {event.preventDefault(); loadCatalogue(0);});
node("#catalogue-previous").addEventListener("click", () => loadCatalogue(Math.max(0,cataloguePage.offset-cataloguePage.limit)));
node("#catalogue-next").addEventListener("click", () => loadCatalogue(cataloguePage.offset+cataloguePage.limit));
loadCatalogue();
