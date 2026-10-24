"""An explicit choice scopes ranking and durable acceptance, not stored progress."""
from copy import deepcopy

from fastapi.testclient import TestClient
import pytest

from astropilot.app import create_app
from test_orion_discovery import REF, winter_weather


def project(field, intent):
    return {"hours": 0, "target_hours": 3, "imaging_field_id": field,
        "acquisition_intent_targets": [{"acquisition_intent_id": intent, "target_hours": 3}],
        "acquisition_intent_progress": [{"acquisition_intent_id": intent, "acquired_duration_manual": 0}]}


@pytest.fixture
def portfolio(tmp_path, monkeypatch):
    from astro_score import build_durable_tonight_application_service
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    def factory():
        service = build_durable_tonight_application_service()
        service.clock = lambda: REF
        return service
    weather = [winter_weather()]
    client = TestClient(create_app(service_factory=factory,
        weather_provider=lambda *args: weather[0], clock=lambda: REF))
    response = client.put("/v1/configuration", json={
        "site": {"name": "Synthetic", "latitude": 46.888, "longitude": 6.55, "bortle": 4},
        "equipment": {"preset_id": "samyang_183"},
        "projects": {"M42": project("m42", "m42_ha"),
                     "NorthAmerica": project("ngc7000", "ngc7000_ha")}})
    assert response.status_code == 200, response.text
    return client, weather


def test_choice_survives_stronger_competing_project_and_acceptance(portfolio):
    client, _ = portfolio
    before = deepcopy(client.get("/v1/configuration").json()["projects"])
    unrestricted = client.post("/v1/tonight", json={"availability": {"mode": "all_night"}})
    assert unrestricted.status_code == 200, unrestricted.text
    assert unrestricted.json()["catalog_key"] == "NorthAmerica"  # reproduces the switch
    scoped = client.post("/v1/tonight", json={"availability": {"mode": "all_night"}, "selected_project_id": "M42"})
    assert scoped.status_code == 200, scoped.text
    decision = scoped.json()
    assert decision["status"] == "available"
    assert decision["catalog_key"] == "M42"
    assert decision["alternatives"] == []
    selection = {"acceptance_request_id": "selected-orion",
        "decision_id": decision["decision_id"], "source": "primary_recommendation",
        "selected_catalog_key": "NorthAmerica", "acquisition_intent_id": "ngc7000_ha",
        "selected_at": REF.isoformat()}
    for source in ("primary_recommendation", "alternative", "other_evaluated_target"):
        rejected = client.post("/v1/decision-selections", json={
            **selection, "acceptance_request_id": "wrong-" + source, "source": source})
        assert rejected.status_code == 409, rejected.text
    selection.update(acceptance_request_id="selected-orion-correct", selected_catalog_key="M42",
                     acquisition_intent_id="m42_ha")
    accepted = client.post("/v1/decision-selections", json=selection)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert client.get("/v1/configuration").json()["projects"] == before


def test_changed_weather_never_substitutes_another_target(portfolio):
    client, weather = portfolio
    weather[0] = winter_weather(clouds=100)
    response = client.post("/v1/tonight", json={"availability": {"mode": "all_night"}, "selected_project_id": "M42"})
    assert response.status_code == 200, response.text
    assert response.json()["status"] != "available"
    assert response.json().get("catalog_key") in (None, "M42")
    assert response.json()["alternatives"] == []
    assert client.get("/v1/accepted-mission/current").json() is None


@pytest.mark.parametrize("selection", ["missing", "", 1])
def test_invalid_choice_is_not_silently_ignored(portfolio, selection):
    client, _ = portfolio
    response = client.post("/v1/tonight", json={"availability": {"mode": "all_night"}, "selected_project_id": selection})
    assert response.status_code == 422
