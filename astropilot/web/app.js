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
  savedMissionChoice: document.querySelector("#saved-mission-choice"),
  openSavedMission: document.querySelector("#open-saved-mission"),
  availabilityError: document.querySelector("#availability-error"),
  availabilityOvernightHint: document.querySelector("#availability-overnight-hint"),
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
  observation: document.querySelector("#field-observation-dialog"),
  closeObservation: document.querySelector("#close-field-observation"),
  addObservationMessage: document.querySelector("#add-field-observation-message"),
  addObservationDecision: document.querySelector("#add-field-observation-decision"),
  addObservationMission: document.querySelector("#add-field-observation-mission"),
  acceptanceStatus: document.querySelector("#acceptance-status"),
  recommendationConfidencePanel: document.querySelector("#recommendation-confidence"),
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
  savedMissions: [],
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
  fieldObservationSelectedExecutionId: null,
  sessionEvidenceInputExecutionId: null,
  sessionBusy: false,
  sessionWriteAttempted: false,
  sessionWriteUncertain: false,
  observationBusy: false,
  fieldObservationDraftContext: null,
  fieldObservationContextInvalid: false,
  invalidFieldObservationContextKey: null,
  fieldObservationConflict: null,
  fieldObservationLock: null,
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

function sessionStatus(status) {
  return status === "unconfirmed" ? "Session non confirmée" : status;
}

function restoreSessionEvidenceInputs(session) {
  const executionId = session?.execution.execution_id || null;
  if (executionId === state.sessionEvidenceInputExecutionId) return;
  state.sessionEvidenceInputExecutionId = executionId;
  let minutes = 0;
  const evidence = usableEvidence(session);
  if (evidence) {
    minutes = Math.round(Number(evidence.usable_integration_duration) / 60);
  } else if (executionId) {
    const saved = JSON.parse(localStorage.getItem(`astropilot.pendingEvidence.${executionId}`) || "null");
    if (Number.isInteger(saved?.minutes) && saved.minutes > 0) minutes = saved.minutes;
  }
  document.querySelector("#session-hours").value = String(Math.floor(minutes / 60));
  document.querySelector("#session-minutes").value = String(minutes % 60);
}

function renderSession() {
  const session = currentSession();
  restoreSessionEvidenceInputs(session);
  const status = session?.execution.status;
  const choice = document.querySelector("#session-choice");
  choice.replaceChildren();
  const noSessionOption = document.createElement("option");
  noSessionOption.value = "";
  noSessionOption.textContent = "Sans session";
  choice.append(noSessionOption);
  for (const item of state.sessions) {
    const option = document.createElement("option");
    option.value = item.execution.execution_id;
    option.textContent = `${item.execution.actual_start ? new Date(item.execution.actual_start).toLocaleString("fr-CH") : "À démarrer"} · ${sessionStatus(item.execution.status)}`;
    choice.append(option);
  }
  choice.hidden = !state.sessions.length;
  choice.value = session?.execution.execution_id || "";
  const intentId = session?.acquisition_intent_id || state.acceptedMission?.acquisitionIntentId;
  text("#session-intent", `Intent de la mission : ${intentId || "non défini"}`);
  document.querySelector("#session-start").hidden = status === "in_progress" || status === "unconfirmed";
  document.querySelector("#session-start").textContent = status === "not_started"
    ? "Démarrer cette session" : "Créer et démarrer une nouvelle session";
  document.querySelector("#session-close-actions").hidden = status !== "in_progress";
  document.querySelector("#session-evidence").hidden = status !== "completed" || Boolean(usableEvidence(session));
  const evidence = usableEvidence(session);
  document.querySelector("#session-credit").hidden = status === "unconfirmed" || !evidence || Boolean(session.credit);
  if (evidence && !session.credit) {
    text("#session-credit-preview", `Intent ${session.acquisition_intent_id} · base historique : ${sessionHours(session.historical_baseline_seconds)} · crédit proposé : ${sessionHours(Number(evidence.usable_integration_duration))}`);
    const mustConfirm = Number(session.historical_baseline_seconds) > 0 && !session.historical_baseline_confirmed;
    document.querySelector("#session-baseline-confirm-wrap").hidden = !mustConfirm;
    document.querySelector("#session-baseline-confirm").checked = false;
  }
  document.querySelector("#session-progress").hidden = !session;
  if (session) {
    text("#session-before-label", session.credit ? "Acquis avant ce crédit" : "Acquis actuel (avant crédit)");
    text("#session-after-label", session.credit ? "Acquis après ce crédit" : "Acquis projeté sans crédit");
    text("#session-before", sessionHours(session.acquired_before_seconds));
    text("#session-added", sessionHours(session.session_credit_seconds));
    text("#session-after", sessionHours(session.acquired_after_seconds));
    text("#session-current", sessionHours(session.current_acquired_seconds));
    text("#session-remaining", session.target_hours == null ? "objectif non défini" : sessionHours(session.remaining_hours * 3600));
    sessionMessage(status === "unconfirmed" ? "Session non confirmée : aucune action disponible."
      : status === "interrupted" ? "Session interrompue : aucun crédit."
      : session.credit ? "Crédit enregistré." : status === "completed" ? "Session terminée."
      : status === "in_progress" ? "Session en cours." : "Session prête à démarrer.");
  } else sessionMessage("Aucune session enregistrée pour cette mission.");
  renderObservationLinkage();
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
  const explicitlySelectedExecutionId = state.fieldObservationSelectedExecutionId;
  state.activeSessionId = sessions.some((item) => item.execution.execution_id === candidate)
    ? candidate : sessions.some((item) => item.execution.execution_id === state.activeSessionId)
      ? state.activeSessionId : null;
  state.fieldObservationSelectedExecutionId = sessions.some(
    (item) => item.execution.execution_id === explicitlySelectedExecutionId,
  ) ? explicitlySelectedExecutionId : null;
  if (pending?.mission_id === missionId && sessions.some((item) => item.execution.execution_id === pending.execution_id)) {
    localStorage.removeItem(SESSION_PENDING_KEY);
  }
  renderSession();
  syncFieldObservationContext();
}

async function sessionCommand(command) {
  if (state.sessionBusy || !state.acceptedMission?.mission_id) return;
  const baselineConfirmed = document.querySelector("#session-baseline-confirm").checked;
  state.sessionBusy = true;
  state.sessionWriteAttempted = false;
  state.sessionWriteUncertain = false;
  document.querySelectorAll(".session-panel button").forEach((button) => { button.disabled = true; });
  const missionId = state.acceptedMission.mission_id;
  try {
    await reloadSessions();
    await command(missionId, baselineConfirmed);
    await reloadSessions();
  } catch (error) {
    try {
      await reloadSessions();
      sessionMessage(state.sessionWriteUncertain
        ? "État relu après une réponse incertaine. Vérifiez la session avant de poursuivre."
        : state.sessionWriteAttempted && error?.status ? sessionRefusalMessage(error)
        : "Lecture ou reprise échouée. État actuel relu ; vérifiez avant de poursuivre.");
    } catch (_readError) {
      sessionMessage(state.sessionWriteAttempted && error?.status
        ? `${sessionRefusalMessage(error)} Lecture impossible ; rechargez la page.`
        : "Lecture impossible. Rechargez la page avant une nouvelle action.");
    }
  } finally {
    state.sessionBusy = false;
    state.sessionWriteAttempted = false;
    state.sessionWriteUncertain = false;
    document.querySelectorAll(".session-panel button").forEach((button) => { button.disabled = false; });
  }
}

async function postSession(url, body) {
  const payload = JSON.stringify(body);
  state.sessionWriteAttempted = true;
  state.sessionWriteUncertain = true;
  const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: payload });
  state.sessionWriteUncertain = false;
  if (!response.ok) throw await sessionHttpError(response);
  return response.json();
}

async function sessionHttpError(response) {
  const error = new Error("session_command_refused");
  error.status = response.status;
  try { error.code = (await response.json()).detail?.code; } catch (_ignored) { /* status remains authoritative */ }
  return error;
}

function sessionRefusalMessage(error) {
  if (error.status === 409) return "Action refusée : la session ou le profil a changé. État actuel relu ; vérifiez avant de poursuivre.";
  if (error.status === 422) return "Action refusée : transition ou données invalides. Corrigez la saisie avant de poursuivre.";
  if (error.status === 503) return "Action impossible : données enregistrées incohérentes ou service indisponible. Rechargez la page.";
  return `Action refusée par le serveur (${error.status}). État actuel relu.`;
}

async function startSession(missionId) {
  let session = currentSession();
  if (session?.execution.status !== "not_started") {
    const pending = JSON.parse(localStorage.getItem(SESSION_PENDING_KEY) || "null");
    const executionId = pending?.mission_id === missionId ? pending.execution_id : crypto.randomUUID();
    localStorage.setItem(SESSION_PENDING_KEY, JSON.stringify({ mission_id: missionId, execution_id: executionId }));
    const lookup = await fetch(`/v1/executions/${encodeURIComponent(executionId)}/session`);
    if (lookup.status === 404) await postSession("/v1/executions", { execution_id: executionId, mission_id: missionId });
    else if (!lookup.ok) throw await sessionHttpError(lookup);
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
  if (!lookup.ok) throw await sessionHttpError(lookup);
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

const OBSERVATION_CHOICES = Object.freeze({
  clouds: Object.freeze(["clear", "few", "partly_cloudy", "mostly_cloudy", "overcast"]),
  transparency: Object.freeze(["poor", "fair", "good", "excellent"]),
});
const OBSERVATION_SEEING_CHOICES = Object.freeze(["poor", "fair", "good", "excellent"]);
const OBSERVATION_STOP_REASONS = Object.freeze([
  "completed", "clouds", "dew", "wind", "technical", "target_lost", "user", "daylight", "not_started", "other",
]);
const OBSERVATION_SURFACE_INPUTS = Object.freeze({
  dry: 'input[name="observation-surface"][value="dry"]',
  damp: 'input[name="observation-surface"][value="damp"]',
  dew_present: 'input[name="observation-surface"][value="dew_present"]',
});
const OBSERVATION_IDENTITY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const PENDING_FIELD_OBSERVATION_VERSION = 2;
const FIELD_OBSERVATION_LOCK_KEY = "astropilot.fieldObservationLock";
const FIELD_OBSERVATION_LOCK_VERSION = 2;
const FIELD_OBSERVATION_PENDING_PREFIX = "astropilot.pendingFieldObservation.";
const FIELD_OBSERVATION_WEB_LOCK_NAME = "astropilot.fieldObservationLock.acquire";
let fieldObservationOperationGeneration = 0;
let activeFieldObservationOperation = null;

function renderObservationLinkage() {
  const element = document.querySelector("#observation-linkage");
  if (!element) return;
  const context = state.fieldObservationDraftContext;
  element.textContent = context?.execution_id
    ? `Session liée : ${context.execution_id}` : "Sans session";
  const night = context?.night_date ? ` · nuit du ${context.night_date}` : "";
  text("#observation-context-decision", context
    ? `Décision ${context.decision_id}${night}` : "Décision indisponible");
}

function siteTimezone() {
  const timezone = state.configuration?.site?.timezone;
  return typeof timezone === "string" && timezone.trim() ? timezone.trim() : null;
}

function siteConfigurationIdentity() {
  const site = state.configuration?.site;
  if (!site) return null;
  return JSON.stringify({
    site_id: site.site_id || site.id || null,
    site_revision: site.site_revision ?? site.revision ?? null,
    name: site.name || null,
    latitude: site.latitude ?? null,
    longitude: site.longitude ?? null,
    timezone: siteTimezone(),
    bortle: site.bortle ?? null,
  });
}

function observationContext(source) {
  const decision = source === "mission" ? state.acceptedMission : state.currentDecision;
  const decisionId = decision?.decision_id;
  if (!decisionId) return null;
  const selectedExecution = source === "mission"
    && currentSession()?.execution.execution_id === state.fieldObservationSelectedExecutionId
    ? state.fieldObservationSelectedExecutionId : null;
  return {
    decision_id: decisionId,
    execution_id: selectedExecution,
    night_date: decision?.night_date || decision?.mission?.night_date || state.currentDecision?.night_date || null,
    source,
    timezone: siteTimezone(),
    site_identity: siteConfigurationIdentity(),
    mission_id: source === "mission" ? decision?.mission_id || decision?.mission?.mission_id || null : null,
  };
}

function activeObservationContext() {
  const source = state.fieldObservationDraftContext?.source;
  return source ? observationContext(source) : null;
}

function setFieldObservationEditorDisabled(disabled) {
  for (const control of document.querySelector("#field-observation-form").querySelectorAll("input, select, button")) {
    if (!state.observationBusy
        && ["observation-reconcile", "observation-refresh-context", "observation-abandon-pending"].includes(control.id)) continue;
    control.disabled = disabled;
  }
}

function fieldObservationContextKey(context) {
  return context?.decision_id
    ? pendingObservationKey(context.decision_id, context.execution_id || null) : null;
}

function fieldObservationLockMatchesDraft(lock, context) {
  return lock?.status === "pending"
    && !lock.persistence_missing
    && lock.key === fieldObservationContextKey(context)
    && sameFieldObservationContext(lock.context, context)
    && lock.pending?.snapshot === fieldObservationSnapshot();
}

function fieldObservationEditorBlocked() {
  const context = state.fieldObservationDraftContext;
  const key = fieldObservationContextKey(context);
  return !context
    || state.fieldObservationContextInvalid
    || !sameFieldObservationContext(context, activeObservationContext())
    || (key !== null && state.invalidFieldObservationContextKey === key)
    || Boolean(state.fieldObservationLock && !fieldObservationLockMatchesDraft(state.fieldObservationLock, context));
}

function updateFieldObservationSubmitState() {
  const blocked = fieldObservationEditorBlocked();
  const lock = state.fieldObservationLock;
  const hardBlocked = blocked && (!lock || state.fieldObservationContextInvalid
    || !sameFieldObservationContext(state.fieldObservationDraftContext, activeObservationContext())
    || lock.status !== "pending" || lock.persistence_missing);
  setFieldObservationEditorDisabled(hardBlocked);
  document.querySelector("#observation-save").disabled = blocked || state.observationBusy;
  const reconcile = document.querySelector("#observation-reconcile");
  const refresh = document.querySelector("#observation-refresh-context");
  const abandon = document.querySelector("#observation-abandon-pending");
  if (reconcile) reconcile.hidden = !lock || ["invalid", "unreadable", "multiple_pending", "corrupt_pending", "persistence_missing"].includes(lock.status);
  if (refresh) refresh.hidden = lock?.status !== "invalid";
  if (abandon) abandon.hidden = !lock || ["multiple_pending", "corrupt_pending", "persistence_missing"].includes(lock.status);
  if (reconcile) reconcile.disabled = state.observationBusy || reconcile.hidden;
  if (refresh) refresh.disabled = state.observationBusy || refresh.hidden;
  if (abandon) abandon.disabled = state.observationBusy || abandon.hidden;
  renderFieldObservationPendingDiagnostics();
}

function fieldObservationEntryDescription(entry) {
  const payload = entry.pending.payload;
  const execution = payload.execution_id ? `session ${payload.execution_id}` : "sans session";
  return `Clé ${entry.key} · décision ${payload.decision_id} · ${execution} · UUID ${payload.observation_id} · statut ${entry.status || "pending"} · observé ${payload.observed_at_utc} · enregistré ${payload.recorded_at_utc}`;
}

function renderFieldObservationPendingDiagnostics() {
  const container = document.querySelector("#observation-pending-diagnostics");
  if (!container || typeof document.createElement !== "function") return;
  const lock = state.fieldObservationLock;
  const entries = ["multiple_pending", "corrupt_pending", "persistence_missing"].includes(lock?.status)
    ? lock.entries || [] : [];
  const corruptions = lock?.corruptions || [];
  container.replaceChildren();
  container.hidden = entries.length === 0 && corruptions.length === 0;
  for (const entry of entries) {
    const item = document.createElement("article");
    item.className = "observation-pending-entry";
    const description = document.createElement("p");
    description.textContent = fieldObservationEntryDescription(entry);
    const actions = document.createElement("div");
    actions.className = "observation-entry-actions";
    const reconcile = document.createElement("button");
    reconcile.type = "button";
    reconcile.className = "secondary-button";
    reconcile.textContent = "Réconcilier";
    reconcile.disabled = state.observationBusy;
    reconcile.addEventListener("click", () => reconcileFieldObservationEntry(entry.key));
    const abandon = document.createElement("button");
    abandon.type = "button";
    abandon.className = "secondary-button";
    abandon.textContent = "Abandonner";
    abandon.disabled = state.observationBusy;
    abandon.addEventListener("click", () => abandonFieldObservationEntry(entry.key));
    actions.append(reconcile, abandon);
    item.append(description, actions);
    container.append(item);
  }
  for (const corruption of corruptions) {
    const item = document.createElement("article");
    item.className = "observation-pending-entry";
    const description = document.createElement("p");
    description.textContent = `Clé locale illisible ${corruption.key} · raison ${corruption.reason}`;
    const actions = document.createElement("div");
    actions.className = "observation-entry-actions";
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "secondary-button";
    remove.textContent = "Supprimer cette clé corrompue";
    remove.disabled = state.observationBusy;
    remove.addEventListener("click", () => removeCorruptFieldObservationEntry(corruption.key));
    actions.append(remove);
    item.append(description, actions);
    container.append(item);
  }
}

function fieldObservationConflictMessage() {
  return "Conflit d’observation : le relevé précédent doit être résolu avant tout nouvel envoi. Le brouillon et son identifiant d’origine sont conservés ; utilisez « Réconcilier l’observation précédente ».";
}

function openFieldObservation(source) {
  const context = observationContext(source);
  if (!context?.decision_id) return;
  resetFieldObservationForm();
  state.fieldObservationDraftContext = Object.freeze(context);
  state.fieldObservationContextInvalid = false;
  renderObservationLinkage();
  text("#observation-timezone", context.timezone
    ? `Fuseau du site : ${context.timezone}` : "Fuseau du site indisponible");
  const observedAt = document.querySelector("#observation-observed-at");
  let openingError = null;
  try {
    if (!context.timezone) throw new Error("timezone_unavailable");
    observedAt.value = formatDateTimeLocalInZone(new Date(), context.timezone);
  } catch (error) {
    observedAt.value = "";
    openingError = error?.message === "unsupported_site_timezone"
      ? "Le fuseau du site configuré n’est pas reconnu. Corrigez la configuration du site avant d’enregistrer une observation."
      : "La conversion du fuseau du site est indisponible sur cet appareil. Utilisez un navigateur compatible avant d’enregistrer une observation.";
    state.fieldObservationContextInvalid = true;
  }
  observationMessage("Choisissez les catégories observées, indiquez le vent mesuré en km/h ou précisez l’état de la surface.");
  ui.observation.showModal();
  if (openingError) {
    updateFieldObservationSubmitState();
    observationMessage(state.fieldObservationLock
      ? `${openingError} ${fieldObservationLockMessage(state.fieldObservationLock)}` : openingError, { error: true });
    return;
  }
  syncFieldObservationContext();
  restorePendingFieldObservation();
  updateFieldObservationSubmitState();
  if (state.fieldObservationLock) {
    observationMessage(fieldObservationLockMessage(state.fieldObservationLock), { error: true });
  }
}

function observationMessage(message, { error = false } = {}) {
  const element = document.querySelector("#observation-status");
  element.textContent = message;
  element.classList.toggle("observation-error", error);
}

function optionalObservationNumber(selector) {
  const raw = document.querySelector(selector).value.trim();
  return raw === "" ? null : Number(raw);
}

function selectedObservationChoice(name) {
  const value = document.querySelector(`[data-observation-choice="${name}"]`).value;
  return OBSERVATION_CHOICES[name].includes(value) ? value : null;
}

function sameFieldObservationContext(left, right) {
  return left?.decision_id === right?.decision_id
    && (left?.execution_id || null) === (right?.execution_id || null)
    && left?.timezone === right?.timezone
    && left?.site_identity === right?.site_identity;
}

function localDateTimeParts(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value || "");
  if (!match) throw new Error("invalid_local_datetime");
  const parts = match.slice(1).map(Number);
  const [year, month, day, hour, minute] = parts;
  const check = new Date(0);
  check.setUTCHours(hour, minute, 0, 0);
  check.setUTCFullYear(year, month - 1, day);
  if (check.getUTCFullYear() !== year || check.getUTCMonth() !== month - 1
      || check.getUTCDate() !== day || check.getUTCHours() !== hour
      || check.getUTCMinutes() !== minute) throw new Error("invalid_local_datetime");
  return {year, month, day, hour, minute};
}

function zonedDateTimeParts(date, timezone) {
  if (typeof Intl === "undefined" || typeof Intl.DateTimeFormat !== "function") {
    throw new Error("timezone_unavailable");
  }
  let formatter;
  try {
    formatter = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
    });
  } catch (_error) {
    throw new Error("unsupported_site_timezone");
  }
  let values;
  try {
    if (typeof formatter?.formatToParts !== "function") throw new Error("format_to_parts_unavailable");
    values = Object.fromEntries(formatter.formatToParts(date)
      .filter((part) => part.type !== "literal").map((part) => [part.type, Number(part.value)]));
  } catch (_error) {
    throw new Error("timezone_unavailable");
  }
  const componentRanges = {
    year: [1, 9999], month: [1, 12], day: [1, 31],
    hour: [0, 23], minute: [0, 59], second: [0, 59],
  };
  if (Object.entries(componentRanges).some(([name, [minimum, maximum]]) => (
    !Number.isFinite(values[name]) || !Number.isInteger(values[name])
      || values[name] < minimum || values[name] > maximum
  ))) throw new Error("timezone_unavailable");
  return {year: values.year, month: values.month, day: values.day,
    hour: values.hour, minute: values.minute, second: values.second};
}

function formatDateTimeLocalInZone(date, timezone) {
  const parts = zonedDateTimeParts(date, timezone);
  const pad = (value) => String(value).padStart(2, "0");
  return `${String(parts.year).padStart(4, "0")}-${pad(parts.month)}-${pad(parts.day)}T${pad(parts.hour)}:${pad(parts.minute)}`;
}

function utcMilliseconds(year, month, day, hour = 0, minute = 0, second = 0, millisecond = 0) {
  const date = new Date(0);
  date.setUTCHours(hour, minute, second, millisecond);
  date.setUTCFullYear(year, month - 1, day);
  return date.getTime();
}

function localDateTimeToUtc(value, timezone) {
  if (!timezone) throw new Error("timezone_unavailable");
  const wanted = localDateTimeParts(value);
  const wallClockAsUtc = utcMilliseconds(
    wanted.year, wanted.month, wanted.day, wanted.hour, wanted.minute,
  );
  const minimumSupportedInstant = utcMilliseconds(1, 1, 1);
  const maximumSupportedInstant = utcMilliseconds(9999, 12, 31, 23, 59, 59);
  const offsets = new Set();
  const sampledInstants = new Set();
  for (let hours = -48; hours <= 48; hours += 6) {
    const instant = Math.max(minimumSupportedInstant, Math.min(
      maximumSupportedInstant, wallClockAsUtc + hours * 3600000,
    ));
    if (sampledInstants.has(instant)) continue;
    sampledInstants.add(instant);
    const parts = zonedDateTimeParts(new Date(instant), timezone);
    offsets.add(utcMilliseconds(
      parts.year, parts.month, parts.day, parts.hour, parts.minute, parts.second,
    ) - instant);
  }
  const matches = [];
  for (const offset of offsets) {
    const instant = wallClockAsUtc - offset;
    const parts = zonedDateTimeParts(new Date(instant), timezone);
    if (parts.year === wanted.year && parts.month === wanted.month && parts.day === wanted.day
        && parts.hour === wanted.hour && parts.minute === wanted.minute) matches.push(instant);
  }
  const unique = [...new Set(matches)].sort((left, right) => left - right);
  if (!unique.length) throw new Error("nonexistent_local_datetime");
  if (unique.length > 1) throw new Error("ambiguous_local_datetime");
  return new Date(unique[0]).toISOString();
}

function fieldObservationDraftForContext(context) {
  if (!context?.decision_id) return null;
  const surface = document.querySelector('input[name="observation-surface"]:checked')?.value || null;
  const moonHalo = document.querySelector("#observation-moon-halo").value;
  const hfr = optionalObservationNumber("#observation-hfr");
  const conditions = {
    temperature_c: optionalObservationNumber("#observation-temperature"),
    relative_humidity_percent: optionalObservationNumber("#observation-humidity"),
    cloud_state: selectedObservationChoice("clouds"),
    transparency: selectedObservationChoice("transparency"),
    seeing: document.querySelector("#observation-seeing").value || null,
    wind_speed_kmh: optionalObservationNumber("#observation-wind"),
    surface_condition: surface,
    moon_halo: moonHalo === "" ? null : moonHalo === "true",
  };
  const acquisition = {
    attempted_frames: optionalObservationNumber("#observation-attempted-frames"),
    usable_frames: optionalObservationNumber("#observation-usable-frames"),
    stop_reason: document.querySelector("#observation-stop-reason").value || null,
  };
  const technical = {
    hfr,
    hfr_unit: hfr === null ? null : document.querySelector("#observation-hfr-unit").value,
    sky_background: null,
    sky_background_unit: null,
    guiding_rms_arcsec: optionalObservationNumber("#observation-guiding"),
  };
  const hasFact = [...Object.values(conditions), ...Object.values(acquisition), ...Object.values(technical)]
    .some((value) => value !== null);
  if (!hasFact) return null;
  return {
    decision_id: context.decision_id, execution_id: context.execution_id || null,
    observed_at_local: document.querySelector("#observation-observed-at").value,
    timezone: context.timezone,
    conditions, acquisition, technical,
  };
}

function fieldObservationDraft() {
  const draftContext = state.fieldObservationDraftContext;
  if (!draftContext || state.fieldObservationContextInvalid) return null;
  return fieldObservationDraftForContext(draftContext);
}

function buildFieldObservationPayload(draft = fieldObservationDraft(), recordedAt = new Date().toISOString()) {
  if (!draft) return null;
  const observedAt = localDateTimeToUtc(draft.observed_at_local, draft.timezone);
  if (Date.parse(observedAt) > Date.parse(recordedAt)) throw new Error("observed_at_in_future");
  return {
    observation_id: crypto.randomUUID(), decision_id: draft.decision_id,
    execution_id: draft.execution_id,
    observed_at_utc: observedAt, recorded_at_utc: recordedAt,
    supersedes_observation_id: null,
    conditions: draft.conditions, acquisition: draft.acquisition, technical: draft.technical,
    confidence: "medium",
    quality_flags: ["estimated", "partial"],
  };
}

function fieldObservationSnapshot(draft = fieldObservationDraft()) {
  return draft ? JSON.stringify(draft) : null;
}

function snapshotFromObservationPayload(payload, observedAtLocal, timezone) {
  if (!payload) return null;
  return JSON.stringify({
    decision_id: payload.decision_id, execution_id: payload.execution_id || null,
    observed_at_local: observedAtLocal, timezone,
    conditions: payload.conditions, acquisition: payload.acquisition, technical: payload.technical,
  });
}

function legacySnapshotFromObservationPayload(payload) {
  if (!payload) return null;
  return JSON.stringify({
    decision_id: payload.decision_id, execution_id: payload.execution_id || null,
    conditions: payload.conditions, acquisition: payload.acquisition, technical: payload.technical,
  });
}

function pendingObservationKey(decisionId, executionId) {
  const decision = `decision:${encodeURIComponent(decisionId)}`;
  const scope = executionId === null || executionId === undefined
    ? "decision-only"
    : `execution:${encodeURIComponent(executionId)}`;
  return `astropilot.pendingFieldObservation.${decision}.${scope}`;
}

function plainObservationRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function exactObservationKeys(value, expected) {
  return plainObservationRecord(value)
    && Object.keys(value).sort().join("\u0000") === [...expected].sort().join("\u0000");
}

function validObservationIdentity(value) {
  return typeof value === "string" && OBSERVATION_IDENTITY_PATTERN.test(value);
}

function validOptionalObservationNumber(value, { minimum = null, maximum = null, integer = false } = {}) {
  if (value === null) return true;
  return typeof value === "number" && Number.isFinite(value)
    && (!integer || Number.isInteger(value))
    && (minimum === null || value >= minimum)
    && (maximum === null || value <= maximum);
}

function validOptionalObservationChoice(value, choices) {
  return value === null || (typeof value === "string" && choices.includes(value));
}

function validObservationTimestamp(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value)) return false;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) && new Date(parsed).toISOString() === value;
}

function validPendingFieldObservationPayload(payload, expectedContext) {
  if (!exactObservationKeys(payload, [
    "observation_id", "decision_id", "execution_id", "observed_at_utc", "recorded_at_utc",
    "supersedes_observation_id", "conditions", "acquisition", "technical", "confidence", "quality_flags",
  ])) return false;
  if (!validObservationIdentity(payload.observation_id) || !validObservationIdentity(payload.decision_id)) return false;
  if (payload.execution_id !== null && !validObservationIdentity(payload.execution_id)) return false;
  if (payload.decision_id !== expectedContext.decision_id
    || payload.execution_id !== (expectedContext.execution_id || null)) return false;
  if (!validObservationTimestamp(payload.observed_at_utc) || !validObservationTimestamp(payload.recorded_at_utc)) return false;
  if (Date.parse(payload.recorded_at_utc) < Date.parse(payload.observed_at_utc)) return false;
  if (payload.supersedes_observation_id !== null || payload.confidence !== "medium") return false;
  if (!Array.isArray(payload.quality_flags)
    || payload.quality_flags.length !== 2
    || payload.quality_flags[0] !== "estimated"
    || payload.quality_flags[1] !== "partial") return false;

  const conditions = payload.conditions;
  if (!exactObservationKeys(conditions, [
    "temperature_c", "relative_humidity_percent", "cloud_state", "transparency", "seeing",
    "wind_speed_kmh", "surface_condition", "moon_halo",
  ])) return false;
  if (!validOptionalObservationNumber(conditions.temperature_c)
    || !validOptionalObservationNumber(conditions.relative_humidity_percent, {minimum: 0, maximum: 100})
    || !validOptionalObservationChoice(conditions.cloud_state, OBSERVATION_CHOICES.clouds)
    || !validOptionalObservationChoice(conditions.transparency, OBSERVATION_CHOICES.transparency)
    || !validOptionalObservationChoice(conditions.seeing, OBSERVATION_SEEING_CHOICES)
    || !validOptionalObservationNumber(conditions.wind_speed_kmh, {minimum: 0})
    || !validOptionalObservationChoice(conditions.surface_condition, Object.keys(OBSERVATION_SURFACE_INPUTS))
    || (conditions.moon_halo !== null && typeof conditions.moon_halo !== "boolean")) return false;

  const acquisition = payload.acquisition;
  if (!exactObservationKeys(acquisition, ["attempted_frames", "usable_frames", "stop_reason"])) return false;
  if (!validOptionalObservationNumber(acquisition.attempted_frames, {minimum: 0, integer: true})
    || !validOptionalObservationNumber(acquisition.usable_frames, {minimum: 0, integer: true})
    || !validOptionalObservationChoice(acquisition.stop_reason, OBSERVATION_STOP_REASONS)
    || (acquisition.usable_frames !== null && acquisition.attempted_frames === null)
    || (acquisition.usable_frames !== null && acquisition.usable_frames > acquisition.attempted_frames)) return false;

  const technical = payload.technical;
  if (!exactObservationKeys(technical, ["hfr", "hfr_unit", "sky_background", "sky_background_unit", "guiding_rms_arcsec"])) return false;
  if (!validOptionalObservationNumber(technical.hfr, {minimum: 0})
    || !validOptionalObservationChoice(technical.hfr_unit, ["px", "arcsec"])
    || (technical.hfr === null) !== (technical.hfr_unit === null)
    || technical.sky_background !== null
    || technical.sky_background_unit !== null
    || !validOptionalObservationNumber(technical.guiding_rms_arcsec, {minimum: 0})) return false;

  const hasFact = [...Object.values(conditions), ...Object.values(acquisition), technical.hfr, technical.guiding_rms_arcsec]
    .some((item) => item !== null);
  return hasFact;
}

function validPendingFieldObservation(value, expectedContext) {
  if (!exactObservationKeys(value, ["version", "payload", "snapshot", "observed_at_local", "timezone"])
      || value.version !== PENDING_FIELD_OBSERVATION_VERSION
      || typeof value.snapshot !== "string"
      || typeof value.observed_at_local !== "string"
      || value.timezone !== expectedContext.timezone
      || !validPendingFieldObservationPayload(value.payload, expectedContext)) return false;
  let normalized;
  try {
    normalized = localDateTimeToUtc(value.observed_at_local, value.timezone);
  } catch (_error) {
    return false;
  }
  return normalized === value.payload.observed_at_utc
    && value.snapshot === snapshotFromObservationPayload(
      value.payload, value.observed_at_local, value.timezone,
    );
}

function validFieldObservationLock(value) {
  const validEntry = (entry) => (exactObservationKeys(entry, ["key", "pending", "context"])
      || exactObservationKeys(entry, ["key", "pending", "context", "status"]))
    && typeof entry.key === "string"
    && (!entry.status || ["pending", "conflict", "invalid"].includes(entry.status))
    && entry.key === fieldObservationContextKey(entry.context)
    && validPendingFieldObservation(entry.pending, entry.context);
  const validCorruption = (entry) => exactObservationKeys(entry, ["key", "reason", "raw"])
    && typeof entry.key === "string"
    && entry.key.startsWith(FIELD_OBSERVATION_PENDING_PREFIX)
    && typeof entry.reason === "string"
    && (entry.raw === null || typeof entry.raw === "string");
  if ((exactObservationKeys(value, ["version", "generation", "status", "entries"])
      || exactObservationKeys(value, ["version", "generation", "status", "entries", "corruptions"]))
      && value.version === FIELD_OBSERVATION_LOCK_VERSION
      && value.status === "multiple_pending"
      && validObservationIdentity(value.generation)
      && Array.isArray(value.entries)
      && value.entries.length > 1) {
    return value.entries.every(validEntry)
      && (!value.corruptions || value.corruptions.every(validCorruption));
  }
  if (exactObservationKeys(value, ["version", "generation", "status", "entries", "corruptions"])
      && value.version === FIELD_OBSERVATION_LOCK_VERSION
      && value.status === "corrupt_pending"
      && validObservationIdentity(value.generation)
      && Array.isArray(value.entries)
      && value.entries.length <= 1
      && Array.isArray(value.corruptions)
      && value.corruptions.length > 0) {
    return value.entries.every(validEntry) && value.corruptions.every(validCorruption);
  }
  if (!exactObservationKeys(value, ["version", "generation", "status", "key", "pending", "context"])
      || value.version !== FIELD_OBSERVATION_LOCK_VERSION
      || !["pending", "conflict", "invalid"].includes(value.status)
      || !validObservationIdentity(value.generation)
      || typeof value.key !== "string"
      || !plainObservationRecord(value.context)
      || typeof value.context.site_identity !== "string"
      || value.key !== fieldObservationContextKey(value.context)
      || !validPendingFieldObservation(value.pending, value.context)) return false;
  return true;
}

function storedFieldObservationLockValue(lock) {
  if (["multiple_pending", "corrupt_pending"].includes(lock.status)) {
    return {
      version: FIELD_OBSERVATION_LOCK_VERSION,
      generation: lock.generation,
      status: lock.status,
      entries: lock.entries,
      ...(lock.corruptions ? {corruptions: lock.corruptions} : {}),
    };
  }
  return {
    version: FIELD_OBSERVATION_LOCK_VERSION,
    generation: lock.generation,
    status: lock.status,
    key: lock.key,
    pending: lock.pending,
    context: lock.context,
  };
}

function fieldObservationLockGeneration(pending) {
  return `lock-${pending.payload.observation_id}`;
}

function sameFieldObservationLock(left, right) {
  return Boolean(left && right
    && left.generation === right.generation
    && (left.key || null) === (right.key || null)
    && left.pending?.payload?.observation_id === right.pending?.payload?.observation_id);
}

function adoptFieldObservationLock(lock) {
  state.fieldObservationLock = lock ? Object.freeze(lock) : null;
  state.fieldObservationConflict = lock?.status === "conflict"
    ? Object.freeze({key: lock.key, pending: lock.pending}) : null;
}

function parseStoredFieldObservationLock(raw) {
  const parsed = JSON.parse(raw);
  if (parsed?.version === 1 && exactObservationKeys(parsed, ["version", "status", "key", "pending", "context"])) {
    parsed.version = FIELD_OBSERVATION_LOCK_VERSION;
    parsed.generation = fieldObservationLockGeneration(parsed.pending);
  }
  if (!validFieldObservationLock(parsed)) throw new Error("invalid_field_observation_lock");
  return parsed;
}

function adoptStoredFieldObservationLockOrBlock(raw) {
  try {
    if (raw === null) throw new Error("missing_field_observation_lock");
    adoptFieldObservationLock(parseStoredFieldObservationLock(raw));
  } catch (_error) {
    adoptFieldObservationLock({status: "unreadable", persistence_missing: true});
  }
}

function persistedFieldObservationLock() {
  try {
    const raw = localStorage.getItem(FIELD_OBSERVATION_LOCK_KEY);
    return raw === null ? {available: true, raw: null, lock: null}
      : {available: true, raw, lock: parseStoredFieldObservationLock(raw)};
  } catch (_error) {
    return {available: false, raw: null, lock: null};
  }
}

function webLocksAvailable() {
  return typeof navigator !== "undefined" && typeof navigator.locks?.request === "function";
}

async function withFieldObservationWebLock(callback) {
  if (!webLocksAvailable()) return {executed: false, reason: "web_locks_unavailable", value: false};
  let executed = false;
  try {
    const value = await navigator.locks.request(
      FIELD_OBSERVATION_WEB_LOCK_NAME,
      {mode: "exclusive"},
      async () => {
        executed = true;
        return callback();
      },
    );
    return {executed, reason: executed ? null : "web_lock_denied", value};
  } catch (error) {
    return {executed: false, reason: "web_lock_failed", value: false, error};
  }
}

function writeFieldObservationLockUnlocked(lock, expectedLock = state.fieldObservationLock) {
  const stored = storedFieldObservationLockValue(lock);
  const expectedRaw = expectedLock ? JSON.stringify(storedFieldObservationLockValue(expectedLock)) : null;
  try {
    const currentRaw = localStorage.getItem(FIELD_OBSERVATION_LOCK_KEY);
    if (currentRaw !== expectedRaw) {
      if (currentRaw !== null) adoptStoredFieldObservationLockOrBlock(currentRaw);
      else if (expectedLock) adoptFieldObservationLock({...expectedLock, persistence_missing: true});
      return false;
    }
    const storedRaw = JSON.stringify(stored);
    localStorage.setItem(FIELD_OBSERVATION_LOCK_KEY, storedRaw);
    if (localStorage.getItem(FIELD_OBSERVATION_LOCK_KEY) !== storedRaw) return false;
    adoptFieldObservationLock(stored);
    return true;
  } catch (_error) {
    adoptFieldObservationLock({...lock, persistence_missing: true});
    return false;
  }
}

function restoreFieldObservationLock() {
  const persisted = persistedFieldObservationLock();
  if (!persisted.available) {
    adoptFieldObservationLock({status: "unreadable", persistence_missing: true});
    return false;
  }
  if (persisted.raw === null) return true;
  try {
    adoptFieldObservationLock(persisted.lock);
    return true;
  } catch (_error) {
    adoptFieldObservationLock({status: "unreadable", persistence_missing: true});
    return false;
  }
}

function clearFieldObservationLockUnlocked(lock = state.fieldObservationLock) {
  if (!lock) return true;
  if (["multiple_pending", "corrupt_pending", "persistence_missing"].includes(lock.status)) return false;
  let removed = true;
  const expectedRaw = JSON.stringify(storedFieldObservationLockValue(lock));
  try {
    const currentRaw = localStorage.getItem(FIELD_OBSERVATION_LOCK_KEY);
    if (currentRaw !== expectedRaw) {
      if (currentRaw === null && lock.persistence_missing) {
        if (lock.key) {
          const pendingRaw = localStorage.getItem(lock.key);
          if (pendingRaw === JSON.stringify(lock.pending)) localStorage.removeItem(lock.key);
          else if (pendingRaw !== null) return false;
        }
        if (sameFieldObservationLock(state.fieldObservationLock, lock)) {
          state.fieldObservationLock = null;
          state.fieldObservationConflict = null;
        }
        return true;
      }
      removed = false;
      if (currentRaw !== null) adoptFieldObservationLock(parseStoredFieldObservationLock(currentRaw));
      else adoptFieldObservationLock({...lock, persistence_missing: true});
      return false;
    }
    if (lock.key) {
      const expectedPending = JSON.stringify(lock.pending);
      if (localStorage.getItem(lock.key) === expectedPending) localStorage.removeItem(lock.key);
      else if (localStorage.getItem(lock.key) !== null) return false;
    }
    const confirmedRaw = localStorage.getItem(FIELD_OBSERVATION_LOCK_KEY);
    if (confirmedRaw !== expectedRaw) {
      if (confirmedRaw !== null) adoptFieldObservationLock(parseStoredFieldObservationLock(confirmedRaw));
      else adoptFieldObservationLock({...lock, persistence_missing: true});
      return false;
    }
    localStorage.removeItem(FIELD_OBSERVATION_LOCK_KEY);
    if (localStorage.getItem(FIELD_OBSERVATION_LOCK_KEY) !== null) return false;
  } catch (_error) {
    removed = false;
  }
  if (removed && sameFieldObservationLock(state.fieldObservationLock, lock)) {
    state.fieldObservationLock = null;
    state.fieldObservationConflict = null;
  }
  return removed;
}

function fieldObservationLockMessage(lock = state.fieldObservationLock) {
  if (!lock) return "";
  if (lock.status === "multiple_pending") {
    return `${lock.entries.length} observations locales non résolues ont été détectées. Résolvez chaque entrée séparément ; aucun nouvel envoi n’est autorisé.`;
  }
  if (lock.status === "corrupt_pending") {
    return `${lock.corruptions.length} clé(s) locale(s) illisible(s) ont été détectée(s). Supprimez explicitement chaque clé ciblée avant tout nouvel envoi.`;
  }
  if (lock.status === "conflict") return fieldObservationConflictMessage();
  if (lock.status === "invalid") {
    return "Le contexte canonique de l’observation précédente est introuvable. Utilisez « Actualiser le contexte » avant toute nouvelle tentative.";
  }
  if (lock.status === "unreadable" || lock.status === "persistence_missing" || lock.persistence_missing) {
    return "Le verrou local de l’observation précédente a disparu ou est illisible. La page reste bloquée jusqu’à une réconciliation ou un abandon explicite.";
  }
  return "Une observation précédente attend encore une réconciliation. Son UUID et son contenu d’origine restent prioritaires ; réconciliez-la avant d’envoyer des modifications.";
}

function readPendingFieldObservation(key, expectedContext) {
  let raw;
  try {
    raw = localStorage.getItem(key);
  } catch (_error) {
    return { available: false, value: null, reason: "storage" };
  }
  if (raw === null) return { available: true, value: null };
  try {
    const value = JSON.parse(raw);
    if (validPendingFieldObservation(value, expectedContext)) return { available: true, value };
    if (exactObservationKeys(value, ["payload", "snapshot"])
        && typeof value.snapshot === "string"
        && validPendingFieldObservationPayload(value.payload, expectedContext)
        && value.snapshot === legacySnapshotFromObservationPayload(value.payload)) {
      const observedAtLocal = formatDateTimeLocalInZone(
        new Date(value.payload.observed_at_utc), expectedContext.timezone,
      );
      const migrated = {
        version: PENDING_FIELD_OBSERVATION_VERSION,
        payload: value.payload,
        snapshot: snapshotFromObservationPayload(value.payload, observedAtLocal, expectedContext.timezone),
        observed_at_local: observedAtLocal,
        timezone: expectedContext.timezone,
      };
      return { available: true, value: migrated, migrated: true };
    }
  } catch (_error) {
    // The cleanup is best-effort only: corruption must remain blocking for this page.
  }
  return { available: false, value: null, reason: "corrupt" };
}

function recoveredFieldObservationContext(pending) {
  return Object.freeze({
    decision_id: pending.payload.decision_id,
    execution_id: pending.payload.execution_id || null,
    night_date: null,
    source: "recovered",
    timezone: pending.timezone,
    site_identity: siteConfigurationIdentity() || JSON.stringify({recovered_timezone: pending.timezone}),
    mission_id: null,
  });
}

function pendingFieldObservationInventory() {
  const entries = [];
  const corruptions = [];
  try {
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (typeof key !== "string" || !key.startsWith(FIELD_OBSERVATION_PENDING_PREFIX)) continue;
      const raw = localStorage.getItem(key);
      let pending;
      try {
        pending = JSON.parse(raw);
      } catch (_error) {
        corruptions.push(Object.freeze({key, reason: "invalid_json", raw}));
        continue;
      }
      if (!plainObservationRecord(pending) || !plainObservationRecord(pending.payload)) {
        corruptions.push(Object.freeze({key, reason: "invalid_shape", raw}));
        continue;
      }
      const context = recoveredFieldObservationContext(pending);
      if (key !== fieldObservationContextKey(context)) {
        corruptions.push(Object.freeze({key, reason: "context_key_mismatch", raw}));
        continue;
      }
      if (!validPendingFieldObservation(pending, context)) {
        corruptions.push(Object.freeze({key, reason: "invalid_envelope", raw}));
        continue;
      }
      entries.push(Object.freeze({key, pending, context, status: "pending"}));
    }
  } catch (_error) {
    return {available: false, entries: [], corruptions: []};
  }
  entries.sort((left, right) => left.key.localeCompare(right.key));
  corruptions.sort((left, right) => left.key.localeCompare(right.key));
  return {available: true, entries, corruptions};
}

function installInventoriedFieldObservationLockUnlocked(lock) {
  try {
    const before = localStorage.getItem(FIELD_OBSERVATION_LOCK_KEY);
    const raw = JSON.stringify(storedFieldObservationLockValue(lock));
    localStorage.setItem(FIELD_OBSERVATION_LOCK_KEY, raw);
    const confirmedRaw = localStorage.getItem(FIELD_OBSERVATION_LOCK_KEY);
    if (confirmedRaw !== raw) {
      adoptStoredFieldObservationLockOrBlock(confirmedRaw);
      return false;
    }
    // A synchronous storage section cannot detect every cross-process race. Re-read and
    // fail closed; Web Locks is used for live acquisitions when the browser supports it.
    if (before !== null && before === raw) {
      adoptFieldObservationLock(lock);
      return true;
    }
    adoptFieldObservationLock(lock);
    return true;
  } catch (_error) {
    adoptFieldObservationLock({...lock, persistence_missing: true});
    return false;
  }
}

function acquireFieldObservationLockUnlocked(candidate) {
  const candidateRaw = JSON.stringify(storedFieldObservationLockValue(candidate));
  const pendingRaw = JSON.stringify(candidate.pending);
  try {
    const currentRaw = localStorage.getItem(FIELD_OBSERVATION_LOCK_KEY);
    if (currentRaw !== null) {
      adoptStoredFieldObservationLockOrBlock(currentRaw);
      return false;
    }
    const inventory = pendingFieldObservationInventory();
    if (!inventory.available || inventory.corruptions.length > 0) {
      adoptFieldObservationLock({status: "unreadable", persistence_missing: true});
      return false;
    }
    const unrelated = inventory.entries.filter((entry) => entry.key !== candidate.key
      || JSON.stringify(entry.pending) !== pendingRaw);
    if (unrelated.length > 0) {
      rebuildPendingFieldObservationInventoryUnlocked();
      return false;
    }
    const existingPending = localStorage.getItem(candidate.key);
    if (existingPending !== null && existingPending !== pendingRaw) return false;
    localStorage.setItem(FIELD_OBSERVATION_LOCK_KEY, candidateRaw);
    let confirmedRaw = localStorage.getItem(FIELD_OBSERVATION_LOCK_KEY);
    if (confirmedRaw !== candidateRaw) {
      adoptStoredFieldObservationLockOrBlock(confirmedRaw);
      return false;
    }
    if (existingPending === null) localStorage.setItem(candidate.key, pendingRaw);
    confirmedRaw = localStorage.getItem(FIELD_OBSERVATION_LOCK_KEY);
    if (confirmedRaw !== candidateRaw || localStorage.getItem(candidate.key) !== pendingRaw) {
      adoptStoredFieldObservationLockOrBlock(confirmedRaw);
      return false;
    }
    adoptFieldObservationLock(candidate);
    return true;
  } catch (_error) {
    adoptFieldObservationLock({...candidate, persistence_missing: true});
    return false;
  }
}

function inventoriedFieldObservationLock(inventory) {
  if (!inventory.available) return {status: "unreadable", persistence_missing: true};
  const persisted = persistedFieldObservationLock();
  const entries = inventory.entries.map((entry) => {
    const persistedEntry = persisted.lock?.entries?.find((candidate) => candidate.key === entry.key
      && candidate.pending?.payload?.observation_id === entry.pending.payload.observation_id);
    const status = persistedEntry?.status || (persisted.lock?.key === entry.key
      && persisted.lock?.pending?.payload?.observation_id === entry.pending.payload.observation_id
      ? persisted.lock.status : entry.status);
    return Object.freeze({...entry, status});
  });
  const corruptions = inventory.corruptions;
  if (corruptions.length > 0 && entries.length <= 1) {
    return {
      version: FIELD_OBSERVATION_LOCK_VERSION,
      generation: `corrupt-${entries.length}-${corruptions.length}`,
      status: "corrupt_pending", entries, corruptions,
    };
  }
  if (entries.length > 1) {
    const generation = `multiple-${entries.map((entry) => entry.pending.payload.observation_id).sort().join("-")}`;
    return {
      version: FIELD_OBSERVATION_LOCK_VERSION,
      generation: generation.slice(0, 128),
      status: "multiple_pending", entries,
      ...(corruptions.length > 0 ? {corruptions} : {}),
    };
  }
  if (entries.length === 1) {
    const entry = entries[0];
    return {
      version: FIELD_OBSERVATION_LOCK_VERSION,
      generation: fieldObservationLockGeneration(entry.pending),
      status: entry.status || "pending", key: entry.key, pending: entry.pending, context: entry.context,
    };
  }
  return null;
}

function rebuildPendingFieldObservationInventoryUnlocked() {
  const inventory = pendingFieldObservationInventory();
  if (!inventory.available) {
    adoptFieldObservationLock({status: "unreadable", persistence_missing: true});
    return false;
  }
  const lock = inventoriedFieldObservationLock(inventory);
  if (!lock) {
    try {
      localStorage.removeItem(FIELD_OBSERVATION_LOCK_KEY);
      adoptFieldObservationLock(null);
      return true;
    } catch (_error) {
      adoptFieldObservationLock({status: "persistence_missing", persistence_missing: true});
      return false;
    }
  }
  return installInventoriedFieldObservationLockUnlocked(lock);
}

async function restorePendingFieldObservationInventory() {
  const inventory = pendingFieldObservationInventory();
  const diagnostic = inventoriedFieldObservationLock(inventory);
  if (diagnostic) adoptFieldObservationLock(diagnostic);
  else if (inventory.available) adoptFieldObservationLock(null);
  const result = await withFieldObservationWebLock(rebuildPendingFieldObservationInventoryUnlocked);
  updateFieldObservationSubmitState();
  return result.executed && result.value === true;
}

function resetFieldObservationForm() {
  const form = document.querySelector("#field-observation-form");
  for (const input of form.querySelectorAll("[data-observation-choice]")) input.value = "";
  for (const input of form.querySelectorAll('input[type="number"]')) input.value = "";
  for (const input of form.querySelectorAll('input[type="radio"]')) input.checked = false;
  for (const select of form.querySelectorAll("select")) select.selectedIndex = 0;
  document.querySelector(".observation-advanced").open = false;
}

function setOptionalObservationValue(selector, value) {
  document.querySelector(selector).value = value === null || value === undefined ? "" : String(value);
}

function unreadablePendingObservationMessage() {
  return "Le brouillon local est illisible : la sécurité d’idempotence n’est plus garantie. Rechargez la page ou réinitialisez explicitement avant tout nouvel envoi.";
}

function blockUnreadablePendingObservation(key) {
  if (!(state.unreadableFieldObservationContextKeys instanceof Set)) {
    state.unreadableFieldObservationContextKeys = new Set();
  }
  state.unreadableFieldObservationContextKeys.add(key);
}

function unreadablePendingObservationBlocked(key) {
  return state.unreadableFieldObservationContextKeys instanceof Set
    && state.unreadableFieldObservationContextKeys.has(key);
}

function syncFieldObservationContext() {
  const dialog = document.querySelector("#field-observation-dialog");
  if (!dialog.open || !state.fieldObservationDraftContext) return;
  if (sameFieldObservationContext(state.fieldObservationDraftContext, activeObservationContext())) return;
  state.fieldObservationContextInvalid = true;
  updateFieldObservationSubmitState();
  observationMessage(
    "La décision ou la session a changé. Cet éditeur est bloqué pour éviter un rattachement incorrect. Fermez-le puis rouvrez-le.",
    { error: true },
  );
}

function restorePendingFieldObservation() {
  const context = state.fieldObservationDraftContext;
  if (!context || state.fieldObservationContextInvalid || fieldObservationDraft()) return;
  const decisionId = context?.decision_id;
  const executionId = context?.execution_id || null;
  if (!decisionId) return;
  const key = pendingObservationKey(decisionId, executionId);
  if (state.fieldObservationLock && state.fieldObservationLock.key !== key) {
    updateFieldObservationSubmitState();
    observationMessage(fieldObservationLockMessage(), { error: true });
    return;
  }
  if (unreadablePendingObservationBlocked(key)) {
    observationMessage(unreadablePendingObservationMessage(), { error: true });
    return;
  }
  const storedPending = readPendingFieldObservation(key, context);
  if (!storedPending.available) {
    if (storedPending.reason === "corrupt") {
      blockUnreadablePendingObservation(key);
      observationMessage(unreadablePendingObservationMessage(), { error: true });
    } else {
      observationMessage("Le stockage local est indisponible : impossible de restaurer une saisie en attente.", { error: true });
    }
    return;
  }
  const pending = state.fieldObservationLock?.key === key
    ? state.fieldObservationLock.pending : storedPending.value;
  const payload = pending?.payload;
  if (!payload || payload.decision_id !== decisionId || (payload.execution_id || null) !== executionId) return;
  if (!state.fieldObservationLock) {
    adoptFieldObservationLock({
      version: FIELD_OBSERVATION_LOCK_VERSION,
      generation: fieldObservationLockGeneration(pending),
      status: "pending", key, pending, context: Object.freeze({...context}),
    });
  }
  document.querySelector("#observation-observed-at").value = pending.observed_at_local;
  document.querySelector("#observation-clouds").value = payload.conditions?.cloud_state || "";
  document.querySelector("#observation-transparency").value = payload.conditions?.transparency || "";
  setOptionalObservationValue("#observation-wind", payload.conditions?.wind_speed_kmh);
  setOptionalObservationValue("#observation-temperature", payload.conditions?.temperature_c);
  setOptionalObservationValue("#observation-humidity", payload.conditions?.relative_humidity_percent);
  document.querySelector("#observation-seeing").value = payload.conditions?.seeing || "";
  document.querySelector("#observation-moon-halo").value = payload.conditions?.moon_halo == null ? "" : String(payload.conditions.moon_halo);
  const surface = payload.conditions?.surface_condition;
  const surfaceSelector = surface === null ? null : OBSERVATION_SURFACE_INPUTS[surface];
  const surfaceInput = surfaceSelector ? document.querySelector(surfaceSelector) : null;
  if (surfaceInput) surfaceInput.checked = true;
  setOptionalObservationValue("#observation-attempted-frames", payload.acquisition?.attempted_frames);
  setOptionalObservationValue("#observation-usable-frames", payload.acquisition?.usable_frames);
  document.querySelector("#observation-stop-reason").value = payload.acquisition?.stop_reason || "";
  setOptionalObservationValue("#observation-hfr", payload.technical?.hfr);
  document.querySelector("#observation-hfr-unit").value = payload.technical?.hfr_unit || "px";
  setOptionalObservationValue("#observation-guiding", payload.technical?.guiding_rms_arcsec);
  updateFieldObservationSubmitState();
  observationMessage(state.fieldObservationLock?.status === "conflict"
    ? fieldObservationConflictMessage()
    : "Saisie restaurée après une confirmation réseau incomplète. L’UUID d’origine sera réutilisé.",
  { error: state.fieldObservationLock?.status === "conflict" });
}

function beginFieldObservationOperation(kind, lock = state.fieldObservationLock) {
  const operation = Object.freeze({
    token: ++fieldObservationOperationGeneration,
    kind,
    rootGeneration: state.fieldObservationLock?.generation || null,
    lockGeneration: lock?.generation || null,
    lockKey: lock?.key || null,
    observationId: lock?.pending?.payload?.observation_id || null,
  });
  activeFieldObservationOperation = operation;
  state.observationBusy = true;
  updateFieldObservationSubmitState();
  return operation;
}

function fieldObservationOperationCurrent(operation) {
  if (activeFieldObservationOperation?.token !== operation?.token
      || !state.observationBusy
      || (state.fieldObservationLock?.generation || null) !== operation.rootGeneration) return false;
  if (state.fieldObservationLock?.key) return state.fieldObservationLock.key === operation.lockKey
    && state.fieldObservationLock.pending?.payload?.observation_id === operation.observationId;
  const entry = state.fieldObservationLock?.entries?.find((candidate) => candidate.key === operation.lockKey
    && candidate.pending?.payload?.observation_id === operation.observationId);
  return Boolean(entry || (operation.lockKey === null && operation.observationId === null));
}

function invalidateFieldObservationOperation() {
  fieldObservationOperationGeneration += 1;
  activeFieldObservationOperation = null;
  state.observationBusy = false;
}

function finishFieldObservationOperation(operation) {
  if (activeFieldObservationOperation?.token !== operation?.token) return false;
  activeFieldObservationOperation = null;
  state.observationBusy = false;
  updateFieldObservationSubmitState();
  return true;
}

function staleFieldObservationOperationError() {
  const error = new Error("stale_field_observation_operation");
  error.staleFieldObservationOperation = true;
  return error;
}

async function storedFieldObservation(observationId, operation = null) {
  const response = await fetch(`/v1/field-observations/${encodeURIComponent(observationId)}`);
  if (operation && !fieldObservationOperationCurrent(operation)) throw staleFieldObservationOperationError();
  if (response.status === 404) return null;
  if (!response.ok) throw await sessionHttpError(response);
  if (operation && !fieldObservationOperationCurrent(operation)) throw staleFieldObservationOperationError();
  const stored = await response.json();
  if (operation && !fieldObservationOperationCurrent(operation)) throw staleFieldObservationOperationError();
  return stored;
}

function storedObservationMatchesPayload(stored, payload) {
  const normalizeDate = (value) => value == null ? null : new Date(value).toISOString();
  return stored?.observation_id === payload.observation_id
    && stored.decision_id === payload.decision_id
    && (stored.execution_id || null) === (payload.execution_id || null)
    && normalizeDate(stored.observed_at_utc) === normalizeDate(payload.observed_at_utc)
    && normalizeDate(stored.recorded_at_utc) === normalizeDate(payload.recorded_at_utc)
    && (stored.supersedes_observation_id || null) === (payload.supersedes_observation_id || null)
    && JSON.stringify(stored.conditions) === JSON.stringify(payload.conditions)
    && JSON.stringify(stored.acquisition) === JSON.stringify(payload.acquisition)
    && JSON.stringify(stored.technical) === JSON.stringify(payload.technical)
    && stored.quality?.confidence === payload.confidence
    && JSON.stringify(stored.quality?.flags || []) === JSON.stringify(payload.quality_flags);
}

function observationConflictError() {
  const error = new Error("field_observation_conflict");
  error.status = 409;
  return error;
}

async function finishFieldObservationSubmission(key, submittedSnapshot, message, operation = null) {
  if (operation && !fieldObservationOperationCurrent(operation)) return false;
  const lock = state.fieldObservationLock?.key === key ? state.fieldObservationLock : null;
  if (!lock || (operation && lock.generation !== operation.lockGeneration)) return false;
  const result = await withFieldObservationWebLock(() => {
    if (operation && !fieldObservationOperationCurrent(operation)) return false;
    if (!clearFieldObservationLockUnlocked(lock)) return false;
    return rebuildPendingFieldObservationInventoryUnlocked();
  });
  const removed = result.executed && result.value === true;
  if (fieldObservationSnapshot() === submittedSnapshot) resetFieldObservationForm();
  else message += " Vos modifications en cours sont conservées.";
  if (!removed) message += " Le brouillon local n’a pas pu être nettoyé.";
  observationMessage(message);
  return removed;
}

async function transitionFieldObservationLockStatus(lock, status, operation = null) {
  const result = await withFieldObservationWebLock(() => {
    if (operation && !fieldObservationOperationCurrent(operation)) return false;
    return writeFieldObservationLockUnlocked({...storedFieldObservationLockValue(lock), status}, lock);
  });
  return result.executed && result.value === true;
}

async function submitFieldObservation(event) {
  event.preventDefault();
  if (state.observationBusy) return;
  const context = state.fieldObservationDraftContext;
  const pageLock = state.fieldObservationLock;
  if (pageLock?.status === "invalid") {
    updateFieldObservationSubmitState();
    observationMessage(fieldObservationLockMessage(pageLock), { error: true });
    return;
  }
  if (state.fieldObservationContextInvalid
      || !sameFieldObservationContext(context, activeObservationContext())) {
    observationMessage("Le contexte du relevé a changé. Fermez cet éditeur puis rouvrez-le depuis la décision ou la mission voulue.", { error: true });
    return;
  }
  const decisionId = context?.decision_id;
  if (!decisionId) {
    observationMessage("La décision liée à cette mission est indisponible.", { error: true });
    return;
  }
  const executionId = context.execution_id || null;
  const key = pendingObservationKey(decisionId, executionId);
  if (state.invalidFieldObservationContextKey === key) {
    observationMessage("Ce contexte est périmé. Rechargez puis re-sélectionnez la mission et la session avant tout nouvel envoi.", { error: true });
    return;
  }
  if (pageLock && (pageLock.status !== "pending" || pageLock.persistence_missing
      || pageLock.key !== key || !sameFieldObservationContext(pageLock.context, context))) {
    updateFieldObservationSubmitState();
    observationMessage(fieldObservationLockMessage(pageLock), { error: true });
    return;
  }
  if (unreadablePendingObservationBlocked(key)) {
    observationMessage(unreadablePendingObservationMessage(), { error: true });
    return;
  }
  const storedPending = pageLock?.key === key
    ? {available: true, value: pageLock.pending}
    : readPendingFieldObservation(key, context);
  if (!storedPending.available) {
    if (storedPending.reason === "corrupt") {
      blockUnreadablePendingObservation(key);
      observationMessage(unreadablePendingObservationMessage(), { error: true });
    } else {
      observationMessage("Le stockage local est indisponible. Envoi bloqué pour éviter un doublon après une coupure réseau.", { error: true });
    }
    return;
  }
  const pending = storedPending.value;
  const draft = fieldObservationDraft();
  if (!draft) {
    observationMessage("Renseignez au moins une observation terrain.", { error: true });
    return;
  }
  const submittedSnapshot = fieldObservationSnapshot(draft);
  const pendingSnapshot = pending?.snapshot;
  const reusingPending = Boolean(pending?.payload && pendingSnapshot === submittedSnapshot);
  if (pending?.payload && !reusingPending) {
    if (!state.fieldObservationLock) {
      adoptFieldObservationLock({
        version: FIELD_OBSERVATION_LOCK_VERSION,
        generation: fieldObservationLockGeneration(pending),
        status: "pending", key, pending, context: Object.freeze({...context}),
      });
    }
    updateFieldObservationSubmitState();
    observationMessage(
      "Vos modifications sont conservées séparément, mais l’observation précédente doit d’abord être réconciliée avec son UUID d’origine.",
      { error: true },
    );
    return;
  }
  const payloadErrorMessages = {
      invalid_local_datetime: "Indiquez une date et une heure d’observation valides.",
      timezone_unavailable: "La conversion du fuseau du site est indisponible sur cet appareil. Utilisez un navigateur compatible avant l’envoi.",
      unsupported_site_timezone: "Le fuseau du site configuré n’est pas reconnu. Corrigez la configuration du site.",
      nonexistent_local_datetime: "Cette heure locale n’existe pas dans le fuseau du site à cause du passage à l’heure d’été. Choisissez une autre heure.",
      ambiguous_local_datetime: "Cette heure locale est ambiguë dans le fuseau du site à cause du passage à l’heure d’hiver. Choisissez une heure non ambiguë.",
      observed_at_in_future: "L’heure observée ne peut pas être postérieure à l’heure d’enregistrement.",
  };
  let payload = pending?.payload || null;
  if (reusingPending && !state.fieldObservationLock) {
    const candidate = {
      version: FIELD_OBSERVATION_LOCK_VERSION,
      generation: fieldObservationLockGeneration(pending),
      status: "pending", key, pending, context: Object.freeze({...context}),
    };
    const acquisitionOperation = beginFieldObservationOperation("restore", null);
    const acquisition = await withFieldObservationWebLock(
      () => acquireFieldObservationLockUnlocked(candidate),
    );
    if (activeFieldObservationOperation?.token !== acquisitionOperation.token
        || !acquisition.executed || acquisition.value !== true) {
      finishFieldObservationOperation(acquisitionOperation);
      adoptFieldObservationLock(candidate);
      observationMessage("L’observation existante est restaurée en lecture seule, mais Web Locks est requis pour la modifier ou publier.", {error: true});
      updateFieldObservationSubmitState();
      return;
    }
    finishFieldObservationOperation(acquisitionOperation);
  }
  if (!state.fieldObservationLock) {
    const acquisitionOperation = beginFieldObservationOperation("acquire", null);
    const acquisition = await withFieldObservationWebLock(() => {
      if (activeFieldObservationOperation?.token !== acquisitionOperation.token) return null;
      const inventory = pendingFieldObservationInventory();
      if (!inventory.available || inventory.entries.length > 0 || inventory.corruptions.length > 0) {
        rebuildPendingFieldObservationInventoryUnlocked();
        return null;
      }
      const acquiredPayload = buildFieldObservationPayload(draft);
      const envelope = {
        version: PENDING_FIELD_OBSERVATION_VERSION,
        payload: acquiredPayload,
        snapshot: submittedSnapshot,
        observed_at_local: draft.observed_at_local,
        timezone: draft.timezone,
      };
      const candidate = {
        version: FIELD_OBSERVATION_LOCK_VERSION,
        generation: fieldObservationLockGeneration(envelope),
        status: "pending", key, pending: envelope, context: Object.freeze({...context}),
      };
      return acquireFieldObservationLockUnlocked(candidate) ? {candidate, payload: acquiredPayload} : null;
    });
    const acquired = acquisition.executed ? acquisition.value : null;
    if (activeFieldObservationOperation?.token !== acquisitionOperation.token
        || !acquired || !sameFieldObservationLock(state.fieldObservationLock, acquired.candidate)) {
      finishFieldObservationOperation(acquisitionOperation);
      const validationMessage = payloadErrorMessages[acquisition.error?.message];
      observationMessage(validationMessage
        || "Envoi bloqué : Web Locks est indisponible ou a refusé la demande. Aucun UUID ni POST n’a été créé ; utilisez un navigateur compatible pour une nouvelle observation.",
      { error: true });
      updateFieldObservationSubmitState();
      return;
    }
    payload = acquired.payload;
    finishFieldObservationOperation(acquisitionOperation);
  }
  const operation = beginFieldObservationOperation("submit", state.fieldObservationLock);
  observationMessage("Enregistrement en cours…");
  try {
    if (reusingPending) {
      const stored = await storedFieldObservation(payload.observation_id, operation);
      if (stored) {
        if (!storedObservationMatchesPayload(stored, payload)) throw observationConflictError();
        await finishFieldObservationSubmission(key, submittedSnapshot, "Observation déjà enregistrée — aucune duplication.", operation);
        return;
      }
    }
    const response = await fetch("/v1/field-observations", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    if (!fieldObservationOperationCurrent(operation)) return;
    if (!response.ok) {
      const responseError = await sessionHttpError(response);
      if (!fieldObservationOperationCurrent(operation)) return;
      throw responseError;
    }
    await finishFieldObservationSubmission(key, submittedSnapshot, response.status === 201
      ? "Observation enregistrée." : "Observation déjà enregistrée — aucune duplication.", operation);
  } catch (error) {
    if (error?.staleFieldObservationOperation || !fieldObservationOperationCurrent(operation)) return;
    if (!error?.status) {
      try {
        const stored = await storedFieldObservation(payload.observation_id, operation);
        if (stored) {
          if (!storedObservationMatchesPayload(stored, payload)) throw observationConflictError();
          await finishFieldObservationSubmission(key, submittedSnapshot, "Observation enregistrée. La confirmation réseau avait été interrompue.", operation);
          return;
        }
      } catch (lookupError) {
        if (lookupError?.staleFieldObservationOperation || !fieldObservationOperationCurrent(operation)) return;
        if (lookupError?.status === 409) error = lookupError;
      }
    }
    if (!fieldObservationOperationCurrent(operation)) return;
    if (error?.status === 404) {
      state.invalidFieldObservationContextKey = key;
      state.fieldObservationContextInvalid = true;
      await transitionFieldObservationLockStatus(state.fieldObservationLock, "invalid", operation);
    }
    if (error?.status === 409) {
      await transitionFieldObservationLockStatus(state.fieldObservationLock, "conflict", operation);
    }
    if (error?.status >= 400 && error.status < 500
        && ![404, 409].includes(error.status)) {
      const lock = state.fieldObservationLock;
      const cleared = await withFieldObservationWebLock(() => {
        if (!fieldObservationOperationCurrent(operation)) return false;
        if (!clearFieldObservationLockUnlocked(lock)) return false;
        return rebuildPendingFieldObservationInventoryUnlocked();
      });
      if (!cleared.executed || cleared.value !== true) blockUnreadablePendingObservation(key);
    }
    const validationMessage = ["recorded_at_precedes_observed_at", "observed_at_in_future"].includes(error?.code)
      ? "L’heure observée est dans le futur par rapport à l’enregistrement. Vérifiez la date, l’heure et le fuseau du site."
      : ["invalid_observed_at_utc", "invalid_recorded_at_utc"].includes(error?.code)
        ? "L’horodatage est invalide. Vérifiez la date, l’heure et le fuseau du site."
        : "Certaines valeurs sont invalides. Vérifiez l’heure observée et les détails saisis.";
    const messages = {
      404: "La décision ou la session liée à ce relevé est introuvable ou périmée. Le formulaire et son UUID sont conservés ; utilisez « Actualiser le contexte ».",
      409: fieldObservationConflictMessage(),
      422: validationMessage,
      503: "Enregistrement momentanément indisponible. Vous pouvez réessayer sans créer de doublon.",
    };
    observationMessage(messages[error?.status] || "Confirmation impossible. Réessayez : la même observation sera reprise sans doublon.", { error: true });
  } finally {
    finishFieldObservationOperation(operation);
  }
}

async function reconcileFieldObservationLock() {
  const lock = state.fieldObservationLock;
  if (!lock?.pending?.payload || state.observationBusy) return;
  const operation = beginFieldObservationOperation("reconcile", lock);
  observationMessage("Réconciliation de l’UUID d’origine en cours…");
  try {
    const stored = await storedFieldObservation(lock.pending.payload.observation_id, operation);
    if (!stored) {
      observationMessage(
        "L’UUID d’origine n’est pas encore présent côté serveur. Le verrou reste actif ; vous pouvez réessayer la réconciliation ou abandonner explicitement.",
        { error: true },
      );
      return;
    }
    if (!storedObservationMatchesPayload(stored, lock.pending.payload)) {
      if (!fieldObservationOperationCurrent(operation)) return;
      await transitionFieldObservationLockStatus(lock, "conflict", operation);
      observationMessage("L’UUID d’origine existe avec un contenu différent. Le conflit reste bloqué.", { error: true });
      return;
    }
    await finishFieldObservationSubmission(
      lock.key, lock.pending.snapshot,
      "Observation d’origine retrouvée et réconciliée — aucun doublon créé.",
      operation,
    );
  } catch (error) {
    if (error?.staleFieldObservationOperation || !fieldObservationOperationCurrent(operation)) return;
    observationMessage("La réconciliation canonique a échoué. Le verrou et l’UUID d’origine restent conservés.", { error: true });
  } finally {
    finishFieldObservationOperation(operation);
  }
}

async function canonicalFieldObservationContextAvailable(context, operation = null) {
  if (context.execution_id) {
    const response = await fetch(`/v1/executions/${encodeURIComponent(context.execution_id)}/session`);
    if (operation && !fieldObservationOperationCurrent(operation)) throw staleFieldObservationOperationError();
    if (!response.ok) return false;
    const canonical = await response.json();
    if (operation && !fieldObservationOperationCurrent(operation)) throw staleFieldObservationOperationError();
    return canonical?.execution?.execution_id === context.execution_id
      && canonical?.mission?.decision_id === context.decision_id;
  }
  if (context.source === "mission") {
    const response = await fetch("/v1/accepted-mission/current");
    if (operation && !fieldObservationOperationCurrent(operation)) throw staleFieldObservationOperationError();
    if (!response.ok) return false;
    const canonical = await response.json();
    if (operation && !fieldObservationOperationCurrent(operation)) throw staleFieldObservationOperationError();
    return canonical?.status === "accepted"
      && canonical?.decision_id === context.decision_id
      && (!context.mission_id || canonical?.mission_id === context.mission_id);
  }
  if (!state.availability) return false;
  await loadTonight(state.availability);
  if (operation && !fieldObservationOperationCurrent(operation)) throw staleFieldObservationOperationError();
  return sameFieldObservationContext(context, observationContext("decision"));
}

async function refreshInvalidFieldObservationContext() {
  const lock = state.fieldObservationLock;
  if (lock?.status !== "invalid" || state.observationBusy) return;
  const operation = beginFieldObservationOperation("refresh", lock);
  observationMessage("Actualisation du contexte canonique en cours…");
  try {
    const stored = await storedFieldObservation(lock.pending.payload.observation_id, operation);
    if (stored) {
      if (!storedObservationMatchesPayload(stored, lock.pending.payload)) {
        if (!fieldObservationOperationCurrent(operation)) return;
        await transitionFieldObservationLockStatus(lock, "conflict", operation);
        observationMessage("L’UUID d’origine existe avec un contenu divergent. Le conflit reste bloqué.", { error: true });
        return;
      }
      await finishFieldObservationSubmission(
        lock.key, lock.pending.snapshot,
        "Observation d’origine retrouvée pendant l’actualisation — aucun doublon créé.",
        operation,
      );
      return;
    }
    if (!await canonicalFieldObservationContextAvailable(lock.context, operation)) {
      if (!fieldObservationOperationCurrent(operation)) return;
      observationMessage("La décision ou la session d’origine reste absente. Le contexte demeure bloqué.", { error: true });
      return;
    }
    if (!fieldObservationOperationCurrent(operation)) return;
    state.invalidFieldObservationContextKey = null;
    state.fieldObservationContextInvalid = !sameFieldObservationContext(
      state.fieldObservationDraftContext, activeObservationContext(),
    );
    await transitionFieldObservationLockStatus(lock, "pending", operation);
    observationMessage(
      "Le contexte canonique est de nouveau disponible. La prochaine tentative réutilisera strictement l’UUID et le contenu d’origine.",
    );
  } catch (error) {
    if (error?.staleFieldObservationOperation || !fieldObservationOperationCurrent(operation)) return;
    observationMessage("L’actualisation canonique a échoué. Le contexte reste bloqué.", { error: true });
  } finally {
    finishFieldObservationOperation(operation);
  }
}

function fieldObservationEntryForKey(key) {
  const lock = state.fieldObservationLock;
  if (lock?.key === key) return {key: lock.key, pending: lock.pending, context: lock.context, status: lock.status};
  return lock?.entries?.find((entry) => entry.key === key) || null;
}

function removeFieldObservationEntryUnlocked(entry) {
  try {
    const currentRaw = localStorage.getItem(entry.key);
    if (currentRaw === null && state.fieldObservationLock?.status === "persistence_missing") {
      const remaining = (state.fieldObservationLock.entries || []).filter((candidate) => candidate.key !== entry.key);
      if (remaining.length === 0) adoptFieldObservationLock(null);
      else adoptFieldObservationLock({...state.fieldObservationLock, entries: remaining});
      return true;
    }
    if (currentRaw !== JSON.stringify(entry.pending)) return false;
    localStorage.removeItem(entry.key);
    return rebuildPendingFieldObservationInventoryUnlocked();
  } catch (_error) {
    return false;
  }
}

function transitionFieldObservationEntryStatusUnlocked(entry, status) {
  const inventory = pendingFieldObservationInventory();
  if (!inventory.available) return false;
  let lock = inventoriedFieldObservationLock(inventory);
  if (!lock) return false;
  if (lock.key === entry.key) lock = {...lock, status};
  else {
    const entries = lock.entries.map((candidate) => candidate.key === entry.key
      && candidate.pending.payload.observation_id === entry.pending.payload.observation_id
      ? {...candidate, status} : candidate);
    lock = {...lock, entries};
  }
  return installInventoriedFieldObservationLockUnlocked(lock);
}

async function reconcileFieldObservationEntry(key) {
  if (state.observationBusy) return;
  const entry = fieldObservationEntryForKey(key);
  if (!entry?.pending?.payload) return;
  const operation = beginFieldObservationOperation("reconcile_entry", entry);
  observationMessage(`Réconciliation de ${entry.pending.payload.observation_id} en cours…`);
  try {
    const stored = await storedFieldObservation(entry.pending.payload.observation_id, operation);
    if (!stored) {
      observationMessage("L’UUID ciblé n’est pas encore présent côté serveur ; cette entrée reste bloquée.", {error: true});
      return;
    }
    if (!storedObservationMatchesPayload(stored, entry.pending.payload)) {
      await withFieldObservationWebLock(() => {
        if (!fieldObservationOperationCurrent(operation)) return false;
        return transitionFieldObservationEntryStatusUnlocked(entry, "conflict");
      });
      observationMessage("L’UUID ciblé existe avec un contenu différent ; cette entrée reste bloquée.", {error: true});
      return;
    }
    const result = await withFieldObservationWebLock(() => {
      if (!fieldObservationOperationCurrent(operation)) return false;
      return removeFieldObservationEntryUnlocked(entry);
    });
    observationMessage(result.executed && result.value
      ? "Entrée ciblée réconciliée ; l’inventaire local a été reconstruit."
      : "L’entrée a été retrouvée, mais sa suppression sûre exige Web Locks ; elle reste bloquée.",
    {error: !result.executed || !result.value});
  } catch (error) {
    if (error?.staleFieldObservationOperation || !fieldObservationOperationCurrent(operation)) return;
    observationMessage("La réconciliation ciblée a échoué ; cette entrée reste intacte.", {error: true});
  } finally {
    finishFieldObservationOperation(operation);
  }
}

async function abandonFieldObservationEntry(key) {
  if (state.observationBusy) return;
  const entry = fieldObservationEntryForKey(key);
  if (!entry) return;
  if (typeof window !== "undefined" && typeof window.confirm === "function"
      && !window.confirm(`Abandonner uniquement l’observation ${entry.pending.payload.observation_id} (${entry.key}) ?`)) return;
  const operation = beginFieldObservationOperation("abandon_entry", entry);
  const result = await withFieldObservationWebLock(() => {
    if (!fieldObservationOperationCurrent(operation)) return false;
    return removeFieldObservationEntryUnlocked(entry);
  });
  finishFieldObservationOperation(operation);
  observationMessage(result.executed && result.value
    ? "Seule l’entrée ciblée a été abandonnée ; l’inventaire local a été reconstruit."
    : "Abandon ciblé impossible sans Web Locks ; aucune entrée n’a été supprimée.",
  {error: !result.executed || !result.value});
}

async function removeCorruptFieldObservationEntry(key) {
  if (state.observationBusy) return;
  const corruption = state.fieldObservationLock?.corruptions?.find((entry) => entry.key === key);
  if (!corruption) return;
  if (typeof window !== "undefined" && typeof window.confirm === "function"
      && !window.confirm(`Supprimer uniquement la clé locale corrompue ${key} ?`)) return;
  const root = state.fieldObservationLock;
  const operation = beginFieldObservationOperation("remove_corrupt", null);
  const result = await withFieldObservationWebLock(() => {
    if (!fieldObservationOperationCurrent(operation)
        || state.fieldObservationLock?.generation !== root.generation) return false;
    try {
      if (localStorage.getItem(key) !== corruption.raw) return false;
      localStorage.removeItem(key);
      return rebuildPendingFieldObservationInventoryUnlocked();
    } catch (_error) {
      return false;
    }
  });
  finishFieldObservationOperation(operation);
  observationMessage(result.executed && result.value
    ? "Clé corrompue ciblée supprimée ; les autres entrées sont conservées."
    : "Suppression ciblée impossible sans Web Locks ; aucune clé n’a été supprimée.",
  {error: !result.executed || !result.value});
}

async function abandonFieldObservationLock() {
  if (state.observationBusy) return;
  const lock = state.fieldObservationLock;
  if (!lock) return;
  if (["multiple_pending", "corrupt_pending"].includes(lock.status)) {
    observationMessage("Choisissez l’action de l’entrée concernée ; aucune suppression globale n’est proposée.", {error: true});
    return;
  }
  if (typeof window !== "undefined" && typeof window.confirm === "function"
      && !window.confirm("Abandonner définitivement l’observation précédente et son UUID ?")) return;
  const key = lock.key;
  const operation = beginFieldObservationOperation("abandon", lock);
  const result = await withFieldObservationWebLock(() => {
    if (!fieldObservationOperationCurrent(operation)) return false;
    if (!clearFieldObservationLockUnlocked(lock)) return false;
    return rebuildPendingFieldObservationInventoryUnlocked();
  });
  const removed = result.executed && result.value === true;
  finishFieldObservationOperation(operation);
  if (state.invalidFieldObservationContextKey === key) state.invalidFieldObservationContextKey = null;
  if (sameFieldObservationContext(state.fieldObservationDraftContext, activeObservationContext())) {
    state.fieldObservationContextInvalid = false;
  }
  updateFieldObservationSubmitState();
  observationMessage(removed
    ? "Observation précédente abandonnée explicitement. Vous pouvez enregistrer la saisie actuelle."
    : "L’abandon est mémorisé pour cette page, mais le stockage local n’a pas pu être nettoyé.",
  { error: !removed });
}

function handleFieldObservationStorageEvent(event) {
  const lock = state.fieldObservationLock;
  if (event.key === null) {
    invalidateFieldObservationOperation();
    const inventory = pendingFieldObservationInventory();
    const rebuilt = inventoriedFieldObservationLock(inventory);
    if (rebuilt) adoptFieldObservationLock(rebuilt);
    else if (lock) {
      const entries = lock.entries || (lock.pending
        ? [{key: lock.key, pending: lock.pending, context: lock.context, status: lock.status}] : []);
      adoptFieldObservationLock({
        version: FIELD_OBSERVATION_LOCK_VERSION,
        generation: lock.generation || "persistence-missing",
        status: "persistence_missing", persistence_missing: true, entries,
        corruptions: lock.corruptions || [],
      });
    } else {
      adoptFieldObservationLock({status: "persistence_missing", persistence_missing: true, entries: [], corruptions: []});
    }
    updateFieldObservationSubmitState();
    if (document.querySelector("#field-observation-dialog").open) {
      observationMessage(fieldObservationLockMessage(state.fieldObservationLock), {error: true});
    }
    return;
  }
  if (event.key === FIELD_OBSERVATION_LOCK_KEY) {
    if (event.newValue) {
      try {
        const incoming = parseStoredFieldObservationLock(event.newValue);
        if (sameFieldObservationLock(lock, incoming)
            && JSON.stringify(storedFieldObservationLockValue(lock)) === event.newValue) return;
        if (state.observationBusy) invalidateFieldObservationOperation();
        adoptFieldObservationLock(incoming);
      } catch (_error) {
        if (state.observationBusy) invalidateFieldObservationOperation();
        adoptFieldObservationLock({status: "unreadable", persistence_missing: true});
      }
    } else if (lock) {
      if (state.observationBusy) invalidateFieldObservationOperation();
      adoptFieldObservationLock({...lock, persistence_missing: true});
    } else {
      return;
    }
  } else {
    if (typeof event.key === "string" && event.key.startsWith(FIELD_OBSERVATION_PENDING_PREFIX)) {
      if (state.observationBusy) invalidateFieldObservationOperation();
      const inventory = pendingFieldObservationInventory();
      const diagnostic = inventoriedFieldObservationLock(inventory);
      if (diagnostic) adoptFieldObservationLock(diagnostic);
      else if (inventory.available) adoptFieldObservationLock(null);
      restorePendingFieldObservationInventory();
      updateFieldObservationSubmitState();
      if (document.querySelector("#field-observation-dialog").open && state.fieldObservationLock) {
        observationMessage(fieldObservationLockMessage(state.fieldObservationLock), { error: true });
      }
      return;
    }
    const watchedKeys = lock?.status === "multiple_pending"
      ? lock.entries.map((entry) => entry.key) : [lock?.key];
    if (!lock || !watchedKeys.includes(event.key)) return;
    const watchedEntry = lock.status === "multiple_pending"
      ? lock.entries.find((entry) => entry.key === event.key) : lock;
    const expectedPending = watchedEntry?.pending ? JSON.stringify(watchedEntry.pending) : null;
    if (event.newValue === expectedPending) return;
    if (state.observationBusy) invalidateFieldObservationOperation();
    adoptFieldObservationLock({...lock, persistence_missing: true});
  }
  updateFieldObservationSubmitState();
  if (document.querySelector("#field-observation-dialog").open) {
    observationMessage(fieldObservationLockMessage(state.fieldObservationLock), { error: true });
  }
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
  const presentation = weatherDecision?.presentation;
  text(`#${prefix}-weather-status`, presentation?.label || "Validation météo non renseignée");
  text(
    `#${prefix}-weather-title`,
    presentation?.summary || "Le statut de validation météo n’est pas renseigné dans cette réponse.",
  );
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
  state.sessions = [];
  state.activeSessionId = null;
  state.fieldObservationSelectedExecutionId = null;
  syncFieldObservationContext();
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

  renderSession();
  reloadSessions().catch(() => sessionMessage("Sessions momentanément indisponibles. Rechargez avant une action."));

}

function showAcceptanceStatus(message, { error = false } = {}) {
  ui.acceptanceStatus.textContent = message || "";
  ui.acceptanceStatus.hidden = !message;
  ui.acceptanceStatus.classList.toggle("error", error);
}

function formatRecommendationConfidence(confidence) {
  if (typeof confidence !== "number" || !Number.isFinite(confidence)) {
    return null;
  }
  const value = confidence;
  if (value < 0 || value > 1) return null;
  return `${Math.round(value * 100)} %`;
}

function renderRecommendationConfidence(confidence) {
  const formatted = formatRecommendationConfidence(confidence);
  ui.recommendationConfidence.textContent = formatted || "";
  ui.recommendationConfidencePanel.hidden = formatted === null;
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

const intentStatusLabels = Object.freeze({
  eligible: "Éligible",
  not_eligible: "Non éligible",
  insufficient_evidence: "Preuves insuffisantes",
});

const intentReasonLabels = Object.freeze({
  intent_not_in_imaging_field: "Cette prise de vue ne fait pas partie du champ défini.",
  intent_not_targeted_by_project: "Cette prise de vue n’est pas ciblée par le projet.",
  intent_target_completed: "L’objectif de cette prise de vue est déjà atteint.",
  required_filter_unavailable: "Le filtre requis n’est pas disponible dans cette configuration.",
  insufficient_actionable_productive_window: "La fenêtre productive continue est trop courte.",
  setup_capabilities_missing: "Les capacités de la configuration ne sont pas suffisamment documentées.",
  productive_window_evidence_missing: "La preuve de fenêtre productive est insuffisante.",
  weather_evidence_insufficient: "Les preuves météo sont insuffisantes pour confirmer cette prise de vue.",
  filter_profile_evidence_insufficient: "Le profil optique du filtre n’est pas suffisamment établi.",
  lunar_evidence_insufficient: "Les preuves lunaires sont insuffisantes pour comparer cette prise de vue.",
});

function intentReasonText(code) {
  return intentReasonLabels[code] || `Raison non traduite : ${code}`;
}

function renderIntentAssessments(container, assessments) {
  if (!Array.isArray(assessments) || !assessments.length) return;
  const list = document.createElement("ul");
  list.className = "intent-assessments";
  for (const assessment of assessments) {
    const item = document.createElement("li");
    const heading = document.createElement("strong");
    const status = intentStatusLabels[assessment?.status] || "Statut indisponible";
    heading.textContent = `${assessment?.label || assessment?.acquisition_intent_id || "Prise de vue"} — ${status}`;
    item.append(heading);
    const reasonCodes = Array.isArray(assessment?.reason_codes)
      ? assessment.reason_codes : [];
    if (reasonCodes.length) {
      const reasons = document.createElement("ul");
      for (const code of reasonCodes) {
        const reason = document.createElement("li");
        reason.textContent = intentReasonText(code);
        reason.dataset.reasonCode = code;
        reasons.append(reason);
      }
      item.append(reasons);
    }
    list.append(item);
  }
  container.append(list);
}

function joinedIntentLabels(assessments) {
  const labels = (Array.isArray(assessments) ? assessments : [])
    .map((assessment) => assessment?.label)
    .filter(Boolean);
  if (labels.length < 2) return labels[0] || "Prises de vue";
  return `${labels.slice(0, -1).join(", ")} et ${labels.at(-1)}`;
}

function intentFilterType(intent) {
  const labelType = intent?.label?.split(" · ")[0]?.trim();
  return labelType || intent?.filter_type?.replaceAll("_", " ") || "non précisé";
}

function filterCardCopy(decision) {
  const assessments = Array.isArray(decision.acquisition_intent_assessments)
    ? decision.acquisition_intent_assessments : [];
  const filter = decision.selected_filter;
  const selectedIntentId = decision.selected_acquisition_intent_id;
  const selectedIntent = assessments.find(
    (assessment) => assessment?.acquisition_intent_id === selectedIntentId,
  ) || (Array.isArray(decision.acquisition_intent_options)
    ? decision.acquisition_intent_options.find(
      (option) => option?.acquisition_intent_id === selectedIntentId,
    ) : null);

  if (selectedIntent) {
    const otherAssessments = assessments.filter(
      (assessment) => assessment?.acquisition_intent_id !== selectedIntentId,
    );
    const detail = `${selectedIntent.label || selectedIntentId} recommandé${otherAssessments.length
      ? ` ; ${joinedIntentLabels(otherAssessments)} également évalué${otherAssessments.length > 1 ? "s" : ""}`
      : ""}`;
    return {
      value: `Type requis : ${intentFilterType(selectedIntent)}`,
      note: filter?.name
        ? `Filtre matériel : ${filter.name}`
        : "Filtre matériel non renseigné",
      detail,
    };
  }

  if (assessments.length) {
    return {
      value: "Aucun type de filtre retenu",
      note: filter?.name ? `Filtre matériel : ${filter.name}` : "Filtre matériel non renseigné",
      detail: `${joinedIntentLabels(assessments)} évalués`,
    };
  }

  return {
    value: filter?.name ? `Filtre matériel : ${filter.name}` : "Filtre non précisé",
    note: filter?.filter_type ? filter.filter_type.replaceAll("_", " ") : "",
    detail: "",
  };
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
    if (mode === "none") {
      renderIntentAssessments(
        container,
        subject.acquisition_intent_assessments,
      );
    }
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
    ? "La sélection en attente ne peut pas être relue de façon sûre. NightMerit bloque toute nouvelle sélection pour éviter un doublon."
    : "Le résultat de votre sélection n’a pas pu être confirmé. NightMerit doit vérifier cette sélection avant de poursuivre.";
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
  const filterCopy = filterCardCopy(decision);
  text("#filter-value", filterCopy.value);
  text("#filter-note", filterCopy.note);
  text("#filter-detail", filterCopy.detail);
  text("#quality-score", qualityScore === null ? "—" : String(qualityScore));
  text("#quality-title", qualityCopy[0]);
  text("#quality-summary", qualityCopy[1]);
  text("#limiting-factor", limiting ? (labels.factors[limiting] || limiting.replaceAll("_", " ")) : "Aucun identifié");
  renderRecommendationConfidence(decision.recommendation_confidence);
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
    ? "NightMerit ne dispose pas d’assez d’éléments fiables pour recommander cette cible pour cette session."
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
  if (ui.addObservationDecision) ui.addObservationDecision.hidden = !decision.decision_id;
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
  syncFieldObservationContext();
  state.configurationDraft = draftFromConfiguration(payload);
  document.querySelector("#legacy-bortle-note").hidden = !payload.needs_configuration_confirmation;
  text("#onboarding-title", payload.needs_configuration_confirmation
    ? "Confirmez votre profil NightMerit."
    : "Préparons NightMerit.");
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
  state.savedMissions = [];
  ui.savedMissionEntry.hidden = true;
  let current = null;
  try {
    const response = await fetch("/v1/accepted-mission/current");
    if (!response.ok) throw new Error("mission_read_unavailable");
    const payload = await response.json();
    const mission = payload?.mission;
    if (state.configuration === configuration && payload?.status === "accepted" && mission
        && payload.mission_id === mission.mission_id
        && payload.selection_id === mission.selection_id
        && payload.decision_id === mission.decision_id) {
      current = {
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
      const seen = new Set();
      for (const item of sessions) {
        if (seen.has(item.mission_id)) continue;
        seen.add(item.mission_id);
        state.savedMissions.push({
          decision_id: item.mission.decision_id, selection_id: item.mission.selection_id,
          mission_id: item.mission_id, selectedCatalogKey: item.project_id,
          acquisitionIntentId: item.acquisition_intent_id, source: "persisted",
          mission: item.mission,
        });
      }
    }
  } catch (_error) {
    // The current mission can still be opened if session discovery is unavailable.
  }
  if (current && !state.savedMissions.some((item) => item.mission_id === current.mission_id)) {
    state.savedMissions.unshift(current);
  }
  state.acceptedMission = current || state.savedMissions[0] || null;
  ui.savedMissionChoice.replaceChildren();
  for (const item of state.savedMissions) {
    const option = document.createElement("option");
    option.value = item.mission_id;
    option.textContent = `${item.mission.target} · ${new Date(item.mission.window_start).toLocaleString("fr-CH")}`;
    ui.savedMissionChoice.append(option);
  }
  if (state.acceptedMission) {
    ui.savedMissionChoice.value = state.acceptedMission.mission_id;
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
    showConfigurationError("NightMerit ne parvient pas à charger la configuration. La saisie pourra reprendre après reconnexion.");
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

function nextCivilDate(dateValue) {
  const [yearValue, monthValue, dayValue] = dateValue.split("-").map(Number);
  const leapYear = yearValue % 4 === 0 && (yearValue % 100 !== 0 || yearValue % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let year = yearValue;
  let month = monthValue;
  let day = dayValue + 1;
  if (day > daysInMonth[month - 1]) {
    day = 1;
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function fixedWindowRolloverDate(start, end) {
  if (!start || !end) return null;
  const startDate = start.slice(0, 10);
  const endDate = end.slice(0, 10);
  if (startDate !== endDate || end.slice(11) >= start.slice(11)) return null;
  return nextCivilDate(endDate);
}

function updateAvailabilityOvernightHint() {
  const mode = document.querySelector('input[name="availability-mode"]:checked')?.value;
  const start = normalizeLocalDateTime(document.querySelector("#availability-start").value);
  const end = normalizeLocalDateTime(document.querySelector("#availability-end").value);
  const rolloverDate = mode === "fixed_window" ? fixedWindowRolloverDate(start, end) : null;
  ui.availabilityOvernightHint.hidden = !rolloverDate;
  ui.availabilityOvernightHint.textContent = rolloverDate
    ? `Fin interprétée le lendemain (${rolloverDate.slice(8, 10)}/${rolloverDate.slice(5, 7)})`
    : "";
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
    const sameDate = start.slice(0, 10) === end.slice(0, 10);
    if (end === start || (!sameDate && end < start)) {
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
  updateAvailabilityOvernightHint();
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
  if (code === "session_availability_equal_times_ambiguous") {
    return "Des heures de début et de fin identiques sont ambiguës. Indiquez explicitement le lendemain pour une plage de 24 h.";
  }
  if (code === "session_availability_fixed_window_too_long") {
    return "La plage de disponibilité ne peut pas dépasser 24 heures.";
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
  no_candidate: ["Aucune cible adaptée", "NightMerit n’a trouvé aucune cible compatible avec cette nuit et votre configuration."],
  no_recommendation: ["Décision encore incertaine", "Les données disponibles ne permettent pas d’établir une recommandation suffisamment fiable."],
  no_mission: ["Mission incomplète", "Une cible a été identifiée, mais la mission opérationnelle n’a pas pu être assemblée."],
  no_productive_window: ["Aucun créneau suffisamment productif", "Une nuit astronomique existe, mais aucune fenêtre n’atteint le seuil opérationnel requis par NightMerit."],
});

const actionabilityCauseLabels = Object.freeze({
  insufficient_actionable_productive_window: "aucune fenêtre productive continue n’atteint le seuil requis",
  productive_window_evidence_missing: "les preuves temporelles de fenêtre productive sont manquantes ou invalides",
});

function actionabilityRefusalMessage(refusal) {
  const title = "Aucun créneau suffisamment productif";
  if (!refusal || refusal.conclusion !== "no_productive_window") {
    return [title, partialMessages.no_productive_window[1]];
  }
  const cause = actionabilityCauseLabels[refusal.cause_code]
    || (refusal.cause_code ? `cause moteur : ${refusal.cause_code}` : null);
  const breakdown = refusal.productivity_breakdown;
  if (
    refusal.status === "constraints_refusal"
    && refusal.refusal_stage === "no_productive_slice"
    && breakdown
  ) {
    const score = Math.round(breakdown.best_slice_score * 100);
    const threshold = Math.round(breakdown.productive_slice_threshold * 100);
    const tieCount = breakdown.best_slice_tie_count;
    const bestLabel = tieCount > 1
      ? `Une des ${tieCount} meilleures tranches`
      : "Meilleure tranche";
    const lossLabels = Object.freeze({
      cloud: "Nuages",
      moon: "Lune",
      altitude: "Altitude",
      humidity: "Humidité",
      wind: "Vent",
    });
    const losses = Object.entries(breakdown.losses || {})
      .filter(([name, value]) => lossLabels[name] && Number.isFinite(value) && value > 0)
      .sort((left, right) => right[1] - left[1])
      .map(([name, value]) => `${lossLabels[name]} : −${Math.round(value * 100)} points`);
    const lossText = losses.length ? ` ${losses.join(" · ")}.` : "";
    return [
      "Aucune tranche productive",
      `${bestLabel} : ${score} % — seuil requis : ${threshold} %.${lossText} Aucune des ${breakdown.evaluated_slice_count} tranches de 15 min n’atteint le seuil.`,
    ];
  }
  if (
    refusal.status === "constraints_refusal"
    && refusal.refusal_stage === "continuous_window_too_short"
    && Number.isFinite(refusal.best_productive_window_minutes)
    && Number.isFinite(refusal.required_continuous_minutes)
  ) {
    const foundMinutes = Math.max(0, Math.floor(refusal.best_productive_window_minutes));
    const requiredMinutes = Math.max(0, Math.ceil(refusal.required_continuous_minutes));
    return [
      "Fenêtre productive trop courte",
      `Des tranches productives existent, mais la meilleure fenêtre continue après vos contraintes dure ${foundMinutes} min. Seuil requis : ${requiredMinutes} min.`,
    ];
  }
  if (
    refusal.status === "constraints_refusal"
    && Number.isFinite(refusal.best_productive_window_minutes)
    && Number.isFinite(refusal.required_continuous_minutes)
  ) {
    const foundMinutes = Math.max(0, Math.floor(refusal.best_productive_window_minutes));
    const requiredMinutes = Math.max(0, Math.ceil(refusal.required_continuous_minutes));
    const causeText = cause ? ` Cause : ${cause}.` : "";
    return [
      title,
      `Meilleure fenêtre trouvée : ${foundMinutes} min. Seuil requis : ${requiredMinutes} min.${causeText}`,
    ];
  }
  const causeText = cause ? ` Indication du moteur : ${cause}.` : "";
  return [
    title,
    `La cause précise n’est pas établie : les preuves disponibles sont insuffisantes.${causeText}`,
  ];
}

function showMessage(title, body, { kicker = "Décision indisponible", retry = true } = {}) {
  text("#message-kicker", kicker);
  text("#message-title", title);
  text("#message-body", body);
  ui.retry.hidden = !retry;
  ui.addObservationMessage.hidden = !state.currentDecision?.decision_id;
  show("message");
}

function setCurrentFieldObservationDecision(decision) {
  state.currentDecision = decision?.decision_id ? decision : null;
  ui.addObservationMessage.hidden = true;
  ui.addObservationDecision.hidden = true;
  syncFieldObservationContext();
}

function normalizeError(response, payload) {
  const detail = payload?.detail;
  if (payload?.error === "user_profile_unavailable") {
    return ["Configuration requise", "NightMerit doit relire votre configuration avant de préparer la nuit."];
  }
  if (response.status === 503) {
    if (detail?.code === "weather_unavailable") {
      return ["Météo temporairement indisponible", "NightMerit ne peut pas encore lire les conditions de votre site. Réessayez dans un instant."];
    }
    if (detail?.code === "weather_invalid") {
      return ["Données météo rejetées", "NightMerit a reçu une réponse météo, mais ses contrôles de cohérence ont échoué. Aucune décision n’est calculée."];
    }
    if (detail?.code === "weather_insufficient") {
      return ["Prévisions météo insuffisantes", "La couverture reçue ne permet pas de préparer la nuit avec assez de données. Aucune décision n’est calculée."];
    }
    if (detail?.code === "weather_stale") {
      return ["Données météo trop anciennes", "Les données météo reçues dépassent la limite de fraîcheur de 90 minutes. NightMerit refuse de calculer une décision potentiellement trompeuse."];
    }
    if (detail?.code === "decision_invalid") {
      return ["Décision rejetée par sécurité", "NightMerit a détecté une contradiction interne et refuse d’afficher une recommandation potentiellement trompeuse."];
    }
    if (detail?.code === "location_timezone_unresolved") {
      return ["Fuseau horaire introuvable", "NightMerit ne peut pas relier ce site à un fuseau horaire fiable et refuse de calculer une nuit locale."];
    }
    return ["Prévisions temporairement indisponibles", "La prévision de cette nuit n’est pas accessible pour le moment. Réessayez dans un instant."];
  }
  if (response.status === 422) {
    const validationMessage = Array.isArray(detail)
      ? detail.map((item) => item.msg).filter(Boolean).join(" · ")
      : detail?.message;
    return ["Informations à vérifier", validationMessage || "Certaines informations nécessaires à la décision ne sont pas valides."];
  }
  return ["NightMerit n’a pas pu répondre", "Une erreur inattendue empêche la préparation de votre nuit."];
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
    return ["NightMerit ne peut pas confirmer cette acceptation. Aucune mission n’est affichée.", true];
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
          ? `NightMerit recommandait ${decision.target || decision.catalog_key}. Vous avez choisi ${selectedTarget}.`
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
  setCurrentFieldObservationDecision(null);

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
    setCurrentFieldObservationDecision(payload);
    if (payload.status === "weather_refused") {
      showMessage(
        payload.weather_decision.presentation.label,
        payload.weather_decision.presentation.summary,
        { kicker: "Analyse terminée" },
      );
      return;
    }

    if (payload.status !== "available") {
      const [title, body] = payload.status === "no_productive_window"
        ? actionabilityRefusalMessage(payload.actionability_refusal)
        : partialMessages[payload.status] || ["Décision indisponible", "NightMerit ne dispose pas encore d’une recommandation exploitable."];
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
document.querySelector("#availability-start").addEventListener("input", updateAvailabilityOvernightHint);
document.querySelector("#availability-end").addEventListener("input", updateAvailabilityOvernightHint);

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
  const selected = state.savedMissions.find((item) => item.mission_id === ui.savedMissionChoice.value);
  if (selected) state.acceptedMission = selected;
  if (!state.acceptedMission?.mission || state.acceptedMission.source !== "persisted") return;
  renderMission(state.acceptedMission.mission);
  ui.mission.showModal();
});
document.querySelector("#session-choice").addEventListener("change", (event) => {
  state.activeSessionId = event.target.value || null;
  state.fieldObservationSelectedExecutionId = event.target.value || null;
  renderSession();
  syncFieldObservationContext();
});
document.querySelector("#session-start").addEventListener("click", () => sessionCommand(startSession));
document.querySelector("#session-complete").addEventListener("click", () => sessionCommand((missionId) => closeSession(missionId, "completed")));
document.querySelector("#session-interrupt").addEventListener("click", () => sessionCommand((missionId) => closeSession(missionId, "interrupted")));
document.querySelector("#session-record-evidence").addEventListener("click", () => sessionCommand(recordSessionEvidence));
document.querySelector("#session-apply-credit").addEventListener("click", () => sessionCommand(creditSession));
document.querySelector("#field-observation-form").addEventListener("submit", submitFieldObservation);
document.querySelector("#observation-reconcile").addEventListener("click", reconcileFieldObservationLock);
document.querySelector("#observation-refresh-context").addEventListener("click", refreshInvalidFieldObservationContext);
document.querySelector("#observation-abandon-pending").addEventListener("click", abandonFieldObservationLock);
window.addEventListener("storage", handleFieldObservationStorageEvent);
ui.addObservationMessage.addEventListener("click", () => openFieldObservation("decision"));
ui.addObservationDecision.addEventListener("click", () => openFieldObservation("decision"));
ui.addObservationMission.addEventListener("click", () => openFieldObservation("mission"));
ui.closeObservation.addEventListener("click", () => ui.observation.close());
ui.observation.addEventListener("click", (event) => {
  if (event.target === ui.observation) ui.observation.close();
});
ui.closeMission.addEventListener("click", () => ui.mission.close());
ui.missionBack.addEventListener("click", () => ui.mission.close());
ui.mission.addEventListener("click", (event) => {
  if (event.target === ui.mission) ui.mission.close();
});
restoreFieldObservationLock();
restorePendingFieldObservationInventory();
if (restorePendingAcceptanceAttempt()) showUnresolvedAcceptance();
else loadConfiguration();
