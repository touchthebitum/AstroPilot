"use strict";

const ui = Object.freeze({
  configurationLoading: document.querySelector("#configuration-loading"),
  configurationError: document.querySelector("#configuration-error"),
  configurationErrorMessage: document.querySelector("#configuration-error-message"),
  configurationRetry: document.querySelector("#configuration-retry"),
  configurationRecover: document.querySelector("#configuration-recover"),
  configurationRecoveryConfirmation: document.querySelector("#configuration-recovery-confirmation"),
  configurationRecoveryCancel: document.querySelector("#configuration-recovery-cancel"),
  configurationRecoveryConfirm: document.querySelector("#configuration-recovery-confirm"),
  onboarding: document.querySelector("#onboarding"),
  formError: document.querySelector("#configuration-form-error"),
  availability: document.querySelector("#availability-step"),
  availabilityForm: document.querySelector("#availability-form"),
  savedMissionEntry: document.querySelector("#saved-mission-entry"),
  savedMissionTarget: document.querySelector("#saved-mission-target"),
  openSavedMission: document.querySelector("#open-saved-mission"),
  availabilityError: document.querySelector("#availability-error"),
  availabilitySiteTimezone: document.querySelector("#availability-site-timezone"),
  availabilityTimezoneWarning: document.querySelector("#availability-timezone-warning"),
  recommendationSubmit: document.querySelector("#request-recommendation"),
  loading: document.querySelector("#loading-state"),
  message: document.querySelector("#message-state"),
  pendingAcceptance: document.querySelector("#pending-acceptance-state"),
  pendingAcceptanceMessage: document.querySelector("#pending-acceptance-message"),
  retryPendingAcceptance: document.querySelector("#retry-pending-acceptance"),
  decision: document.querySelector("#decision"),
  refresh: document.querySelector("#refresh"),
  editConfiguration: document.querySelector("#edit-configuration"),
  editAvailability: document.querySelector("#edit-availability"),
  retry: document.querySelector("#message-retry"),
  mission: document.querySelector("#mission-dialog"),
  openMission: document.querySelector("#open-mission"),
  closeMission: document.querySelector("#close-mission"),
  missionBack: document.querySelector("#mission-back"),
  acceptanceStatus: document.querySelector("#acceptance-status"),
  recommendationConfidence: document.querySelector("#recommendation-confidence-value"),
  alternatives: document.querySelector("#alternatives-section"),
  alternativesList: document.querySelector("#alternatives-list"),
  primaryIntentChoice: document.querySelector("#primary-intent-choice"),
});

const state = {
  view: "loading_configuration",
  configuration: null,
  configurationDraft: {
    site: null,
    equipment: null,
    projects: {},
  },
  availability: null,
  currentDecision: null,
  acceptedMission: null,
  pendingAcceptanceAttempt: null,
  pendingAcceptanceStorageInvalid: false,
  acceptingRecommendation: false,
  acceptanceBlocked: false,
  savingConfiguration: false,
  requestingRecommendation: false,
  configurationErrorCode: null,
  recoveringConfiguration: false,
  progressEditor: null,
  progressEditorBaseline: null,
  sessions: [],
  activeSessionId: null,
  sessionBusy: false,
};

const SESSION_PENDING_KEY = "astropilot.pendingSession";

function sessionMessage(message) {
  text("#session-status", message);
}

function sessionHours(seconds) {
  if (seconds == null) return "inconnu";
  const minutes = Math.round(Number(seconds) / 60);
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")}`;
}

function currentSession() {
  return state.sessions.find((item) => item.execution.execution_id === state.activeSessionId) || null;
}

function usableEvidence(session) {
  return (session?.evidence || []).find((item) => item.category === "acquisition"
    && Number(item.usable_integration_duration) > 0);
}

function renderSession() {
  const session = currentSession();
  const status = session?.execution.status;
  const choice = document.querySelector("#session-choice");
  choice.replaceChildren();
  for (const item of state.sessions) {
    const option = document.createElement("option");
    option.value = item.execution.execution_id;
    option.textContent = `${item.execution.actual_start ? new Date(item.execution.actual_start).toLocaleString("fr-CH") : "À démarrer"} · ${item.execution.status}`;
    choice.append(option);
  }
  choice.hidden = !state.sessions.length;
  if (session) choice.value = session.execution.execution_id;
  const intentId = session?.acquisition_intent_id || state.acceptedMission?.acquisitionIntentId;
  text("#session-intent", `Intent de la mission : ${intentId || "non défini"}`);
  document.querySelector("#session-start").hidden = status === "in_progress";
  document.querySelector("#session-start").textContent = status === "not_started"
    ? "Démarrer cette session" : "Créer et démarrer une nouvelle session";
  document.querySelector("#session-close-actions").hidden = status !== "in_progress";
  document.querySelector("#session-evidence").hidden = status !== "completed" || Boolean(usableEvidence(session));
  const evidence = usableEvidence(session);
  document.querySelector("#session-credit").hidden = !evidence || Boolean(session.credit);
  if (evidence && !session.credit) {
    text("#session-credit-preview", `Intent ${session.acquisition_intent_id} · base historique : ${sessionHours(session.historical_baseline_seconds)} · crédit proposé : ${sessionHours(Number(evidence.usable_integration_duration))}`);
    const mustConfirm = Number(session.historical_baseline_seconds) > 0 && !session.historical_baseline_confirmed;
    document.querySelector("#session-baseline-confirm-wrap").hidden = !mustConfirm;
    document.querySelector("#session-baseline-confirm").checked = false;
  }
  document.querySelector("#session-progress").hidden = !session;
  if (session) {
    text("#session-before", sessionHours(session.acquired_before_seconds));
    text("#session-added", sessionHours(session.session_credit_seconds));
    text("#session-after", sessionHours(session.acquired_after_seconds));
    text("#session-remaining", session.target_hours == null ? "objectif non défini" : sessionHours(session.remaining_hours * 3600));
    sessionMessage(status === "interrupted" ? "Session interrompue : aucun crédit."
      : session.credit ? "Crédit enregistré." : status === "completed" ? "Session terminée."
      : status === "in_progress" ? "Session en cours." : "Session prête à démarrer.");
  } else sessionMessage("Aucune session enregistrée pour cette mission.");
}

async function reloadSessions({ selectId = null } = {}) {
  const missionId = state.acceptedMission?.mission_id;
  if (!missionId) return;
  const response = await fetch(`/v1/missions/${encodeURIComponent(missionId)}/executions`);
  if (!response.ok) throw new Error("session_read_unavailable");
  const sessions = await response.json();
  if (state.acceptedMission?.mission_id !== missionId) return;
  state.sessions = sessions;
  const pending = JSON.parse(localStorage.getItem(SESSION_PENDING_KEY) || "null");
  const candidate = selectId || (pending?.mission_id === missionId ? pending.execution_id : null);
  state.activeSessionId = sessions.some((item) => item.execution.execution_id === candidate)
    ? candidate : sessions.some((item) => item.execution.execution_id === state.activeSessionId)
      ? state.activeSessionId : sessions.at(-1)?.execution.execution_id || null;
  if (pending?.mission_id === missionId && sessions.some((item) => item.execution.execution_id === pending.execution_id)) {
    localStorage.removeItem(SESSION_PENDING_KEY);
  }
  renderSession();
}

async function sessionCommand(command) {
  if (state.sessionBusy || !state.acceptedMission?.mission_id) return;
  const baselineConfirmed = document.querySelector("#session-baseline-confirm").checked;
  state.sessionBusy = true;
  document.querySelectorAll(".session-panel button").forEach((button) => { button.disabled = true; });
  const missionId = state.acceptedMission.mission_id;
  try {
    await reloadSessions();
    await command(missionId, baselineConfirmed);
    await reloadSessions();
  } catch (_error) {
    try {
      await reloadSessions();
      sessionMessage("État relu après une réponse incertaine. Vérifiez la session avant de poursuivre.");
    } catch (_readError) {
      sessionMessage("Lecture impossible. Rechargez la page avant une nouvelle action.");
    }
  } finally {
    state.sessionBusy = false;
    document.querySelectorAll(".session-panel button").forEach((button) => { button.disabled = false; });
  }
}

async function postSession(url, body) {
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!response.ok) throw new Error("session_command_failed");
  return response.json();
}

async function startSession(missionId) {
  let session = currentSession();
  if (session?.execution.status !== "not_started") {
    const pending = JSON.parse(localStorage.getItem(SESSION_PENDING_KEY) || "null");
    const executionId = pending?.mission_id === missionId ? pending.execution_id : crypto.randomUUID();
    localStorage.setItem(SESSION_PENDING_KEY, JSON.stringify({ mission_id: missionId, execution_id: executionId }));
    const lookup = await fetch(`/v1/executions/${encodeURIComponent(executionId)}/session`);
    if (lookup.status === 404) await postSession("/v1/executions", { execution_id: executionId, mission_id: missionId });
    else if (!lookup.ok) throw new Error("session_read_unavailable");
    await reloadSessions({ selectId: executionId });
    session = currentSession();
  }
  if (session?.execution.status === "not_started") {
    await postSession("/v1/execution-transitions", {
      execution_id: session.execution.execution_id, mission_id: missionId,
      status: "in_progress", actual_start: new Date().toISOString(), actual_end: null, actual_duration: null,
    });
  }
}

async function closeSession(missionId, status) {
  const session = currentSession();
  if (session?.execution.status !== "in_progress") return;
  const end = new Date();
  const start = new Date(session.execution.actual_start);
  await postSession("/v1/execution-transitions", {
    execution_id: session.execution.execution_id, mission_id: missionId, status,
    actual_start: session.execution.actual_start, actual_end: end.toISOString(),
    actual_duration: Math.max(0, (end.getTime() - start.getTime()) / 1000),
  });
}

async function recordSessionEvidence() {
  const session = currentSession();
  if (session?.execution.status !== "completed" || usableEvidence(session)) return;
  const hours = Number(document.querySelector("#session-hours").value);
  const minutes = Number(document.querySelector("#session-minutes").value);
  if (!Number.isInteger(hours) || hours < 0 || !Number.isInteger(minutes) || minutes < 0 || minutes > 59 || hours * 60 + minutes <= 0) {
    sessionMessage("Saisissez une durée utilisable positive en heures et minutes.");
    return;
  }
  const key = `astropilot.pendingEvidence.${session.execution.execution_id}`;
  const saved = JSON.parse(localStorage.getItem(key) || "null");
  const evidenceId = saved?.evidence_id || crypto.randomUUID();
  localStorage.setItem(key, JSON.stringify({ evidence_id: evidenceId, minutes: hours * 60 + minutes }));
  const lookup = await fetch(`/v1/executions/${encodeURIComponent(session.execution.execution_id)}/session`);
  if (!lookup.ok) throw new Error("session_read_unavailable");
  const canonical = await lookup.json();
  if (canonical.evidence.some((item) => item.evidence_id === evidenceId || Number(item.usable_integration_duration) > 0)) return;
  await postSession("/v1/outcome-evidence", {
    evidence_id: evidenceId, execution_id: session.execution.execution_id,
    category: "acquisition", observed_at: new Date().toISOString(), source: "user",
    usable_integration_duration: (hours * 60 + minutes) * 60,
  });
}

async function creditSession(_missionId, confirmed) {
  const session = currentSession();
  const evidence = usableEvidence(session);
  if (!evidence || session.credit) return;
  const mustConfirm = Number(session.historical_baseline_seconds) > 0 && !session.historical_baseline_confirmed;
  if (mustConfirm && !confirmed) {
    sessionMessage("Confirmez la valeur historique affichée avant de créditer.");
    return;
  }
  await postSession(`/v1/executions/${encodeURIComponent(session.execution.execution_id)}/intent-progress-credit`, {
    expected_revision: session.profile_revision, evidence_ids: [evidence.evidence_id],
    confirm_historical_baseline: mustConfirm && confirmed,
  });
}

const PENDING_ACCEPTANCE_STORAGE_KEY = "astropilot.pendingAcceptance";
const PENDING_ACCEPTANCE_STORAGE_VERSION = 2;

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
  ui.pendingAcceptance.hidden = view !== "unresolved_acceptance";
  ui.decision.hidden = true;
  ui.refresh.hidden = view !== "recommendation";
  ui.editAvailability.hidden = view !== "recommendation";
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
  } else if (view === "availability") {
    requestAnimationFrame(() => {
      document.querySelector("#availability-title")?.focus();
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
  riskLevels: { low: "faible", medium: "modéré", high: "élevé" },
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

function renderMission(mission) {
  const start = clock(mission.window_start);
  const end = clock(mission.window_end);
  text("#mission-title", mission.target || "Mission de cette nuit");
  text("#mission-summary", mission.site_name ? `Mission acceptée · ${mission.site_name}` : "Mission acceptée");
  text("#mission-window", start && end ? `${start} — ${end}` : "À confirmer");
  text("#mission-duration", duration(mission.recommended_hours));
  text("#mission-gain", Number(mission.expected_gain) > 0 ? `+${Math.round(Number(mission.expected_gain))} %` : "Non estimé");

  const equipment = document.querySelector("#mission-equipment");
  equipment.replaceChildren();
  const equipmentItems = (mission.equipment || []).filter(Boolean);
  for (const value of equipmentItems.length ? equipmentItems : ["Configuration non précisée"]) {
    const item = document.createElement("li");
    item.textContent = value;
    if (!equipmentItems.length) item.className = "mission-empty";
    equipment.append(item);
  }

  const filter = mission.selected_filter;
  document.querySelector("#mission-filter-wrap").hidden = !filter;
  text("#mission-filter", filter?.name || "—");

  const tasks = document.querySelector("#mission-tasks");
  tasks.replaceChildren();
  const taskItems = (mission.tasks || []).filter((task) => task?.title);
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

  reloadSessions().catch(() => sessionMessage("Sessions momentanément indisponibles. Rechargez avant une action."));

}

function showAcceptanceStatus(message, { error = false } = {}) {
  ui.acceptanceStatus.textContent = message || "";
  ui.acceptanceStatus.hidden = !message;
  ui.acceptanceStatus.classList.toggle("error", error);
}

function formatRecommendationConfidence(confidence) {
  if (typeof confidence !== "number" || !Number.isFinite(confidence)) {
    return "Non disponible";
  }
  const value = confidence;
  if (value < 0 || value > 1) return "Non disponible";
  return `${Math.round(value * 100)} %`;
}

function clearAlternatives() {
  ui.alternativesList.replaceChildren();
  ui.alternatives.hidden = true;
}

function alternativeReasonText(reason) {
  const value = reason?.rendered?.classic_text || reason?.message;
  return typeof value === "string" && value.trim() && value.trim() !== "."
    ? value.trim() : null;
}

function intentMode(subject) {
  if (!subject?.acquisition_intent_selection_status) return "legacy";
  if (subject.acquisition_intent_selection_status === "no_eligible_intent") return "none";
  const frontier = subject.viable_acquisition_intent_ids || [];
  const options = subject.acquisition_intent_options || [];
  if (!Array.isArray(frontier) || !Array.isArray(options)
      || options.length !== frontier.length
      || options.some((option, index) => option.acquisition_intent_id !== frontier[index]
        || !option.label)) return "unavailable";
  if (frontier.length === 1 && subject.selected_acquisition_intent_id === frontier[0]) return "unique";
  if (frontier.length > 1 && subject.selected_acquisition_intent_id === null) return "multiple";
  return "unavailable";
}

function renderIntentChoice(container, subject, selectId) {
  container.replaceChildren();
  const mode = intentMode(subject);
  container.hidden = mode === "legacy";
  if (mode === "legacy") return;
  if (mode === "unique") {
    container.textContent = `Acquisition prévue : ${subject.acquisition_intent_options[0].label}`;
    return;
  }
  if (mode === "none" || mode === "unavailable") {
    const warning = document.createElement("span");
    warning.className = "intent-warning";
    warning.textContent = mode === "none"
      ? "Aucune acquisition recommandée pour cette nuit. Aucune prise de vue de ce champ ne répond aux critères de sélection."
      : "Le choix de prise de vue est indisponible. Actualisez la recommandation.";
    container.append(warning);
    return;
  }
  const label = document.createElement("label");
  label.htmlFor = selectId;
  label.textContent = "Choisissez votre prise de vue pour créer la mission";
  const select = document.createElement("select");
  select.id = selectId;
  select.append(new Option("Choisir une prise de vue", ""));
  for (const option of subject.acquisition_intent_options) {
    select.append(new Option(option.label, option.acquisition_intent_id));
  }
  select.addEventListener("change", () => {
    if (state.acceptedMission) return;
    showAcceptanceStatus("");
    restoreAcceptanceControls();
  });
  container.append(label, select);
}

function chosenIntent(subject, container) {
  const mode = intentMode(subject);
  if (mode === "legacy") return null;
  if (mode === "unique") return subject.selected_acquisition_intent_id;
  if (mode !== "multiple") return undefined;
  const value = container?.querySelector("select")?.value;
  return subject.viable_acquisition_intent_ids.includes(value) ? value : undefined;
}

function renderAlternatives(decision) {
  clearAlternatives();
  const alternatives = (Array.isArray(decision.alternatives) ? decision.alternatives : [])
    .filter((alternative) => (
      typeof alternative?.catalog_key === "string"
      && alternative.catalog_key.trim()
      && alternative.target_decision_status === "viable"
      && !["none", "unavailable"].includes(intentMode(alternative))
    ))
    .slice(0, 2);
  if (!alternatives.length || !decision.decision_id) return;

  for (const alternative of alternatives) {
    const displayTarget = alternative.target || alternative.catalog_key;
    const card = document.createElement("article");
    const copy = document.createElement("div");
    const name = document.createElement("h4");
    const reasons = document.createElement("ul");
    const intentChoice = document.createElement("div");
    const button = document.createElement("button");
    card.className = "alternative-card";
    if (alternative.acquisition_intent_selection_status) card.classList.add("has-intent");
    copy.className = "alternative-copy";
    name.textContent = displayTarget;
    reasons.className = "alternative-reasons";
    const reasonTexts = (alternative.reasons || [])
      .map(alternativeReasonText)
      .filter(Boolean)
      .slice(0, 2);
    if (!reasonTexts.length && decision.weather_decision?.admissibility === "caution") {
      reasonTexts.push("Autre cible exploitable, sous réserve des conditions météo.");
    }
    for (const reasonText of reasonTexts) {
      const item = document.createElement("li");
      item.textContent = reasonText;
      reasons.append(item);
    }
    copy.append(name);
    if (reasonTexts.length) copy.append(reasons);
    intentChoice.className = "intent-choice";
    renderIntentChoice(intentChoice, alternative, `alternative-intent-${alternative.catalog_key}`);
    if (!intentChoice.hidden) copy.append(intentChoice);

    button.type = "button";
    button.className = "mission-button alternative-button";
    button.textContent = `Photographier ${displayTarget}`;
    button.dataset.acceptanceSource = "alternative";
    button.dataset.catalogKey = alternative.catalog_key;
    button.dataset.decisionId = decision.decision_id;
    button.hidden = ["none", "unavailable"].includes(intentMode(alternative));
    button.addEventListener("click", () => acceptRecommendation({
      source: "alternative",
      selectedCatalogKey: alternative.catalog_key,
      expectedDecisionId: decision.decision_id,
      triggerButton: button,
      selectedTarget: displayTarget,
    }));
    card.append(copy, button);
    ui.alternativesList.append(card);
  }
  ui.alternatives.hidden = false;
}

function acceptanceControls() {
  return [ui.openMission, ...ui.alternativesList.querySelectorAll("button")];
}

function intentReady(button) {
  const decision = state.currentDecision;
  if (!decision) return false;
  if (button === ui.openMission && (decision.target_decision_status !== "recommended"
      || !decision.decision_id || !decision.catalog_key)) return false;
  const subject = button === ui.openMission ? decision
    : (decision.alternatives || []).find((item) => item.catalog_key === button.dataset.catalogKey);
  if (!subject || (button !== ui.openMission && subject.target_decision_status !== "viable")) return false;
  const container = button === ui.openMission ? ui.primaryIntentChoice
    : button.closest(".alternative-card")?.querySelector(".intent-choice");
  return chosenIntent(subject, container) !== undefined;
}

function disableAcceptanceControls(disabled) {
  for (const button of acceptanceControls()) button.disabled = disabled;
}

function showAcceptedIntent(subject, container, intentId) {
  if (intentMode(subject) === "legacy") return intentId === null;
  const option = subject.acquisition_intent_options?.find(
    (item) => item.acquisition_intent_id === intentId
  );
  if (!option) return false;
  container.replaceChildren();
  container.hidden = false;
  container.textContent = `Acquisition choisie : ${option.label}`;
  return true;
}

function restoreAcceptanceControls() {
  disableAcceptanceControls(Boolean(state.acceptanceBlocked || state.acceptedMission));
  if (!state.acceptanceBlocked && !state.acceptedMission) {
    for (const button of acceptanceControls()) button.disabled = !intentReady(button);
  }
  if (state.pendingAcceptanceAttempt) {
    disableAcceptanceControls(true);
    const pending = state.pendingAcceptanceAttempt;
    const selected = acceptanceControls().find((button) => (
      button.dataset.acceptanceSource === pending.source
      && button.dataset.catalogKey === pending.selected_catalog_key
      && button.dataset.decisionId === pending.decision_id
    ));
    if (selected) selected.disabled = !intentReady(selected);
    return;
  }
  if (state.acceptedMission) {
    const selected = acceptanceControls().find((button) => (
      button.dataset.acceptanceSource === state.acceptedMission.source
      && button.dataset.catalogKey === state.acceptedMission.selectedCatalogKey
    ));
    if (selected) {
      selected.disabled = false;
      selected.textContent = "Ouvrir la mission";
    }
  }
}

function sameAcceptanceIntent(attempt, intent) {
  return attempt.decision_id === intent.decision_id
    && attempt.source === intent.source
    && attempt.selected_catalog_key === intent.selected_catalog_key
    && attempt.acquisition_intent_id === intent.acquisition_intent_id;
}

function parsePendingAcceptance(raw) {
  let stored;
  try {
    stored = JSON.parse(raw);
  } catch (_error) {
    return null;
  }
  if (!stored || typeof stored !== "object" || Array.isArray(stored)) return null;
  const storedKeys = Object.keys(stored).sort();
  if (storedKeys.join(",") !== "request,state,version") return null;
  if (
    ![1, PENDING_ACCEPTANCE_STORAGE_VERSION].includes(stored.version)
    || stored.state !== "unresolved"
    || !stored.request
    || typeof stored.request !== "object"
    || Array.isArray(stored.request)
  ) return null;
  const request = stored.request;
  const requestKeys = Object.keys(request).sort();
  if (
    requestKeys.join(",") !== (stored.version === 1
      ? "acceptance_request_id,decision_id,selected_at,selected_catalog_key,source"
      : "acceptance_request_id,acquisition_intent_id,decision_id,selected_at,selected_catalog_key,source")
  ) return null;
  const identityPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
  const timestampPattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
  if (
    !identityPattern.test(request.acceptance_request_id)
    || !identityPattern.test(request.decision_id)
    || !["primary_recommendation", "alternative"].includes(request.source)
    || typeof request.selected_catalog_key !== "string"
    || !request.selected_catalog_key.trim()
    || (stored.version === 2 && request.acquisition_intent_id !== null
      && (typeof request.acquisition_intent_id !== "string" || !request.acquisition_intent_id.trim()))
    || !timestampPattern.test(request.selected_at)
    || !Number.isFinite(Date.parse(request.selected_at))
    || new Date(request.selected_at).toISOString() !== request.selected_at
  ) return null;
  return Object.freeze({
    acceptance_request_id: request.acceptance_request_id,
    decision_id: request.decision_id,
    source: request.source,
    selected_catalog_key: request.selected_catalog_key,
    acquisition_intent_id: request.acquisition_intent_id ?? null,
    selected_at: request.selected_at,
  });
}

function persistPendingAcceptanceAttempt(attempt) {
  localStorage.setItem(PENDING_ACCEPTANCE_STORAGE_KEY, JSON.stringify({
    version: PENDING_ACCEPTANCE_STORAGE_VERSION,
    state: "unresolved",
    request: attempt,
  }));
}

function restorePendingAcceptanceAttempt() {
  let raw;
  try {
    raw = localStorage.getItem(PENDING_ACCEPTANCE_STORAGE_KEY);
  } catch (_error) {
    state.pendingAcceptanceStorageInvalid = true;
    return true;
  }
  if (raw === null) return false;
  const attempt = parsePendingAcceptance(raw);
  if (!attempt) {
    state.pendingAcceptanceStorageInvalid = true;
    return true;
  }
  state.pendingAcceptanceAttempt = Object.freeze(attempt);
  return true;
}

function showUnresolvedAcceptance({ malformed = state.pendingAcceptanceStorageInvalid } = {}) {
  ui.pendingAcceptanceMessage.textContent = malformed
    ? "La sélection en attente ne peut pas être relue de façon sûre. AstroPilot bloque toute nouvelle sélection pour éviter un doublon."
    : "Le résultat de votre sélection n’a pas pu être confirmé. AstroPilot doit vérifier cette sélection avant de poursuivre.";
  ui.retryPendingAcceptance.disabled = malformed || state.acceptingRecommendation;
  setView("unresolved_acceptance");
}

function hasUnresolvedAcceptance() {
  return Boolean(
    state.pendingAcceptanceAttempt || state.pendingAcceptanceStorageInvalid
  );
}

function guardUnresolvedAcceptance() {
  if (!hasUnresolvedAcceptance()) return false;
  showUnresolvedAcceptance();
  return true;
}

function acceptanceAttempt(intent) {
  const existing = state.pendingAcceptanceAttempt;
  if (existing) {
    if (sameAcceptanceIntent(existing, intent)) return existing;
    return null;
  }
  const attempt = Object.freeze({
    acceptance_request_id: crypto.randomUUID(),
    decision_id: intent.decision_id,
    source: intent.source,
    selected_catalog_key: intent.selected_catalog_key,
    acquisition_intent_id: intent.acquisition_intent_id,
    selected_at: new Date().toISOString(),
  });
  persistPendingAcceptanceAttempt(attempt);
  state.pendingAcceptanceAttempt = attempt;
  return attempt;
}

function clearPendingAcceptanceAttempt() {
  localStorage.removeItem(PENDING_ACCEPTANCE_STORAGE_KEY);
  state.pendingAcceptanceAttempt = null;
  state.pendingAcceptanceStorageInvalid = false;
}

function resetMissionPresentation() {
  text("#mission-title", "—");
  text("#mission-summary", "—");
  text("#mission-window", "—");
  text("#mission-duration", "—");
  text("#mission-gain", "—");
  text("#mission-filter", "—");
  document.querySelector("#mission-filter-wrap").hidden = true;
  document.querySelector("#mission-equipment").replaceChildren();
  document.querySelector("#mission-tasks").replaceChildren();
}

function clearAcceptedMission() {
  state.acceptedMission = null;
  ui.savedMissionEntry.hidden = true;
  state.acceptingRecommendation = false;
  state.acceptanceBlocked = false;
  showAcceptanceStatus("");
  if (ui.mission.open) ui.mission.close();
  resetMissionPresentation();
  clearAlternatives();
}

function renderDecision(decision) {
  clearAcceptedMission();
  state.currentDecision = decision;

  const productivity = decision.productivity;
  const actionableHours = decision.recommended_hours;
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
  const recommended = decision.target_decision_status === "recommended";
  const insufficient = decision.target_decision_status === "insufficient_evidence";
  const noAcquisition = intentMode(decision) === "none";
  const intentUnavailable = intentMode(decision) === "unavailable";
  text("#target-label", recommended && !noAcquisition && !intentUnavailable ? "Cible prioritaire" : "Cible évaluée");
  text("#recommendation", noAcquisition
    ? "Aucune acquisition recommandée cette nuit"
    : intentUnavailable ? "Prise de vue à confirmer"
    : recommended
    ? (labels.actions[decision.action] || "Session recommandée")
    : insufficient ? "Preuves insuffisantes" : "Cible non recommandée");
  text("#target-name", decision.target || "Cible à confirmer");
  text("#catalog-key", decision.target_common_name || (decision.catalog_key && decision.catalog_key !== decision.target ? decision.catalog_key : ""));
  text("#window-value", start && end ? `${start} — ${end}` : "À confirmer");
  text("#window-note", firstWindow?.reason ? "Fenêtre productive principale" : "Heure locale");
  text("#duration-value", duration(actionableHours));
  text("#duration-note", "Durée de mission exploitable");
  text("#filter-value", filter?.name || "Aucun filtre précisé");
  text("#filter-note", filter?.filter_type ? filter.filter_type.replaceAll("_", " ") : "Selon la cible et le ciel");
  text("#quality-score", qualityScore === null ? "—" : String(qualityScore));
  text("#quality-title", qualityCopy[0]);
  text("#quality-summary", qualityCopy[1]);
  text("#limiting-factor", limiting ? (labels.factors[limiting] || limiting.replaceAll("_", " ")) : "Aucun identifié");
  ui.recommendationConfidence.textContent = formatRecommendationConfidence(
    decision.recommendation_confidence,
  );
  renderWeatherTrust(weatherTrust, weatherDecision, "classic");

  const circumference = 2 * Math.PI * 48;
  const progress = document.querySelector("#quality-progress");
  const visualScore = qualityScore === null ? 0 : Math.max(0, Math.min(100, qualityScore));
  progress.style.strokeDashoffset = String(circumference * (1 - visualScore / 100));

  const positives = (decision.explanation?.positives || []).map(reasonText);
  const information = (decision.explanation?.information || []).map(reasonText);
  const warnings = (decision.explanation?.warnings || []).map(reasonText);
  const risks = [...warnings];
  if (decision.dew_risk && String(decision.dew_risk.level).toLowerCase() !== "low") {
    const level = String(decision.dew_risk.level).toLowerCase();
    risks.push(`Rosée : risque ${labels.riskLevels[level] || level}`);
  }
  if (decision.postponement_risk) {
    risks.push(...(decision.postponement_risk.explanations || []));
  }

  const evidenceMessage = insufficient
    ? "AstroPilot ne dispose pas d’assez d’éléments fiables pour recommander cette cible pour cette session."
    : null;
  setList("#insights-list", [...(evidenceMessage ? [evidenceMessage] : []), ...positives, ...information], "Aucune explication supplémentaire disponible.");
  text("#decision-essential", evidenceMessage || positives.find(Boolean) || information.find(Boolean)
    || "Décision calculée pour votre configuration actuelle.");
  setList("#risks-list", risks, "Aucun risque essentiel signalé.");
  renderIntentChoice(ui.primaryIntentChoice, decision, "primary-intent");
  const actionablePrimary = Boolean(
    decision.decision_id
    && decision.catalog_key
    && decision.target_decision_status === "recommended"
  );
  ui.openMission.hidden = !actionablePrimary || ["none", "unavailable"].includes(intentMode(decision));
  ui.openMission.disabled = !actionablePrimary || !intentReady(ui.openMission);
  ui.openMission.dataset.acceptanceSource = "primary_recommendation";
  ui.openMission.dataset.catalogKey = decision.catalog_key || "";
  ui.openMission.dataset.decisionId = decision.decision_id || "";
  renderAlternatives(decision);
  restoreAcceptanceControls();
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
  location_timezone_unresolved: "site",
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

function progressEditorSnapshot(fieldOverride = null) {
  const editor = document.querySelector("#project-progress-editor");
  if (!state.progressEditor || editor.hidden || !editor.querySelector("#project-imaging-field")) return null;
  return JSON.stringify({
    field: fieldOverride ?? editor.querySelector("#project-imaging-field").value,
    intents: [...editor.querySelectorAll("fieldset[data-intent-id]")].map((section) => [
      section.dataset.intentId,
      ...[...section.querySelectorAll("input, select")].map((input) => input.value),
    ]),
  });
}

function confirmDiscardProjectProgress() {
  return progressEditorSnapshot() === state.progressEditorBaseline
    || window.confirm("Des modifications de l’avancement ne sont pas enregistrées. Les abandonner ?");
}

function renderProjects() {
  if (!confirmDiscardProjectProgress()) return false;
  document.querySelector("#project-progress-editor").hidden = true;
  state.progressEditor = null;
  state.progressEditorBaseline = null;
  const projects = state.configurationDraft.projects || {};
  const entries = Object.entries(projects);
  const summary = document.querySelector("#existing-projects");
  const zeroProjects = document.querySelector("#zero-projects");
  const zeroProjectsControl = document.querySelector("#zero-projects-wrap");
  summary.replaceChildren();
  summary.hidden = !entries.length;
  zeroProjectsControl.hidden = Boolean(entries.length);
  if (entries.length) {
    const heading = document.createElement("p");
    heading.textContent = "Projets actuellement conservés";
    const explanation = document.createElement("p");
    explanation.textContent = "Vos projets existants sont conservés. Ouvrez un projet pour renseigner son avancement par intention d’acquisition. Changer votre site ou votre matériel ne les supprimera pas.";
    const list = document.createElement("ul");
    for (const [catalogKey, project] of entries) {
      const item = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = `${catalogKey} · ${project.hours} h sur ${project.target_hours} h (historique) `;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary-button";
      button.textContent = "Ouvrir";
      button.addEventListener("click", () => openProjectProgress(catalogKey));
      item.append(label, button);
      list.append(item);
    }
    summary.append(heading, explanation, list);
    zeroProjects.checked = false;
    zeroProjects.disabled = true;
  } else {
    zeroProjects.checked = true;
    zeroProjects.disabled = true;
  }
  return true;
}

function progressDuration(seconds) {
  if (seconds === null) return "non renseigné";
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours} h ${String(minutes).padStart(2, "0")}`;
}

function progressInput(label, value, field, type = "number") {
  const wrapper = document.createElement("label");
  wrapper.textContent = label;
  const input = document.createElement("input");
  input.type = type;
  input.min = field === "exposure_seconds" || field === "target_hours" ? "0.000001" : "0";
  input.step = field === "acquired_frames" ? "1" : "any";
  input.value = value ?? "";
  input.dataset.field = field;
  wrapper.append(input);
  return wrapper;
}

async function openProjectProgress(projectId, { discardConfirmed = false } = {}) {
  if (!discardConfirmed && !confirmDiscardProjectProgress()) return;
  const editor = document.querySelector("#project-progress-editor");
  editor.hidden = false;
  editor.textContent = "Chargement du projet…";
  state.progressEditor = null;
  state.progressEditorBaseline = null;
  try {
    const response = await fetch(`/v1/projects/${encodeURIComponent(projectId)}/progress`);
    if (!response.ok) throw new Error("load failed");
    state.progressEditor = await response.json();
    renderProjectProgressEditor();
  } catch (_error) {
    editor.textContent = "Le projet ne peut pas être ouvert. Réessayez.";
  }
}

function renderProjectProgressEditor(message = "") {
  const data = state.progressEditor;
  const editor = document.querySelector("#project-progress-editor");
  editor.replaceChildren();
  const heading = document.createElement("h3");
  heading.textContent = data.project_id;
  const feedback = document.createElement("p");
  feedback.className = "project-progress-feedback";
  feedback.textContent = message;
  const fieldLabel = document.createElement("label");
  fieldLabel.textContent = "Champ d’imagerie ";
  const fieldSelect = document.createElement("select");
  fieldSelect.id = "project-imaging-field";
  const unknown = document.createElement("option");
  unknown.value = "";
  unknown.textContent = "Choisir explicitement un champ";
  fieldSelect.append(unknown);
  for (const field of data.imaging_fields) {
    const option = document.createElement("option");
    option.value = field.imaging_field_id;
    option.textContent = field.display_name;
    fieldSelect.append(option);
  }
  fieldSelect.value = data.imaging_field_id || "";
  const credited = new Set((data.intent_progress_breakdown || [])
    .filter((item) => item.credits_us > 0).map((item) => item.acquisition_intent_id));
  if (credited.size) {
    fieldSelect.disabled = true;
    const note = document.createElement("p");
    note.textContent = "Ce champ contient des crédits d’exécution : le champ et leurs bases historiques sont verrouillés.";
    fieldLabel.append(note);
  }
  fieldLabel.append(fieldSelect);
  const intents = document.createElement("div");
  intents.id = "project-intents";
  const renderIntents = () => {
    intents.replaceChildren();
    const selected = data.imaging_fields.find((field) => field.imaging_field_id === fieldSelect.value);
    if (!selected) {
      intents.textContent = "Choisissez un champ pour voir ses intentions d’acquisition.";
      return;
    }
    for (const intent of selected.acquisition_intents) {
      const id = intent.acquisition_intent_id;
      const progress = (data.acquisition_intent_progress || []).find((item) => item.acquisition_intent_id === id);
      const target = (data.acquisition_intent_targets || []).find((item) => item.acquisition_intent_id === id);
      const section = document.createElement("fieldset");
      section.dataset.intentId = id;
      const legend = document.createElement("legend");
      legend.textContent = `${id} · ${intent.filter_type}`;
      const mode = document.createElement("select");
      mode.dataset.field = "mode";
      for (const [value, label] of [["unknown", "non renseigné"], ["detailed", "Poses × secondes"], ["manual", "Durée manuelle (secondes)"]]) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        mode.append(option);
      }
      mode.value = progress?.acquired_frames !== undefined ? "detailed"
        : progress?.acquired_duration_manual !== undefined ? "manual" : "unknown";
      const frames = progressInput("Poses acquises ", progress?.acquired_frames, "acquired_frames");
      const exposure = progressInput("Secondes par pose ", progress?.exposure_seconds, "exposure_seconds");
      const manual = progressInput("Durée acquise (secondes) ", progress?.acquired_duration_manual, "acquired_duration_manual");
      const hours = progressInput("Objectif (heures, facultatif) ", target?.target_hours, "target_hours");
      const computed = document.createElement("output");
      const update = () => {
        frames.hidden = exposure.hidden = mode.value !== "detailed";
        manual.hidden = mode.value !== "manual";
        const count = Number(frames.querySelector("input").value);
        const seconds = Number(exposure.querySelector("input").value);
        const duration = Number(manual.querySelector("input").value);
        const known = mode.value === "detailed"
          ? frames.querySelector("input").value !== "" && exposure.querySelector("input").value !== "" && Number.isFinite(count * seconds)
          : mode.value === "manual" && manual.querySelector("input").value !== "" && Number.isFinite(duration);
        computed.textContent = `Durée calculée : ${progressDuration(known ? mode.value === "detailed" ? count * seconds : duration : null)}`;
      };
      mode.addEventListener("change", update);
      for (const input of [frames, exposure, manual]) input.querySelector("input").addEventListener("input", update);
      section.append(legend, mode, frames, exposure, manual, hours, computed);
      if (credited.has(id)) {
        mode.disabled = true;
        for (const input of [frames, exposure, manual]) input.querySelector("input").disabled = true;
        const note = document.createElement("p");
        note.textContent = "Base verrouillée après crédit d’exécution ; l’objectif reste modifiable.";
        section.append(note);
      }
      intents.append(section);
      update();
    }
  };
  let displayedField = fieldSelect.value;
  fieldSelect.addEventListener("change", () => {
    const selected = data.imaging_fields.find((item) => item.imaging_field_id === fieldSelect.value);
    const validIds = new Set(selected?.acquisition_intents.map((intent) => intent.acquisition_intent_id) || []);
    const removed = [...(data.acquisition_intent_progress || []), ...(data.acquisition_intent_targets || [])]
      .filter((item) => !validIds.has(item.acquisition_intent_id))
      .map((item) => item.acquisition_intent_id);
    const edited = progressEditorSnapshot(displayedField) !== state.progressEditorBaseline;
    if ((edited || removed.length) && !window.confirm(
      `${edited ? "Les modifications non enregistrées seront abandonnées. " : ""}`
      + `${removed.length ? `Changer de champ supprimera l’avancement et les objectifs des intentions incompatibles (${[...new Set(removed)].join(", ")}) à l’enregistrement. ` : ""}`
      + "Continuer ?",
    )) {
      fieldSelect.value = displayedField;
      return;
    }
    displayedField = fieldSelect.value;
    renderIntents();
  });
  const save = document.createElement("button");
  save.type = "button";
  save.className = "primary-button";
  save.textContent = "Enregistrer l’avancement";
  save.addEventListener("click", saveProjectProgress);
  editor.append(heading, feedback, fieldLabel, intents, save);
  renderIntents();
  state.progressEditorBaseline = progressEditorSnapshot();
}

async function saveProjectProgress() {
  const data = state.progressEditor;
  const editor = document.querySelector("#project-progress-editor");
  const feedback = editor.querySelector(".project-progress-feedback");
  const field = editor.querySelector("#project-imaging-field").value;
  if (!field) {
    feedback.textContent = "Choisissez un champ d’imagerie.";
    return;
  }
  const progress = [];
  const targets = [];
  for (const section of editor.querySelectorAll("fieldset[data-intent-id]")) {
    const id = section.dataset.intentId;
    const value = (name) => section.querySelector(`[data-field="${name}"]`).value;
    const mode = value("mode");
    if (mode === "detailed") {
      const frames = Number(value("acquired_frames"));
      const seconds = Number(value("exposure_seconds"));
      if (value("acquired_frames") === "" || !Number.isInteger(frames) || frames < 0
          || value("exposure_seconds") === "" || !Number.isFinite(seconds) || seconds <= 0) {
        feedback.textContent = `Corrigez les poses et la durée de ${id}.`;
        return;
      }
      progress.push({ acquisition_intent_id: id, acquired_frames: frames, exposure_seconds: seconds });
    } else if (mode === "manual") {
      const duration = Number(value("acquired_duration_manual"));
      if (value("acquired_duration_manual") === "" || !Number.isFinite(duration) || duration < 0) {
        feedback.textContent = `Corrigez la durée de ${id}.`;
        return;
      }
      progress.push({ acquisition_intent_id: id, acquired_duration_manual: duration });
    }
    if (value("target_hours") !== "") {
      const targetHours = Number(value("target_hours"));
      if (!Number.isFinite(targetHours) || targetHours <= 0) {
        feedback.textContent = `Corrigez l’objectif de ${id}.`;
        return;
      }
      targets.push({ acquisition_intent_id: id, target_hours: targetHours });
    }
  }
  const body = { expected_revision: data.profile_revision, imaging_field_id: field,
    acquisition_intent_progress: progress, acquisition_intent_targets: targets };
  try {
    const response = await fetch(`/v1/projects/${encodeURIComponent(data.project_id)}/progress`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (response.status === 409) {
      const detail = (await response.json()).detail || {};
      if (String(detail.code || "").startsWith("intent_progress_")) {
        feedback.textContent = "Crédit d’exécution présent : cette base ou ce champ ne peut plus être modifié. Rechargez le projet pour voir les dernières valeurs.";
        return;
      }
      if (!confirmDiscardProjectProgress()) {
        feedback.textContent = "Le projet a changé. Votre saisie est conservée ; rechargez le projet avant de réessayer.";
        return;
      }
      await openProjectProgress(data.project_id, { discardConfirmed: true });
      state.progressEditor && (document.querySelector(".project-progress-feedback").textContent =
        "Le projet a changé. Les dernières valeurs ont été rechargées ; vérifiez-les avant de réenregistrer.");
      return;
    }
    if (!response.ok) throw new Error("save failed");
    state.progressEditor = await response.json();
    state.configuration.profile_revision = state.progressEditor.profile_revision;
    const project = state.configuration.projects[data.project_id];
    project.imaging_field_id = field;
    project.acquisition_intent_progress = progress;
    project.acquisition_intent_targets = targets;
    state.configurationDraft.projects[data.project_id] = structuredClone(project);
    renderProjectProgressEditor("Avancement enregistré.");
  } catch (_error) {
    feedback.textContent = "L’avancement n’a pas pu être enregistré. Vérifiez les valeurs et réessayez.";
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
  const site = state.configurationDraft.site;
  const payload = {
    site: {
      name: site.name,
      latitude: site.latitude,
      longitude: site.longitude,
      bortle: site.bortle,
    },
    equipment: state.configurationDraft.equipment,
    projects: copyProjects(state.configurationDraft.projects),
  };
  if (state.configuration?.configured) {
    payload.expected_revision = state.configuration.profile_revision;
  }
  return payload;
}

function hideRecoveryConfirmation() {
  ui.configurationRecoveryConfirmation.hidden = true;
}

function showRecoveryConfirmation() {
  if (state.configurationErrorCode !== "configuration_corrupt") return;
  ui.configurationRecoveryConfirmation.hidden = false;
  ui.configurationRecoveryConfirm.focus();
}

function showConfigurationError(message, { code = null } = {}) {
  state.configurationErrorCode = code;
  ui.configurationErrorMessage.textContent = message;
  hideRecoveryConfirmation();
  ui.configurationRecover.hidden = code !== "configuration_corrupt";
  setView("configuration_error");
}

function initializeConfiguration(payload) {
  if (state.configuration && (
    state.configuration.profile_revision !== payload.profile_revision
    || JSON.stringify(state.configuration.site) !== JSON.stringify(payload.site)
    || JSON.stringify(state.configuration.equipment) !== JSON.stringify(payload.equipment)
  )) clearAcceptedMission();
  invalidateAvailabilityForSiteChange(state.configuration?.site, payload.site);
  state.configuration = payload;
  state.configurationDraft = draftFromConfiguration(payload);
  document.querySelector("#legacy-bortle-note").hidden = !payload.needs_configuration_confirmation;
  text("#onboarding-title", payload.needs_configuration_confirmation
    ? "Confirmez votre profil AstroPilot."
    : "Préparons AstroPilot.");
  ui.onboarding.querySelector(".wizard-heading .state-kicker").textContent =
    payload.needs_configuration_confirmation ? "Profil historique"
      : payload.configured ? "Modifier la configuration" : "Première configuration";
  state.configurationErrorCode = null;
  hideRecoveryConfirmation();
  ui.configurationRecover.hidden = true;
  prefillConfiguration();
  renderAvailabilityTimezone();
}

async function restoreSavedMission() {
  const configuration = state.configuration;
  state.acceptedMission = null;
  ui.savedMissionEntry.hidden = true;
  try {
    const response = await fetch("/v1/accepted-mission/current");
    if (!response.ok) throw new Error("mission_read_unavailable");
    const payload = await response.json();
    const mission = payload?.mission;
    if (state.configuration === configuration && payload?.status === "accepted" && mission
        && payload.mission_id === mission.mission_id
        && payload.selection_id === mission.selection_id
        && payload.decision_id === mission.decision_id) {
      state.acceptedMission = {
        decision_id: payload.decision_id,
        selection_id: payload.selection_id,
        mission_id: payload.mission_id,
        selectedCatalogKey: payload.catalog_key,
        acquisitionIntentId: payload.selected_acquisition_intent_id,
        source: "persisted",
        mission,
      };
    }
  } catch (_error) {
    // Availability remains usable if the persisted lineage is unavailable.
  }
  try {
    const response = await fetch("/v1/execution-sessions");
    if (response.ok && state.configuration === configuration) {
      const sessions = await response.json();
      if (!state.acceptedMission && sessions.length) {
        const latest = sessions.at(-1);
        state.acceptedMission = {
          decision_id: latest.mission.decision_id, selection_id: latest.mission.selection_id,
          mission_id: latest.mission.mission_id, selectedCatalogKey: latest.project_id,
          acquisitionIntentId: latest.acquisition_intent_id, source: "persisted",
          mission: latest.mission,
        };
      }
    }
  } catch (_error) {
    // The current mission can still be opened if session discovery is unavailable.
  }
  if (state.acceptedMission) {
    ui.savedMissionTarget.textContent = state.acceptedMission.mission.target;
    ui.savedMissionEntry.hidden = false;
  }
}

function invalidateAvailabilityForSiteChange(previousSite, nextSite) {
  if (!previousSite || !nextSite) return;
  const sameSite = previousSite.latitude === nextSite.latitude
    && previousSite.longitude === nextSite.longitude
    && previousSite.timezone === nextSite.timezone;
  if (sameSite) return;
  document.querySelector("#availability-start").value = "";
  document.querySelector("#availability-end").value = "";
  state.availability = null;
}

async function loadConfiguration({ afterConflict = false } = {}) {
  if (guardUnresolvedAcceptance()) return;
  setView("loading_configuration");
  try {
    const response = await fetch("/v1/configuration");
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const code = payload?.detail?.code;
      const message = code === "configuration_corrupt"
        ? "La configuration enregistrée ne peut pas être relue. Réessayez dans un instant."
        : "La configuration est temporairement inaccessible. Réessayez dans un instant.";
      showConfigurationError(message, { code });
      return;
    }
    initializeConfiguration(payload);
    if (afterConflict) {
      showFormError("La configuration a changé. Vérifiez les dernières valeurs avant de l’enregistrer à nouveau.");
      renderReview();
      setView("review");
    } else if (payload.needs_configuration_confirmation) {
      showFormError("Votre profil historique est conservé. Confirmez la qualité du ciel (Bortle) pour activer les recommandations ; aucune réinitialisation n’est nécessaire.");
      setView("site");
    } else if (payload.configured) {
      showFormError("");
      setView("availability");
      await restoreSavedMission();
    } else {
      showFormError("");
      setView("site");
    }
  } catch (_error) {
    showConfigurationError("AstroPilot ne parvient pas à charger la configuration. La saisie pourra reprendre après reconnexion.");
  }
}

async function recoverConfiguration() {
  if (state.configurationErrorCode !== "configuration_corrupt") return;
  if (state.recoveringConfiguration) return;
  state.recoveringConfiguration = true;
  ui.configurationRecoveryConfirm.disabled = true;
  try {
    const response = await fetch("/v1/configuration/recover", {
      method: "POST",
    });
    const payload = await response.json().catch(() => ({}));
    if (response.ok && payload.configured === false) {
      initializeConfiguration(payload);
      showFormError("");
      setView("site");
      return;
    }
    const detail = payload?.detail;
    if (detail?.code === "configuration_recovery_conflict") {
      hideRecoveryConfirmation();
      await loadConfiguration();
      return;
    }
    const message = detail?.code === "configuration_recovery_unavailable"
      ? "La réinitialisation est temporairement indisponible. Vous pourrez réessayer plus tard."
      : "La réinitialisation n’a pas pu être confirmée. Vous pouvez réessayer.";
    showConfigurationError(message, { code: "configuration_corrupt" });
  } catch (_error) {
    showConfigurationError(
      "Le résultat de la réinitialisation n’a pas pu être confirmé. Vérifiez votre connexion puis réessayez.",
      { code: "configuration_corrupt" },
    );
  } finally {
    state.recoveringConfiguration = false;
    ui.configurationRecoveryConfirm.disabled = false;
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
        showFormError(
          detail?.code === "location_timezone_unresolved"
            ? "Le fuseau horaire du site ne peut pas être déterminé. Vérifiez les coordonnées du site."
            : "Certaines informations doivent être corrigées avant l’enregistrement.",
        );
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
    initializeConfiguration(payload);
    setView("availability");
  } catch (_error) {
    showFormError("Connexion impossible pendant l’enregistrement. Vérifiez vos informations puis réessayez.");
    setView("review");
  } finally {
    state.savingConfiguration = false;
    button.disabled = false;
  }
}

const availabilityFieldsByMode = Object.freeze({
  all_night: [],
  duration: ["duration"],
  start_and_duration: ["start", "duration"],
  until: ["end"],
  fixed_window: ["start", "end"],
});

const availabilityValidationMessages = Object.freeze({
  availability_mode_required: "Choisissez votre disponibilité pour cette nuit.",
  availability_duration_required: "Indiquez une durée positive en heures.",
  availability_start_required: "Indiquez une heure de début valide.",
  availability_end_required: "Indiquez une heure de fin valide.",
  availability_end_must_follow_start: "L’heure de fin doit être postérieure à l’heure de début.",
  availability_timezone_unresolved: "Le fuseau horaire du site ne peut pas être déterminé. Vérifiez les coordonnées du site.",
});

function showAvailabilityError(message) {
  ui.availabilityError.textContent = message || "";
  ui.availabilityError.hidden = !message;
}

const wallClockAvailabilityModes = Object.freeze([
  "start_and_duration",
  "until",
  "fixed_window",
]);

function currentSiteTimezone() {
  const timezone = state.configuration?.site?.timezone;
  return typeof timezone === "string" && timezone.trim() ? timezone.trim() : null;
}

function renderAvailabilityTimezone() {
  const timezone = currentSiteTimezone();
  ui.availabilitySiteTimezone.hidden = !timezone;
  ui.availabilitySiteTimezone.textContent = timezone ? `Fuseau du site : ${timezone}` : "";
  ui.availabilityTimezoneWarning.hidden = Boolean(timezone);
  for (const mode of wallClockAvailabilityModes) {
    const input = document.querySelector(`input[name="availability-mode"][value="${mode}"]`);
    input.disabled = !timezone;
    if (!timezone && input.checked) input.checked = false;
  }
  updateAvailabilityFields();
}

function hoursToIsoDuration(rawValue) {
  if (String(rawValue).trim() === "") return null;
  const hours = Number(rawValue);
  if (!Number.isFinite(hours) || hours <= 0) return null;
  const totalMinutes = Math.round(hours * 60);
  if (totalMinutes <= 0 || Math.abs(totalMinutes / 60 - hours) > 1e-9) return null;
  const wholeHours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `PT${wholeHours ? `${wholeHours}H` : ""}${minutes ? `${minutes}M` : ""}`;
}

function normalizeLocalDateTime(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const [, , month, day, hour, minute] = match.map(Number);
  if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59) return null;
  return value;
}

function availabilityInputError(code) {
  const error = new Error(code);
  error.availabilityCode = code;
  return error;
}

function collectAvailabilityPayload() {
  const mode = document.querySelector('input[name="availability-mode"]:checked')?.value;
  if (!mode) throw availabilityInputError("availability_mode_required");

  if (mode === "all_night") return { mode: "all_night" };
  if (wallClockAvailabilityModes.includes(mode) && !currentSiteTimezone()) {
    throw availabilityInputError("availability_timezone_unresolved");
  }

  const duration = hoursToIsoDuration(
    document.querySelector("#availability-duration").value,
  );
  const startValue = document.querySelector("#availability-start").value;
  const endValue = document.querySelector("#availability-end").value;
  const start = normalizeLocalDateTime(startValue);
  const end = normalizeLocalDateTime(endValue);

  if (mode === "duration") {
    if (!duration) throw availabilityInputError("availability_duration_required");
    const availability = { mode: "duration" };
    availability.duration = duration;
    return availability;
  }
  if (mode === "start_and_duration") {
    if (!start) throw availabilityInputError("availability_start_required");
    if (!duration) throw availabilityInputError("availability_duration_required");
    const availability = { mode: "start_and_duration" };
    availability.start_local = start;
    availability.duration = duration;
    return availability;
  }
  if (mode === "until") {
    if (!end) throw availabilityInputError("availability_end_required");
    const availability = { mode: "until" };
    availability.end_local = end;
    return availability;
  }
  if (mode === "fixed_window") {
    if (!start) throw availabilityInputError("availability_start_required");
    if (!end) throw availabilityInputError("availability_end_required");
    if (end <= start) {
      throw availabilityInputError("availability_end_must_follow_start");
    }
    const availability = { mode: "fixed_window" };
    availability.start_local = start;
    availability.end_local = end;
    return availability;
  }
  throw availabilityInputError("availability_mode_required");
}

function updateAvailabilityFields() {
  const mode = document.querySelector('input[name="availability-mode"]:checked')?.value;
  const required = availabilityFieldsByMode[mode] || [];
  for (const field of document.querySelectorAll("[data-availability-field]")) {
    const visible = required.includes(field.dataset.availabilityField);
    field.hidden = !visible;
    field.querySelector("input").disabled = !visible;
  }
  showAvailabilityError("");
}

function backendAvailabilityMessage(detail) {
  const code = Array.isArray(detail) ? null : detail?.code;
  if (code === "session_availability_local_datetime_invalid") {
    return "Vérifiez la date et l’heure saisies.";
  }
  if (code === "session_availability_local_time_nonexistent") {
    return "Cette heure locale n’existe pas à cause du changement d’heure. Choisissez une autre heure.";
  }
  if (code === "session_availability_local_time_ambiguous") {
    return "Cette heure locale est ambiguë à cause du changement d’heure. Choisissez une autre heure.";
  }
  if (code === "session_availability_mixed_time_contract") {
    return "Vérifiez votre disponibilité avant de réessayer.";
  }
  if (code === "session_availability_end_must_follow_start") {
    return "L’heure de fin doit être postérieure à l’heure de début.";
  }
  const descriptions = Array.isArray(detail)
    ? detail.map((item) => `${item?.msg || ""} ${item?.ctx?.error || ""}`).join(" ")
    : `${detail?.message || ""}`;
  if (descriptions.includes("session_availability_timezone_required")) {
    return "L’heure saisie doit inclure un fuseau horaire valide.";
  }
  if (descriptions.includes("session_availability_duration_must_be_positive")) {
    return "La durée doit être supérieure à zéro.";
  }
  if (descriptions.includes("session_availability_end_must_follow_start")) {
    return "L’heure de fin doit être postérieure à l’heure de début.";
  }
  if (descriptions.includes("invalid_session_availability_fields") || descriptions.includes("Field required")) {
    return "Complétez uniquement les horaires requis pour le mode choisi.";
  }
  return "Vérifiez les informations de disponibilité avant de réessayer.";
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

function acceptanceError(code, status) {
  if (["acquisition_intent_selection_required", "selected_acquisition_intent_not_viable", "selected_acquisition_intent_mismatch", "acquisition_intent_required_for_mission"].includes(code)) {
    return ["Cette prise de vue n’est plus disponible pour la cible. Actualisez la recommandation et choisissez à nouveau.", true];
  }
  if (code === "no_eligible_acquisition_intent") {
    return ["Aucune acquisition n’est recommandée pour cette cible cette nuit. Actualisez la recommandation.", true];
  }
  if (code === "decision_context_stale") {
    return ["Cette recommandation a expiré. Actualisez-la avant de choisir votre cible.", true];
  }
  if (code === "decision_context_not_found") {
    return ["Cette recommandation n’est plus disponible. Demandez une nouvelle recommandation.", true];
  }
  if (code === "selected_target_not_primary_recommendation") {
    return ["La cible affichée ne correspond plus à cette décision. Actualisez la recommandation.", true];
  }
  if (code === "selected_target_not_exposed_alternative") {
    return ["Cette alternative n’est plus disponible pour cette décision. Actualisez la recommandation.", true];
  }
  if (code === "acceptance_request_conflict") {
    return ["Cette tentative d’acceptation ne correspond plus au choix initial. Actualisez la recommandation.", true];
  }
  if (["selection_id_conflict", "mission_id_conflict", "acceptance_lineage_conflict"].includes(code)) {
    return ["AstroPilot ne peut pas confirmer cette acceptation. Aucune mission n’est affichée.", true];
  }
  if (code === "decision_lineage_persistence_error") {
    return ["La mission n’a pas pu être enregistrée. Réessayez lorsque le stockage est disponible.", false];
  }
  if (code === "decision_acceptance_unavailable" || status === 503) {
    return ["L’acceptation est temporairement indisponible. Vous pourrez réessayer plus tard.", false];
  }
  if (status === 422) {
    return ["La demande d’acceptation n’est pas valide. Actualisez la recommandation.", true];
  }
  return ["L’acceptation n’a pas pu être confirmée. La recommandation reste affichée.", false];
}

async function retryPendingAcceptance() {
  const attempt = state.pendingAcceptanceAttempt;
  if (!attempt || state.pendingAcceptanceStorageInvalid) {
    showUnresolvedAcceptance();
    return;
  }
  await acceptRecommendation({
    source: attempt.source,
    selectedCatalogKey: attempt.selected_catalog_key,
    expectedDecisionId: attempt.decision_id,
    triggerButton: ui.retryPendingAcceptance,
    selectedTarget: attempt.selected_catalog_key,
    acquisitionIntentId: attempt.acquisition_intent_id,
    attemptOverride: attempt,
  });
}

async function acceptRecommendation({
  source,
  selectedCatalogKey,
  expectedDecisionId,
  triggerButton,
  selectedTarget,
  acquisitionIntentId,
  attemptOverride = null,
}) {
  if (state.acceptingRecommendation) return;
  const decision = state.currentDecision;
  if (!attemptOverride && state.acceptedMission) {
    if (
      state.acceptedMission.decision_id === expectedDecisionId
      && state.acceptedMission.source === source
      && state.acceptedMission.selectedCatalogKey === selectedCatalogKey
    ) {
      renderMission(state.acceptedMission.mission);
      ui.mission.showModal();
    }
    return;
  }
  if (!attemptOverride) {
    if (state.acceptanceBlocked) return;
    if (!decision || state.currentDecision?.decision_id !== expectedDecisionId) {
      return;
    }
    const validPrimary = source === "primary_recommendation"
      && selectedCatalogKey === decision.catalog_key
      && decision.target_decision_status === "recommended";
    const validAlternative = source === "alternative"
      && (decision.alternatives || []).some((alternative) => (
        alternative.catalog_key === selectedCatalogKey
        && alternative.target_decision_status === "viable"
      ));
    if (!validPrimary && !validAlternative) {
      state.acceptanceBlocked = true;
      showAcceptanceStatus("Cette cible n’est plus sélectionnable. Actualisez la recommandation.", { error: true });
      disableAcceptanceControls(true);
      return;
    }
    const subject = validPrimary ? decision : (decision.alternatives || []).find(
      (alternative) => alternative.catalog_key === selectedCatalogKey
    );
    const container = validPrimary ? ui.primaryIntentChoice
      : triggerButton?.closest(".alternative-card")?.querySelector(".intent-choice");
    acquisitionIntentId = chosenIntent(subject, container);
    if (acquisitionIntentId === undefined) {
      showAcceptanceStatus("Choisissez d’abord une prise de vue disponible pour créer la mission.", { error: true });
      restoreAcceptanceControls();
      return;
    }
  }
  let attempt;
  try {
    attempt = attemptOverride || acceptanceAttempt({
      decision_id: expectedDecisionId,
      source,
      selected_catalog_key: selectedCatalogKey,
      acquisition_intent_id: acquisitionIntentId,
    });
  } catch (_storageError) {
    showAcceptanceStatus(
      "La sélection ne peut pas être enregistrée de façon sûre dans ce navigateur. Aucun envoi n’a été effectué.",
      { error: true },
    );
    return;
  }
  if (!attempt) {
    showAcceptanceStatus(
      "Une acceptation précédente reste à confirmer. Réessayez la même cible avant d’en choisir une autre.",
      { error: true },
    );
    restoreAcceptanceControls();
    return;
  }
  state.acceptingRecommendation = true;
  disableAcceptanceControls(true);
  triggerButton?.setAttribute("aria-busy", "true");
  showAcceptanceStatus("Enregistrement de votre choix et création de la mission…");

  try {
    const response = await fetch("/v1/decision-selections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(attempt),
    });
    const payload = await response.json().catch(() => ({}));

    if (!response.ok) {
      clearPendingAcceptanceAttempt();
      const [message, blocked] = acceptanceError(payload?.detail?.code, response.status);
      state.acceptanceBlocked = blocked;
      if (decision?.decision_id === expectedDecisionId) {
        show("decision");
        showAcceptanceStatus(message, { error: true });
      } else {
        await loadConfiguration();
        showAvailabilityError(message);
      }
      return;
    }
    const mission = payload.mission;
    const validAcceptedMission = payload.status === "accepted"
      && mission
      && payload.decision_id === expectedDecisionId
      && payload.catalog_key === selectedCatalogKey
      && payload.mission_id === mission.mission_id
      && payload.selection_id === mission.selection_id
      && payload.decision_id === mission.decision_id;
    if (!validAcceptedMission) {
      showUnresolvedAcceptance();
      return;
    }
    if (decision?.decision_id === expectedDecisionId) {
      const acceptedSubject = source === "primary_recommendation" ? decision
        : (decision.alternatives || []).find((item) => item.catalog_key === selectedCatalogKey);
      const acceptedButton = acceptanceControls().find((button) => (
        button.dataset.acceptanceSource === source && button.dataset.catalogKey === selectedCatalogKey
      ));
      const acceptedContainer = source === "primary_recommendation" ? ui.primaryIntentChoice
        : acceptedButton?.closest(".alternative-card")?.querySelector(".intent-choice");
      if (!acceptedSubject || (intentMode(acceptedSubject) !== "legacy" && !acceptedContainer)
          || !showAcceptedIntent(acceptedSubject, acceptedContainer, payload.selected_acquisition_intent_id)) {
        showUnresolvedAcceptance();
        return;
      }
    }
    clearPendingAcceptanceAttempt();
    state.acceptedMission = {
      decision_id: payload.decision_id,
      selection_id: payload.selection_id,
      mission_id: payload.mission_id,
      selectedCatalogKey: payload.catalog_key,
      acquisitionIntentId: payload.selected_acquisition_intent_id,
      source,
      mission,
    };
    if (decision?.decision_id === expectedDecisionId) {
      show("decision");
      showAcceptanceStatus(
        source === "alternative"
          ? `AstroPilot recommandait ${decision.target || decision.catalog_key}. Vous avez choisi ${selectedTarget}.`
          : "Mission enregistrée.",
      );
    } else {
      showMessage(
        "Mission enregistrée",
        "La réponse du serveur confirme votre sélection et votre mission.",
        { kicker: "Sélection confirmée", retry: false },
      );
    }
    renderMission(mission);
    ui.mission.showModal();
  } catch (_error) {
    showUnresolvedAcceptance();
  } finally {
    state.acceptingRecommendation = false;
    triggerButton?.removeAttribute("aria-busy");
    if (hasUnresolvedAcceptance()) {
      showUnresolvedAcceptance();
    } else if (state.currentDecision?.decision_id === expectedDecisionId) {
      restoreAcceptanceControls();
    }
  }
}

async function loadTonight(availability) {
  if (guardUnresolvedAcceptance()) return;
  if (!availability) {
    showAvailabilityError("Choisissez votre disponibilité avant de préparer la nuit.");
    setView("availability");
    return;
  }
  if (state.requestingRecommendation) return;
  state.requestingRecommendation = true;
  state.availability = { ...availability };
  ui.recommendationSubmit.disabled = true;
  showAvailabilityError("");
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
      if (payload?.error === "user_profile_unavailable") {
        showConfigurationError("Votre configuration doit être rechargée avant de préparer la nuit.");
        return;
      }
      if (payload?.detail?.code === "location_timezone_unresolved") {
        state.availability = null;
        state.configurationDraft = draftFromConfiguration(state.configuration);
        prefillConfiguration();
        showFormError("Le fuseau horaire du site ne peut pas être déterminé. Vérifiez les coordonnées du site avant de choisir une heure précise.");
        setView("site");
        return;
      }
      if (payload?.detail?.code === "invalid_tonight_equipment") {
        state.configurationDraft = draftFromConfiguration(state.configuration);
        prefillConfiguration();
        showFormError("Vérifiez le matériel actif avant de préparer la nuit.");
        setView("equipment");
        return;
      }
      if (response.status === 422) {
        showAvailabilityError(backendAvailabilityMessage(payload?.detail));
        setView("availability");
        return;
      }
      const [title, body] = normalizeError(response, payload);
      showAvailabilityError(`${title} ${body}`);
      setView("availability");
      return;
    }

    clearAcceptedMission();
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
    showAvailabilityError("Connexion impossible. Vos horaires sont conservés; réessayez dans un instant.");
    setView("availability");
  } finally {
    state.requestingRecommendation = false;
    ui.recommendationSubmit.disabled = false;
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
  if (renderProjects()) setView("projects");
});

document.querySelector("#projects-next").addEventListener("click", () => {
  if (!confirmDiscardProjectProgress()) return;
  showFormError("");
  renderReview();
  setView("review");
});

for (const button of document.querySelectorAll("[data-back]")) {
  button.addEventListener("click", () => {
    if (state.view === "projects" && button.dataset.back !== "projects" && !confirmDiscardProjectProgress()) return;
    showFormError("");
    setView(button.dataset.back);
  });
}

for (const input of document.querySelectorAll('input[name="equipment-kind"]')) {
  input.addEventListener("change", toggleEquipmentKind);
}

function editConfiguration() {
  if (guardUnresolvedAcceptance()) return;
  state.configurationDraft = draftFromConfiguration(state.configuration);
  prefillConfiguration();
  showFormError("");
  setView("site");
}

document.querySelector("#save-configuration").addEventListener("click", saveConfiguration);
ui.configurationRetry.addEventListener("click", loadConfiguration);
ui.configurationRecover.addEventListener("click", showRecoveryConfirmation);
ui.configurationRecoveryCancel.addEventListener("click", hideRecoveryConfirmation);
ui.configurationRecoveryConfirm.addEventListener("click", recoverConfiguration);
ui.editConfiguration.addEventListener("click", editConfiguration);
document.querySelector("#availability-edit-configuration").addEventListener("click", editConfiguration);
ui.editAvailability.addEventListener("click", () => {
  if (guardUnresolvedAcceptance()) return;
  setView("availability");
});
ui.refresh.addEventListener("click", () => {
  if (guardUnresolvedAcceptance()) return;
  if (state.availability) loadTonight(state.availability);
  else setView("availability");
});
ui.retry.addEventListener("click", () => {
  if (guardUnresolvedAcceptance()) return;
  if (state.availability) loadTonight(state.availability);
  else setView("availability");
});
ui.retryPendingAcceptance.addEventListener("click", retryPendingAcceptance);

for (const input of document.querySelectorAll('input[name="availability-mode"]')) {
  input.addEventListener("change", updateAvailabilityFields);
}

ui.availabilityForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (guardUnresolvedAcceptance()) return;
  if (state.requestingRecommendation) return;
  try {
    const availability = collectAvailabilityPayload();
    showAvailabilityError("");
    loadTonight(availability);
  } catch (error) {
    const message = availabilityValidationMessages[error.availabilityCode]
      || "Vérifiez votre disponibilité avant de continuer.";
    showAvailabilityError(message);
    setView("availability");
  }
});

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

ui.openMission.addEventListener("click", () => acceptRecommendation({
  source: "primary_recommendation",
  selectedCatalogKey: state.currentDecision?.catalog_key,
  expectedDecisionId: state.currentDecision?.decision_id,
  triggerButton: ui.openMission,
  selectedTarget: state.currentDecision?.target,
}));
ui.openSavedMission.addEventListener("click", () => {
  if (!state.acceptedMission?.mission || state.acceptedMission.source !== "persisted") return;
  renderMission(state.acceptedMission.mission);
  ui.mission.showModal();
});
document.querySelector("#session-choice").addEventListener("change", (event) => {
  state.activeSessionId = event.target.value;
  renderSession();
});
document.querySelector("#session-start").addEventListener("click", () => sessionCommand(startSession));
document.querySelector("#session-complete").addEventListener("click", () => sessionCommand((missionId) => closeSession(missionId, "completed")));
document.querySelector("#session-interrupt").addEventListener("click", () => sessionCommand((missionId) => closeSession(missionId, "interrupted")));
document.querySelector("#session-record-evidence").addEventListener("click", () => sessionCommand(recordSessionEvidence));
document.querySelector("#session-apply-credit").addEventListener("click", () => sessionCommand(creditSession));
ui.closeMission.addEventListener("click", () => ui.mission.close());
ui.missionBack.addEventListener("click", () => ui.mission.close());
ui.mission.addEventListener("click", (event) => {
  if (event.target === ui.mission) ui.mission.close();
});
if (restorePendingAcceptanceAttempt()) showUnresolvedAcceptance();
else loadConfiguration();
