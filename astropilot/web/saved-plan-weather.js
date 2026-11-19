"use strict";
// A recheck describes an archived plan; it never accepts or rewrites a mission.
(() => {
  const instant = value => typeof value === "string" ? Date.parse(value) : NaN;
  const simulated = trust => /simul/i.test(trust?.provider || "");
  function summarize(accepted, payload, previousTrust) {
    const mission = accepted.mission;
    const trust = payload?.weather_trust || payload?.refusal_weather || null;
    const oldTime = instant(previousTrust?.retrieved_at_utc), newTime = instant(trust?.retrieved_at_utc);
    let collection = "La date de collecte précédente n’est pas disponible pour comparaison.";
    if (Number.isFinite(oldTime) && Number.isFinite(newTime)) {
      collection = newTime > oldTime ? "Une nouvelle collecte météo est disponible."
        : newTime === oldTime ? "La date de collecte météo est identique à la précédente."
        : "La collecte reçue est antérieure à la précédente : actualisez à nouveau.";
      if (previousTrust.provider !== trust.provider) collection += " La source météo a changé.";
    }
    const answer = (status, summary) => ({status, summary, trust, collection});
    if (!payload) return answer("unknown", "Actualisation impossible : le plan n’est pas confirmé. Réessayez avant de commencer.");
    if (payload.catalog_key !== accepted.selectedCatalogKey) {
      return answer("unknown", "Cette analyse ne confirme pas le projet du plan enregistré.");
    }
    const id = accepted.acquisitionIntentId || mission.acquisition_intent_id;
    const assessment = (payload.acquisition_intent_assessments || []).find(item => item.acquisition_intent_id === id);
    if (payload.status === "weather_refused" || (assessment?.status === "not_eligible"
        && !(assessment.reason_codes || []).includes("intent_not_targeted_by_project"))) {
      return answer("refused", "Plan non confirmé par la nouvelle analyse. Consultez les facteurs de refus avant de prévoir la séance.");
    }
    const start = instant(mission.window_start), end = instant(mission.window_end);
    const usableWeather = [start, end, newTime].every(Number.isFinite) && start < end
      && trust?.freshness_status === "fresh" && trust?.validation_status === "validated"
      && instant(trust.valid_from) <= start && instant(trust.valid_until) >= end
      && !(Number.isFinite(oldTime) && newTime < oldTime);
    const viable = Array.isArray(payload.viable_acquisition_intent_ids) ? payload.viable_acquisition_intent_ids : [];
    const options = (payload.acquisition_intent_options || []).filter(item => viable.includes(item.acquisition_intent_id));
    const ownOption = options.find(item => item.acquisition_intent_id === id
      && item.filter_type === mission.selected_filter?.filter_type);
    if (payload.status === "no_mission" && payload.acquisition_intent_choice_available === true
        && payload.creation_refusal === "preselection_evidence_cannot_authorize_mission"
        && options.length > 1 && ownOption && assessment?.status === "eligible") {
      if (!usableWeather) return answer("unknown", "Les prévisions disponibles ne permettent pas de confirmer ce plan. Actualisez avant de commencer.");
      const filters = [...new Set(options.map(item => item.filter_type).filter(Boolean))].join(" et ");
      return answer("choice_required", `Choix de filtre à confirmer : ${filters} sont proposés${simulated(trust) ? " dans cette simulation" : ""}. Sélectionnez ${ownOption.filter_type} dans la nouvelle analyse, puis confirmez votre choix. Le plan enregistré reste à revérifier.`);
    }
    if (payload.status !== "available" || payload.selected_acquisition_intent_id !== id
        || payload.selected_filter?.filter_type !== mission.selected_filter?.filter_type) {
      return answer("unknown", "La nouvelle analyse ne confirme pas ce filtre. Vérifiez le choix proposé avant de continuer.");
    }
    if (!usableWeather) {
      return answer("unknown", "Les prévisions disponibles ne permettent pas de confirmer ce plan. Actualisez avant de commencer.");
    }
    if (!(instant(payload.window_start) <= start && instant(payload.window_end) >= end)) {
      return answer("revise", "Le créneau proposé a changé : comparez les nouveaux horaires et confirmez un nouveau plan si nécessaire.");
    }
    if (simulated(trust)) return answer("simulated", "Le plan reste réalisable dans cette simulation ; cela ne confirme pas la météo réelle.");
    if (payload.weather_decision?.admissibility === "caution") {
      return answer("caution", "Le plan reste proposé sous réserve : " + (payload.weather_decision.presentation?.summary || "la validation météo est partielle."));
    }
    if (payload.weather_decision?.admissibility !== "admissible") {
      return answer("unknown", "La validation météo ne permet pas de confirmer ce plan.");
    }
    return answer("favorable", "La nouvelle analyse confirme le filtre et le créneau de pose du plan enregistré.");
  }
  const api = {summarize};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else globalThis.NightMeritSavedPlanWeather = api;
})();
