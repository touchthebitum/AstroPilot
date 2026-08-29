"use strict";

const ui = Object.freeze({
  loading: document.querySelector("#loading-state"),
  message: document.querySelector("#message-state"),
  decision: document.querySelector("#decision"),
  refresh: document.querySelector("#refresh"),
  retry: document.querySelector("#message-retry"),
  mission: document.querySelector("#mission-dialog"),
  openMission: document.querySelector("#open-mission"),
  closeMission: document.querySelector("#close-mission"),
  missionBack: document.querySelector("#mission-back"),
});

const state = { currentDecision: null };

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
  ui.loading.hidden = view !== "loading";
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
  if (weatherTrust?.validation_status === "validated") {
    const retrieved = clock(weatherTrust.retrieved_at_utc);
    const retrieval = retrieved ? ` · récupérées à ${retrieved}` : "";
    const age = Number.isFinite(Number(weatherTrust.snapshot_age_minutes))
      ? ` · âge ${Number(weatherTrust.snapshot_age_minutes).toLocaleString("fr-CH")} min`
      : "";
    text("#weather-trust", `${weatherTrust.provider} · ${weatherTrust.timezone} · réponse fraîche · ${weatherTrust.hour_count} h couvertes${age}${retrieval}`);
  } else {
    text("#weather-trust", "Provenance météo non disponible.");
  }

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

async function loadTonight() {
  show("loading");
  ui.refresh.disabled = true;
  state.currentDecision = null;

  try {
    const response = await fetch("/v1/tonight", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const payload = await response.json().catch(() => ({}));

    if (!response.ok) {
      const [title, body] = normalizeError(response, payload);
      showMessage(title, body, { kicker: response.status === 422 ? "Entrée invalide" : "Service indisponible" });
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

ui.refresh.addEventListener("click", loadTonight);
ui.retry.addEventListener("click", loadTonight);
ui.openMission.addEventListener("click", () => {
  if (state.currentDecision) ui.mission.showModal();
});
ui.closeMission.addEventListener("click", () => ui.mission.close());
ui.missionBack.addEventListener("click", () => ui.mission.close());
ui.mission.addEventListener("click", (event) => {
  if (event.target === ui.mission) ui.mission.close();
});
loadTonight();
