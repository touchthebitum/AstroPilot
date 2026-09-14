from pathlib import Path
import re

from fastapi.testclient import TestClient

from astropilot.app import create_app


class UnusedService:
    def evaluate(self, **kwargs):
        raise AssertionError("the UI shell must not evaluate a decision")


def make_client():
    return TestClient(
        create_app(
            service_factory=lambda: UnusedService(),
            weather_provider=lambda lat, lon: object(),
            profile_provider=lambda: {},
        )
    )


def test_root_serves_tonight_classic_ui():
    response = make_client().get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Ce soir — AstroPilot" in response.text
    assert "Photographier cette cible" in response.text
    assert "Données météo par Open-Meteo.com" in response.text
    assert 'id="weather-trust"' in response.text
    assert 'id="classic-weather-coverage"' in response.text
    assert 'id="classic-weather-status"' in response.text
    assert "Fraîcheur météo" in response.text
    assert "Âge du snapshot" not in response.text
    assert 'id="mission-dialog"' in response.text
    assert 'id="onboarding"' in response.text
    assert 'id="site-step"' in response.text
    assert 'id="equipment-step"' in response.text
    assert 'id="projects-step"' in response.text
    assert 'id="review-step"' in response.text
    assert 'id="availability-step"' in response.text
    assert 'id="availability-form"' in response.text
    assert 'id="availability-error"' in response.text
    assert 'id="availability-site-timezone"' in response.text
    assert 'id="availability-timezone-warning"' in response.text
    assert 'id="request-recommendation"' in response.text
    assert 'id="edit-availability"' in response.text
    assert 'id="availability-duration"' in response.text
    assert 'id="availability-start"' in response.text
    assert 'id="availability-end"' in response.text
    for mode in (
        "all_night",
        "duration",
        "start_and_duration",
        "until",
        "fixed_window",
    ):
        assert f'value="{mode}"' in response.text
    availability_radios = re.findall(
        r'<input[^>]+name="availability-mode"[^>]*>',
        response.text,
    )
    assert len(availability_radios) == 5
    assert all("checked" not in radio for radio in availability_radios)
    assert 'id="configuration-error"' in response.text
    assert 'id="configuration-recover"' in response.text
    assert 'id="configuration-recovery-confirmation"' in response.text
    assert 'id="configuration-recovery-cancel"' in response.text
    assert 'id="configuration-recovery-confirm"' in response.text
    assert 'id="edit-configuration"' in response.text
    assert "Modifier ma configuration" in response.text
    assert "Site d’observation" in response.text
    assert "Votre matériel" in response.text
    assert "Aucun projet pour l’instant" in response.text
    assert "Configuration enregistrée" in response.text
    for field_id in (
        "custom-optics-manufacturer",
        "custom-optics-model",
        "custom-focal-length-mm",
        "custom-aperture-mm",
        "custom-f-ratio",
        "custom-camera-manufacturer",
        "custom-camera-model",
        "custom-pixel-size-um",
        "custom-sensor-width-px",
        "custom-sensor-height-px",
        "custom-monochrome",
    ):
        assert f'id="{field_id}"' in response.text
    assert 'id="recommendation-confidence-value"' in response.text
    assert "Fiabilité de la recommandation" in response.text
    assert 'id="alternatives-section"' in response.text
    assert 'id="alternatives-list"' in response.text
    assert 'src="/ui/app.js"' in response.text


def test_tonight_ui_assets_are_served():
    client = make_client()

    stylesheet = client.get("/ui/styles.css")
    script = client.get("/ui/app.js")
    page = client.get("/")

    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert 'fetch("/v1/configuration"' in script.text
    assert 'method: "PUT"' in script.text
    assert "fetch(\"/v1/tonight\"" in script.text
    assert 'fetch("/v1/decision-selections"' in script.text
    assert 'fetch("/v1/configuration/recover"' in script.text
    assert script.text.count("fetch(") == 5
    assert script.text.rstrip().endswith("loadConfiguration();")
    assert "body: JSON.stringify({})," not in script.text
    assert "collectAvailabilityPayload" in script.text
    assert "hoursToIsoDuration" in script.text
    assert 'return "PT1H30M"' not in script.text
    assert "normalizeLocalDateTime" in script.text
    assert "localDateTimeToRfc3339" not in script.text
    assert "getTimezoneOffset()" not in script.text
    assert 'mode: "all_night"' in script.text
    assert 'mode: "duration"' in script.text
    assert 'mode: "start_and_duration"' in script.text
    assert 'mode: "until"' in script.text
    assert 'mode: "fixed_window"' in script.text
    assert "availability.duration =" in script.text
    assert "availability.start_local =" in script.text
    assert "availability.end_local =" in script.text
    assert "JSON.stringify({ availability })" in script.text
    assert "state.availability" in script.text
    assert "requestingRecommendation" in script.text
    assert "invalid_session_availability_fields" in script.text
    assert "session_availability_timezone_required" in script.text
    assert "session_availability_duration_must_be_positive" in script.text
    assert "session_availability_end_must_follow_start" in script.text
    assert 'setView("availability")' in script.text
    assert 'ui.editAvailability.addEventListener("click"' in script.text
    assert "loadTonight(state.availability)" in script.text
    configuration_payload = script.text.split(
        "function configurationPayload()",
        1,
    )[1].split("function showConfigurationError", 1)[0]
    assert "availability" not in configuration_payload
    assert ".reset()" not in script.text
    assert 'setView("site")' in script.text
    assert 'setView("availability")' in script.text
    assert 'projects: {},' in script.text
    assert "expected_revision" in script.text
    assert "profile_revision" in script.text
    assert 'detail?.code === "configuration_revision_conflict"' in script.text
    assert "await loadConfiguration({ afterConflict: true })" in script.text
    assert "retryConfigurationSave" not in script.text
    assert "navigator.geolocation.getCurrentPosition" in script.text
    assert "La saisie manuelle reste disponible" in script.text
    assert "choice.name" in script.text
    assert "choice.id" in script.text
    assert "renderReview" in script.text
    assert "prefillConfiguration" in script.text
    assert "configuration_invalid_site" in script.text
    assert "configuration_invalid_bortle" in script.text
    assert "configuration_invalid_equipment" in script.text
    assert "configuration_invalid_custom_equipment" in script.text
    assert "configuration_invalid_project" in script.text
    assert "configuration_corrupt" in script.text
    assert "configuration_persistence_error" in script.text
    for field_name in (
        "optics_manufacturer",
        "optics_model",
        "focal_length_mm",
        "aperture_mm",
        "f_ratio",
        "camera_manufacturer",
        "camera_model",
        "pixel_size_um",
        "sensor_width_px",
        "sensor_height_px",
        "monochrome",
    ):
        assert field_name in script.text
    assert 'const PENDING_ACCEPTANCE_STORAGE_KEY = "astropilot.pendingAcceptance"' in script.text
    assert "currentDecision" in script.text
    assert "target_common_name" in script.text
    assert "weather_trust" in script.text
    assert "weather_decision" in script.text
    assert 'detail?.code === "weather_invalid"' in script.text
    assert 'detail?.code === "weather_insufficient"' in script.text
    assert 'detail?.code === "weather_stale"' in script.text
    assert 'detail?.code === "weather_window_uncovered"' not in script.text
    assert "weatherTrust.snapshot_age_minutes" in script.text
    assert "weatherTrust.valid_from" in script.text
    assert "weatherTrust.valid_until" in script.text
    assert "weatherTrust.retrieved_at_utc" in script.text
    assert 'renderWeatherTrust(weatherTrust, weatherDecision, "classic")' in script.text
    assert 'renderWeatherTrust(weatherTrust, weatherDecision, "mission")' not in script.text
    assert "weatherDecision?.presentation?.label" in script.text
    assert "weatherDecision?.presentation?.summary" in script.text
    assert 'payload.status === "weather_refused"' in script.text
    assert "Validation météo partielle" not in script.text
    assert "Météo validée pour cette décision" not in script.text
    assert "Mission météo non confirmée" not in script.text
    assert "ne peut pas confirmer une mission fiable" not in script.text
    assert "weatherDecision.reasons" not in script.text
    assert "provider_reliability_unavailable" not in script.text
    assert "selected_window_uncovered" not in script.text
    assert "timeZone," in script.text
    assert "Date.now(" not in script.text
    assert "Récupérées il y a" in script.text
    assert "no_productive_window" in script.text
    assert 'detail?.code === "decision_invalid"' in script.text
    assert 'detail?.code === "location_timezone_unresolved"' in script.text
    assert 'payload?.error === "user_profile_unavailable"' in script.text
    assert "ASTROPILOT_DATA_DIR" not in script.text
    assert "user_profile.json" not in script.text
    assert "weatherTrust.timezone" in script.text
    assert "productive_hours ?? decision.recommended_hours" in script.text
    assert "showModal()" in script.text
    assert 'source: "primary_recommendation"' in script.text
    assert 'source: "alternative"' in script.text
    assert "selected_catalog_key: selectedCatalogKey" in script.text
    assert "decision_id: expectedDecisionId" in script.text
    assert "payload.mission" in script.text
    assert "acceptedMission" in script.text
    assert "acceptingRecommendation" in script.text
    acceptance_function = script.text.split(
        "async function acceptRecommendation(",
        1,
    )[1].split("async function loadTonight", 1)[0]
    acceptance_request = script.text.split(
        "function acceptanceAttempt(intent)",
        1,
    )[1].split("function clearPendingAcceptanceAttempt", 1)[0]
    assert "selection_id" not in acceptance_request
    assert "mission_id" not in acceptance_request
    assert "crypto.randomUUID()" in acceptance_request
    assert "acceptance_request_id" in acceptance_request
    assert "body: JSON.stringify(attempt)" in acceptance_function
    assert "decision_context_stale" in script.text
    assert "decision_context_not_found" in script.text
    assert "selected_target_not_primary_recommendation" in script.text
    assert "selected_target_not_exposed_alternative" in script.text
    assert "acceptance_lineage_conflict" in script.text
    assert "decision_lineage_persistence_error" in script.text
    render_decision = script.text.split("function renderDecision(decision)", 1)[1].split("const customEquipmentFields", 1)[0]
    assert "renderMission(decision)" not in render_decision
    assert "showModal()" not in render_decision
    assert "resetMissionPresentation" in script.text
    assert "decision.alternatives" in script.text
    assert ".slice(0, 2)" in script.text
    render_alternatives = script.text.split(
        "function renderAlternatives(decision)",
        1,
    )[1].split("function renderDecision(decision)", 1)[0]
    assert "shortlist_entries" not in render_alternatives
    assert 'alternative.target_decision_status === "viable"' in render_alternatives
    assert "alternative.catalog_key" in render_alternatives
    assert "reason?.rendered?.classic_text" in script.text
    assert "reason?.message" in script.text
    assert "Photographier ${displayTarget}" in render_alternatives
    assert "expectedDecisionId: decision.decision_id" in render_alternatives
    assert "selectedCatalogKey: alternative.catalog_key" in render_alternatives
    assert "disableAcceptanceControls" in script.text
    assert "clearAlternatives" in script.text
    assert "ui.alternativesList.replaceChildren()" in script.text
    assert "state.currentDecision?.decision_id !== expectedDecisionId" in acceptance_function
    assert "payload.catalog_key === selectedCatalogKey" in acceptance_function
    assert 'source === "alternative"' in acceptance_function
    assert "AstroPilot recommandait ${decision.target || decision.catalog_key}. Vous avez choisi ${selectedTarget}." in acceptance_function
    assert 'text("#target-name"' not in acceptance_function
    assert 'text("#recommendation"' not in acceptance_function
    assert "recommendation_confidence" in script.text
    assert "Number.isFinite" in script.text
    assert "Math.round(value * 100)" in script.text
    assert "value < 0 || value > 1" in script.text
    assert 'return "Non disponible"' in script.text
    assert "renderMission(mission)" in acceptance_function
    assert "decision_score" not in script.text
    assert "final_score" not in script.text
    assert "execution" not in page.text.lower()
    assert "outcome" not in page.text.lower()
    assert 'source: "declined"' not in script.text
    assert "other_evaluated_target" not in script.text


def test_acceptance_attempt_generates_identity_and_timestamp_once():
    script = make_client().get("/ui/app.js").text
    helper = script.split(
        "function acceptanceAttempt(intent)",
        1,
    )[1].split("function clearPendingAcceptanceAttempt", 1)[0]

    assert "state.pendingAcceptanceAttempt" in helper
    assert "sameAcceptanceIntent(existing, intent)" in helper
    assert "return existing" in helper
    assert "crypto.randomUUID()" in helper
    assert "selected_at: new Date().toISOString()" in helper
    assert helper.count("crypto.randomUUID()") == 1
    assert helper.count("new Date().toISOString()") == 1
    assert "Object.freeze" in helper
    assert "persistPendingAcceptanceAttempt(attempt)" in helper
    assert "selection_id" not in helper
    assert "mission_id" not in helper


def test_uncertain_acceptance_retry_reuses_exact_pending_payload():
    script = make_client().get("/ui/app.js").text
    acceptance = script.split(
        "async function acceptRecommendation(",
        1,
    )[1].split("async function loadTonight", 1)[0]
    uncertain = acceptance.split("} catch (_error) {", 1)[1].split(
        "} finally {", 1
    )[0]

    assert "attempt = attemptOverride || acceptanceAttempt({" in acceptance
    assert "decision_id: expectedDecisionId" in acceptance
    assert "source," in acceptance
    assert "selected_catalog_key: selectedCatalogKey" in acceptance
    assert "body: JSON.stringify(attempt)" in acceptance
    assert "clearPendingAcceptanceAttempt()" not in uncertain
    assert "showUnresolvedAcceptance()" in uncertain
    assert "Le résultat de votre sélection n’a pas pu être confirmé" in script
    assert "restoreAcceptanceControls()" in acceptance


def test_acceptance_attempt_clears_only_after_definite_outcome():
    script = make_client().get("/ui/app.js").text
    acceptance = script.split(
        "async function acceptRecommendation(",
        1,
    )[1].split("async function loadTonight", 1)[0]
    definite_failure = acceptance.split("if (!response.ok) {", 1)[1].split(
        "const mission = payload.mission", 1
    )[0]
    after_validation = acceptance.split(
        "if (!validAcceptedMission) {", 1
    )[1]
    uncertain_success, success = after_validation.split("return;\n    }", 1)
    success = success.split("state.acceptedMission = {", 1)[0]

    assert "clearPendingAcceptanceAttempt()" in definite_failure
    assert "clearPendingAcceptanceAttempt()" in success
    assert "clearPendingAcceptanceAttempt()" not in uncertain_success
    assert 'code === "acceptance_request_conflict"' in script
    assert "pendingAcceptanceAttempt" in script
    assert "button.dataset.acceptanceSource === pending.source" in script
    assert "button.dataset.catalogKey === pending.selected_catalog_key" in script


def test_unresolved_acceptance_is_persisted_before_network_submission():
    script = make_client().get("/ui/app.js").text
    attempt = script.split(
        "function acceptanceAttempt(intent)",
        1,
    )[1].split("function clearPendingAcceptanceAttempt", 1)[0]
    acceptance = script.split(
        "async function acceptRecommendation(",
        1,
    )[1].split("async function loadTonight", 1)[0]
    persistence = script.split(
        "function persistPendingAcceptanceAttempt(attempt)",
        1,
    )[1].split("function restorePendingAcceptanceAttempt", 1)[0]

    assert 'const PENDING_ACCEPTANCE_STORAGE_KEY = "astropilot.pendingAcceptance"' in script
    assert 'version: PENDING_ACCEPTANCE_STORAGE_VERSION' in persistence
    assert 'state: "unresolved"' in persistence
    for field in (
        "acceptance_request_id",
        "decision_id",
        "source",
        "selected_catalog_key",
        "selected_at",
    ):
        assert field in attempt
    assert script.index("persistPendingAcceptanceAttempt(attempt)") < (
        script.index('fetch("/v1/decision-selections"')
    )
    assert "selection_id" not in attempt
    assert "mission_id" not in attempt


def test_startup_restores_exact_retry_command_without_fabricating_success():
    client = make_client()
    page = client.get("/").text
    script = client.get("/ui/app.js").text
    restore = script.split(
        "function restorePendingAcceptanceAttempt()",
        1,
    )[1].split("function showUnresolvedAcceptance", 1)[0]
    startup = script.rsplit("\n", 4)

    assert 'id="pending-acceptance-state"' in page
    assert 'id="retry-pending-acceptance"' in page
    assert "Réessayer la sélection" in page
    assert "parsePendingAcceptance" in restore
    assert "Object.freeze" in restore
    assert "state.pendingAcceptanceAttempt = Object.freeze(attempt)" in restore
    assert "renderMission" not in restore
    assert "acceptedMission" not in restore
    assert "Mission enregistrée" not in restore
    assert any("restorePendingAcceptanceAttempt()" in line for line in startup)


def test_restored_retry_reuses_exact_persisted_payload_and_timestamp():
    script = make_client().get("/ui/app.js").text
    retry = script.split(
        "async function retryPendingAcceptance()",
        1,
    )[1].split("async function acceptRecommendation", 1)[0]
    acceptance = script.split(
        "async function acceptRecommendation(",
        1,
    )[1].split("async function loadTonight", 1)[0]

    assert "const attempt = state.pendingAcceptanceAttempt" in retry
    assert "attemptOverride: attempt" in retry
    assert "acceptance_request_id" not in retry
    assert "crypto.randomUUID" not in retry
    assert "new Date" not in retry
    assert "attempt = attemptOverride" in acceptance
    assert "body: JSON.stringify(attempt)" in acceptance


def test_unresolved_acceptance_guards_navigation_and_new_recommendations():
    script = make_client().get("/ui/app.js").text
    guard = script.split(
        "function guardUnresolvedAcceptance()",
        1,
    )[1].split("function editConfiguration", 1)[0]
    load_tonight = script.split(
        "async function loadTonight(availability)",
        1,
    )[1].split('document.querySelector("#site-next")', 1)[0]

    assert "showUnresolvedAcceptance()" in guard
    assert "if (guardUnresolvedAcceptance()) return" in load_tonight
    assert load_tonight.index("if (guardUnresolvedAcceptance()) return") < (
        load_tonight.index('fetch("/v1/tonight"')
    )
    assert load_tonight.index("if (guardUnresolvedAcceptance()) return") < (
        load_tonight.index("clearAcceptedMission()")
    )
    assert script.count("guardUnresolvedAcceptance()") >= 6
    assert "ui.editConfiguration.addEventListener" in script
    assert "ui.editAvailability.addEventListener" in script
    assert "ui.refresh.addEventListener" in script


def test_pending_storage_clears_only_after_definite_result():
    script = make_client().get("/ui/app.js").text
    acceptance = script.split(
        "async function acceptRecommendation(",
        1,
    )[1].split("async function loadTonight", 1)[0]
    definite_failure = acceptance.split("if (!response.ok) {", 1)[1].split(
        "const mission = payload.mission", 1
    )[0]
    incomplete = acceptance.split("if (!validAcceptedMission) {", 1)[1].split(
        "return;\n    }", 1
    )[0]
    success = acceptance.split("if (!validAcceptedMission) {", 1)[1].split(
        "return;\n    }", 1
    )[1].split("state.acceptedMission = {", 1)[0]
    uncertain = acceptance.split("} catch (_error) {", 1)[1].split(
        "} finally {", 1
    )[0]

    assert "clearPendingAcceptanceAttempt()" in definite_failure
    assert "clearPendingAcceptanceAttempt()" in success
    assert "clearPendingAcceptanceAttempt()" not in incomplete
    assert "clearPendingAcceptanceAttempt()" not in uncertain
    assert "showUnresolvedAcceptance" in incomplete
    assert "showUnresolvedAcceptance" in uncertain
    assert 'code === "acceptance_request_conflict"' in script


def test_malformed_storage_fails_closed_and_storage_is_never_mission_authority():
    script = make_client().get("/ui/app.js").text
    parser = script.split(
        "function parsePendingAcceptance(raw)",
        1,
    )[1].split("function persistPendingAcceptanceAttempt", 1)[0]
    restore = script.split(
        "function restorePendingAcceptanceAttempt()",
        1,
    )[1].split("function showUnresolvedAcceptance", 1)[0]

    assert "JSON.parse(raw)" in parser
    assert "Object.keys" in parser
    assert "return null" in parser
    assert "pendingAcceptanceStorageInvalid = true" in restore
    assert "localStorage.removeItem" not in restore
    assert "renderMission" not in parser + restore
    assert "acceptedMission" not in parser + restore
    assert "selection_id" not in parser
    assert "mission_id" not in parser


def test_availability_uses_read_only_site_timezone_and_local_wall_clock_transport():
    client = make_client()
    page = client.get("/").text
    script = client.get("/ui/app.js").text

    assert "Fuseau du site" in page
    assert "Le fuseau horaire du site ne peut pas être déterminé." in page
    assert "state.configuration?.site?.timezone" in script
    assert "Fuseau du site : ${timezone}" in script

    normalization = script.split(
        "function normalizeLocalDateTime(value)",
        1,
    )[1].split("function availabilityInputError", 1)[0]
    assert "return value" in normalization
    assert "new Date(" not in normalization
    assert "getTimezoneOffset" not in normalization
    assert '"Z"' not in normalization

    collector = script.split(
        "function collectAvailabilityPayload()",
        1,
    )[1].split("function updateAvailabilityFields()", 1)[0]
    assert "availability.start_local = start" in collector
    assert "availability.end_local = end" in collector
    assert "availability.start =" not in collector
    assert "availability.end =" not in collector
    assert "availability.timezone" not in collector
    assert "timezone:" not in collector
    assert "new Date(" not in collector
    assert "end <= start" in collector
    assert 'return { mode: "all_night" }' in collector
    assert 'const availability = { mode: "duration" }' in collector


def test_wall_clock_modes_fail_closed_without_a_site_timezone():
    script = make_client().get("/ui/app.js").text

    renderer = script.split(
        "function renderAvailabilityTimezone()",
        1,
    )[1].split("function hoursToIsoDuration", 1)[0]
    for mode in ("start_and_duration", "until", "fixed_window"):
        assert f'"{mode}"' in script
    assert "for (const mode of wallClockAvailabilityModes)" in renderer
    assert "input.disabled = !timezone" in renderer
    assert "availability-timezone-warning" in script
    assert "availability_timezone_unresolved" in script
    assert 'location_timezone_unresolved: "site"' in script
    assert "Vérifiez les coordonnées du site" in script


def test_site_change_invalidates_only_stale_site_time_assumptions():
    script = make_client().get("/ui/app.js").text

    invalidation = script.split(
        "function invalidateAvailabilityForSiteChange(previousSite, nextSite)",
        1,
    )[1].split("async function loadConfiguration", 1)[0]
    assert "previousSite.latitude === nextSite.latitude" in invalidation
    assert "previousSite.longitude === nextSite.longitude" in invalidation
    assert "previousSite.timezone === nextSite.timezone" in invalidation
    assert 'document.querySelector("#availability-start").value = ""' in invalidation
    assert 'document.querySelector("#availability-end").value = ""' in invalidation
    assert "state.availability = null" in invalidation
    assert "if (sameSite) return" in invalidation
    assert script.count("invalidateAvailabilityForSiteChange(") >= 3


def test_site_timezone_and_dst_errors_have_controlled_french_messages():
    script = make_client().get("/ui/app.js").text

    messages = script.split(
        "function backendAvailabilityMessage(detail)",
        1,
    )[1].split("const partialMessages", 1)[0]
    assert "session_availability_local_datetime_invalid" in messages
    assert "Vérifiez la date et l’heure saisies." in messages
    assert "session_availability_local_time_nonexistent" in messages
    assert "Cette heure locale n’existe pas" in messages
    assert "session_availability_local_time_ambiguous" in messages
    assert "Cette heure locale est ambiguë" in messages
    assert "session_availability_mixed_time_contract" in messages
    assert "Vérifiez votre disponibilité avant de réessayer." in messages


def test_existing_projects_are_preserved_by_the_configuration_wizard():
    client = make_client()

    page = client.get("/").text
    script = client.get("/ui/app.js").text

    assert 'id="zero-projects"' in page
    assert 'id="zero-projects-wrap"' in page
    assert "Aucun projet pour l’instant" in page

    render_projects = script.split(
        "function renderProjects()",
        1,
    )[1].split("function prefillConfiguration()", 1)[0]
    assert "Projets actuellement conservés" in render_projects
    assert "Vos projets existants sont conservés." in render_projects
    assert "Leur création et leur modification seront disponibles dans une prochaine version bêta." in render_projects
    assert "Changer votre site ou votre matériel ne les supprimera pas." in render_projects
    assert "zeroProjectsControl.hidden = Boolean(entries.length)" in render_projects
    assert "project.id" not in render_projects
    assert "project_id" not in render_projects

    projects_next = script.split(
        'document.querySelector("#projects-next").addEventListener("click", () => {',
        1,
    )[1].split("});", 1)[0]
    assert "state.configurationDraft.projects = {}" not in projects_next
    assert "renderReview()" in projects_next

    payload = script.split(
        "function configurationPayload()",
        1,
    )[1].split("function showConfigurationError", 1)[0]
    assert "projects: copyProjects(state.configurationDraft.projects)" in payload
    assert "expected_revision" in payload

    review = script.split(
        "function renderReview()",
        1,
    )[1].split("function configurationPayload()", 1)[0]
    assert "Object.keys(state.configurationDraft.projects || {}).length" in review
    assert "conservé" in review
    assert "Aucun projet pour l’instant" in review

    initialization = script.split(
        "function initializeConfiguration(payload)",
        1,
    )[1].split("async function loadConfiguration", 1)[0]
    assert "state.configurationDraft = draftFromConfiguration(payload)" in initialization
    assert "prefillConfiguration()" in initialization

    conflict = script.split(
        "async function loadConfiguration({ afterConflict = false } = {})",
        1,
    )[1].split("async function recoverConfiguration()", 1)[0]
    assert "initializeConfiguration(payload)" in conflict
    assert "renderReview()" in conflict


def test_new_profile_can_keep_the_explicit_zero_project_state():
    script = make_client().get("/ui/app.js").text

    assert "projects: {}," in script
    render_projects = script.split(
        "function renderProjects()",
        1,
    )[1].split("function prefillConfiguration()", 1)[0]
    assert "zeroProjects.checked = true" in render_projects
    assert "zeroProjects.disabled = true" in render_projects


def test_corrupt_configuration_alone_exposes_explicit_recovery():
    script = make_client().get("/ui/app.js").text

    error_renderer = script.split(
        "function showConfigurationError(message, { code = null } = {})",
        1,
    )[1].split("function initializeConfiguration", 1)[0]
    assert 'state.configurationErrorCode = code' in error_renderer
    assert 'code !== "configuration_corrupt"' in error_renderer
    assert "ui.configurationRecover.hidden" in error_renderer

    loader = script.split(
        "async function loadConfiguration({ afterConflict = false } = {})",
        1,
    )[1].split("async function recoverConfiguration()", 1)[0]
    assert 'code === "configuration_corrupt"' in loader
    assert 'showConfigurationError(message, { code })' in loader
    assert 'showConfigurationError("AstroPilot ne parvient pas à charger la configuration.' in loader
    assert "configuration_corrupt" in loader
    assert "location_timezone_unresolved" not in error_renderer
    assert "configuration_persistence_error" not in error_renderer


def test_configuration_retry_remains_non_destructive():
    script = make_client().get("/ui/app.js").text

    retry_handler = script.split(
        'ui.configurationRetry.addEventListener("click",',
        1,
    )[1].split(";", 1)[0]
    assert "loadConfiguration" in retry_handler
    assert "recoverConfiguration" not in retry_handler
    assert "/v1/configuration/recover" not in retry_handler


def test_recovery_requires_confirmation_and_cancel_sends_no_request():
    page = make_client().get("/").text
    script = make_client().get("/ui/app.js").text

    assert "Réinitialiser ma configuration" in page
    assert "votre site, votre matériel et vos projets" in page
    assert "Une copie locale des données illisibles sera conservée" in page
    assert "Annuler" in page
    assert "quarantine" not in page.lower()
    assert "user_profile.json" not in page

    open_handler = script.split(
        'ui.configurationRecover.addEventListener("click",',
        1,
    )[1].split(";", 1)[0]
    assert "showRecoveryConfirmation" in open_handler
    assert "recoverConfiguration" not in open_handler
    assert "fetch(" not in open_handler

    cancel_handler = script.split(
        'ui.configurationRecoveryCancel.addEventListener("click",',
        1,
    )[1].split(";", 1)[0]
    assert "hideRecoveryConfirmation" in cancel_handler
    assert "recoverConfiguration" not in cancel_handler
    assert "fetch(" not in cancel_handler


def test_recovery_posts_once_and_prevents_duplicate_submission():
    script = make_client().get("/ui/app.js").text
    recovery = script.split(
        "async function recoverConfiguration()",
        1,
    )[1].split("async function saveConfiguration()", 1)[0]

    assert 'state.configurationErrorCode !== "configuration_corrupt"' in recovery
    assert "if (state.recoveringConfiguration) return" in recovery
    assert "state.recoveringConfiguration = true" in recovery
    assert "ui.configurationRecoveryConfirm.disabled = true" in recovery
    assert recovery.count('fetch("/v1/configuration/recover"') == 1
    assert 'method: "POST"' in recovery
    assert "body:" not in recovery
    assert "state.recoveringConfiguration = false" in recovery
    assert "ui.configurationRecoveryConfirm.disabled = false" in recovery


def test_recovery_responses_preserve_authoritative_state_and_fail_closed():
    script = make_client().get("/ui/app.js").text
    recovery = script.split(
        "async function recoverConfiguration()",
        1,
    )[1].split("async function saveConfiguration()", 1)[0]

    assert "response.ok && payload.configured === false" in recovery
    assert "initializeConfiguration(payload)" in recovery
    assert 'setView("site")' in recovery
    assert 'detail?.code === "configuration_recovery_conflict"' in recovery
    assert "await loadConfiguration()" in recovery
    assert 'detail?.code === "configuration_recovery_unavailable"' in recovery
    assert "La réinitialisation est temporairement indisponible" in recovery
    assert "Le résultat de la réinitialisation n’a pas pu être confirmé" in recovery
    assert 'showConfigurationError(message, { code: "configuration_corrupt" })' in recovery
    assert "supprim" not in recovery.lower()
    assert "quarantine" not in recovery.lower()
    assert "ASTROPILOT_DATA_DIR" not in recovery


def test_recovered_projection_reuses_first_run_initialization():
    script = make_client().get("/ui/app.js").text
    initializer = script.split(
        "function initializeConfiguration(payload)",
        1,
    )[1].split("async function loadConfiguration", 1)[0]
    loader = script.split(
        "async function loadConfiguration({ afterConflict = false } = {})",
        1,
    )[1].split("async function recoverConfiguration()", 1)[0]
    recovery = script.split(
        "async function recoverConfiguration()",
        1,
    )[1].split("async function saveConfiguration()", 1)[0]

    assert "state.configuration = payload" in initializer
    assert "state.configurationDraft = draftFromConfiguration(payload)" in initializer
    assert "prefillConfiguration()" in initializer
    assert "renderAvailabilityTimezone()" in initializer
    assert "initializeConfiguration(payload)" in loader
    assert "initializeConfiguration(payload)" in recovery
    assert 'setView("site")' in recovery


def test_web_assets_are_declared_as_package_data():
    project = Path(__file__).parents[2]
    pyproject = (project / "pyproject.toml").read_text()

    assert '"web/*"' in pyproject
