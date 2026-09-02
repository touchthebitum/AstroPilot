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
    assert "confidence-value" not in response.text
    assert 'src="/ui/app.js"' in response.text


def test_tonight_ui_assets_are_served():
    client = make_client()

    stylesheet = client.get("/ui/styles.css")
    script = client.get("/ui/app.js")

    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert script.status_code == 200
    assert "fetch(\"/v1/tonight\"" in script.text
    assert script.text.count("fetch(") == 1
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
    assert "Un profil utilisateur valide est requis" in script.text
    assert "ASTROPILOT_DATA_DIR et user_profile.json" in script.text
    assert "weatherTrust.timezone" in script.text
    assert "productive_hours ?? decision.recommended_hours" in script.text
    assert "showModal()" in script.text


def test_web_assets_are_declared_as_package_data():
    project = Path(__file__).parents[2]
    pyproject = (project / "pyproject.toml").read_text()

    assert '"web/*"' in pyproject
