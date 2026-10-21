"""Discovery is a physical preselection, never invented portfolio capacity."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest

from astropilot.app import create_app
from astropilot.project_templates import project_templates
from test_clean_machine_all_night_regression import _weather_snapshot

REF = datetime(2026, 8, 29, 18, tzinfo=timezone.utc)
HA = "baader_ha_highspeed_6_5nm"


def profile():
    return {"location": {"name": "Buttes", "latitude": 46.888, "longitude": 6.55,
                         "timezone": "Europe/Zurich"},
            "preferences": {"bortle": 4}, "active_equipment": "samyang_183",
            "available_equipment": ["samyang_183"], "projects": {}, "sessions": []}


def client_for(tmp_path, monkeypatch, *, saved=None, weather=None):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    return TestClient(create_app(profile_provider=lambda: saved if saved is not None else profile(),
        weather_provider=lambda *args: weather if weather is not None else _weather_snapshot(reference_time=REF),
        clock=lambda: REF))


def request(**overrides):
    return {"availability": {"mode": "all_night"}, "confirmed_filter_profile_ids": [HA], **overrides}


def test_real_preselection_preserves_profile_and_requires_explicit_project(tmp_path, monkeypatch):
    saved = profile()
    saved["projects"] = {"Sh2-129": {"hours": 2, "target_hours": 15}}
    before = deepcopy(saved)
    client = client_for(tmp_path, monkeypatch, saved=saved)
    response = client.post("/v1/target-suggestions", json=request())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "suggestions"
    proposal = next(item for item in result["suggestions"] if item["catalog_key"] == "NorthAmerica")
    assert proposal["filter"]["filter_profile_id"] == HA
    assert proposal["acquisition_intent_id"] == "ngc7000_ha"
    assert proposal["window_start"] < proposal["window_end"]
    assert not {"mission", "decision_id", "target_hours", "hours", "expected_gain"} & proposal.keys()
    assert saved == before
    assert not list(tmp_path.rglob("user_profile.json"))
    assert not list(tmp_path.rglob("*.json"))  # no durable decision/mission/credit
    image = client.get(proposal["image"]["src"])
    assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg"


@pytest.mark.parametrize("overrides", [
    {"availability": None}, {"confirmed_filter_profile_ids": []},
    {"confirmed_filter_profile_ids": ["unknown_filter"]},
    {"confirmed_filter_profile_ids": [HA, "unknown_filter"]},
])
def test_confirmation_and_availability_cannot_be_guessed(tmp_path, monkeypatch, overrides):
    response = client_for(tmp_path, monkeypatch).post("/v1/target-suggestions", json=request(**overrides))
    assert response.status_code == 422


def test_oiii_only_does_not_suggest_ha_targets(tmp_path, monkeypatch):
    response = client_for(tmp_path, monkeypatch).post("/v1/target-suggestions", json=request(
        confirmed_filter_profile_ids=["baader_oiii_highspeed_6_5nm"]))
    assert response.status_code == 200
    assert response.json()["suggestions"] == []


def test_solid_cloud_and_too_short_availability_produce_no_suggestion(tmp_path, monkeypatch):
    from dataclasses import replace
    weather = _weather_snapshot(reference_time=REF)
    payload = deepcopy(weather.payload)
    payload["hourly"]["cloud_cover"] = [100.0] * weather.hour_count
    cloudy = replace(weather, payload=payload)
    response = client_for(tmp_path, monkeypatch, weather=cloudy).post("/v1/target-suggestions", json=request())
    assert response.status_code == 200, response.text
    assert response.json()["suggestions"] == []
    response = client_for(tmp_path, monkeypatch).post("/v1/target-suggestions", json=request(
        availability={"mode": "fixed_window", "start": "2026-08-29T23:00:00+02:00", "end": "2026-08-29T23:30:00+02:00"}))
    assert response.status_code == 200, response.text
    assert response.json()["suggestions"] == []


def test_stale_weather_is_refused_instead_of_an_optimistic_proposal(tmp_path, monkeypatch):
    from dataclasses import replace
    stale = replace(_weather_snapshot(reference_time=REF), retrieved_at_utc=REF - timedelta(days=3))
    response = client_for(tmp_path, monkeypatch, weather=stale).post("/v1/target-suggestions", json=request())
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "weather_stale"


def test_new_catalog_fields_accept_explicit_targets_and_keep_zero_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    client = TestClient(create_app())
    projects = {}
    for template in project_templates()[1:]:
        identity = template["acquisition_intents"][0]["acquisition_intent_id"]
        projects[template["catalog_key"]] = {"hours": 0, "target_hours": 3,
            "imaging_field_id": template["imaging_field_id"],
            "acquisition_intent_targets": [{"acquisition_intent_id": identity, "target_hours": 3}],
            "acquisition_intent_progress": [{"acquisition_intent_id": identity, "acquired_duration_manual": 0}]}
    response = client.put("/v1/configuration", json={"site": {"name": "Synthetic", "latitude": 46.888, "longitude": 6.55, "bortle": 4},
        "equipment": {"preset_id": "samyang_183"}, "projects": projects})
    assert response.status_code == 200, response.text
    loaded = client.get("/v1/configuration").json()
    assert set(loaded["projects"]) == {"NorthAmerica", "Rosette"}
    assert all(item["hours"] == 0 for item in loaded["projects"].values())

    from astro_score import build_durable_tonight_application_service
    live = TestClient(create_app(service_factory=build_durable_tonight_application_service, weather_provider=lambda *args: _weather_snapshot(reference_time=REF), clock=lambda: REF))
    decision = live.post("/v1/tonight", json={"availability": {"mode": "all_night"}})
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "available", decision.text
    assert decision.json()["selected_acquisition_intent_id"] == "ngc7000_ha"
    assert all(item["hours"] == 0 for item in live.get("/v1/configuration").json()["projects"].values())
