from pathlib import Path

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
    assert "Voir ma mission" in response.text
    assert "Données météo par Open-Meteo.com" in response.text
    assert 'id="weather-trust"' in response.text
    assert 'id="classic-weather-coverage"' in response.text
    assert 'id="mission-weather-coverage"' in response.text
    assert 'id="classic-weather-status"' in response.text
    assert 'id="mission-weather-status"' in response.text
    assert "Fraîcheur météo" in response.text
    assert "Âge du snapshot" not in response.text
    assert 'id="mission-dialog"' in response.text
    assert 'id="onboarding"' in response.text
    assert 'id="site-step"' in response.text
    assert 'id="equipment-step"' in response.text
    assert 'id="projects-step"' in response.text
    assert 'id="review-step"' in response.text
    assert 'id="availability-step"' in response.text
    assert 'id="configuration-error"' in response.text
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
    assert "confidence-value" not in response.text
    assert 'src="/ui/app.js"' in response.text


def test_tonight_ui_assets_are_served():
    client = make_client()

    stylesheet = client.get("/ui/styles.css")
    script = client.get("/ui/app.js")

    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert 'fetch("/v1/configuration"' in script.text
    assert 'method: "PUT"' in script.text
    assert "fetch(\"/v1/tonight\"" in script.text
    assert script.text.count("fetch(") == 3
    assert script.text.rstrip().endswith("loadConfiguration();")
    assert "body: JSON.stringify({})," not in script.text
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
    assert "localStorage" not in script.text
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
    assert 'renderWeatherTrust(weatherTrust, weatherDecision, "mission")' in script.text
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


def test_web_assets_are_declared_as_package_data():
    project = Path(__file__).parents[2]
    pyproject = (project / "pyproject.toml").read_text()

    assert '"web/*"' in pyproject
