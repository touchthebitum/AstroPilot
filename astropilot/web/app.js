"use strict";

const ui = Object.freeze({
  configurationLoading: document.querySelector("#configuration-loading"),
  configurationError: document.querySelector("#configuration-error"),
  configurationErrorMessage: document.querySelector("#configuration-error-message"),
  configurationRetry: document.querySelector("#configuration-retry"),
  onboarding: document.querySelector("#onboarding"),
  formError: document.querySelector("#configuration-form-error"),
  availability: document.querySelector("#availability-step"),
  loading: document.querySelector("#loading-state"),
  message: document.querySelector("#message-state"),
  decision: document.querySelector("#decision"),
  refresh: document.querySelector("#refresh"),
  editConfiguration: document.querySelector("#edit-configuration"),
  retry: document.querySelector("#message-retry"),
  mission: document.querySelector("#mission-dialog"),
  openMission: document.querySelector("#open-mission"),
  closeMission: document.querySelector("#close-mission"),
  missionBack: document.querySelector("#mission-back"),
});

const state = {
  view: "loading_configuration",
  configuration: null,
  configurationDraft: {
    site: null,
    equipment: null,
    projects: {},
  },
  currentDecision: null,
  savingConfiguration: false,
};

const wizardStates = Object.freeze(["site", "equipment", "projects", "review"]);

function setView(view) {
  state.view = view;
  const wizardVisible = wizardStates.includes(view);
  ui.configurationLoading.hidden = view !== "loading_configuration";
  ui.configurationError.hidden = view !== "configuration_error";
  ui.onboarding.hidden = !wizardVisible;
  ui.availability.hidden = view !== "availability";
  ui.loading.hidden = view !== "loading_recommendation";
  ui.message.hidden = true;
  ui.decision.hidden = true;
  ui.refresh.hidden = true;
  ui.editConfiguration.hidden = !state.configuration?.configured || wizardVisible;

  for (const step of document.querySelectorAll("[data-step]")) {
    step.hidden = step.dataset.step !== view;
  }
  for (const marker of document.querySelectorAll("[data-progress]")) {
    marker.classList.toggle("active", marker.dataset.progress === view);
  }
  if (wizardVisible) {
    requestAnimationFrame(() => {
      document.querySelector(`[data-step="${view}"] h2`)?.focus();
    });
  }
}

const labels = Object.freeze({
  actions: {
    start_project: "Commencer ce projet",
    continue_project: "Continuer ce projet",
    complete_project: "Terminer ce projet",
    observe: "Observer cette cible",
  },
  quality: {
    excellent: ["Excellente", "Une nuit rare : les conditions soutiennent pleinement cette cible."],
    very_good: ["Très bonne", "Les conditions sont solides pour une session productive."],
    good: ["Bonne", "La nuit est exploitable avec quelques compromis limités."],
    average: ["Moyenne", "La session reste possible, en surveillant le facteur limitant."],
    low: ["Faible", "Les conditions réduisent sensiblement le potentiel de la session."],
  },
  factors: {
    altitude: "Altitude de la cible",
    clouds: "Couverture nuageuse",
    cloud_cover: "Couverture nuageuse",
    moon: "Lumière lunaire",
    seeing: "Turbulence atmosphérique",
    weather: "Conditions météo",
    dew: "Risque de rosée",
    setup: "Configuration matérielle",
  },
});

function text(selector, value) {
  document.querySelector(selector).textContent = value;
}

function show(view) {
  if (view === "loading") {
    setView("loading_recommendation");
    return;
  }
  setView("recommendation");
  ui.message.hidden = view !== "message";
  ui.decision.hidden = view !== "decision";
}

function duration(hours) {
  const value = Number(hours);
  if (!Number.isFinite(value) || value <= 0) return "Non précisée";
  const whole = Math.floor(value);
  const minutes = Math.round((value - whole) * 60);
  if (!whole) return `${minutes} min`;
  if (!minutes) return `${whole} h`;
  return `${whole} h ${String(minutes).padStart(2, "0")}`;
}

function clock(value) {
  if (!value) return null;
  if (/^\d{2}:\d{2}$/.test(value)) return value;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return new Intl.DateTimeFormat("fr-CH", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed);
}

function dateLabel(value) {
  if (!value) return "Prochaine nuit disponible";
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("fr-CH", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(parsed);
}

function siteDateTime(value, timeZone) {
  if (!value) return "Non précisée";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  try {
    return new Intl.DateTimeFormat("fr-CH", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone,
      timeZoneName: "short",
    }).format(parsed);
  } catch (_error) {
    return String(value);
  }
}

function renderWeatherTrust(weatherTrust, weatherDecision, prefix) {
  const ingressValidated = weatherTrust?.validation_status === "validated"
    && weatherTrust?.freshness_status === "fresh";
  if (!ingressValidated) {
    text(`#${prefix}-weather-status`, "Non disponible");
    text(`#${prefix}-weather-provider`, "Provenance non disponible");
    text(`#${prefix}-weather-age`, "Non évalué");
    text(`#${prefix}-weather-retrieved`, "Non précisée");
    text(`#${prefix}-weather-coverage`, "Non précisée");
    if (prefix === "classic") text("#classic-weather-timezone", "Fuseau du site non disponible.");
    return;
  }

  const zone = weatherTrust.timezone;
  const age = Number(weatherTrust.snapshot_age_minutes);
  const maximumAge = Number(weatherTrust.maximum_age_minutes);
  text(`#${prefix}-weather-status`, weatherDecision?.presentation?.label);
  text(`#${prefix}-weather-title`, weatherDecision?.presentation?.summary);
  text(`#${prefix}-weather-provider`, weatherTrust.provider);
  text(
    `#${prefix}-weather-age`,
    Number.isFinite(age)
      ? `Récupérées il y a ${age.toLocaleString("fr-CH")} min${Number.isFinite(maximumAge) ? ` · limite ${maximumAge.toLocaleString("fr-CH")} min` : ""}`
      : "Non évalué",
  );
  text(
    `#${prefix}-weather-retrieved`,
    siteDateTime(weatherTrust.retrieved_at_utc, zone),
  );
  text(
    `#${prefix}-weather-coverage`,
    `${siteDateTime(weatherTrust.valid_from, zone)} → ${siteDateTime(weatherTrust.valid_until, zone)}`,
  );
  if (prefix === "classic") {
    text("#classic-weather-timezone", `Horaires affichés dans le fuseau du site : ${zone}.`);
  }
}

function reasonText(reason) {
  if (!reason) return null;
  const title = reason.title || "Information";
  return reason.value ? `${title} — ${reason.value}` : title;
}

function setList(selector, items, fallback) {
  const list = document.querySelector(selector);
  list.replaceChildren();
  const values = items.filter(Boolean).slice(0, 3);
  if (!values.length) values.push(fallback);
  for (const value of values) {
    const item = document.createElement("li");
    item.textContent = value;
    if (value === fallback) item.className = "empty-insight";
    list.append(item);
  }
}

function renderMission(decision) {
  const start = clock(decision.window_start);
  const end = clock(decision.window_end);
  text("#mission-title", decision.target || "Mission de cette nuit");
  const missionAction = labels.actions[decision.action] || "Session recommandée";
  text("#mission-summary", decision.target_common_name ? `${decision.target_common_name} · ${missionAction}` : missionAction);
  text("#mission-window", start && end ? `${start} — ${end}` : "À confirmer");
  text("#mission-duration", duration(decision.recommended_hours));
  text("#mission-gain", Number(decision.expected_gain) > 0 ? `+${Math.round(Number(decision.expected_gain))} %` : "Non estimé");

  const equipment = document.querySelector("#mission-equipment");
  equipment.replaceChildren();
  const equipmentItems = (decision.equipment || []).filter(Boolean);
  for (const value of equipmentItems.length ? equipmentItems : ["Configuration non précisée"]) {
    const item = document.createElement("li");
    item.textContent = value;
    if (!equipmentItems.length) item.className = "mission-empty";
    equipment.append(item);
  }

  const filter = decision.selected_filter;
  document.querySelector("#mission-filter-wrap").hidden = !filter;
  text("#mission-filter", filter?.name || "—");

  const tasks = document.querySelector("#mission-tasks");
  tasks.replaceChildren();
  const taskItems = (decision.tasks || []).filter((task) => task?.title);
  for (const task of taskItems) {
    const item = document.createElement("li");
    const time = document.createElement("span");
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    time.className = "task-time";
    copy.className = "task-copy";
    time.textContent = `${task.start} → ${task.end}`;
    title.textContent = task.title;
    copy.append(title);
    if (task.description) {
      const description = document.createElement("small");
      description.textContent = task.description;
      copy.append(description);
    }
    item.append(time, copy);
    tasks.append(item);
  }
  if (!taskItems.length) {
    const item = document.createElement("li");
    item.className = "mission-empty";
    item.textContent = "Plan opérationnel non disponible.";
    tasks.append(item);
  }

  const advices = document.querySelector("#mission-advices");
  advices.replaceChildren();
  const adviceItems = (decision.advices || []).filter((advice) => advice?.message);
  for (const advice of adviceItems) {
    const item = document.createElement("li");
    const time = document.createElement("span");
    time.className = "advice-time";
    time.textContent = advice.time || "Cette nuit";
    item.append(time, document.createTextNode(advice.message));
    advices.append(item);
  }
  if (!adviceItems.length) {
    const item = document.createElement("li");
    item.className = "mission-empty";
    item.textContent = "Aucun conseil particulier pour cette nuit.";
    advices.append(item);
  }
}

function renderDecision(decision) {
  state.currentDecision = decision;

  const productivity = decision.productivity;
  const productiveHours = productivity?.productive_hours ?? decision.recommended_hours;
  const firstWindow = productivity?.windows?.find((window) => window.productive)
    || productivity?.windows?.[0];
  const start = clock(decision.window_start) || firstWindow?.start_time || null;
  const end = clock(decision.window_end) || firstWindow?.end_time || null;
  const filter = decision.selected_filter;
  const quality = decision.astro_quality;
  const qualityScore = quality ? Math.round(Number(quality.score)) : null;
  const qualityCopy = labels.quality[quality?.label] || ["Non évaluée", "L’indice de qualité n’est pas disponible pour cette décision."];
  const limiting = quality?.limiting_factor;
  const weatherTrust = decision.weather_trust;
  const weatherDecision = decision.weather_decision;

  text("#night-date", dateLabel(decision.night_date));
  text("#recommendation", labels.actions[decision.action] || "Session recommandée");
  text("#target-name", decision.target || "Cible à confirmer");
  text("#catalog-key", decision.target_common_name || (decision.catalog_key && decision.catalog_key !== decision.target ? decision.catalog_key : ""));
  text("#window-value", start && end ? `${start} — ${end}` : "À confirmer");
  text("#window-note", firstWindow?.reason ? "Fenêtre productive principale" : "Heure locale");
  text("#duration-value", duration(productiveHours));
  text("#duration-note", productivity?.productive_hours ? "Temps réellement exploitable" : "Durée de mission recommandée");
  text("#filter-value", filter?.name || "Aucun filtre précisé");
  text("#filter-note", filter?.filter_type ? filter.filter_type.replaceAll("_", " ") : "Selon la cible et le ciel");
  text("#quality-score", qualityScore === null ? "—" : String(qualityScore));
  text("#quality-title", qualityCopy[0]);
  text("#quality-summary", qualityCopy[1]);
  text("#limiting-factor", limiting ? (labels.factors[limiting] || limiting.replaceAll("_", " ")) : "Aucun identifié");
  renderWeatherTrust(weatherTrust, weatherDecision, "classic");
  renderWeatherTrust(weatherTrust, weatherDecision, "mission");

  const circumference = 2 * Math.PI * 48;
  const progress = document.querySelector("#quality-progress");
  const visualScore = qualityScore === null ? 0 : Math.max(0, Math.min(100, qualityScore));
  progress.style.strokeDashoffset = String(circumference * (1 - visualScore / 100));

  const positives = (decision.explanation?.positives || []).map(reasonText);
  const information = (decision.explanation?.information || []).map(reasonText);
  const warnings = (decision.explanation?.warnings || []).map(reasonText);
  const risks = [...warnings];
  if (decision.dew_risk && String(decision.dew_risk.level).toLowerCase() !== "low") {
    risks.push(`Rosée : risque ${String(decision.dew_risk.level).toLowerCase()}`);
  }
  if (decision.postponement_risk) {
    risks.push(...(decision.postponement_risk.explanations || []));
  }

  setList("#insights-list", [...positives, ...information], "Aucune explication supplémentaire disponible.");
  setList("#risks-list", risks, "Aucun risque essentiel signalé.");
  renderMission(decision);
  show("decision");
}

const customEquipmentFields = Object.freeze([
  ["optics_manufacturer", "#custom-optics-manufacturer", "text"],
  ["optics_model", "#custom-optics-model", "text"],
  ["focal_length_mm", "#custom-focal-length-mm", "number"],
  ["aperture_mm", "#custom-aperture-mm", "number"],
  ["f_ratio", "#custom-f-ratio", "number"],
  ["camera_manufacturer", "#custom-camera-manufacturer", "text"],
  ["camera_model", "#custom-camera-model", "text"],
  ["pixel_size_um", "#custom-pixel-size-um", "number"],
  ["sensor_width_px", "#custom-sensor-width-px", "number"],
  ["sensor_height_px", "#custom-sensor-height-px", "number"],
  ["monochrome", "#custom-monochrome", "boolean"],
]);

const configurationErrorSteps = Object.freeze({
  configuration_invalid_site: "site",
  configuration_invalid_bortle: "site",
  configuration_invalid_equipment: "equipment",
  configuration_invalid_custom_equipment: "equipment",
  configuration_invalid_project: "projects",
});

function copyProjects(projects) {
  return JSON.parse(JSON.stringify(projects || {}));
}

function draftFromConfiguration(configuration) {
  const active = (configuration.available_equipment || []).find(
    (equipment) => equipment.id === configuration.active_equipment_id,
  );
  let equipment = null;
  if (active?.kind === "custom") {
    equipment = {
      custom: Object.fromEntries(
        customEquipmentFields.map(([name]) => [name, active[name]]),
      ),
    };
  } else if (active) {
    equipment = { preset_id: active.id };
  } else if (configuration.preset_equipment?.length) {
    equipment = { preset_id: configuration.preset_equipment[0].id };
  }
  return {
    site: configuration.site ? { ...configuration.site } : null,
    equipment,
    projects: copyProjects(configuration.projects),
  };
}

function showFormError(message) {
  ui.formError.textContent = message || "";
  ui.formError.hidden = !message;
}

function renderPresetChoices() {
  const container = document.querySelector("#preset-equipment");
  container.replaceChildren();
  for (const choice of state.configuration?.preset_equipment || []) {
    const label = document.createElement("label");
    const radio = document.createElement("input");
    const copy = document.createElement("span");
    const name = document.createElement("strong");
    const details = document.createElement("small");
    label.className = "equipment-choice";
    radio.type = "radio";
    radio.name = "preset-equipment";
    radio.value = choice.id;
    name.textContent = choice.name;
    details.textContent = `${choice.optics_manufacturer} ${choice.optics_model} · ${choice.camera_manufacturer} ${choice.camera_model}`;
    copy.append(name, details);
    label.append(radio, copy);
    container.append(label);
  }
}

function toggleEquipmentKind() {
  const kind = document.querySelector('input[name="equipment-kind"]:checked')?.value;
  document.querySelector("#preset-equipment").hidden = kind !== "preset";
  document.querySelector("#custom-equipment").hidden = kind !== "custom";
}

function renderProjects() {
  const projects = state.configurationDraft.projects || {};
  const entries = Object.entries(projects);
  const summary = document.querySelector("#existing-projects");
  const zeroProjects = document.querySelector("#zero-projects");
  summary.replaceChildren();
  summary.hidden = !entries.length;
  if (entries.length) {
    const heading = document.createElement("p");
    heading.textContent = "Projets actuellement conservés";
    const list = document.createElement("ul");
    for (const [catalogKey, project] of entries) {
      const item = document.createElement("li");
      item.textContent = `${catalogKey} · ${project.hours} h sur ${project.target_hours} h`;
      list.append(item);
    }
    summary.append(heading, list);
    zeroProjects.checked = false;
    zeroProjects.disabled = false;
  } else {
    zeroProjects.checked = true;
    zeroProjects.disabled = true;
  }
}

function prefillConfiguration() {
  renderPresetChoices();
  const site = state.configurationDraft.site || {};
  document.querySelector("#site-name").value = site.name || "";
  document.querySelector("#site-latitude").value = site.latitude ?? "";
  document.querySelector("#site-longitude").value = site.longitude ?? "";
  document.querySelector("#site-bortle").value = site.bortle ?? "";

  const custom = state.configurationDraft.equipment?.custom;
  const kind = custom ? "custom" : "preset";
  document.querySelector(`input[name="equipment-kind"][value="${kind}"]`).checked = true;
  const presetId = state.configurationDraft.equipment?.preset_id;
  const preset = [...document.querySelectorAll('input[name="preset-equipment"]')]
    .find((input) => input.value === presetId);
  if (preset) preset.checked = true;
  for (const [name, selector, type] of customEquipmentFields) {
    const input = document.querySelector(selector);
    if (type === "boolean") input.checked = Boolean(custom?.[name]);
    else input.value = custom?.[name] ?? "";
  }
  toggleEquipmentKind();
  renderProjects();
}

function readSite() {
  const latitudeInput = document.querySelector("#site-latitude").value.trim();
  const longitudeInput = document.querySelector("#site-longitude").value.trim();
  const bortleInput = document.querySelector("#site-bortle").value.trim();
  const site = {
    name: document.querySelector("#site-name").value.trim(),
    latitude: Number(latitudeInput),
    longitude: Number(longitudeInput),
    bortle: Number(bortleInput),
  };
  if (!site.name) return [null, "Donnez un nom à votre site."];
  if (!latitudeInput || !Number.isFinite(site.latitude) || site.latitude < -90 || site.latitude > 90) {
    return [null, "La latitude doit être comprise entre −90 et 90."];
  }
  if (!longitudeInput || !Number.isFinite(site.longitude) || site.longitude < -180 || site.longitude > 180) {
    return [null, "La longitude doit être comprise entre −180 et 180."];
  }
  if (!bortleInput || !Number.isInteger(site.bortle) || site.bortle < 1 || site.bortle > 9) {
    return [null, "La valeur Bortle doit être un entier de 1 à 9."];
  }
  return [site, null];
}

function readCustomEquipment() {
  const custom = {};
  for (const [name, selector, type] of customEquipmentFields) {
    const input = document.querySelector(selector);
    if (type === "boolean") {
      custom[name] = input.checked;
    } else if (type === "number") {
      custom[name] = Number(input.value);
      if (!Number.isFinite(custom[name]) || custom[name] <= 0) {
        return [null, "Toutes les mesures du matériel doivent être positives."];
      }
    } else {
      custom[name] = input.value.trim();
      if (!custom[name]) {
        return [null, "Renseignez le fabricant et le modèle de l’optique et de la caméra."];
      }
    }
  }
  return [custom, null];
}

function readEquipment() {
  const kind = document.querySelector('input[name="equipment-kind"]:checked')?.value;
  if (kind === "custom") {
    const [custom, error] = readCustomEquipment();
    return [custom ? { custom } : null, error];
  }
  const selected = document.querySelector('input[name="preset-equipment"]:checked');
  if (!selected) return [null, "Choisissez une configuration matérielle."];
  return [{ preset_id: selected.value }, null];
}

function selectedEquipmentName() {
  const equipment = state.configurationDraft.equipment;
  if (equipment?.custom) {
    const custom = equipment.custom;
    return `${custom.optics_manufacturer} ${custom.optics_model} + ${custom.camera_manufacturer} ${custom.camera_model}`;
  }
  const choice = (state.configuration?.preset_equipment || []).find(
    (preset) => preset.id === equipment?.preset_id,
  );
  return choice?.name || "Matériel à confirmer";
}

function renderReview() {
  const site = state.configurationDraft.site;
  text("#review-site", site.name);
  text("#review-coordinates", `${site.latitude}, ${site.longitude}`);
  text("#review-bortle", `Bortle ${site.bortle}`);
  text("#review-equipment", selectedEquipmentName());
  const count = Object.keys(state.configurationDraft.projects || {}).length;
  text("#review-projects", count ? `${count} projet${count > 1 ? "s" : ""} conservé${count > 1 ? "s" : ""}` : "Aucun projet pour l’instant");
}

function configurationPayload() {
  const payload = {
    site: state.configurationDraft.site,
    equipment: state.configurationDraft.equipment,
    projects: copyProjects(state.configurationDraft.projects),
  };
  if (state.configuration?.configured) {
    payload.expected_revision = state.configuration.profile_revision;
  }
  return payload;
}

function showConfigurationError(message) {
  ui.configurationErrorMessage.textContent = message;
  setView("configuration_error");
}

async function loadConfiguration({ afterConflict = false } = {}) {
  setView("loading_configuration");
  try {
    const response = await fetch("/v1/configuration");
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const code = payload?.detail?.code;
      const message = code === "configuration_corrupt"
        ? "La configuration enregistrée ne peut pas être relue. Réessayez dans un instant."
        : "La configuration est temporairement inaccessible. Réessayez dans un instant.";
      showConfigurationError(message);
      return;
    }
    state.configuration = payload;
    state.configurationDraft = draftFromConfiguration(payload);
    prefillConfiguration();
    if (afterConflict) {
      showFormError("La configuration a changé. Vérifiez les dernières valeurs avant de l’enregistrer à nouveau.");
      renderReview();
      setView("review");
    } else if (payload.configured) {
      showFormError("");
      setView("availability");
    } else {
      showFormError("");
      setView("site");
    }
  } catch (_error) {
    showConfigurationError("AstroPilot ne parvient pas à charger la configuration. La saisie pourra reprendre après reconnexion.");
  }
}

async function saveConfiguration() {
  if (state.savingConfiguration) return;
  state.savingConfiguration = true;
  const button = document.querySelector("#save-configuration");
  button.disabled = true;
  showFormError("");
  try {
    const response = await fetch("/v1/configuration", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(configurationPayload()),
    });
    const payload = await response.json().catch(() => ({}));
    const detail = payload?.detail;
    if (!response.ok) {
      if (response.status === 409 && detail?.code === "configuration_revision_conflict") {
        await loadConfiguration({ afterConflict: true });
        return;
      }
      const target = configurationErrorSteps[detail?.code];
      if (target) {
        showFormError("Certaines informations doivent être corrigées avant l’enregistrement.");
        setView(target);
        return;
      }
      if (["configuration_corrupt", "configuration_persistence_error"].includes(detail?.code)) {
        showConfigurationError("La configuration ne peut pas être enregistrée pour le moment. Réessayez dans un instant.");
        return;
      }
      showFormError("La configuration n’a pas pu être validée.");
      setView("review");
      return;
    }
    state.configuration = payload;
    state.configurationDraft = draftFromConfiguration(payload);
    prefillConfiguration();
    setView("availability");
  } catch (_error) {
    showFormError("Connexion impossible pendant l’enregistrement. Vérifiez vos informations puis réessayez.");
    setView("review");
  } finally {
    state.savingConfiguration = false;
    button.disabled = false;
  }
}

const partialMessages = Object.freeze({
  no_night: ["Aucune nuit exploitable", "Les prévisions ne montrent pas encore de fenêtre adaptée. Revenez lorsque les conditions évoluent."],
  no_candidate: ["Aucune cible adaptée", "AstroPilot n’a trouvé aucune cible compatible avec cette nuit et votre configuration."],
  no_recommendation: ["Décision encore incertaine", "Les données disponibles ne permettent pas d’établir une recommandation suffisamment fiable."],
  no_mission: ["Mission incomplète", "Une cible a été identifiée, mais la mission opérationnelle n’a pas pu être assemblée."],
  no_productive_window: ["Aucun créneau suffisamment productif", "Une nuit astronomique existe, mais aucune fenêtre n’atteint le seuil opérationnel requis par AstroPilot."],
});

function showMessage(title, body, { kicker = "Décision indisponible", retry = true } = {}) {
  text("#message-kicker", kicker);
  text("#message-title", title);
  text("#message-body", body);
  ui.retry.hidden = !retry;
  show("message");
}

function normalizeError(response, payload) {
  const detail = payload?.detail;
  if (payload?.error === "user_profile_unavailable") {
    return ["Configuration requise", "AstroPilot doit relire votre configuration avant de préparer la nuit."];
  }
  if (response.status === 503) {
    if (detail?.code === "weather_unavailable") {
      return ["Météo temporairement indisponible", "AstroPilot ne peut pas encore lire les conditions de votre site. Réessayez dans un instant."];
    }
    if (detail?.code === "weather_invalid") {
      return ["Données météo rejetées", "AstroPilot a reçu une réponse météo, mais ses contrôles de cohérence ont échoué. Aucune décision n’est calculée."];
    }
    if (detail?.code === "weather_insufficient") {
      return ["Prévisions météo insuffisantes", "La couverture reçue ne permet pas de préparer la nuit avec assez de données. Aucune décision n’est calculée."];
    }
    if (detail?.code === "weather_stale") {
      return ["Données météo trop anciennes", "Les données météo reçues dépassent la limite de fraîcheur de 90 minutes. AstroPilot refuse de calculer une décision potentiellement trompeuse."];
    }
    if (detail?.code === "decision_invalid") {
      return ["Décision rejetée par sécurité", "AstroPilot a détecté une contradiction interne et refuse d’afficher une recommandation potentiellement trompeuse."];
    }
    if (detail?.code === "location_timezone_unresolved") {
      return ["Fuseau horaire introuvable", "AstroPilot ne peut pas relier ce site à un fuseau horaire fiable et refuse de calculer une nuit locale."];
    }
    return ["Prévisions temporairement indisponibles", "La prévision de cette nuit n’est pas accessible pour le moment. Réessayez dans un instant."];
  }
  if (response.status === 422) {
    const validationMessage = Array.isArray(detail)
      ? detail.map((item) => item.msg).filter(Boolean).join(" · ")
      : detail?.message;
    return ["Informations à vérifier", validationMessage || "Certaines informations nécessaires à la décision ne sont pas valides."];
  }
  return ["AstroPilot n’a pas pu répondre", "Une erreur inattendue empêche la préparation de votre nuit."];
}

async function loadTonight(availability) {
  show("loading");
  ui.refresh.disabled = true;
  state.currentDecision = null;

  try {
    const response = await fetch("/v1/tonight", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ availability }),
    });
    const payload = await response.json().catch(() => ({}));

    if (!response.ok) {
      const [title, body] = normalizeError(response, payload);
      showMessage(title, body, { kicker: response.status === 422 ? "Entrée invalide" : "Service indisponible" });
      return;
    }

    if (payload.status === "weather_refused") {
      showMessage(
        payload.weather_decision.presentation.label,
        payload.weather_decision.presentation.summary,
        { kicker: "Analyse terminée" },
      );
      return;
    }

    if (payload.status !== "available") {
      const [title, body] = partialMessages[payload.status] || ["Décision indisponible", "AstroPilot ne dispose pas encore d’une recommandation exploitable."];
      showMessage(title, body, { kicker: "Analyse terminée" });
      return;
    }

    renderDecision(payload);
  } catch (_error) {
    showMessage("Connexion impossible", "AstroPilot ne parvient pas à joindre le service de décision. Vérifiez la connexion puis réessayez.", { kicker: "Hors ligne" });
  } finally {
    ui.refresh.disabled = false;
  }
}

document.querySelector("#site-next").addEventListener("click", () => {
  const [site, error] = readSite();
  if (error) {
    showFormError(error);
    return;
  }
  state.configurationDraft.site = site;
  showFormError("");
  setView("equipment");
});

document.querySelector("#equipment-next").addEventListener("click", () => {
  const [equipment, error] = readEquipment();
  if (error) {
    showFormError(error);
    return;
  }
  state.configurationDraft.equipment = equipment;
  showFormError("");
  renderProjects();
  setView("projects");
});

document.querySelector("#projects-next").addEventListener("click", () => {
  if (document.querySelector("#zero-projects").checked) {
    state.configurationDraft.projects = {};
  }
  showFormError("");
  renderReview();
  setView("review");
});

for (const button of document.querySelectorAll("[data-back]")) {
  button.addEventListener("click", () => {
    showFormError("");
    setView(button.dataset.back);
  });
}

for (const input of document.querySelectorAll('input[name="equipment-kind"]')) {
  input.addEventListener("change", toggleEquipmentKind);
}

document.querySelector("#save-configuration").addEventListener("click", saveConfiguration);
ui.configurationRetry.addEventListener("click", loadConfiguration);
ui.editConfiguration.addEventListener("click", () => {
  state.configurationDraft = draftFromConfiguration(state.configuration);
  prefillConfiguration();
  showFormError("");
  setView("site");
});
ui.refresh.addEventListener("click", () => setView("availability"));
ui.retry.addEventListener("click", () => setView("availability"));

document.querySelector("#use-geolocation").addEventListener("click", () => {
  const message = document.querySelector("#geolocation-message");
  if (!navigator.geolocation) {
    message.textContent = "La géolocalisation n’est pas disponible. La saisie manuelle reste disponible.";
    return;
  }
  message.textContent = "Recherche de votre position…";
  navigator.geolocation.getCurrentPosition(
    (position) => {
      document.querySelector("#site-latitude").value = position.coords.latitude.toFixed(6);
      document.querySelector("#site-longitude").value = position.coords.longitude.toFixed(6);
      message.textContent = "Coordonnées ajoutées. Vous pouvez les corriger manuellement.";
    },
    () => {
      message.textContent = "Position non disponible. La saisie manuelle reste disponible.";
    },
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
  );
});

ui.openMission.addEventListener("click", () => {
  if (state.currentDecision) ui.mission.showModal();
});
ui.closeMission.addEventListener("click", () => ui.mission.close());
ui.missionBack.addEventListener("click", () => ui.mission.close());
ui.mission.addEventListener("click", (event) => {
  if (event.target === ui.mission) ui.mission.close();
});
loadConfiguration();
