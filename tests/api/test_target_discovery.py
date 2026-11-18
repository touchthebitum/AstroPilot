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
    assert result["refusal_reason"] is None
    proposal = next(item for item in result["suggestions"] if item["catalog_key"] == "NorthAmerica")
    assert proposal["filter"]["filter_profile_id"] == HA
    assert proposal["acquisition_intent_id"] == "ngc7000_ha"
    assert proposal["window_start"] < proposal["window_end"]
    assert proposal["equipment_match"]["framing"]["status"] == "nominal_fit"
    assert proposal["equipment_match"]["filter"]["status"] == "documented_match"
    assert len(result["catalogue"]["targets"]) == 26
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


@pytest.mark.parametrize("change", [{"f_ratio": 5.6}, {"focal_length_mm": 1000}])
def test_discovery_rejects_nominally_wrong_filter_range_or_incomplete_framing(tmp_path, monkeypatch, change):
    from astropilot.equipment_catalog import EQUIPMENT_PROFILES
    monkeypatch.setitem(EQUIPMENT_PROFILES, "samyang_183", {**EQUIPMENT_PROFILES["samyang_183"], **change})
    response = client_for(tmp_path, monkeypatch).post("/v1/target-suggestions", json=request())
    assert response.status_code == 200, response.text
    assert response.json()["suggestions"] == []
    assert response.json()["catalogue"]["targets"]
    assert response.json()["refusal_reason"] is None


def test_solid_cloud_and_too_short_availability_produce_no_suggestion(tmp_path, monkeypatch):
    from dataclasses import replace
    weather = _weather_snapshot(reference_time=REF)
    payload = deepcopy(weather.payload)
    payload["hourly"]["cloud_cover"] = [100.0] * weather.hour_count
    cloudy = replace(weather, payload=payload)
    response = client_for(tmp_path, monkeypatch, weather=cloudy).post("/v1/target-suggestions", json=request())
    assert response.status_code == 200, response.text
    assert response.json()["suggestions"] == []
    assert response.json()["refusal_reason"] == "clouds_no_productive_window"
    # An incompatible confirmed filter must not receive a cloud explanation.
    incompatible = client_for(tmp_path, monkeypatch, weather=cloudy).post(
        "/v1/target-suggestions", json=request(
            confirmed_filter_profile_ids=["baader_oiii_highspeed_6_5nm"]))
    assert incompatible.status_code == 200
    assert incompatible.json()["suggestions"] == []
    assert incompatible.json()["refusal_reason"] is None
    response = client_for(tmp_path, monkeypatch).post("/v1/target-suggestions", json=request(
        availability={"mode": "fixed_window", "start": "2026-08-29T23:00:00+02:00", "end": "2026-08-29T23:30:00+02:00"}))
    assert response.status_code == 200, response.text
    assert response.json()["suggestions"] == []
    assert response.json()["refusal_reason"] is None


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
    assert set(loaded["projects"]) == set(projects)
    assert all(item["hours"] == 0 for item in loaded["projects"].values())

    from astro_score import build_durable_tonight_application_service
    live = TestClient(create_app(service_factory=build_durable_tonight_application_service, weather_provider=lambda *args: _weather_snapshot(reference_time=REF), clock=lambda: REF))
    decision = live.post("/v1/tonight", json={"availability": {"mode": "all_night"}})
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "available", decision.text
    assert decision.json()["selected_acquisition_intent_id"] == "ngc7000_ha"
    assert all(item["hours"] == 0 for item in live.get("/v1/configuration").json()["projects"].values())


def test_cloud_humidity_explanation_requires_joint_blockage(tmp_path, monkeypatch):
    from dataclasses import replace
    weather = _weather_snapshot(reference_time=REF)
    payload = deepcopy(weather.payload)
    payload['hourly']['cloud_cover'] = [42.0] * weather.hour_count
    payload['hourly']['relative_humidity_2m'] = [92.0] * weather.hour_count
    result = client_for(tmp_path, monkeypatch, weather=replace(weather, payload=payload)).post(
        '/v1/target-suggestions', json=request()).json()
    assert result['suggestions'] == []
    assert result['refusal_reason'] == 'clouds_humidity_no_productive_window'
    payload['hourly']['relative_humidity_2m'] = [50.0] * weather.hour_count
    result = client_for(tmp_path, monkeypatch, weather=replace(weather, payload=payload)).post(
        '/v1/target-suggestions', json=request()).json()
    assert result['refusal_reason'] is None  # Other constraints must not be labelled humidity.


def november_weather(reference):
    from decision.weather.weather_ingress import validate_weather_payload
    from zoneinfo import ZoneInfo
    payload = deepcopy(_weather_snapshot(reference_time=reference).payload)
    start = reference.astimezone(ZoneInfo("Europe/Zurich")).replace(hour=0, minute=0)
    payload["hourly"]["time"] = [int((start + timedelta(hours=i)).timestamp())
                                 for i in range(len(payload["hourly"]["time"]))]
    payload["utc_offset_seconds"] = 3600
    return validate_weather_payload(payload, requested_latitude=46.888,
        requested_longitude=6.55, requested_timezone="Europe/Zurich",
        retrieved_at_utc=reference - timedelta(minutes=5))


@pytest.mark.parametrize("filter_type,wavelength", [("OIII", 500.7), ("SII", 672.4)])
def test_rosette_november_exact_filter_readonly(tmp_path, monkeypatch, filter_type, wavelength):
    reference = datetime(2026, 11, 10, 18, tzinfo=timezone.utc)
    saved = profile()
    saved["projects"] = {"Rosette": {"hours": 2, "target_hours": 6}}
    saved["sessions"] = [{"target": "Rosette", "filter_type": "Ha", "hours": 1}]
    before = deepcopy(saved)
    filter_id = f"baader_{filter_type.lower()}_highspeed_6_5nm"
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    client = TestClient(create_app(profile_provider=lambda: saved,
        weather_provider=lambda *args: november_weather(reference), clock=lambda: reference))
    response = client.post("/v1/target-suggestions", json=request(confirmed_filter_profile_ids=[filter_id]))
    assert response.status_code == 200, response.text
    suggestions = response.json()["suggestions"]
    assert len(suggestions) == 1, response.text
    item = suggestions[0]
    assert (item["catalog_key"], item["acquisition_intent_id"], item["filter_type"]) == ("Rosette", "rosette_" + filter_type.lower(), filter_type)
    assert item["filter"]["filter_profile_id"] == filter_id
    assert item["lunar_assessment"]["filter_profile_id"] == filter_id
    assert item["lunar_assessment"]["central_wavelength_nm"] == wavelength
    assert item["already_saved"] and item["existing_project_key"] == "Rosette"
    assert "exposure_guidance" not in item
    assert saved == before
    assert not list(tmp_path.rglob("*.json"))
    template = next(t for t in project_templates() if t["catalog_key"] == "Rosette")
    intent = next(i for i in template["acquisition_intents"] if i["filter_type"] == filter_type)
    assert "exposure_guidance" not in intent


def test_rosette_three_profiles_have_separate_lunar_evaluations(tmp_path, monkeypatch):
    # Inject lunar geometry only: the existing common weather/altitude gate is
    # not a calibrated spectral model. A raised Moon exposes profile differences.
    reference = datetime(2026, 11, 10, 18, tzinfo=timezone.utc)
    from decision.models.lunar_geometry import LunarGeometry
    from decision.services.lunar_geometry_service import LunarGeometryService
    monkeypatch.setattr(LunarGeometryService, "calculate",
        lambda self, **kwargs: LunarGeometry(0.8, 45.0, 60.0))
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    import astropilot.target_discovery as discovery
    monkeypatch.setattr(discovery, "TARGET_IMAGES", {"Rosette": discovery.TARGET_IMAGES["Rosette"]})
    from decision.services.lunar_contamination_estimator import LunarContaminationEstimator
    original = LunarContaminationEstimator.estimate
    calls = []
    def record(self, evidence, optical):
        result = original(self, evidence, optical)
        calls.append((optical.filter_profile_id, optical.central_wavelength_nm, result))
        return result
    monkeypatch.setattr(LunarContaminationEstimator, "estimate", record)
    client = TestClient(create_app(profile_provider=profile,
        weather_provider=lambda *args: november_weather(reference), clock=lambda: reference))
    ids = [f"baader_{kind}_highspeed_6_5nm" for kind in ("ha", "oiii", "sii")]
    response = client.post("/v1/target-suggestions", json=request(confirmed_filter_profile_ids=ids))
    assert response.status_code == 200, response.text
    assert {c[0] for c in calls} == set(ids), response.text
    assert {c[1] for c in calls} == {656.3, 500.7, 672.4}
    assert len({c[2].rayleigh_relative_index for c in calls}) == 3
    assert [s["filter_type"] for s in response.json()["suggestions"]] == ["SII", "Ha", "OIII"]


@pytest.mark.parametrize("kind", ["oiii", "sii"])
def test_rosette_filters_still_refuse_clouds(tmp_path, monkeypatch, kind):
    from dataclasses import replace
    reference = datetime(2026, 11, 10, 18, tzinfo=timezone.utc)
    monkeypatch.setenv("ASTROPILOT_DATA_DIR", str(tmp_path))
    weather = november_weather(reference)
    payload = deepcopy(weather.payload)
    payload["hourly"]["cloud_cover"] = [100.0] * weather.hour_count
    client = TestClient(create_app(profile_provider=profile,
        weather_provider=lambda *args: replace(weather, payload=payload), clock=lambda: reference))
    response = client.post("/v1/target-suggestions", json=request(confirmed_filter_profile_ids=[f"baader_{kind}_highspeed_6_5nm"]))
    assert response.status_code == 200, response.text
    assert response.json()["suggestions"] == []
    assert response.json()["refusal_reason"] == "clouds_no_productive_window"


@pytest.mark.parametrize("kind", ["oiii", "sii"])
def test_rosette_absent_and_incompatible_filter_cannot_be_used(tmp_path, monkeypatch, kind):
    saved = profile()
    saved['filter_inventories'] = {'samyang_183': {'wheel_name': 'FICTIF', 'slot_count': 5, 'slots': []}}
    filter_id = f"baader_{kind}_highspeed_6_5nm"
    response = client_for(tmp_path, monkeypatch, saved=saved).post('/v1/target-suggestions',
        json=request(confirmed_filter_profile_ids=[filter_id]))
    assert response.status_code == 422
    assert response.json()['detail']['code'] == 'discovery_filter_not_installed'
    from astropilot.equipment_catalog import EQUIPMENT_PROFILES
    monkeypatch.setitem(EQUIPMENT_PROFILES, 'samyang_183', {**EQUIPMENT_PROFILES['samyang_183'], 'f_ratio': 5.6})
    response = client_for(tmp_path, monkeypatch).post('/v1/target-suggestions',
        json=request(confirmed_filter_profile_ids=[filter_id]))
    assert response.status_code == 200
    rosette = next(t for t in response.json()['catalogue']['targets'] if t['key'] == 'Rosette')
    assert rosette['confirmed_filters'][0]['status'] != 'documented_match'
    assert response.json()['suggestions'] == []


def test_rosette_progress_remains_separate_when_adding_filters(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    client = TestClient(create_app())
    response = client.put('/v1/configuration', json={
        'site': {'name': 'FICTIF', 'latitude': 46.888, 'longitude': 6.55, 'bortle': 4},
        'equipment': {'preset_id': 'samyang_183'}, 'projects': {'Rosette': {
            'hours': 2, 'target_hours': 6, 'imaging_field_id': 'rosette',
            'acquisition_intent_targets': [{'acquisition_intent_id': 'rosette_ha', 'target_hours': 6}],
            'acquisition_intent_progress': [{'acquisition_intent_id': 'rosette_ha', 'acquired_duration_manual': 7200}]}}})
    assert response.status_code == 200, response.text
    before = client.get('/v1/projects/Rosette/progress').json()
    response = client.put('/v1/projects/Rosette/progress', json={
        'expected_revision': before['profile_revision'], 'imaging_field_id': 'rosette',
        'acquisition_intent_targets': before['acquisition_intent_targets'] + [
            {'acquisition_intent_id': 'rosette_oiii', 'target_hours': 3},
            {'acquisition_intent_id': 'rosette_sii', 'target_hours': 4}],
        'acquisition_intent_progress': before['acquisition_intent_progress'] + [
            {'acquisition_intent_id': 'rosette_oiii', 'acquired_duration_manual': 0},
            {'acquisition_intent_id': 'rosette_sii', 'acquired_duration_manual': 0}]})
    assert response.status_code == 200, response.text
    after = client.get('/v1/projects/Rosette/progress').json()
    progress = {i['acquisition_intent_id']: i for i in after['acquisition_intent_progress']}
    assert progress['rosette_ha']['acquired_duration_manual'] == 7200
    assert progress['rosette_oiii']['acquired_duration_manual'] == 0
    assert progress['rosette_sii']['acquired_duration_manual'] == 0
    assert len(client.get('/v1/configuration').json()['projects']) == 1


def test_rosette_missing_lunar_evidence_does_not_reuse_ha(tmp_path, monkeypatch):
    from decision.services.intent_night_evidence_builder import IntentNightEvidenceBuilder, IntentNightEvidenceBuildError
    def unavailable(self, **kwargs):
        raise IntentNightEvidenceBuildError('synthetic missing evidence')
    monkeypatch.setattr(IntentNightEvidenceBuilder, 'build', unavailable)
    reference = datetime(2026, 11, 10, 18, tzinfo=timezone.utc)
    monkeypatch.setenv('ASTROPILOT_DATA_DIR', str(tmp_path))
    client = TestClient(create_app(profile_provider=profile,
        weather_provider=lambda *args: november_weather(reference), clock=lambda: reference))
    response = client.post('/v1/target-suggestions', json=request(
        confirmed_filter_profile_ids=['baader_oiii_highspeed_6_5nm', 'baader_sii_highspeed_6_5nm']))
    assert response.status_code == 200
    assert response.json()['suggestions'] == []
    assert response.json()['refusal_reason'] is None


@pytest.mark.parametrize('kind',['oiii','sii'])
def test_weather_refusal_exposes_exact_scoped_evidence_and_collection_time(tmp_path,monkeypatch,kind):
    from dataclasses import replace
    reference=datetime(2026,11,10,18,tzinfo=timezone.utc)
    weather=november_weather(reference);payload=deepcopy(weather.payload)
    payload['hourly']['cloud_cover']=[100.0]*weather.hour_count
    weather=replace(weather,payload=payload)
    monkeypatch.setenv('ASTROPILOT_DATA_DIR',str(tmp_path))
    client=TestClient(create_app(profile_provider=profile,weather_provider=lambda *args:weather,clock=lambda:reference))
    response=client.post('/v1/target-suggestions',json=request(confirmed_filter_profile_ids=[f'baader_{kind}_highspeed_6_5nm'],
        availability={'mode':'fixed_window','start':'2026-11-14T03:00:00+01:00','end':'2026-11-14T05:00:00+01:00'}))
    assert response.status_code==200,response.text
    data=response.json();assert data['suggestions']==[]
    assert data['weather_context']['retrieved_at_utc']==weather.retrieved_at_utc.isoformat()
    evidence=data['refusal_evidence'];assert len(evidence)==1,data
    assert evidence[0]['acquisition_intent_id']=='rosette_'+kind
    assert datetime.fromisoformat(evidence[0]['evaluated_start'])>=datetime.fromisoformat('2026-11-14T03:00:00+01:00')
    assert datetime.fromisoformat(evidence[0]['evaluated_end'])<=datetime.fromisoformat('2026-11-14T05:00:00+01:00')
    assert evidence[0]['losses']['cloud']>0
    assert evidence[0]['refusal_stage']=='no_productive_slice'
    assert not list(tmp_path.rglob('*.json'))
